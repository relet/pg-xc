#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from codecs import open
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, List, Tuple
from geojson import load
import os
import re
import sys
import urllib
import urllib.parse
import logging

from shapely.geometry import Polygon

from targets import geojson, openaip, openair, xcontest
from util.utils import *

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
init_utils(logger)


"""
SPECIAL CASES AND WORKAROUNDS IN PARSE.PY
==========================================

This document lists all special cases, hacks, and workarounds in the Norwegian AIP parser.
These exist because human-written AIP documents are inconsistent and error-prone.

1. OSLO/ROMERIKE NOTAM AREAS (Kongsvinger, Romerike, Oslo)
   Location: finalize() function
   Issue: Reserved ENR areas in Oslo region are NOTAM-activated only
   Solution: Set notam_only='true' flag, swap vertical limits if inverted
   Reference: en_sup_a_2018_015_en
   Files affected: EN R areas with "Romerike" or "Oslo" (not Oslo 102)

2. SÄLEN/SAAB CTR SECTORS  
   Location: parse() line parsing, BorderFollower
   Issue: Multi-sector airspace with incorrect border following direction
   Solution: 
   - Split sectors dynamically when "Sector" keyword appears
   - Reverse border fill for "Sälen TMA b" and "SÄLEN CTR Sector b"
   - First sector in docs is union of others, skip it during finalization
   Reference: Swedish AIP format (legacy, now removed but code remains)

3. VALLDAL CUSTOM FORMAT
   Location: parse(), main file loop
   Issue: Custom document format different from standard AIP
   Solution:
   - Detect by filename "valldal"
   - Extract name from first two words
   - Hardcode class as 'Luftsport', lower limit 0
   Reference: valldal.txt custom format

4. FARRIS TMA COUNTER SKIP
   Location: finalize() - duplicate handling
   Issue: Counter numbering has gaps
   Solution: If count > 4, add 2 to counter (skip 5 and 6)
   Reference: Farris TMA naming convention

5. GEITERYGGEN FINALIZATION SKIP
   Location: parse() vertical limit handling
   Issue: Should not finalize on certain conditions
   Solution: Explicitly skip finalization if "Geiteryggen" in name

6. ROMERIKE/OSLO ALTITUDE HANDLING
   Location: finalize() vertical limit validation
   Issue: These restricted areas allow finalization without complete upper limit
   Solution: Special exception in finalization validation
   Reference: en_sup_a_2018_015_en

7. "SEE RMK" VERTICAL LIMIT HACK
   Location: VerticalLimitParser
   Issue: "See RMK" appears where altitude should be
   Solution: Treat as 13499 ft placeholder
   Reference: Various AIP documents with remarks

8. COLUMN SHIFT HACK (TIA AIP ACC)
   Location: ColumnParser.detect_columns_from_pattern()
   Issue: Column detection off by 2 characters
   Solution: Subtract 2 from all detected column positions
   Reference: TIA AIP ACC format with "1     " pattern

9. EN D476/D477 NAME NORMALIZATION
   Location: finalize() name processing
   Issue: Names need sector suffixes for uniqueness
   Solution: Append " R og B 1" for D476, " R og B 2" for D477

10. SECTOR NAME SKIPPING (SÄLEN/SAAB)
    Location: NameParser.should_skip_name()
    Issue: Sector subdivisions "Sector a", "Sector b" should be ignored as standalone
    Solution: Skip if name is exactly "Sector a" or "Sector b"
    
GENERAL NOTES:
- Most special cases exist due to inconsistent AIP formatting
- Many are location-specific (Oslo area, Farris, Valldal, etc.)
- Some are format-specific (TIA ACC, airsport docs, supplements)
- Keep these even if ugly - removing them breaks real-world parsing
- Swedish AIP support was removed (2024) - some Swedish remnants may remain
"""


class RegexPatterns:
    """Centralized regex patterns for parsing AIP documents.
    
    Organizes all parsing patterns by purpose:
    - Name patterns: Identify airspace names
    - Class patterns: Identify airspace class
    - Coordinate patterns: Parse coordinates, circles, sectors, arcs
    - Vertical limit patterns: Parse altitude limits
    - Period patterns: Parse temporary airspace periods
    - Frequency patterns: Parse radio frequencies
    """
    
    # === Coordinate Components (building blocks) ===
    RE_NE = r'(?P<ne>\(?(?P<n>[\d\.]{5,10})\s?N(?: N)?\s*(?:\s*|-)+(?P<e>[\d\.]+)[E\)]+)'
    RE_NE2 = r'(?P<ne2>\(?(?P<n2>\d+)N\s*(?P<e2>\d+)E\)?)'
    RE_CIRCLE = r'A circle(?: with|,) radius (?P<rad>[\d\.]+) NM cente?red on (?P<cn>\d+)N\s+(?P<ce>\d+)E'
    RE_SECTOR = u'('+RE_NE + r' - )?((\d\. )?A s|S)ector (?P<secfrom>\d+)° - (?P<secto>\d+)° \(T\), radius ((?P<radfrom>[\d\.,]+) - )?(?P<rad>[\d\.,]+) NM'
    RE_MONTH = r"(?:JAN|FEB|MAR|APR|MAI|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
    
    # === Name Patterns ===
    # Standard airspace names with type designators
    re_name = re.compile(r"^\s*(?P<name>[^\s]* ((Centre|West|North|South|East| Norway) )?(TRIDENT|ADS|HTZ|AOR|RMZ|ATZ|FAB|TMA|TIA|TIA/RMZ|CTA|CTR|CTR,|TIZ|FIR|OCEANIC FIR|CTR/TIZ|TIZ/RMZ|RMZ/TMZ)( (West|Centre|[a-z]))?|[^\s]*( ACC sector| ACC Oslo|ESTRA|EUCBA|RPAS).*)( cont.)?\s*($|\s{5}|.*FIR)")
    # Norwegian/Swedish D/R areas
    re_name2 = re.compile(r"^\s*(?P<name>E[NS] [RD].*)\s*$")
    re_name3 = re.compile(r"^\s*(?P<name>E[NS]D\d.*)\s*$")
    # Norwegian format
    re_name4 = re.compile(r"Navn og utstrekning /\s+(?P<name>.*)$")
    # ACC sectors
    re_name5 = re.compile(r"^(?P<name>Sector .*)$")
    re_name6 = re.compile(r"^(?P<name>Norway ACC .*)$")
    # Controlled airspace format
    re_name_cr = re.compile(r"^Area Name: \((?P<name>EN .*)\) (?P<name_cont>.*)$")
    # Miscellaneous names
    re_miscnames = re.compile(r"^(?P<name>Hareid .*)$")
    # OpenAir format
    re_name_openair = re.compile(r"^AN (?P<name>.*)$")
    
    # === Class Patterns ===
    re_class = re.compile(r"Class:? (?P<class>.)")
    re_class2 = re.compile(r"^(?P<class>[CDG])$")
    re_class_openair = re.compile(r"^AC (?P<class>.*)$")
    
    # === Coordinate Patterns ===
    # Circle with radius
    re_coord = re.compile(r"(?:" + RE_NE + r" - )?(?:\d\. )?(?:A circle(?: with|,)? r|R)adius (?:(?P<rad>[\d\.,]+) NM|(?P<rad_m>[\d]+) m)(?: \([\d\.,]+ k?m\))?(?: cente?red on (?P<cn>\d+)N\s+(?P<ce>\d+)E)?")
    # Sector definition
    re_coord2 = re.compile(RE_SECTOR)
    # All formats in coordinate list (Norway - using "along" for border following)
    re_coord3 = re.compile(RE_NE+r"|(?P<along>along)|(?P<arc>(?:counter)?clockwise)|(?:\d+)N|(?:\d{4,10})E|"+RE_CIRCLE)
    # Arc along circle segment
    re_arc = re.compile(r'(?P<dir>(counter)?clockwise) along an arc (?:of (?P<rad1>[\d\.,]+) NM radius )?centred on '+RE_NE+r'(?:( and)?( with)?( radius) (?P<rad2>[ \d\.,]+) NM(?: \([\d\.]+ k?m\))?)? (?:- )'+RE_NE2)
    
    # === Vertical Limit Patterns ===
    re_vertl_upper = re.compile(r"Upper limit:\s+(FL\s+(?P<flto>\d+)|(?P<ftamsl>\d+)\s+FT\s+(AMSL)?)")
    re_vertl_lower = re.compile(r"ower limit:\s+(FL\s+(?P<flfrom>\d+)|(?P<ftamsl>\d+)\s+FT\s+(AMSL|SFC)|(?P<msl>MSL))")  # Intentionally "ower" not "Lower"
    re_vertl = re.compile(r"(?P<from>GND|\d{3,6}) (?:(?:til/)?to|-) (?P<to>UNL|\d{3,6})( [Ff][Tt] AMSL)?")
    re_vertl2 = re.compile(r"((?P<ftamsl>\d+)\s?[Ff][Tt] (A?MSL|GND))|(?P<gnd>GND)|(?P<unl>UNL)|(FL\s?(?P<fl>\d+))|(?P<rmk>See (remark|RMK))")
    re_vertl3 = re.compile(r"((?P<ftamsl>\d+) FT$)")
    
    # === Period Patterns (temporary airspace) ===
    re_period = re.compile(r"Active from (?P<pfrom>\d+ "+RE_MONTH+r") (?P<ptimefrom>\d+)")
    re_period2 = re.compile(r"^(?P<pto>\d+ "+RE_MONTH+r") (?P<ptimeto>\d+)")
    re_period3 = re.compile(r"Established for (?P<pfrom>\d+ "+RE_MONTH+r") - (?P<pto>\d+ "+RE_MONTH+")")
    
    # === Frequency Patterns ===
    re_freq = re.compile(r'(?P<freq>\d+\.\d+ MHZ)')


# Create global instance for backward compatibility
patterns = RegexPatterns()

# Export individual patterns for backward compatibility
re_name = patterns.re_name
re_name2 = patterns.re_name2
re_name3 = patterns.re_name3
re_name4 = patterns.re_name4
re_name5 = patterns.re_name5
re_name6 = patterns.re_name6
re_name_cr = patterns.re_name_cr
re_miscnames = patterns.re_miscnames
re_name_openair = patterns.re_name_openair
re_class = patterns.re_class
re_class2 = patterns.re_class2
re_class_openair = patterns.re_class_openair
RE_NE = patterns.RE_NE
RE_NE2 = patterns.RE_NE2
re_coord = patterns.re_coord
RE_SECTOR = patterns.RE_SECTOR
re_coord2 = patterns.re_coord2
RE_CIRCLE = patterns.RE_CIRCLE
re_coord3 = patterns.re_coord3
re_arc = patterns.re_arc
re_vertl_upper = patterns.re_vertl_upper
re_vertl_lower = patterns.re_vertl_lower
re_vertl = patterns.re_vertl
re_vertl2 = patterns.re_vertl2
re_vertl3 = patterns.re_vertl3
RE_MONTH = patterns.RE_MONTH
re_period = patterns.re_period
re_period2 = patterns.re_period2
re_period3 = patterns.re_period3
re_freq = patterns.re_freq


# COLUMN PARSING:
rexes_header_es_enr = [re.compile(r"(?:(?:(Name|Identification)|(Lateral limits)|(Vertical limits)|(C unit)|(Freq MHz)|(Callsign)|(AFIS unit)|(Remark)).*){%i}" % mult) \
                           for mult in reversed(range(3,8))]

LINEBREAK = '--linebreak--'

# define polygons for the country borders
norway_fc = load(open("norway.geojson","r"))
norway = norway_fc.features[0].geometry.coordinates[0]
logger.debug("Norway has %i points.", len(norway))

sweden_fc = load(open("fastland-sweden.geojson","r"))
sweden = sweden_fc.features[0].geometry.coordinates[0]
logger.debug("Sweden has %i points.", len(sweden))

borders = {
        'norway': norway,
        'sweden': sweden
}

collection = []
completed = {}
names = {}
accsectors = []


class ParsingContext:
    """Context object to hold parsing state for each file.
    
    Replaces global variables with organized state management.
    Makes code more testable and easier to understand.
    """
    def __init__(self):
        # Feature construction state
        self.aipname = None
        self.feature = {"properties": {}}
        self.obj = []
        self.features = []
        
        # Coordinate parsing state
        self.alonging = False
        self.lastn = None
        self.laste = None
        self.lastv = None
        self.finalcoord = False
        self.coords_wrap = ""
        self.sectors = []
        
        # Document parsing state
        self.ats_chapter = False
        self.airsport_intable = False
        self.name_cont = False
        
        # Country-specific
        self.country = None
        self.border = None
        self.re_coord3 = None
        
        # Special flags
        self.sanntid = False
    
    def reset_feature(self):
        """Reset feature state for new feature"""
        self.feature = {"properties": {}}
        self.obj = []
        self.alonging = False
        self.coords_wrap = ""
        self.lastv = None


class NameParser:
    """Parser for airspace names from AIP documents.
    
    Tries multiple regex patterns in sequence to identify airspace names.
    Handles special cases like name continuation, Swedish/Norwegian formats,
    and document-specific naming conventions.
    """
    
    def __init__(self, patterns):
        """Initialize with RegexPatterns instance"""
        self.patterns = patterns
    
    def parse_name(self, line):
        """Try to extract an airspace name from a line.
        
        Args:
            line: Text line to parse
            
        Returns:
            Match object if name found, None otherwise
        """
        # Try all name patterns in sequence
        return (self.patterns.re_name.search(line) or 
                self.patterns.re_name2.search(line) or 
                self.patterns.re_name3.search(line) or 
                self.patterns.re_name4.search(line) or 
                self.patterns.re_miscnames.search(line) or 
                self.patterns.re_name5.search(line) or 
                self.patterns.re_name_cr.search(line) or 
                self.patterns.re_name6.search(line) or 
                self.patterns.re_name_openair.search(line))
    
    def process_name(self, match, line, ctx):
        """Process a matched name and update context.
        
        Args:
            match: Regex match object containing name groups
            line: Original line text
            ctx: ParsingContext to update
            
        Returns:
            Extracted and processed name string
        """
        named = match.groupdict()
        name = named.get('name')
        
        # Handle Polaris Norway special case
        if name and 'polaris' in name.lower() and 'norway' in name.lower():
            pos = name.lower().index('norway')
            name = name[:pos]
        
        # Handle name continuation
        if named.get('name_cont'):
            name += ' ' + named.get('name_cont')
            ctx.name_cont = True
        
        # Set name continuation flag for Swedish/Norwegian D/R areas
        if name and ("ES R" in name or "ES D" in name):
            ctx.name_cont = True
        if name and "EN D" in name and len(name) < 8:
            ctx.name_cont = True
        
        return name
    
    def should_skip_name(self, name, ctx):
        """Check if this name should be skipped/ignored.
        
        Args:
            name: Extracted name string
            ctx: ParsingContext
            
        Returns:
            True if name should be skipped
        """
        # SPECIAL CASE #12: Skip sector subdivisions of SÄLEN/SAAB
        # These sector names are handled as part of parent airspace
        if (name == "Sector a" or name == "Sector b" or 
            (ctx.aipname and "Sector" in ctx.aipname and 
             ("SÄLEN" in ctx.aipname or "SAAB" in ctx.aipname))):
            return True
        
        # Skip sector names if already in ACC context
        if name and name[:6] == "Sector" and ctx.aipname and "ACC" in ctx.aipname:
            return True
        
        return False


class ClassParser:
    """Parser for airspace class designations.
    
    Recognizes airspace classes (A, B, C, D, E, F, G) from various formats:
    - Standard format: "Class: C" or "Class C"
    - Single letter: "C" (on its own line)
    - OpenAir format: "AC C"
    """
    
    def __init__(self, patterns):
        """Initialize with RegexPatterns instance"""
        self.patterns = patterns
    
    def parse_class(self, line):
        """Try to extract airspace class from a line.
        
        Args:
            line: Text line to parse
            
        Returns:
            Match object if class found, None otherwise
        """
        return (self.patterns.re_class.search(line) or 
                self.patterns.re_class2.search(line) or 
                self.patterns.re_class_openair.search(line))
    
    def extract_class(self, match):
        """Extract the class value from a match.
        
        Args:
            match: Regex match object
            
        Returns:
            AirspaceClass enum or string (for backward compatibility)
        """
        class_str = match.groupdict().get('class')
        # Try to parse as enum, fall back to string for unknown classes
        airspace_class = AirspaceClass.from_string(class_str)
        return airspace_class.value if airspace_class else class_str


class VerticalLimitParser:
    """Parser for vertical limits (altitude ranges).
    
    Handles various formats for altitude limits:
    - Upper/Lower limit format: "Upper limit: FL 100" or "Lower limit: 5000 FT AMSL"
    - Range format: "GND to 4500 FT AMSL" or "1000 - 5000"
    - Flight level format: "FL 100" or "FL 450"
    - Special values: GND (ground), UNL (unlimited), MSL (mean sea level)
    - See RMK (remark) - special case for controlled airspace lower limit
    """
    
    def __init__(self, patterns):
        """Initialize with RegexPatterns instance"""
        self.patterns = patterns
    
    def parse_vertical_limit(self, line, military_aip=False):
        """Try to extract vertical limits from a line.
        
        Args:
            line: Text line to parse
            military_aip: Whether this is from military AIP (enables re_vertl3)
            
        Returns:
            Match object if vertical limit found, None otherwise
        """
        return (self.patterns.re_vertl_upper.search(line) or 
                self.patterns.re_vertl_lower.search(line) or 
                self.patterns.re_vertl.search(line) or 
                self.patterns.re_vertl2.search(line) or 
                (military_aip and self.patterns.re_vertl3.search(line)))
    
    def extract_limits(self, match, ctx):
        """Extract and process vertical limit values.
        
        Args:
            match: Regex match object
            ctx: ParsingContext (uses ctx.lastv for state)
            
        Returns:
            Tuple of (from_altitude, to_altitude, from_fl, to_fl) in feet AMSL
            Any value can be None if not found
        """
        vertl = match.groupdict()
        fromamsl, toamsl = None, None
        fl, flfrom, flto = None, None, None
        
        v = vertl.get('ftamsl')
        flfrom = vertl.get('flfrom')
        flto = vertl.get('flto')
        fl = vertl.get('fl')
        rmk = vertl.get('rmk')
        
        # SPECIAL CASE #8: "See RMK" = Lower limit of controlled airspace
        # Used as placeholder when actual limit is in remarks section
        if rmk is not None:
            v = 13499
        
        # Convert flight level to feet
        if fl is not None:
            v = int(fl) * 100
        
        # Handle upper/lower limit pairs
        if flto is not None:
            toamsl = int(flto) * 100
            if flfrom:
                fromamsl = v or (int(flfrom) * 100)
                fl = fl or flfrom
        elif flfrom is not None:
            fromamsl = int(flfrom) * 100
            fl = fl or flfrom
        elif v is not None:
            # Single value - use context to determine if it's from or to
            if ctx.lastv is None:
                toamsl = v
                if fl is not None:
                    flto = fl
            else:
                fromamsl = v
        else:
            # Handle special keywords and ranges
            fromamsl = vertl.get('msl', vertl.get('gnd', vertl.get('from')))
            if fromamsl == "GND": fromamsl = 0
            if fromamsl == "MSL": fromamsl = 0
            toamsl = vertl.get('unl', vertl.get('to'))
            if toamsl == "UNL": toamsl = 999999
        
        return fromamsl, toamsl, fl, flto


class CoordinateParser:
    """Parser for coordinate definitions in airspace boundaries.
    
    Handles multiple coordinate formats:
    - Circles: "Radius 5 NM centered on 600000N 0100000E"
    - Sectors: "Sector 090° - 180° (T), radius 10 NM"
    - Coordinate lists: "600000N 0100000E - 610000N 0110000E"
    - Arcs: "clockwise along an arc of 5 NM radius centered on..."
    - Border following: "along border" (uses pre-loaded border coordinates)
    
    Supports line continuation for incomplete coordinates.
    """
    
    def __init__(self, patterns):
        """Initialize with RegexPatterns instance"""
        self.patterns = patterns
    
    def has_coordinates(self, line, ctx):
        """Check if line contains any coordinate format.
        
        Args:
            line: Text line to check
            ctx: ParsingContext (for country-specific re_coord3)
            
        Returns:
            Tuple of (coords, coords2, coords3) match objects/lists
        """
        coords = self.patterns.re_coord.search(line)
        coords2 = self.patterns.re_coord2.search(line)
        coords3 = ctx.re_coord3.findall(line)
        return coords, coords2, coords3


class BorderFollower:
    """Handler for "along border" coordinate filling logic.
    
    Handles the special case where airspace boundaries follow national borders.
    Finds closest points on the border and fills in the intermediate coordinates.
    
    The logic:
    1. When "along" keyword is found, store the current coordinate as start point
    2. On next coordinate, use fill_along() to insert border points between start and end
    3. Supports both Norwegian ("along") and Swedish ("border") syntax
    """
    
    def __init__(self):
        """Initialize border follower."""
        pass
    
    def start_following(self, ctx, n, e):
        """Mark start of border following.
        
        Args:
            ctx: ParsingContext
            n: North coordinate (or None to use last)
            e: East coordinate (or None to use last)
        """
        if not n and not e:
            n, e = ctx.lastn, ctx.laste
        ctx.alonging = (n, e)
        logger.debug(f"Starting border following from {n}, {e}")
    
    def finish_following(self, ctx, n, e, special_case_name=None):
        """Complete border following by filling coordinates.
        
        Args:
            ctx: ParsingContext with alonging start point and border data
            n: North coordinate of end point (or None to use last)
            e: East coordinate of end point (or None to use last)
            special_case_name: Name for special case handling (e.g., "Sälen TMA b")
            
        Returns:
            List of (lon, lat) coordinate pairs along the border
        """
        if not ctx.alonging:
            return []
        
        if not n and not e:
            n, e = ctx.lastn, ctx.laste
        
        fill = fill_along(ctx.alonging, (n, e), ctx.border)
        
        # SPECIAL CASE #2: Sälen border fill direction fix
        # Border following goes wrong direction for these specific sectors
        # FIXME: Should detect direction properly instead of reversing afterward
        if special_case_name and ("Sälen TMA b" in special_case_name or "SÄLEN CTR Sector b" in special_case_name):
            logger.debug("SÄLEN HACK: Reversing border fill direction")
            fill = list(reversed(fill))
        
        ctx.alonging = False
        ctx.lastn, ctx.laste = None, None
        
        logger.debug(f"Filled border with {len(fill)} points")
        return fill


class GeometryBuilder:
    """Builder for airspace geometry construction.
    
    Consolidates geometry operations (circles, sectors, arcs, merging).
    Provides consistent interface for building and combining airspace boundaries.
    """
    
    def add_circle(self, obj, center_n, center_e, radius_nm, convert=True):
        """Add a circle to the geometry.
        
        Args:
            obj: Current object coordinate list
            center_n: North coordinate of center
            center_e: East coordinate of center  
            radius_nm: Radius in nautical miles
            convert: Whether to convert coordinates (default True)
            
        Returns:
            Updated object coordinate list
        """
        logger.debug(f"Adding circle: center=({center_n}, {center_e}), radius={radius_nm}nm")
        circle = gen_circle(center_n, center_e, radius_nm, convert=convert)
        return merge_poly(obj, circle)
    
    def add_sector(self, obj, center_n, center_e, sec_from, sec_to, rad_from, rad_to):
        """Add a sector (pie slice) to the geometry.
        
        Args:
            obj: Current object coordinate list
            center_n: North coordinate of center
            center_e: East coordinate of center
            sec_from: Starting angle in degrees
            sec_to: Ending angle in degrees
            rad_from: Starting radius (or None)
            rad_to: Ending radius
            
        Returns:
            Updated object coordinate list
        """
        logger.debug(f"Adding sector: center=({center_n}, {center_e}), angles={sec_from}°-{sec_to}°, radius={rad_from or 0}-{rad_to}nm")
        sector = gen_sector(center_n, center_e, sec_from, sec_to, rad_from, rad_to)
        return merge_poly(obj, sector)
    
    def add_arc(self, obj, center_n, center_e, radius_nm, to_n, to_e, clockwise):
        """Add an arc segment to the geometry.
        
        Args:
            obj: Current object coordinate list (must have at least one point)
            center_n: North coordinate of arc center
            center_e: East coordinate of arc center
            radius_nm: Radius in nautical miles
            to_n: North coordinate of arc endpoint
            to_e: East coordinate of arc endpoint
            clockwise: Direction of arc (True = clockwise)
            
        Returns:
            Updated object coordinate list with arc points inserted
        """
        if not obj:
            logger.warning("Cannot add arc: obj is empty")
            return obj
        
        logger.debug(f"Adding arc: center=({center_n}, {center_e}), to=({to_n}, {to_e}), radius={radius_nm}nm, {'CW' if clockwise else 'CCW'}")
        
        # Generate circle and use fill_along to get arc segment
        arc_circle = gen_circle(center_n, center_e, radius_nm, convert=False)
        fill = fill_along(obj[-1], (to_n, to_e), arc_circle, clockwise)
        
        # Insert arc points
        for lon, lat in fill:
            n, e = ll2c((lon, lat))
            obj.insert(0, (n, e))
        
        return obj


class FeatureValidator:
    """Validator for airspace features.
    
    Provides validation checks for feature completeness and correctness.
    Helps identify issues with parsed airspace data before finalization.
    """
    
    def validate(self, feature, obj, aipname=None):
        """Validate a feature for completeness and consistency.
        
        Args:
            feature: Feature dict to validate
            obj: Geometry coordinate list
            aipname: Optional airspace name for error messages
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        name_str = f" ({aipname})" if aipname else ""
        
        # Check for required properties
        if not feature.get('properties'):
            errors.append(f"Missing properties{name_str}")
        else:
            # Check vertical limits
            from_amsl = feature['properties'].get('from (ft amsl)')
            to_amsl = feature['properties'].get('to (ft amsl)')
            
            if from_amsl is None:
                errors.append(f"Missing lower limit{name_str}")
            if to_amsl is None:
                errors.append(f"Missing upper limit{name_str}")
            
            # Validate vertical limit consistency
            if from_amsl is not None and to_amsl is not None:
                try:
                    if int(from_amsl) >= int(to_amsl):
                        errors.append(f"Invalid vertical limits: from={from_amsl} >= to={to_amsl}{name_str}")
                except (ValueError, TypeError):
                    errors.append(f"Non-numeric vertical limits{name_str}")
        
        # Check geometry
        if not obj or len(obj) < 3:
            errors.append(f"Insufficient geometry points: {len(obj) if obj else 0}{name_str}")
        
        return len(errors) == 0, errors
    
    def check_required_property(self, feature, property_name, aipname=None):
        """Check if a required property exists.
        
        Args:
            feature: Feature dict
            property_name: Name of required property
            aipname: Optional airspace name for logging
            
        Returns:
            True if property exists and is not None
        """
        value = feature.get('properties', {}).get(property_name)
        if value is None:
            name_str = f" ({aipname})" if aipname else ""
            logger.warning(f"Missing required property '{property_name}'{name_str}")
            return False
        return True


class DocumentType(Enum):
    """Enumeration of Norwegian AIP document types.
    
    Each document type has specific parsing rules and column layouts.
    Replaces the previous boolean flag approach for better type safety.
    """
    AD_AIP = auto()          # Aerodrome documents (AD-2.*)
    CTA_AIP = auto()         # Control area (ENR-2.1)
    TIA_AIP = auto()         # Traffic information area (ENR-2.2)
    RESTRICT_AIP = auto()    # Restricted areas (ENR-5.1)
    MILITARY_AIP = auto()    # Military areas (ENR-5.2)
    AIRSPORT_AIP = auto()    # Airsport areas (ENR-5.5)
    AIP_SUP = auto()         # Supplements (en_sup)
    VALLDAL = auto()         # Custom Valldal format
    UNKNOWN = auto()         # Unrecognized format
    
    @property
    def is_column_based(self):
        """True if document uses column-based table format."""
        return self in (
            DocumentType.CTA_AIP,
            DocumentType.TIA_AIP,
            DocumentType.RESTRICT_AIP,
            DocumentType.MILITARY_AIP,
            DocumentType.AIRSPORT_AIP
        )
    
    @property
    def has_special_finalize_trigger(self):
        """True if finalizes on final coordinate instead of name."""
        return self in (
            DocumentType.AIRSPORT_AIP,
            DocumentType.AIP_SUP,
            DocumentType.MILITARY_AIP
        )
    
    @property
    def description(self):
        """Human-readable description of document type."""
        descriptions = {
            DocumentType.AD_AIP: "AD (Aerodrome)",
            DocumentType.CTA_AIP: "ENR-2.1 (CTA)",
            DocumentType.TIA_AIP: "ENR-2.2 (TIA)",
            DocumentType.RESTRICT_AIP: "ENR-5.1 (Restricted)",
            DocumentType.MILITARY_AIP: "ENR-5.2 (Military)",
            DocumentType.AIRSPORT_AIP: "ENR-5.5 (Airsport)",
            DocumentType.AIP_SUP: "SUP (Supplement)",
            DocumentType.VALLDAL: "Valldal",
            DocumentType.UNKNOWN: "Unknown"
        }
        return descriptions.get(self, "Unknown")


@dataclass
class VerticalLimit:
    """Vertical limit specification for airspace.
    
    Encapsulates altitude/flight level with validation and unit conversion.
    Replaces dict-based vertical limits for type safety.
    """
    from_ft: Optional[int] = None    # Lower limit in feet AMSL
    to_ft: Optional[int] = None      # Upper limit in feet AMSL
    from_m: Optional[int] = None     # Lower limit in meters AMSL (derived)
    to_m: Optional[int] = None       # Upper limit in meters AMSL (derived)
    from_fl: Optional[int] = None    # Lower flight level
    to_fl: Optional[int] = None      # Upper flight level
    is_gnd: bool = False             # Lower limit is ground
    is_unl: bool = False             # Upper limit is unlimited
    
    def __post_init__(self):
        """Validate and convert units after initialization."""
        # Convert meters if provided but feet not
        if self.from_m is not None and self.from_ft is None:
            self.from_ft = int(self.from_m * 3.28084)
        if self.to_m is not None and self.to_ft is None:
            self.to_ft = int(self.to_m * 3.28084)
        
        # Convert feet to meters if not provided
        if self.from_ft is not None and self.from_m is None:
            self.from_m = ft2m(self.from_ft)
        if self.to_ft is not None and self.to_m is None:
            self.to_m = ft2m(self.to_ft)
        
        # Convert flight levels to feet if provided
        if self.from_fl is not None and self.from_ft is None:
            self.from_ft = self.from_fl * 100
            self.from_m = ft2m(self.from_ft)
        if self.to_fl is not None and self.to_ft is None:
            self.to_ft = self.to_fl * 100
            self.to_m = ft2m(self.to_ft)
        
        # Set to GND if specified
        if self.is_gnd:
            self.from_ft = 0
            self.from_m = 0
    
    def is_valid(self) -> bool:
        """Check if vertical limits are valid and consistent.
        
        Returns:
            True if limits are complete and from < to
        """
        if self.from_ft is None and not self.is_gnd:
            return False
        if self.to_ft is None and not self.is_unl:
            return False
        if self.from_ft is not None and self.to_ft is not None:
            return self.from_ft < self.to_ft
        return True
    
    @property
    def is_complete(self) -> bool:
        """True if both lower and upper limits are defined."""
        has_lower = self.from_ft is not None or self.is_gnd
        has_upper = self.to_ft is not None or self.is_unl
        return has_lower and has_upper
    
    def to_properties(self) -> dict:
        """Convert to GeoJSON properties dict.
        
        Returns:
            Dict with 'from (ft amsl)', 'to (ft amsl)', etc.
        """
        props = {}
        if self.from_ft is not None:
            props['from (ft amsl)'] = str(self.from_ft)
        if self.to_ft is not None:
            props['to (ft amsl)'] = str(self.to_ft)
        if self.from_m is not None:
            props['from (m amsl)'] = str(self.from_m)
        if self.to_m is not None:
            props['to (m amsl)'] = str(self.to_m)
        return props
    
    @classmethod
    def from_properties(cls, props: dict) -> 'VerticalLimit':
        """Create from GeoJSON properties dict.
        
        Args:
            props: Properties dict with 'from (ft amsl)', etc.
            
        Returns:
            VerticalLimit instance
        """
        from_ft = props.get('from (ft amsl)')
        to_ft = props.get('to (ft amsl)')
        from_m = props.get('from (m amsl)')
        to_m = props.get('to (m amsl)')
        
        # Convert strings to ints
        return cls(
            from_ft=int(from_ft) if from_ft else None,
            to_ft=int(to_ft) if to_ft else None,
            from_m=int(from_m) if from_m else None,
            to_m=int(to_m) if to_m else None
        )


class AirspaceClass(Enum):
    """ICAO airspace classification.
    
    Represents the different classes of airspace with validation.
    Norwegian AIP uses: A, C, D, G, Q (Danger), R (Restricted), Luftsport.
    """
    A = "A"  # Class A - IFR only, clearance required
    B = "B"  # Class B - IFR/VFR, clearance required
    C = "C"  # Class C - IFR/VFR, clearance required
    D = "D"  # Class D - IFR/VFR, clearance required for IFR
    E = "E"  # Class E - IFR/VFR, clearance required for IFR
    F = "F"  # Class F - Advisory (not used in Norway)
    G = "G"  # Class G - Uncontrolled
    Q = "Q"  # Danger area
    R = "R"  # Restricted area
    LUFTSPORT = "Luftsport"  # Norwegian airsport designation
    
    @classmethod
    def from_string(cls, value: str) -> Optional['AirspaceClass']:
        """Parse airspace class from string.
        
        Args:
            value: Class string (e.g. "C", "G", "Luftsport")
            
        Returns:
            AirspaceClass enum or None if invalid
        """
        if not value:
            return None
        
        # Direct match
        try:
            return cls(value)
        except ValueError:
            pass
        
        # Case-insensitive match
        for member in cls:
            if member.value.upper() == value.upper():
                return member
        
        return None
    
    @property
    def is_controlled(self) -> bool:
        """True if airspace requires ATC clearance."""
        return self in (
            AirspaceClass.A,
            AirspaceClass.B,
            AirspaceClass.C,
            AirspaceClass.D
        )
    
    @property
    def is_restricted(self) -> bool:
        """True if airspace has entry restrictions."""
        return self in (
            AirspaceClass.Q,
            AirspaceClass.R,
            AirspaceClass.LUFTSPORT
        )


class DocumentTypeStrategy:
    """Strategy for determining document type and parsing behavior.
    
    Encapsulates the logic for identifying AIP document types (AD, ENR-2.1, etc.)
    and their specific parsing requirements.
    """
    
    def __init__(self, filename):
        """Initialize by detecting document type from filename.
        
        Args:
            filename: Path to the AIP document file
        """
        self.filename = filename
        self.doc_type = self._detect_type(filename)
        
        # Legacy boolean flags for backward compatibility
        # TODO: Remove once all code uses doc_type enum
        self.ad_aip = (self.doc_type == DocumentType.AD_AIP)
        self.cta_aip = (self.doc_type == DocumentType.CTA_AIP)
        self.tia_aip = (self.doc_type == DocumentType.TIA_AIP)
        self.restrict_aip = (self.doc_type == DocumentType.RESTRICT_AIP)
        self.military_aip = (self.doc_type == DocumentType.MILITARY_AIP)
        self.airsport_aip = (self.doc_type == DocumentType.AIRSPORT_AIP)
        self.aip_sup = (self.doc_type == DocumentType.AIP_SUP)
        self.valldal = (self.doc_type == DocumentType.VALLDAL)
        self.en_enr_5_1 = "EN_ENR_5_1" in filename
    
    def _detect_type(self, filename):
        """Detect document type from filename patterns.
        
        Args:
            filename: Document filename
            
        Returns:
            DocumentType enum value
        """
        # Check patterns in priority order
        if "-AD-" in filename or "_AD_" in filename:
            return DocumentType.AD_AIP
        elif "ENR-2.1" in filename:
            return DocumentType.CTA_AIP
        elif "ENR-2.2" in filename:
            return DocumentType.TIA_AIP
        elif "ENR-5.1" in filename:
            return DocumentType.RESTRICT_AIP
        elif "ENR-5.2" in filename:
            return DocumentType.MILITARY_AIP
        elif "ENR-5.5" in filename:
            return DocumentType.AIRSPORT_AIP
        elif "en_sup" in filename:
            return DocumentType.AIP_SUP
        elif "valldal" in filename:
            return DocumentType.VALLDAL
        else:
            return DocumentType.UNKNOWN
    
    def get_document_type(self):
        """Get human-readable document type description.
        
        Returns:
            String describing the document type
        """
        return self.doc_type.description
    
    def is_special_finalize_trigger(self):
        """Check if this doc type has special finalization triggers.
        
        Returns:
            True if airsport, supplement, or military (finalizes on final coord)
        """
        return self.doc_type.has_special_finalize_trigger
    
    def is_any_of(self, *doc_types):
        """Check if current doc type matches any of the given types.
        
        Args:
            *doc_types: Variable number of DocumentType enum values
            
        Returns:
            True if doc_type matches any of the provided types
            
        Example:
            if doc_strategy.is_any_of(DocumentType.RESTRICT_AIP, DocumentType.MILITARY_AIP):
                # Handle restricted/military parsing
        """
        return self.doc_type in doc_types


class SpecialCaseRegistry:
    """Registry for all special cases and workarounds.
    
    Provides centralized checking for location-specific and format-specific
    quirks in Norwegian AIP documents. See module docstring for full list.
    """
    
    # Special case identifiers
    OSLO_ROMERIKE_NOTAM = "oslo_romerike_notam"
    SALEN_SAAB_SECTORS = "salen_saab_sectors"
    KRAMFORS_WITHIN = "kramfors_within"
    VALLDAL_FORMAT = "valldal_format"
    FARRIS_COUNTER = "farris_counter"
    GEITERYGGEN_SKIP = "geiteryggen_skip"
    ROMERIKE_OSLO_ALT = "romerike_oslo_alt"
    SEE_RMK_VERTL = "see_rmk_vertl"
    TIA_COLUMN_SHIFT = "tia_column_shift"
    INCOMPLETE_CIRCLE = "incomplete_circle"
    D476_D477_NAMES = "d476_d477_names"
    SALEN_SAAB_NAME_SKIP = "salen_saab_name_skip"
    
    def __init__(self):
        """Initialize special case registry."""
        pass
    
    def is_oslo_romerike_notam_area(self, aipname):
        """Check if airspace is Oslo/Romerike NOTAM-only area.
        
        Args:
            aipname: Airspace name
            
        Returns:
            True if this is a NOTAM-only restricted area
        """
        if "EN R" not in aipname:
            return False
        
        # Specific areas that are NOTAM-activated
        if "Kongsvinger" in aipname:
            return True
        if "Romerike" in aipname:
            return True
        if "Oslo" in aipname and "102" not in aipname:
            return True
        
        return False
    
    def is_salen_saab_sector(self, aipname):
        """Check if airspace is SÄLEN or SAAB CTR sector.
        
        Args:
            aipname: Airspace name
            
        Returns:
            True if this is a SÄLEN or SAAB sector airspace
        """
        if not aipname:
            return False
        return "SÄLEN" in aipname or "SAAB" in aipname
    
    def is_farris_tma(self, aipname):
        """Check if airspace is Farris TMA (counter skip issue).
        
        Args:
            aipname: Airspace name
            
        Returns:
            True if this is Farris TMA
        """
        return aipname and "Farris" in aipname
    
    def is_geiteryggen(self, aipname):
        """Check if airspace is Geiteryggen (skip finalization).
        
        Args:
            aipname: Airspace name
            
        Returns:
            True if this is Geiteryggen
        """
        return aipname and "Geiteryggen" in aipname
    
    def is_romerike_oslo_alt(self, aipname):
        """Check if airspace is Romerike/Oslo with altitude handling.
        
        Args:
            aipname: Airspace name
            
        Returns:
            True if this requires special altitude handling
        """
        if not aipname:
            return False
        return "Romerike" in aipname or "Oslo" in aipname
    
    def needs_d476_d477_normalization(self, aipname):
        """Check if name needs D476/D477 suffix normalization.
        
        Args:
            aipname: Airspace name
            
        Returns:
            'D476', 'D477', or None
        """
        if aipname == 'EN D476':
            return 'D476'
        elif aipname == 'EN D477':
            return 'D477'
        return None
    
    def is_sector_name_to_skip(self, name, ctx):
        """Check if sector name should be skipped (SÄLEN/SAAB subdivisions).
        
        Args:
            name: Name to check
            ctx: ParsingContext
            
        Returns:
            True if name should be skipped
        """
        if name == "Sector a" or name == "Sector b":
            return True
        if ctx.aipname and "Sector" in ctx.aipname and self.is_salen_saab_sector(ctx.aipname):
            return True
        return False


class SpecialCaseHandler:
    """Base class for location-specific special case handlers.
    
    Each handler encapsulates the logic for one specific special case,
    making the code more maintainable and testable.
    """
    
    def applies(self, aipname, line=None, ctx=None):
        """Check if this handler applies to the current situation.
        
        Args:
            aipname: Airspace name
            line: Optional current line being parsed
            ctx: Optional parsing context
            
        Returns:
            True if this handler should be applied
        """
        raise NotImplementedError
    
    def handle(self, feature, ctx, line=None, **kwargs):
        """Apply the special case handling.
        
        Args:
            feature: Feature dict to modify
            ctx: ParsingContext
            line: Optional current line
            **kwargs: Additional handler-specific parameters
            
        Returns:
            Modified feature or None if feature should be skipped
        """
        raise NotImplementedError


class OsloNotamHandler(SpecialCaseHandler):
    """Handler for Oslo/Romerike NOTAM-only restricted areas.
    
    Special Case #1: These areas are only active when NOTAMs are issued.
    Reference: en_sup_a_2018_015_en
    """
    
    def applies(self, aipname, line=None, ctx=None):
        """Check if airspace is Oslo/Romerike NOTAM area."""
        if "EN R" not in aipname:
            return False
        if "Kongsvinger" in aipname:
            return True
        if "Romerike" in aipname:
            return True
        if "Oslo" in aipname and "102" not in aipname:
            return True
        return False
    
    def handle(self, feature, ctx, line=None, **kwargs):
        """Set NOTAM-only flag and handle inverted limits."""
        feature['properties']['notam_only'] = 'true'
        
        # Also set limits to 0/99999 for Romerike/Oslo (unspecified upper limit)
        if "Romerike" in feature['properties'].get('name', '') or "Oslo" in feature['properties'].get('name', ''):
            feature['properties']['from (ft amsl)'] = '0'
            feature['properties']['from (m amsl)'] = '0'
            feature['properties']['to (ft amsl)'] = '99999'
            feature['properties']['to (m amsl)'] = '99999'
        
        logger.debug(f"Applied Oslo/Romerike NOTAM handler to {feature['properties'].get('name')}")
        return feature


class SalenSaabHandler(SpecialCaseHandler):
    """Handler for SÄLEN/SAAB CTR multi-sector airspaces.
    
    Special Case #2: These airspaces have multiple sectors that need special handling.
    - Split sectors dynamically when "Sector" keyword appears
    - First sector is union of others (skip during finalization)
    """
    
    def applies(self, aipname, line=None, ctx=None):
        """Check if airspace is SÄLEN or SAAB CTR."""
        if not aipname:
            return False
        return "SÄLEN" in aipname or "SAAB" in aipname
    
    def handle(self, feature, ctx, line=None, **kwargs):
        """Handle sector splitting."""
        mode = kwargs.get('mode', 'split')
        
        if mode == 'split' and line and "Sector" in line:
            # Store current sector
            logger.debug(f"Splitting SÄLEN/SAAB sector: {ctx.aipname}")
            ctx.sectors.append((ctx.aipname, ctx.obj))
            
            # Reset for next sector
            ctx.feature = {"properties": {}}
            ctx.obj = []
            
            # Set new sector name
            if "SÄLEN" in ctx.aipname:
                ctx.aipname = "SÄLEN CTR " + line
            else:
                ctx.aipname = "SAAB CTR " + line
        
        return feature


class ValldolHandler(SpecialCaseHandler):
    """Handler for Valldal custom document format.
    
    Special Case #4: Non-standard AIP format requiring special handling.
    Reference: valldal.txt
    """
    
    def applies(self, aipname, line=None, ctx=None):
        """Check if this is Valldal format."""
        return line and 'Valldal' in line
    
    def handle(self, feature, ctx, line=None, **kwargs):
        """Extract Valldal name and set defaults."""
        # Extract name from first two words
        ctx.aipname = " ".join(line.strip().split()[0:2])
        logger.debug(f"Valldal name: '{ctx.aipname}'")
        
        # Set hardcoded class and lower limit
        feature['properties']['class'] = 'Luftsport'
        feature['properties']['from (ft amsl)'] = 0
        feature['properties']['from (m amsl)'] = 0
        
        return feature


class FarrisTMAHandler(SpecialCaseHandler):
    """Handler for Farris TMA counter skip.
    
    Special Case #5: Counter numbering has gaps (skip 5 and 6).
    Reference: Farris TMA naming convention
    """
    
    def applies(self, aipname, line=None, ctx=None):
        """Check if this is Farris TMA."""
        return aipname and "Farris" in aipname
    
    def handle(self, feature, ctx, line=None, **kwargs):
        """Adjust counter for gaps."""
        recount = kwargs.get('recount', 0)
        
        if recount > 4:
            # Skip counter values 5 and 6
            adjusted_count = recount + 2
            logger.debug(f"Farris TMA counter: {recount} -> {adjusted_count}")
            return adjusted_count
        
        return recount


class ColumnParser:
    """Parser for table-based AIP documents with column layouts.
    
    Many AIP documents use tabular formats where information is organized in columns.
    This class detects column boundaries and splits lines for separate parsing.
    """
    
    def __init__(self, doc_strategy):
        """Initialize with document type strategy.
        
        Args:
            doc_strategy: DocumentTypeStrategy instance
        """
        self.doc_strategy = doc_strategy
        self.vcuts = None  # Column cut positions
        self.vcut = 999    # Default vertical cut position
        self.vend = 1000   # Default vertical end position
    
    def detect_columns_from_header(self, line, headers):
        """Detect column positions from header line.
        
        Args:
            line: Header line text
            headers: Parsed header fields
            
        Returns:
            List of column cut positions
        """
        vcuts = []
        
        # Detect from header positions
        for header in headers[0]:
            if header:
                vcuts.append(line.index(header))
        vcuts.append(len(line))
        
        self.vcuts = vcuts
        logger.debug(f"Detected column positions: {vcuts}")
        return vcuts
    
    def detect_columns_from_pattern(self, line, tia_aip_acc=False):
        """Detect column positions from numbered pattern.
        
        Args:
            line: Line to analyze for pattern
            tia_aip_acc: Whether this is TIA AIP ACC format
            
        Returns:
            List of column positions or None
        """
        if tia_aip_acc and ("1     " in line):
            logger.debug("VCUT LINE? %s", line)
            vcuts = [m.start() for m in re.finditer(r'[^\s]', line)]
            # SPECIAL CASE #9: Column shift hack for TIA AIP ACC format
            # Column positions detected are off by 2 characters
            vcuts = [(x and (x-2)) for x in vcuts]
            self.vcuts = vcuts
            logger.debug("vcuts %s", vcuts)
            return vcuts
        return None
    
    def update_vertical_limit_column(self, line):
        """Update vertical limit column positions based on header keywords.
        
        Args:
            line: Line to check for vertical limit headers
            
        Returns:
            True if column positions were updated
        """
        doc_type = self.doc_strategy.doc_type
        
        if doc_type == DocumentType.AIRSPORT_AIP:
            if "Vertical limits" in line:
                self.vcut = line.index("Vertical limits")
                self.vend = self.vcut + 28
                logger.debug(f"Airsport vcut: {self.vcut}, vend: {self.vend}")
                return True
        
        elif self.doc_strategy.is_any_of(DocumentType.RESTRICT_AIP, DocumentType.MILITARY_AIP):
            if "Vertikale grenser" in line:
                self.vcut = line.index("Vertikale grenser")
                self.vend = self.vcut + 16
                if "Aktiviseringstid" in line:
                    self.vend = line.index("Aktiviseringstid")
                logger.debug(f"Restrict/Military vcut: {self.vcut}, vend: {self.vend}")
                return True
        
        elif doc_type == DocumentType.CTA_AIP:
            if "Tjenesteenhet" in line:
                self.vcut = line.index("Tjenesteenhet")
                logger.debug(f"CTA vcut: {self.vcut}")
                return True
        
        elif doc_type == DocumentType.TIA_AIP:
            if "Unit providing" in line:
                self.vcut = line.index("Unit providing")
                logger.debug(f"TIA vcut: {self.vcut}")
                return True
        
        return False
    
    def split_line_by_columns(self, line, tia_aip_acc=False):
        """Split a line into columns for parsing.
        
        Args:
            line: Line to split
            tia_aip_acc: Whether this is TIA AIP ACC format
            
        Returns:
            List of (column_text, column_number) tuples
        """
        columns = []
        doc_type = self.doc_strategy.doc_type
        
        if tia_aip_acc and self.vcuts:
            # Split by detected column positions
            for i in range(len(self.vcuts) - 1):
                columns.append((line[self.vcuts[i]:self.vcuts[i+1]], i+1))
            columns.append((line[self.vcuts[-1]:], len(self.vcuts)))
        
        elif doc_type == DocumentType.AIRSPORT_AIP:
            # Two columns: main and vertical limits
            columns.append((line[:self.vcut], 1))
            columns.append((line[self.vcut:self.vend], 2))
        
        elif self.doc_strategy.is_any_of(DocumentType.RESTRICT_AIP, DocumentType.MILITARY_AIP):
            # Two or three columns depending on type
            columns.append((line[:self.vcut], 1))
            if doc_type == DocumentType.MILITARY_AIP:
                columns.append((line[self.vcut:self.vend], 2))
            else:
                columns.append((line[self.vcut:], 2))
        
        elif self.doc_strategy.is_any_of(DocumentType.CTA_AIP, DocumentType.TIA_AIP):
            # Single column before vertical cut
            columns.append((line[:self.vcut], 1))
        
        else:
            # No column splitting - full line
            columns.append((line, 1))
        
        return columns


class FeatureBuilder:
    """Builder for airspace feature properties.
    
    Encapsulates property assignment and validation for airspace features.
    Handles altitude conversions, property overwrite warnings, and ensures
    consistency of feature data.
    """
    
    def set_class(self, feature, airspace_class):
        """Set the airspace class property with validation.
        
        Args:
            feature: Feature dict to update
            airspace_class: Class value (string or AirspaceClass enum)
        """
        # Normalize to string if enum
        if isinstance(airspace_class, AirspaceClass):
            class_value = airspace_class.value
        else:
            # Validate if it's a string
            parsed = AirspaceClass.from_string(airspace_class)
            if parsed:
                class_value = parsed.value
            else:
                # Unknown class, keep as-is but warn
                logger.warning(f"Unknown airspace class: {airspace_class}")
                class_value = airspace_class
        
        feature['properties']['class'] = class_value
    
    def set_vertical_limits(self, feature, from_amsl=None, to_amsl=None, from_fl=None, to_fl=None, warn=True):
        """Set vertical limit properties with optional overwrite warnings.
        
        Args:
            feature: Feature dict to update
            from_amsl: Lower limit in feet AMSL
            to_amsl: Upper limit in feet AMSL
            from_fl: Lower flight level
            to_fl: Upper flight level
            warn: Whether to warn on property overwrites
            
        Returns:
            True if values were set, False if skipped due to overwrite conflict
        """
        if to_amsl is not None:
            currentv = feature['properties'].get('to (ft amsl)')
            if warn and currentv is not None and currentv != to_amsl:
                logger.warning("attempt to overwrite vertl_to %s with %s." % (currentv, to_amsl))
                if int(currentv) > int(to_amsl):
                    logger.warning("skipping.")
                    return False
                logger.warning("ok.")
            if to_fl is not None:
                feature['properties']['to (fl)'] = to_fl
            feature['properties']['to (ft amsl)'] = to_amsl
            feature['properties']['to (m amsl)'] = ft2m(to_amsl)
        
        if from_amsl is not None:
            currentv = feature['properties'].get('from (ft amsl)')
            if warn and currentv is not None and currentv != from_amsl:
                logger.warning("attempt to overwrite vertl_from %s with %s." % (currentv, from_amsl))
                if int(currentv) < int(from_amsl):
                    logger.warning("skipping.")
                    return False
                logger.warning("ok.")
            if from_fl is not None:
                feature['properties']['from (fl)'] = from_fl
            feature['properties']['from (ft amsl)'] = from_amsl
            feature['properties']['from (m amsl)'] = ft2m(from_amsl)
        
        return True
    
    def set_frequency(self, feature, frequency):
        """Set the frequency property."""
        feature['properties']['frequency'] = frequency
    
    def has_vertical_limits(self, feature):
        """Check if feature has complete vertical limits."""
        return (feature['properties'].get('from (ft amsl)') is not None and
                feature['properties'].get('to (ft amsl)') is not None)


class FeatureFinalizer:
    """Handles finalization and validation of airspace features.
    
    Encapsulates the complex finalization logic including:
    - Name normalization and deduplication
    - Class assignment based on airspace type
    - Special case handling (Oslo NOTAM, SÄLEN/SAAB, etc.)
    - Geometry validation and simplification
    - Duplicate detection
    - Sanity checks
    """
    
    def __init__(self, completed, names, accsectors, oslo_notam_handler):
        """Initialize finalizer with shared state.
        
        Args:
            completed: Dict tracking completed feature names
            names: Dict tracking all seen names
            accsectors: List for ACC sector features
            oslo_notam_handler: Handler for Oslo NOTAM special cases
        """
        self.completed = completed
        self.names = names
        self.accsectors = accsectors
        self.oslo_notam_handler = oslo_notam_handler
    
    def finalize(self, feature, features, obj, source, aipname, doc_flags, country, end_notam, sanntid_ref):
        """Complete and sanity check a feature definition.
        
        Args:
            feature: Feature dict to finalize
            features: List to append completed features to
            obj: Geometry coordinates
            source: Source filename
            aipname: Airspace name
            doc_flags: Dict with cta_aip, restrict_aip, aip_sup, tia_aip, military_aip
            country: Country code ('NO' or 'SE')
            end_notam: Whether document is NOTAM-related
            sanntid_ref: List with single element [bool] to track sanntid state
            
        Returns:
            Tuple of (empty_feature, empty_obj) for reset
        """
        cta_aip = doc_flags.get('cta_aip', False)
        restrict_aip = doc_flags.get('restrict_aip', False)
        aip_sup = doc_flags.get('aip_sup', False)
        tia_aip = doc_flags.get('tia_aip', False)
        military_aip = doc_flags.get('military_aip', False)
        
        sanntid = sanntid_ref[0]  # Get current value
        
        feature['properties']['source_href'] = source
        feature['properties']['country'] = country
        feature['geometry'] = obj
        aipname = wstrip(str(aipname))
        
        # SPECIAL CASE #11: EN D476/D477 name normalization
        if aipname == 'EN D476':
            aipname = 'EN D476 R og B 1'
        if aipname == 'EN D477':
            aipname = 'EN D477 R og B 2'
        
        # Skip unwanted airspace types
        for ignore in ['ADS', 'AOR', 'FAB', ' FIR', 'HTZ']:
            if ignore in aipname:
                logger.debug("Ignoring: %s", aipname)
                return {"properties": {}}, []
        
        feature['properties']['name'] = aipname
        
        # Handle ACC/TMA/CTA sector numbering
        if cta_aip or aip_sup or tia_aip or 'ACC' in aipname:
            recount = len([f for f in features if aipname in f['properties']['name']])
            recount = recount or len([f for f in self.accsectors if aipname in f['properties']['name']])
            if recount > 0:
                separator = " "
                if re.search(r'\d$', aipname):
                    separator = "-"
                # SPECIAL CASE #5: Farris TMA counter skip
                if "Farris" in aipname:
                    if recount > 4:
                        recount += 2
                    else:
                        recount += 1
                logger.debug("RECOUNT renamed " + aipname + " INTO " + aipname + separator + str(recount + 1))
                feature['properties']['name'] = aipname + separator + str(recount + 1)
        
        # Set airspace class based on name patterns
        if 'TIZ' in aipname or 'TIA' in aipname:
            feature['properties']['class'] = 'G'
        elif 'CTR' in aipname:
            feature['properties']['class'] = 'D'
        elif 'TRIDENT' in aipname or 'EN D' in aipname or 'END' in aipname or 'ES D' in aipname:
            feature['properties']['class'] = 'Q'
        elif 'EN R' in aipname or 'ES R' in aipname or 'ESTRA' in aipname or 'EUCBA' in aipname or 'RPAS' in aipname:
            feature['properties']['class'] = 'R'
        elif 'TMA' in aipname or 'CTA' in aipname or 'FIR' in aipname or 'ACC' in aipname or 'ATZ' in aipname or 'FAB' in aipname or 'Sector' in aipname:
            feature['properties']['class'] = 'C'
        elif '5.5' in source or "Hareid" in aipname:
            if "Nidaros" in aipname:
                # Skip old Nidaros airspace
                return {"properties": {}}, []
            feature['properties']['class'] = 'Luftsport'
        
        index = len(collection) + len(features)
        
        if self.names.get(aipname):
            logger.debug("DUPLICATE NAME: %s", aipname)
        
        # Simplify complex polygons
        if len(obj) > 100:
            logger.debug("COMPLEX POLYGON %s with %i points", feature['properties'].get('name'), len(obj))
            obj = simplify_poly(obj, 100)
            feature['geometry'] = obj
        
        if len(obj) > 3:
            logger.debug("Finalizing polygon #%i %s with %i points.", index, feature['properties'].get('name'), len(obj))
            
            name = feature['properties'].get('name')
            source_href = feature['properties'].get('source_href')
            from_ = feature['properties'].get('from (ft amsl)')
            to_ = feature['properties'].get('to (ft amsl)')
            class_ = feature['properties'].get('class')
            
            # Check for duplicates
            if name in self.completed:
                logger.info("ERROR Duplicate feature name: #%i %s", index, name)
                return {"properties": {}}, []
            else:
                if 'ACC' in aipname:
                    logger.debug("Writing ACC sector to separate file: %s", aipname)
                    self.accsectors.append(feature)
                else:
                    features.append(feature)
            
            # Sanity checks
            if name is None:
                logger.error("Feature without name: #%i", index)
                sys.exit(1)
            if "None" in name:
                logger.error("Feature without name: #%i", index)
                sys.exit(1)
            self.completed[name] = True
            if source_href is None:
                logger.error("Feature without source: #%i", index)
                sys.exit(1)
            if feature['properties'].get('name') is None:
                logger.error("Feature without name: #%i (%s)", index, source_href)
                sys.exit(1)
            if class_ is None:
                logger.error("Feature without class (boo): #%i (%s)", index, source_href)
                sys.exit(1)
            
            # SPECIAL CASE #1: Oslo/Romerike NOTAM areas
            if self.oslo_notam_handler.applies(aipname):
                feature = self.oslo_notam_handler.handle(feature, None)
                # Old code had a bug: it set local vars to '0','0' forcing a swap
                # We need to replicate this for exact output compatibility
                if "Romerike" in aipname or "Oslo" in aipname:
                    from_ = '0'
                    to_ = '0'
                else:
                    from_ = feature['properties'].get('from (ft amsl)')
                    to_ = feature['properties'].get('to (ft amsl)')
            
            # Handle NOTAM and AMC classifications
            if ("EN D" in aipname or "END" in aipname) and (end_notam or sanntid):
                feature['properties']['notam_only'] = 'true'
                if sanntid:
                    logger.debug("Classifying %s as AMC/Sanntidsaktivering", aipname)
                    feature['properties']['amc_only'] = 'true'
                    sanntid = False
                    sanntid_ref[0] = False  # Update reference
            if ("EN D" in aipname or "END" in aipname) and (military_aip or ("Klepp" in aipname)):
                feature['properties']['amc_only'] = 'true'
            
            # Handle missing vertical limits
            if from_ is None:
                if "en_sup_a_2018_015_en" in source_href:
                    feature['properties']['from (ft amsl)'] = '0'
                    feature['properties']['from (m amsl)'] = '0'
                    from_ = '0'
                else:
                    logger.error("Feature without lower limit: #%i (%s)", index, source_href)
                    sys.exit(1)
            if to_ is None:
                if "en_sup_a_2018_015_en" in source_href:
                    feature['properties']['to (ft amsl)'] = '99999'
                    feature['properties']['to (m amsl)'] = '9999'
                    to_ = '99999'
                else:
                    logger.error("Feature without upper limit: #%i (%s)", index, source_href)
                    sys.exit(1)
            
            # Handle inverted vertical limits (SPECIAL CASE #1)
            if int(from_) >= int(to_):
                if "en_sup_a_2018_015_en" in source_href or "Romerike" in aipname or "Oslo" in aipname:
                    feature['properties']['from (ft amsl)'] = to_
                    feature['properties']['to (ft amsl)'] = from_
                else:
                    logger.error("Lower limit %s > upper limit %s: #%i (%s)", from_, to_, index, source_href)
                    sys.exit(1)
        elif len(obj) > 0:
            logger.error("ERROR Finalizing incomplete polygon #%i (%i points)", index, len(obj))
        
        self.names[aipname] = True
        logger.debug("OK polygon #%i %s with %i points (%s-%s).", index, feature['properties'].get('name'),
                     len(obj),
                     feature['properties'].get('from (ft amsl)'),
                     feature['properties'].get('to (ft amsl)'))
        return {"properties": {}}, []


def finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, aip_sup, tia_aip, military_aip=False):
    """DEPRECATED: Legacy wrapper for backward compatibility.
    
    This function is maintained for existing call sites but delegates to FeatureFinalizer.
    New code should instantiate FeatureFinalizer directly.
    """
    global completed
    global country
    global end_notam
    global sanntid
    global accsectors
    global names
    
    # Create finalizer if not exists (will be called multiple times per file)
    if not hasattr(finalize, '_finalizer'):
        # Initialize with globals on first call
        finalize._finalizer = FeatureFinalizer(completed, names, accsectors, OsloNotamHandler())
    
    doc_flags = {
        'cta_aip': cta_aip,
        'restrict_aip': restrict_aip,
        'aip_sup': aip_sup,
        'tia_aip': tia_aip,
        'military_aip': military_aip
    }
    
    sanntid_ref = [sanntid]  # Wrap in list so it can be modified
    result = finalize._finalizer.finalize(feature, features, obj, source, aipname, 
                                          doc_flags, country, end_notam, sanntid_ref)
    sanntid = sanntid_ref[0]  # Update global
    return result


for filename in os.listdir("./sources/txt"):
    logger.info("Reading %s", "./sources/txt/"+filename)
    source = urllib.parse.unquote(filename.split(".txt")[0])
    if ".swp" in filename:
        logger.warning("Skipping swap file %s", filename)
        continue

    data = open("./sources/txt/"+filename,"r","utf-8").readlines()
    
    # Determine document type using strategy
    doc_strategy = DocumentTypeStrategy(filename)
    logger.debug(f"Document type: {doc_strategy.get_document_type()}")
    
    # Extract boolean flags for backward compatibility
    ad_aip = doc_strategy.ad_aip
    cta_aip = doc_strategy.cta_aip
    tia_aip = doc_strategy.tia_aip
    restrict_aip = doc_strategy.restrict_aip
    military_aip = doc_strategy.military_aip
    airsport_aip = doc_strategy.airsport_aip
    aip_sup = doc_strategy.aip_sup
    valldal = doc_strategy.valldal
    en_enr_5_1 = doc_strategy.en_enr_5_1

    # Initialize parsing context for this file
    ctx = ParsingContext()
    name_parser = NameParser(patterns)
    class_parser = ClassParser(patterns)
    vertical_parser = VerticalLimitParser(patterns)
    coord_parser = CoordinateParser(patterns)
    border_follower = BorderFollower()
    geometry_builder = GeometryBuilder()
    feature_validator = FeatureValidator()
    feature_builder = FeatureBuilder()
    column_parser = ColumnParser(doc_strategy)
    special_cases = SpecialCaseRegistry()
    
    # Initialize special case handlers
    oslo_notam_handler = OsloNotamHandler()
    salen_saab_handler = SalenSaabHandler()
    valldol_handler = ValldolHandler()
    farris_handler = FarrisTMAHandler()

    # Norwegian AIP only (Swedish files will be skipped/ignored)
    country = 'EN'
    ctx.country = 'EN'
    ctx.border = borders['norway']
    ctx.re_coord3 = re_coord3
    logger.debug("Processing Norwegian AIP document")

    def parse(line, half=1):
        """Parse a line (or half line) of converted pdftotext"""
        line = line.strip()
        logger.debug("LINE '%s'", line)

        # No more globals! Using ctx.* instead
        if line==LINEBREAK:
            # drop current ctx.feature, if we don't have vertl by now,
            # then this is just an overview polygon
            ctx.reset_feature()
            return


        if ad_aip and not "ENNO" in filename:
            if not ctx.ats_chapter:
                # skip to chapter 2.71
                if "ATS airspace" in line or "ATS AIRSPACE" in line:
                    logger.debug("Found chapter 2.71")
                    ctx.ats_chapter=True
                return
            else:
                # then skip everything after
                if "AD 2." in line or "ATS COMM" in line:
                #if "ATS komm" in line or "Kallesignal" in line:
                    logger.debug("End chapter 2.71")
                    ctx.ats_chapter=False

        if 'Sanntidsaktivering' in line:
            logger.debug("Activating AMC/Sanntidsaktivering for this ctx.feature.")
            ctx.sanntid = True
            global sanntid
            sanntid = True  # Sync with global for finalize()

        class_ = class_parser.parse_class(line)
        if class_:
            logger.debug("Found class in line: %s", line)
            class_value = class_parser.extract_class(class_)
            feature_builder.set_class(ctx.feature, class_value)
            if tia_aip or (ctx.aipname and "RMZ" in ctx.aipname):
                ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip, military_aip)
            return

        # SPECIAL CASE #2: SÄLEN/SAAB CTR sectors (using handler)
        if salen_saab_handler.applies(ctx.aipname, line, ctx) and "Sector" in line:
            salen_saab_handler.handle(ctx.feature, ctx, line, mode='split')
        
        # SPECIAL CASE #4: Valldal custom format (using handler)
        if valldal and valldol_handler.applies(ctx.aipname, line, ctx):
            ctx.feature = valldol_handler.handle(ctx.feature, ctx, line)

        coords, coords2, coords3 = coord_parser.has_coordinates(line, ctx)

        if (coords or coords2 or coords3):

            logger.debug("Found %i coords in line: %s", coords3 and len(coords3) or 1, line)
            logger.debug(printj(coords3))
            if line.strip()[-1] == "N":
                ctx.coords_wrap += line.strip() + " "
                logger.debug("Continuing line after N coordinate: %s", ctx.coords_wrap)
                return
            elif ctx.coords_wrap:
                nline = ctx.coords_wrap + line
                logger.debug("Continued line: %s", nline)
                coords = re_coord.search(nline)
                coords2 = re_coord2.search(nline)
                coords3 = ctx.re_coord3.findall(nline)
                logger.debug("Found %i coords in merged line: %s", coords3 and len(coords3) or '1', nline)
                line = nline
                ctx.coords_wrap = ""

            if coords and not ("Lyng" in ctx.aipname or "Halten" in ctx.aipname):
                coords  = coords.groupdict()
                n = coords.get('cn') or coords.get('n')
                e = coords.get('ce') or coords.get('e')
                #n = coords.get('n') or coords.get('cn')
                #e = coords.get('e') or coords.get('ce')
                rad = coords.get('rad')
                if not rad:
                    rad_m = coords.get('rad_m')
                    if rad_m:
                        rad = m2nm(rad_m)
                if not n or not e or not rad:
                    logger.warning("Incomplete circle definition (missing n/e/rad), skipping: %s", line)
                    return
                ctx.lastn, ctx.laste = n, e
                logger.debug("Circle center is %s %s %s %s", coords.get('n'), coords.get('e'), coords.get('cn'), coords.get('ce'))
                logger.debug("COORDS is %s", json.dumps(coords))
                ctx.obj = geometry_builder.add_circle(ctx.obj, n, e, rad)
                logger.debug("LENS %s", len(ctx.obj))

            elif coords2:
                coords  = coords2.groupdict()
                n = coords.get('n')
                e = coords.get('e')
                if n is None and e is None:
                    n,e = ctx.lastn, ctx.laste
                secfrom = coords.get('secfrom')
                secto = coords.get('secto')
                radfrom = coords.get('radfrom')
                radto = coords.get('rad')
                ctx.obj = geometry_builder.add_sector(ctx.obj, n, e, secfrom, secto, radfrom, radto)

            else:
                skip_next = 0
                for blob in coords3:
                    ne,n,e,along,arc,rad,cn,ce = blob[:8]
                    circle = blob[8] if len(blob)==9 else None
                    logger.debug("Coords: %s", (n,e,ne,along,arc,rad,cn,ce,circle))
                    if skip_next > 0 and n:
                        logger.debug("Skipped.")
                        skip_next -= 1
                        continue
                    if arc:
                        arcdata = re_arc.search(line)
                        if not arcdata:
                            ctx.coords_wrap += line.strip() + " "
                            logger.debug("Continuing line after incomplete arc: %s", ctx.coords_wrap)
                            return
                        arcdata = arcdata.groupdict()
                        logger.debug("Completed arc: %s", arcdata)
                        n = arcdata['n']
                        e = arcdata['e']
                        rad = arcdata.get('rad1') or arcdata.get('rad2')
                        to_n = arcdata['n2']
                        to_e = arcdata['e2']
                        cw = arcdata['dir']
                        logger.debug("ARC IS "+cw)
                        ctx.obj = geometry_builder.add_arc(ctx.obj, n, e, rad, to_n, to_e, cw=='clockwise')
                        ctx.lastn, ctx.laste = None, None
                        skip_next = 1
                    elif circle:
                        logger.warning("Incomplete circle in coordinate list, skipping")
                        return


                    if ctx.alonging:
                        fill = border_follower.finish_following(ctx, n, e, ctx.aipname)
                        for bpair in fill:
                            bn, be = ll2c(bpair)
                            ctx.obj.insert(0,(bn,be))

                    if rad and cn and ce:
                        logger.debug("Merging circle using cn, ce.")
                        ctx.obj = geometry_builder.add_circle(ctx.obj, cn, ce, rad)
                    if n and e:
                        ctx.lastn, ctx.laste = n, e
                        ctx.obj.insert(0,(n,e))
                    if along:
                        border_follower.start_following(ctx, n, e)
                    if '(' in ne:
                        ctx.finalcoord = True
                        logger.debug("Found final coord.")
                    else:
                        ctx.finalcoord = False
                    if (airsport_aip or aip_sup or military_aip) and ctx.finalcoord:
                        if ctx.feature['properties'].get('from (ft amsl)') is not None:
                            logger.debug("Finalizing: ctx.finalcoord.")
                            # Optional validation logging (doesn't block finalize)
                            is_valid, errors = feature_validator.validate(ctx.feature, ctx.obj, ctx.aipname)
                            if not is_valid:
                                logger.debug(f"Feature validation warnings: {', '.join(errors)}")
                            ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip, military_aip)
                            ctx.lastv = None

            if not valldal:
                return

        # IDENTIFY temporary restrictions
        period = re_period.search(line) or re_period2.search(line) or re_period3.search(line)

        # IDENTIFY frequencies
        freq = re_freq.search(line)
        if freq:
            freq = freq.groupdict()
            logger.debug("Found FREQUENCY: %s", freq['freq'])
            feature_builder.set_frequency(ctx.feature, freq.get('freq'))

        # IDENTIFY altitude limits
        vertl = vertical_parser.parse_vertical_limit(line, military_aip)

        if vertl:
            logger.debug("Found vertl in line: %s", vertl.groupdict())
            fromamsl, toamsl, fl, flto = vertical_parser.extract_limits(vertl, ctx)

            # Use feature_builder to set limits with overwrite handling
            if not feature_builder.set_vertical_limits(ctx.feature, fromamsl, toamsl, fl, flto):
                return  # Skipped due to overwrite conflict
            
            if toamsl is not None:
                ctx.lastv = toamsl
                if valldal:
                    ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip, military_aip)
                    ctx.lastv = None
            if fromamsl is not None:
                ctx.lastv = None
                # SPECIAL CASE #6/#7: Finalization conditions
                # - Skip Geiteryggen (#6)
                # - Allow Romerike/Oslo without upper limit (#7)
                # Finalize if: special doc types have final coord
                should_finalize = (((cta_aip or airsport_aip or aip_sup or tia_aip or (ctx.aipname and ("TIZ" in ctx.aipname))) and (ctx.finalcoord or tia_aip_acc))
                                  and not ("Geiteryggen" in ctx.aipname))
                if should_finalize:
                    logger.debug("Finalizing poly: Vertl complete.")
                    # SPECIAL CASE #2: SÄLEN/SAAB sector finalization
                    # Process accumulated sectors (skip first which is union)
                    if ctx.aipname and (("SÄLEN" in ctx.aipname) or ("SAAB" in ctx.aipname)) and len(ctx.sectors)>0:
                        for x in ctx.sectors[1:]: # skip the first sector, which is the union of the other ctx.sectors in Swedish docs
                            aipname_,  obj_ = x
                            logger.debug("Restoring "+aipname_+" "+str(len(ctx.sectors)))
                            feature_ = deepcopy(ctx.feature)
                            logger.debug("Finalizing SAAB/SÄLEN: " + aipname_)
                            finalize(feature_, ctx.features, obj_, source, aipname_, cta_aip, restrict_aip, aip_sup, tia_aip, military_aip)
                        ctx.sectors = []
                        logger.debug("Finalizing last poly as ."+ctx.aipname)
                    ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip, military_aip)

            logger.debug("From %s to %s", ctx.feature['properties'].get('from (ft amsl)'), ctx.feature['properties'].get('to (ft amsl)'))
            return

        # IDENTIFY airspace naming
        name = name_parser.parse_name(line)

        if ctx.name_cont and not 'Real time' in line:
            ctx.aipname = ctx.aipname + " " + line
            logger.debug("Continuing name as "+ctx.aipname)
            if line == '' or 'EN D' in ctx.aipname:
                ctx.name_cont = False

        if name:
            if en_enr_5_1 or "Hareid" in line:
                logger.debug("RESTRICT/HAREID")
                ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip, military_aip)
                ctx.lastv = None

            # Process the matched name
            name = name_parser.process_name(name, line, ctx)
            
            # Check if we should skip this name
            if name_parser.should_skip_name(name, ctx):
                return

            if restrict_aip or military_aip:
                # SPECIAL CASE #7: Romerike/Oslo altitude handling
                # Allow finalization without upper limit for these specific areas
                if ctx.feature['properties'].get('from (ft amsl)') is not None and (ctx.feature['properties'].get('to (ft amsl)') or "Romerike" in ctx.aipname or "Oslo" in ctx.aipname):
                    logger.debug("RESTRICT/MILITARY + name and vertl complete")
                    ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip, military_aip)
                    ctx.lastv = None
                else:
                    logger.debug("RESTRICT/MILITARY + name and vertl NOT complete")

            ctx.aipname = name
            logger.debug("Found name '%s' in line: %s", ctx.aipname, line)
            return

        # The airsport document doesn't have recognizable airspace names
        # so we just assume every line that isn't otherwise parsed is the name of the next box.
        if airsport_aip and line.strip():
            logger.debug("Unhandled line in airsport_aip: %s", line)
            if wstrip(line)=="1":
                logger.debug("Starting airsport_aip table")
                ctx.airsport_intable = True
            elif wstrip(line)[0] != "2" and ctx.airsport_intable:
                logger.debug("Considering as new ctx.aipname: '%s'", line)
                ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip, military_aip)
                ctx.aipname = wstrip(line)

        if line.strip()=="-+-":
            ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip, military_aip)

    # end def parse

    # IDENTIFY document types
    table = []
    column_parsing = []
    header_cont = False
    cr_areas = False
    end_notam = False
    sanntid = False
    skip_tia = False
    tia_aip_acc = False
    vcuts = None
    skip_valldal = True

    for line in data:

        if "\f" in line:
            logger.debug("Stop column parsing, \f found")
            column_parsing = []

        if valldal:
            if line.strip() == 'Valldal Midt':
                skip_valldal = False
            if 'Varsling av aktivitet' in line:
                break
            if skip_valldal:
                continue

        if tia_aip:
            if "Norway ACC sectorization" in line:
                logger.debug("SECTORIZATION START")
                tia_aip_acc = True
                skip_tia = False
            if "Functional Airspace block" in line:
                break
            if tia_aip_acc and ("1     " in line):
                column_parser.detect_columns_from_pattern(line, tia_aip_acc=True)
            if "ADS areas" in line:
                skip_tia = True
            if skip_tia:
                continue

        if aip_sup and ("Luftromsklasse" in line) and not ("2025" in filename) or ("obligatoriske meldepunkter" in line):
            logger.debug("Skipping end of SUP")
            break

        if 'Danger Areas active only as notified by NOTAM' in line:
            logger.debug("FOLLOWING danger areas are NOTAM activated.")
            end_notam = True

        if not line.strip():
            if column_parsing and table:
                # parse rows first, then cols
                for col in range(0,len(table[0])):
                    for row in table:
                        if not len(row)>col:
                            logger.debug("ERROR not in table format: row=%s, col=%s", row, col)
                            #sys.exit(1)
                        else:
                           parse(row[col])
                parse(LINEBREAK)
                table = []
        headers = None

        if column_parsing and not header_cont:
            row = []
            for i in range(0,len(column_parsing)-1):
                lcut = line[column_parsing[i]:column_parsing[i+1]].strip()
                row.append(lcut)
            table.append(row)
            continue
        
        # Check for headers (Norwegian documents only)
        if headers:
            logger.debug("Parsed header line as %s.", headers)
            logger.debug("line=%s.", line)
            vcuts = column_parser.detect_columns_from_header(line, headers)
            column_parsing = sorted((column_parsing + vcuts))
            logger.debug("DEBUG: column parsing: %s", vcuts)
            continue

        # parse columns separately for table formatted files
        # use header fields to detect column positions
        if tia_aip_acc and column_parser.vcuts:
            for i in range(len(column_parser.vcuts)-1):
                parse(line[column_parser.vcuts[i]:column_parser.vcuts[i+1]])
            parse(line[column_parser.vcuts[len(column_parser.vcuts)-1]:])
        elif airsport_aip:
            if not column_parser.update_vertical_limit_column(line):
                parse(line[:column_parser.vcut],1)
                parse(line[column_parser.vcut:column_parser.vend],2)
        elif restrict_aip or military_aip:
            if not column_parser.update_vertical_limit_column(line):
                parse(line[:column_parser.vcut],1)
                if military_aip:
                    parse(line[column_parser.vcut:column_parser.vend],2)
                else:
                    parse(line[column_parser.vcut:],2)
        elif cta_aip:
            if not column_parser.update_vertical_limit_column(line):
                parse(line[:column_parser.vcut],1)
        elif tia_aip and not tia_aip_acc:
            if not column_parser.update_vertical_limit_column(line):
                parse(line[:column_parser.vcut],1)
        else:
            parse(line,1)

    if "nidaros" in source:
        ctx.aipname = "Nidaros"
        ctx.feature['properties']['from (ft amsl)'] = 0
        ctx.feature['properties']['from (m amsl)'] = 0
        ctx.feature['properties']['to (ft amsl)']= 3500
        ctx.feature['properties']['to (m amsl)'] = ft2m(3500)
        ctx.feature['properties']['class'] = 'Luftsport'

    logger.debug("Finalizing: end of doc.")
    ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip, military_aip)
    collection.extend(ctx.features)

logger.info("%i Features", len(collection))

# Add LonLat conversion to each feature

def geoll(feature):
    name=feature['properties']['name']

    geom = feature['geometry']
    geo_ll=[c2ll(c) for c in geom]
    feature['geometry_ll']=geo_ll

    #print("POSTPROCESSING POLYGON",name)
    sh_geo = Polygon(geo_ll).buffer(0)

    if not sh_geo.is_valid:
        print("INVALID POLYGON",name)
        sys.exit(1)

        if 'RAVLUNDA' in name:
            # this is hard to fix and far away
            sh_geo = sh_geo.convex_hull
        else:
            sh_geo = sh_geo.buffer(0)

        if not sh_geo.is_valid:
            print("ERROR: POLYGON REMAINS INVALID")
            print(sh_geo.is_valid)
            sys.exit(1)

        if hasattr(sh_geo,'exterior'):
            feature['geometry_ll']=list(sh_geo.exterior.coords)
        else:
            logger.error("INVALID OBJECT: %s is not a simple polygon", name )
            #sys.exit(1)
            feature['area']=0
    feature['area']=Polygon(geo_ll).area

for feature in collection:
    geoll(feature)
for feature in accsectors:
    geoll(feature)

# TEST: intersect all polygons to remove overlaps
# dissection = dissect(collection)

# Apply filter by index or name

if len(sys.argv)>1:
    try:
        x = int(sys.argv[1])
        collection = [collection[x]]
    except:
        filt = sys.argv[1]
        collection = [x for x in collection if x.get('properties',{}).get('name') is not None and filt in x.get('properties').get('name','')]


## Sort dataset by size, so that smallest geometries are shown on top:
collection.sort(key=lambda f:f['area'], reverse=True)

# Output file formats
geojson.dumps(logger, "result/luftrom", collection)
openaip.dumps(logger, "result/luftrom", collection)
openair.dumps(logger, "result/luftrom", collection)
xcontest.dumps(logger, "result/xcontest", collection)

# output ACC sectors into a separate file
geojson.dumps(logger, "result/accsectors", accsectors)

print("Completed successfully.")
