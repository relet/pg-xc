#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from codecs import open
from copy import deepcopy
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
    # All formats in coordinate list (Norway)
    re_coord3_no = re.compile(RE_NE+r"|(?P<along>along)|(?P<arc>(?:counter)?clockwise)|(?:\d+)N|(?:\d{4,10})E|"+RE_CIRCLE)
    # All formats in coordinate list (Sweden)
    re_coord3_se = re.compile(RE_NE+r"|(?P<along>border)|(?P<arc>(?:counter)?clockwise)|(?:\d+)N|(?:\d{4,10})E|"+RE_CIRCLE+r"|(?P<circle>A circle)|(?:radius)")
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
re_coord3_no = patterns.re_coord3_no
re_coord3_se = patterns.re_coord3_se
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
        # Skip sector subdivisions of SÄLEN/SAAB
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
            Class string (e.g., "C", "D", "G")
        """
        return match.groupdict().get('class')


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
        
        # HACK: "See remark" = lower limit of controlled airspace
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
        
        # HACK: Special case for Sälen - matching point in wrong direction
        # FIXME: Don't select closest but next point in correct direction
        if special_case_name and ("Sälen TMA b" in special_case_name or "SÄLEN CTR Sector b" in special_case_name):
            logger.debug("SÄLEN HACK: Reversing border fill direction")
            fill = list(reversed(fill))
        
        ctx.alonging = False
        ctx.lastn, ctx.laste = None, None
        
        logger.debug(f"Filled border with {len(fill)} points")
        return fill


class FeatureBuilder:
    """Builder for airspace feature properties.
    
    Encapsulates property assignment and validation for airspace features.
    Handles altitude conversions, property overwrite warnings, and ensures
    consistency of feature data.
    """
    
    def set_class(self, feature, airspace_class):
        """Set the airspace class property."""
        feature['properties']['class'] = airspace_class
    
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


def finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, aip_sup, tia_aip):
    """Complete and sanity check a feature definition.
    
    Args:
        feature: Feature dict to finalize
        features: List to append completed features to
        obj: Geometry coordinates
        source: Source filename
        aipname: Airspace name
        cta_aip, restrict_aip, aip_sup, tia_aip: Document type flags

    Returns:
        Tuple of (empty_feature, empty_obj) for reset
    """
    global completed
    global country
    global end_notam
    global sanntid

    feature['properties']['source_href']=source
    feature['properties']['country']=country
    feature['geometry'] = obj
    aipname = wstrip(str(aipname))
    if aipname == 'EN D476':
        aipname = 'EN D476 R og B 1'
    if aipname == 'EN D477':
        aipname = 'EN D477 R og B 2'

    if 'ACC' in aipname and country=="ES":
        return {"properties":{}}, []
    for ignore in ['ADS','AOR','FAB',' FIR','HTZ']:
        if ignore in aipname:
            logger.debug("Ignoring: %s", aipname)
            return {"properties":{}}, []
    feature['properties']['name']=aipname
    if cta_aip or aip_sup or tia_aip or 'ACC' in aipname:
        recount = len([f for f in features if aipname in f['properties']['name']])
        recount = recount or len([f for f in accsectors if aipname in f['properties']['name']])
        if recount>0:
            separator = " "
            if re.search(r'\d$', aipname):
                separator="-"
            # special handling Farris TMA skipping counters
            if "Farris" in aipname:
                if recount > 4:
                    recount += 2
                else:
                    recount += 1
            logger.debug("RECOUNT renamed " + aipname + " INTO " + aipname + separator + str(recount+1))
            feature['properties']['name']=aipname + separator + str(recount+1)
    if 'TIZ' in aipname or 'TIA' in aipname:
        feature['properties']['class']='G'
    elif 'CTR' in aipname:
        feature['properties']['class']='D'
    elif 'TRIDENT' in aipname \
        or 'EN D' in aipname or 'END' in aipname \
        or 'ES D' in aipname:
        feature['properties']['class']='Q'
    elif 'EN R' in aipname \
      or 'ES R' in aipname or 'ESTRA' in aipname \
      or 'EUCBA' in aipname or 'RPAS' in aipname:
        feature['properties']['class']='R'
    elif 'TMA' in aipname or 'CTA' in aipname or 'FIR' in aipname \
      or 'ACC' in aipname or 'ATZ' in aipname or 'FAB' in aipname \
      or 'Sector' in aipname:
        feature['properties']['class']='C'
    elif '5.5' in source or "Hareid" in aipname:
        if "Nidaros" in aipname:
            #skip old Nidaros airspace
            return {"properties":{}}, []
        feature['properties']['class']='Luftsport'
    index = len(collection)+len(features)

    if names.get(aipname):
        logger.debug("DUPLICATE NAME: %s", aipname)

    if len(obj)>100:
        logger.debug("COMPLEX POLYGON %s with %i points", feature['properties'].get('name'), len(obj))
        obj=simplify_poly(obj, 100)
        feature['geometry'] = obj

    if len(obj)>3:
        logger.debug("Finalizing polygon #%i %s with %i points.", index, feature['properties'].get('name'), len(obj))

        name   = feature['properties'].get('name')
        source = feature['properties'].get('source_href')
        from_  = feature['properties'].get('from (ft amsl)')
        to_    = feature['properties'].get('to (ft amsl)')
        class_ = feature['properties'].get('class')


        if name in completed:
            logger.info("ERROR Duplicate feature name: #%i %s", index, name)
            return {"properties":{}}, []
            #sys.exit(1)
        else:
            if 'ACC' in aipname:
                logger.debug("Writing ACC sector to separate file: %s", aipname)
                accsectors.append(feature)
            else:
                features.append(feature)

        # SANITY CHECK
        if name is None:
            logger.error("Feature without name: #%i", index)
            sys.exit(1)
        if "None" in name:
            logger.error("Feature without name: #%i", index)
            sys.exit(1)
        completed[name]=True
        if source is None:
            logger.error("Feature without source: #%i", index)
            sys.exit(1)
        if feature['properties'].get('name') is None:
            logger.error("Feature without name: #%i (%s)", index, source)
            sys.exit(1)
        if class_ is None:
            logger.error("Feature without class (boo): #%i (%s)", index, source)
            sys.exit(1)
        # SPECIAL CASE NOTAM reserved ENR in Oslo area
        if "EN R" in aipname and "Kongsvinger" in aipname:
          feature['properties']['notam_only'] = 'true'
        if "EN R" in aipname and ("Romerike" in aipname or ("Oslo" in aipname and not "102" in aipname)):
          feature['properties']['notam_only'] = 'true'
          feature['properties']['from (ft amsl)'] = '0'
          feature['properties']['to (ft amsl)'] = '99999' # unspecified
          feature['properties']['from (m amsl)'] = '0'
          feature['properties']['to (m amsl)'] = '99999'
          from_ = '0'
          to_ = '0'
        if ("EN D" in aipname or "END" in aipname) and (end_notam or sanntid):
          #logger.addFilter(logging.Filter("notam_only"))
          feature['properties']['notam_only'] = 'true'
          if sanntid:
              logger.debug("Classifying %s as AMC/Sanntidsaktivering", aipname)
              feature['properties']['amc_only'] = 'true'
              sanntid = False
        if ("EN D" in aipname or "END" in aipname) and (military_aip or ("Klepp" in aipname)):
          feature['properties']['amc_only'] = 'true'
        if from_ is None:
            if "en_sup_a_2018_015_en" in source:
                feature['properties']['from (ft amsl)']='0'
                feature['properties']['from (m amsl)']='0'
                from_ = '0'
            else:
                logger.error("Feature without lower limit: #%i (%s)", index, source)
                sys.exit(1)
        if to_ is None:
            if "en_sup_a_2018_015_en" in source:
                feature['properties']['to (ft amsl)']='99999'
                feature['properties']['to (m amsl)']='9999'
                to_ = '99999'
            else:
                logger.error("Feature without upper limit: #%i (%s)", index, source)
                sys.exit(1)
        if int(from_) >= int(to_):
            # SPECIAL CASE NOTAM reserved ENR in Oslo area
            if "en_sup_a_2018_015_en" in source or "Romerike" in aipname or "Oslo" in aipname:
                feature['properties']['from (ft amsl)']=to_
                feature['properties']['to (ft amsl)']=from_
            else:
                logger.error("Lower limit %s > upper limit %s: #%i (%s)", from_, to_, index, source)
                sys.exit(1)
    elif len(obj)>0:
        logger.error("ERROR Finalizing incomplete polygon #%i (%i points)", index, len(obj))

    names[aipname]=True
    logger.debug("OK polygon #%i %s with %i points (%s-%s).", index, feature['properties'].get('name'),
                                                                     len(obj),
                                                                     feature['properties'].get('from (ft amsl)'),
                                                                     feature['properties'].get('to (ft amsl)'))
    return {"properties":{}}, []


for filename in os.listdir("./sources/txt"):
    logger.info("Reading %s", "./sources/txt/"+filename)
    source = urllib.parse.unquote(filename.split(".txt")[0])
    if ".swp" in filename:
        logger.warning("Skipping swap file %s", filename)
        continue

    data = open("./sources/txt/"+filename,"r","utf-8").readlines()
    
    ad_aip       = "-AD-" in filename or "_AD_" in filename
    cta_aip      = "ENR-2.1" in filename
    tia_aip      = "ENR-2.2" in filename
    restrict_aip = "ENR-5.1" in filename
    military_aip = "ENR-5.2" in filename
    airsport_aip = "ENR-5.5" in filename
    aip_sup      = "en_sup" in filename
    es_aip_sup   = "aro.lfv.se" in filename and "editorial" in filename
    valldal      = "valldal" in filename

    # TODO: merge the cases
    es_enr_2_1 = "ES_ENR_2_1" in filename
    es_enr_2_2 = "ES_ENR_2_2" in filename
    es_enr_5_1 = "ES_ENR_5_1" in filename
    es_enr_5_2 = "ES_ENR_5_2" in filename
    en_enr_5_1 = "EN_ENR_5_1" in filename

    # Initialize parsing context for this file
    ctx = ParsingContext()
    name_parser = NameParser(patterns)
    class_parser = ClassParser(patterns)
    vertical_parser = VerticalLimitParser(patterns)
    coord_parser = CoordinateParser(patterns)
    border_follower = BorderFollower()
    feature_builder = FeatureBuilder()

    if "EN_" or "en_" or "_en." in filename:
        country = 'EN'  # Keep as global for finalize()
        ctx.country = 'EN'
        ctx.border = borders['norway']
        ctx.re_coord3 = re_coord3_no
    if "ES_" in filename or "aro.lfv.se" in filename:
        country = 'ES'  # Keep as global for finalize()
        ctx.country = 'ES'
        ctx.border = borders['sweden']
        ctx.re_coord3 = re_coord3_se
    logger.debug("Country is %s", ctx.country)

    vcut = 999
    vend = 1000

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
                ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
            return

        # SPECIAL CASE temporary workaround KRAMFORS
        if ctx.aipname and ("KRAMFORS" in ctx.aipname) and ("within" in line):
            return
        # SPECIAL CASE workaround SÄLEN/SAAB CTR ctx.sectors
        if ctx.aipname and (("SÄLEN" in ctx.aipname) or ("SAAB" in ctx.aipname)) and ("Sector" in line):
            logger.debug("TEST: Breaking up SÄLEN/SAAB, ctx.aipname=."+ctx.aipname)
            ctx.sectors.append((ctx.aipname, ctx.obj))
            ctx.feature, ctx.obj =  {"properties":{}}, []
            if "SÄLEN" in ctx.aipname:
                ctx.aipname = "SÄLEN CTR "+line
            else:
                ctx.aipname = "SAAB CTR "+line
        # SPECIAL CASE check for Valldal AIP names
        if valldal and 'Valldal' in line:
            ctx.aipname=" ".join(line.strip().split()[0:2])
            logger.debug("Valldal ctx.aipname: '%s'", ctx.aipname)
            feature_builder.set_class(ctx.feature, 'Luftsport')
            feature_builder.set_vertical_limits(ctx.feature, from_amsl=0, to_amsl=None, warn=False)

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
                    ctx.coords_wrap += line.strip() + " "
                    # FIXME: incomplete circle continuation is broken
                    logger.debug("Continuing line after incomplete circle: %s", ctx.coords_wrap)
                    return
                ctx.lastn, ctx.laste = n, e
                logger.debug("Circle center is %s %s %s %s", coords.get('n'), coords.get('e'), coords.get('cn'), coords.get('ce'))
                logger.debug("COORDS is %s", json.dumps(coords))
                c_gen = gen_circle(n, e, rad)
                logger.debug("LENS %s %s", len(ctx.obj), len(c_gen))
                ctx.obj = merge_poly(ctx.obj, c_gen)
                logger.debug("LENS %s %s", len(ctx.obj), len(c_gen))

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
                c_gen = gen_sector(n, e, secfrom, secto, radfrom, radto)

                ctx.obj = merge_poly(ctx.obj, c_gen)

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
                        arc = gen_circle(n, e, rad, convert=False)
                        to_n = arcdata['n2']
                        to_e = arcdata['e2']
                        cw = arcdata['dir']
                        logger.debug("ARC IS "+cw)
                        fill = fill_along(ctx.obj[-1],(to_n,to_e), arc, (cw=='clockwise'))
                        ctx.lastn, ctx.laste = None, None

                        for apair in fill:
                            bn, be = ll2c(apair)
                            ctx.obj.insert(0,(bn,be))
                        skip_next = 1
                    elif circle:
                        ctx.coords_wrap += line.strip() + " "
                        # FIXME: incomplete circle continuation is broken
                        logger.debug("Continuing line after incomplete circle (3): %s", ctx.coords_wrap)
                        return


                    if ctx.alonging:
                        fill = border_follower.finish_following(ctx, n, e, ctx.aipname)
                        for bpair in fill:
                            bn, be = ll2c(bpair)
                            ctx.obj.insert(0,(bn,be))

                    if rad and cn and ce:
                        c_gen = gen_circle(cn, ce, rad)
                        logger.debug("Merging circle using cn, ce.")
                        ctx.obj = merge_poly(ctx.obj, c_gen)
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
                            ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
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
                    ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
                    ctx.lastv = None
            if fromamsl is not None:
                ctx.lastv = None
                if (((cta_aip or airsport_aip or aip_sup or tia_aip or (ctx.aipname and ("TIZ" in ctx.aipname))) and (ctx.finalcoord or tia_aip_acc)) or ctx.country != 'EN') and not ("Geiteryggen" in ctx.aipname):
                    logger.debug("Finalizing poly: Vertl complete.")
                    if ctx.aipname and (("SÄLEN" in ctx.aipname) or ("SAAB" in ctx.aipname)) and len(ctx.sectors)>0:
                        for x in ctx.sectors[1:]: # skip the first sector, which is the union of the other ctx.sectors in Swedish docs
                            aipname_,  obj_ = x
                            logger.debug("Restoring "+aipname_+" "+str(len(ctx.sectors)))
                            feature_ = deepcopy(ctx.feature)
                            logger.debug("Finalizing SAAB/SÄLEN: " + aipname_)
                            finalize(feature_, ctx.features, obj_, source, aipname_, cta_aip, restrict_aip, aip_sup, tia_aip)
                        ctx.sectors = []
                        logger.debug("Finalizing last poly as ."+ctx.aipname)
                    ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip)

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
                ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
                ctx.lastv = None

            # Process the matched name
            name = name_parser.process_name(name, line, ctx)
            
            # Check if we should skip this name
            if name_parser.should_skip_name(name, ctx):
                return

            if restrict_aip or military_aip:
                if ctx.feature['properties'].get('from (ft amsl)') is not None and (ctx.feature['properties'].get('to (ft amsl)') or "Romerike" in ctx.aipname or "Oslo" in ctx.aipname):
                    logger.debug("RESTRICT/MILITARY + name and vertl complete")
                    ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
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
                ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
                ctx.aipname = wstrip(line)

        if line.strip()=="-+-":
            ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip)

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
                logger.debug("VCUT LINE? %s", line)
                vcuts = [m.start() for m in re.finditer(r'[^\s]', line)]
                vcuts=[(x and (x-2)) for x in vcuts] # HACK around annoying column shift
                logger.debug("vcuts %s", vcuts)
            if "ADS areas" in line:
                skip_tia = True
            if skip_tia:
                continue

        if aip_sup and ("Luftromsklasse" in line) and not ("2025" in filename) or ("obligatoriske meldepunkter" in line):
            logger.debug("Skipping end of SUP")
            break

        if ctx.country == 'ES' and 'Vinschning av sk' in line:
            logger.debug("Skipping end of document")
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
        elif es_enr_2_1 or es_enr_2_2 or es_enr_5_1 or es_enr_5_2:
            if line.strip()=='Vertical limits': # hack around ES_ENR_2_2 malformatting
                headers = 'Vertical'
                header_cont = True
            for rex in rexes_header_es_enr:
                headers = headers or rex.findall(line)
                header_cont = False
        elif es_aip_sup and not vcuts:
            headers = True
        if headers:
            logger.debug("Parsed header line as %s.", headers)
            logger.debug("line=%s.", line)
            vcuts = []
            if es_aip_sup:
               vcuts = [0, 45, 110]
            else:
                for header in headers[0]:
                    if header:
                        vcuts.append(line.index(header))
                vcuts.append(len(line))
            column_parsing = sorted((column_parsing + vcuts))
            logger.debug("DEBUG: column parsing: %s", vcuts)
            continue

        # parse columns separately for table formatted files
        # use header fields to detect the vcut character limit
        if tia_aip_acc and vcuts:
            for i in range(len(vcuts)-1):
                parse(line[vcuts[i]:vcuts[i+1]])
            parse(line[vcuts[len(vcuts)-1]:])
        elif airsport_aip:
            if "Vertical limits" in line:
                vcut = line.index("Vertical limits")
                vend = vcut+28
            else:
                parse(line[:vcut],1)
                parse(line[vcut:vend],2)
        elif restrict_aip or military_aip:
            if "Vertikale grenser" in line:
                vcut = line.index("Vertikale grenser")
                vend = vcut+16
                if "Aktiviseringstid" in line:
                    vend = line.index("Aktiviseringstid")
            else:
                parse(line[:vcut],1)
                if military_aip:
                    parse(line[vcut:vend],2)
                else:
                    parse(line[vcut:],2)
        elif cta_aip:
            if "Tjenesteenhet" in line:
                vcut = line.index("Tjenesteenhet")
            else:
                parse(line[:vcut],1)
        elif tia_aip and not tia_aip_acc:
            if "Unit providing" in line:
                vcut = line.index("Unit providing")
            else:
                parse(line[:vcut],1)
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
    ctx.feature, ctx.obj = finalize(ctx.feature, ctx.features, ctx.obj, source, ctx.aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
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
