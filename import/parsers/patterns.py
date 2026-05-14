"""Regex patterns for parsing Norwegian and Swedish AIP documents.

All patterns use re.VERBOSE (free-spacing mode) with inline comments explaining
each part. Literal spaces are written as ``\\ `` (escaped space) since unescaped
whitespace is ignored in verbose mode.

Building-block constants (RE_NE, RE_NE2, RE_CIRCLE, RE_SECTOR, RE_MONTH) are
plain strings used for documentation/reference. The compiled patterns expand
these inline so every compiled regex is self-contained and readable.

Coordinate notation:
  - DMS full format: ``DDMMSSn DDDMMSSe``  e.g. ``595500N 0104400E``
  - DMS short format: ``DDDn DDDe``        e.g. ``600N 0100E``
"""

import re


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

    # === Coordinate-component building blocks (plain strings, not compiled) ===
    # These are kept as reference constants. The compiled patterns below expand
    # them inline so verbose comments can cover every sub-expression.

    # Full DMS coordinate:  DDMMSSn  DDDMMSSe  (n 5-10 digits, e variable)
    RE_NE = r'(?P<ne>\(?(?P<n>[\d\.]{5,10})\s?N(?: N)?\s*(?:\s*|-)+(?P<e>[\d\.]+)[E\)]+)'

    # Short coordinate:  DDDn  DDDe  (plain digit groups, no seconds)
    RE_NE2 = r'(?P<ne2>\(?(?P<n2>\d+)N\s*(?P<e2>\d+)E\)?)'

    # ENR-2.2 circle definition
    RE_CIRCLE = r'A circle(?: with|,) radius (?P<rad>[\d\.]+) NM cente?red on (?P<cn>\d+)N\s+(?P<ce>\d+)E'

    # Sector definition (optionally preceded by a coordinate)
    RE_SECTOR = (
        r'(' + RE_NE + r' - )?'
        r'((\d\. )?A s|S)ector (?P<secfrom>\d+)° - (?P<secto>\d+)° \(T\), radius '
        r'((?P<radfrom>[\d\.,]+) - )?(?P<rad>[\d\.,]+) NM'
    )

    # Month abbreviations used in period patterns
    RE_MONTH = r"(?:JAN|FEB|MAR|APR|MAI|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"

    # === Name Patterns ===

    # Standard airspace names with type designators.
    # Matches two alternatives inside (?P<name>...):
    #   1. Designator + optional direction qualifier + type keyword + optional suffix
    #   2. Designator + ACC/special keyword + rest of name
    re_name = re.compile(r"""
        ^\s*                                # Optional leading whitespace
        (?P<name>
            [^\s]*\                         # Airspace designator (non-whitespace chars) + space
            (?:                             # Optional direction/region qualifier
                (?:Centre|West|North|South|East|\ Norway)  # Direction or " Norway" (note leading space)
                \                           # Space after qualifier
            )?
            (?:                             # Airspace type designator
                TRIDENT|ADS|HTZ|AOR|RMZ|ATZ|FAB|TMA|TIA|TIA/RMZ|CTA|CTR|CTR,|TIZ|FIR
                |OCEANIC\ FIR|CTR/TIZ|TIZ/RMZ|RMZ/TMZ
            )
            (?:\ (?:West|Centre|[a-z]))?    # Optional sub-area suffix (sector letter or word)
            |                               # -- OR second alternative --
            [^\s]*                          # Special designator (no spaces)
            (?:\ ACC\ sector|\ ACC\ Oslo|ESTRA|EUCBA|RPAS)  # Special designation type
            .*                              # Rest of the airspace name
        )
        (?:\ cont\.)?                       # Optional continuation marker ("cont.")
        \s*                                 # Optional trailing whitespace
        (?:$|\s{5}|.*FIR)                   # End: EOL, 5+ spaces (wide gap), or trailing FIR reference
    """, re.VERBOSE)

    # Norwegian Restricted and Danger area designations.
    # Handles both the old AIP format ("EN R102 Oslo Sentrum", space between country
    # code and type letter) and the new AIRAC 153+ format ("ENR102      Oslo Sentrum",
    # no space, extra whitespace between designation and human-readable name).
    # Whitespace in the captured name is normalized in process_name().
    re_name2 = re.compile(r"""
        ^\s*                    # Optional leading whitespace
        (?P<name>
            EN                  # Country code: Norway only
            \s?                 # Optional space (old: "EN R102", new: "ENR102")
            [RD]                # Area type: R=Restricted, D=Danger
            .*                  # Designation number, optional suffix, and human-readable name
        )
        \s*$                    # Optional trailing whitespace
    """, re.VERBOSE)

    # Norwegian Danger area with END prefix (e.g. "END476")
    re_name3 = re.compile(r"""
        ^\s*(?P<name>END\d.*)\s*$   # "END" + digit + rest of name
    """, re.VERBOSE)

    # Norwegian-language AIP section header ("Navn og utstrekning" = Name and extent)
    re_name4 = re.compile(r"""
        Navn\ og\ utstrekning\ /\s+  # Norwegian AIP section header
        (?P<name>.*)$                # Airspace name
    """, re.VERBOSE)

    # ACC sector name starting with "Sector"
    re_name5 = re.compile(r"""
        ^(?P<name>Sector\ .*)$   # Sector name (e.g. "Sector North")
    """, re.VERBOSE)

    # Norway ACC sector name
    re_name6 = re.compile(r"""
        ^(?P<name>Norway\ ACC\ .*)$  # Norway ACC sector (e.g. "Norway ACC sector 1")
    """, re.VERBOSE)

    # Controlled region format: "Area Name: (EN CTR) rest-of-name"
    re_name_cr = re.compile(r"""
        ^Area\ Name:\ \(         # Controlled region format header
        (?P<name>EN\ .*)         # Airspace name (EN prefix = Norway)
        \)\ (?P<name_cont>.*)$   # Continuation of name after closing paren
    """, re.VERBOSE)

    # Miscellaneous airspace names (currently only Hareid Luftsport)
    re_miscnames = re.compile(r"""
        ^(?P<name>Hareid\ .*)$   # Hareid Luftsport airsport area
    """, re.VERBOSE)

    # OpenAir format airspace name line: "AN <name>"
    re_name_openair = re.compile(r"""
        ^AN\ (?P<name>.*)$   # OpenAir "AN" (Airspace Name) record
    """, re.VERBOSE)

    # AD-2 aerodrome table format: row 1 contains the CTR/TMA/TIZ name
    re_name_ad2 = re.compile(r"""
        ^1\s+                               # Row number "1" with following whitespace
        Designation\ and\ lateral\ limits   # Column header text
        \s+(?P<name>                        # Whitespace separator before name
            .*\s+(?:CTR|TMA|TIZ)            # Name ending with airspace type designator
        )\s*$                               # Optional trailing whitespace
    """, re.VERBOSE)

    # === Class Patterns ===

    # "Class: X" or "Class X" — airspace class letter
    re_class = re.compile(r"""
        Class:?\ (?P<class>.)   # "Class" optionally followed by colon, then space and class letter
    """, re.VERBOSE)

    # Standalone single class character on its own line
    re_class2 = re.compile(r"""
        ^(?P<class>[CDG])$   # Single airspace class character (C, D, or G)
    """, re.VERBOSE)

    # OpenAir format class line: "AC <class>"
    re_class_openair = re.compile(r"""
        ^AC\ (?P<class>.*)$   # OpenAir "AC" (Airspace Class) record
    """, re.VERBOSE)

    # === Coordinate Patterns ===

    # Circle or radius definition, optionally preceded by a centre-point coordinate.
    # Matches: "A circle radius X NM", "A circle with radius X NM",
    #          "A circle, radius X NM", "Radius X NM", "Radius X m"
    # RE_NE expanded: (?P<ne>\(?(?P<n>[\d\.]{5,10})\s?N(?: N)?\s*(?:\s*|-)+(?P<e>[\d\.]+)[E\)]+)
    re_coord = re.compile(r"""
        (?:                                     # Optional leading centre-point coordinate
            (?P<ne>                             # Named group: full DMS coordinate
                \(?                             # Optional opening paren
                (?P<n>[\d\.]{5,10})             # North: 5-10 digit/dot DMS value (DDMMSSs)
                \s?N                            # Optional whitespace + "N" compass letter
                (?:\ N)?                        # Optional duplicate " N" (typo tolerance)
                \s*                             # Optional whitespace
                (?:\s*|-)+                      # Separator: whitespace or dashes
                (?P<e>[\d\.]+)                  # East: digit/dot DMS value
                [E\)]+                          # "E" compass letter + optional closing paren
            )
            \ -\ )                              # " - " separator after coordinate
        ?                                       # (entire leading coordinate group is optional)
        (?:\d\.\ )?                             # Optional numbered-list prefix (e.g. "1. ")
        (?:A\ circle(?:\ with|,)?\ r|R)adius   # "A circle radius", "A circle, radius", or "Radius"
        \ (?:
            (?P<rad>[\d\.,]+)\ NM               # Radius in nautical miles
            |(?P<rad_m>[\d]+)\ m                # Radius in metres
        )
        (?:\ \([\d\.,]+\ k?m\))?               # Optional metric equivalent "(X km)" or "(X m)"
        (?:\ cente?red\ on                      # Optional centre specification
            \ (?P<cn>\d+)N\s+(?P<ce>\d+)E      # Centre coordinate in short lat/lon format
        )?
    """, re.VERBOSE)

    # Sector definition (bearing range + radius), optionally preceded by a coordinate.
    # Matches: "Sector 270° - 360° (T), radius 5 NM"
    #          "595500N 0104400E - Sector 270° - 360° (T), radius 1 - 5 NM"
    # RE_NE expanded inline; RE_SECTOR expanded inline.
    re_coord2 = re.compile(r"""
        (?:                                     # Optional leading coordinate
            (?P<ne>                             # Full DMS coordinate
                \(?
                (?P<n>[\d\.]{5,10})             # North DMS value
                \s?N(?:\ N)?\s*(?:\s*|-)+       # "N" compass + separator
                (?P<e>[\d\.]+)[E\)]+            # East DMS + "E" and optional paren
            )
            \ -\ )?                             # " - " separator
        (?:(?:\d\.\ )?A\ s|S)ector             # "Sector", "A sector", or "1. A sector"
        \ (?P<secfrom>\d+)°                     # Sector start bearing in degrees
        \ -\ (?P<secto>\d+)°                    # Sector end bearing in degrees
        \ \(T\),\ radius\                       # Magnetic bearing indicator "(T)" then "radius "
        (?:(?P<radfrom>[\d\.,]+)\ -\ )?         # Optional inner radius (annular sector)
        (?P<rad>[\d\.,]+)\ NM                   # Outer radius in nautical miles
    """, re.VERBOSE)

    # All coordinate-line token formats for Norway (scans a line for any coord/keyword).
    # Matches one of: full DMS coordinate, "along" border keyword, arc direction,
    # bare north ordinate, bare east ordinate, or ENR-2.2 circle definition.
    # RE_NE and RE_CIRCLE expanded inline.
    re_coord3 = re.compile(r"""
        (?P<ne>                                 # Full DMS coordinate (DDMMSSn DDDMMSSe)
            \(?                                 # Optional opening paren
            (?P<n>[\d\.]{5,10})                 # North: 5-10 digits/dots
            \s?N                                # Optional whitespace + "N"
            (?:\ N)?                            # Optional duplicate " N" (typo tolerance)
            \s*(?:\s*|-)+                       # Whitespace/dash separator
            (?P<e>[\d\.]+)[E\)]+                # East + "E" and optional closing paren
        )
        |(?P<along>along)                       # Border-following keyword (Norwegian border)
        |(?P<arc>(?:counter)?clockwise)         # Arc direction keyword
        |(?:\d+)N                               # Bare north ordinate (consumed, not captured)
        |(?:\d{4,10})E                          # Bare east ordinate (consumed, not captured)
        |A\ circle(?:\ with|,)\ radius          # ENR-2.2 circle definition start
            \ (?P<rad>[\d\.]+)\ NM              # Circle radius in nautical miles
            \ cente?red\ on                     # Centre specification keyword
            \ (?P<cn>\d+)N\s+(?P<ce>\d+)E      # Centre coordinate in short lat/lon format
    """, re.VERBOSE)

    # Arc segment along a circle.
    # Matches: "clockwise along an arc of 16.2 NM radius centred on 550404N 0144448E - 601000N 0101800E"
    #          "counterclockwise along an arc centred on 600000N 0100000E - 610000N 0110000E"
    # RE_NE and RE_NE2 expanded inline.
    re_arc = re.compile(r"""
        (?P<dir>(?:counter)?clockwise)          # Arc direction: "clockwise" or "counterclockwise"
        \ along\ an\ arc\                       # Literal phrase
        (?:of\ (?P<rad1>[\d\.,]+)\ NM\ radius\ )?  # Optional arc radius "of X NM radius "
        centred\ on\                            # Centre keyword phrase
        (?P<ne>                                 # Centre coordinate (RE_NE: DDMMSSn DDDMMSSe)
            \(?                                 # Optional opening paren
            (?P<n>[\d\.]{5,10})                 # North: 5-10 digit/dot DMS
            \s?N                                # Optional whitespace + "N"
            (?:\ N)?                            # Optional duplicate " N" (typo tolerance)
            \s*(?:\s*|-)+                       # Whitespace/dash separator
            (?P<e>[\d\.]+)[E\)]+                # East + "E" and optional closing paren
        )
        (?:                                     # Optional alternative radius specification
            (?:\ and)?                          # Optional "and" connector
            (?:\ with)?                         # Optional "with" preposition
            \ radius                            # Keyword "radius"
            \ (?P<rad2>[ \d\.,]+)\ NM           # Radius value (character class includes space)
            (?:\ \([\d\.]+\ k?m\))?             # Optional metric equivalent "(X km)"
        )?
        \ (?:-\ )                               # Separator " - " before arc endpoint
        (?P<ne2>                                # Arc endpoint coordinate (RE_NE2 short format)
            \(?                                 # Optional opening paren
            (?P<n2>\d+)N                        # North in short format (degrees+minutes)
            \s*(?P<e2>\d+)E                     # East in short format
            \)?                                 # Optional closing paren
        )
    """, re.VERBOSE)

    # === Vertical Limit Patterns ===

    # "Upper limit: FL 660"  or  "Upper limit: 3000 FT AMSL"
    re_vertl_upper = re.compile(r"""
        Upper\ limit:\s+                        # Label with optional whitespace
        (?:
            FL\s+(?P<flto>\d+)                  # Flight level (e.g. "FL 660")
            |(?P<ftamsl>\d+)\s+FT\s+(?:AMSL)?  # Feet AMSL (e.g. "3000 FT AMSL")
        )
    """, re.VERBOSE)

    # "Lower limit: FL 105"  or  "lower limit: 500 FT SFC"  or  "Lower limit: MSL"
    # Intentionally starts with "ower" (not "Lower") to match both "Lower" and "lower".
    re_vertl_lower = re.compile(r"""
        ower\ limit:\s+                         # "ower limit:" matches "Lower" or "lower"
        (?:
            FL\s+(?P<flfrom>\d+)                # Flight level (e.g. "FL 105")
            |(?P<ftamsl>\d+)\s+FT\s+(?:AMSL|SFC)  # Feet AMSL or SFC (e.g. "500 FT AMSL")
            |(?P<msl>MSL)                       # Mean sea level
        )
    """, re.VERBOSE)

    # Range format: "GND to UNL", "0 to 2000 FT AMSL", "3500 - 5500 FT AMSL"
    re_vertl = re.compile(r"""
        (?P<from>GND|\d{3,6})               # Lower altitude: GND or numeric (feet or FL digits)
        \ (?:(?:til/)?to|-)\ +              # Separator: "to", "til/to", or "-" (with spaces)
        (?P<to>UNL|\d{3,6})                 # Upper altitude: UNL or numeric
        (?:\ [Ff][Tt]\ AMSL)?               # Optional " ft AMSL" or " Ft AMSL" unit suffix
    """, re.VERBOSE)

    # Single altitude value in various formats:
    # "3000 FT AMSL", "500 FT GND", "GND", "UNL", "FL 105", "See remark"
    re_vertl2 = re.compile(r"""
        (?:(?P<ftamsl>\d+)\s?[Ff][Tt]\ (?:A?MSL|GND))  # Feet with unit: AMSL, MSL, or GND
        |(?P<gnd>GND)                                    # Ground level
        |(?P<unl>UNL)                                    # Unlimited altitude
        |(?:FL\s?(?P<fl>\d+))                            # Flight level: "FL 105" or "FL105"
        |(?P<rmk>See\ (?:remark|RMK))                    # Altitude specified in remarks
    """, re.VERBOSE)

    # Military AIP format: feet value without AMSL suffix, at end of string
    re_vertl3 = re.compile(r"""
        (?P<ftamsl>\d+)\ FT$   # Feet value at end of line (no AMSL suffix)
    """, re.VERBOSE)

    # === Period Patterns (temporary/notam-activated airspace) ===

    # "Active from 15 MAR 1230"
    re_period = re.compile(r"""
        Active\ from\                               # Activation keyword phrase
        (?P<pfrom>
            \d+                                     # Day number
            \ (?:JAN|FEB|MAR|APR|MAI|JUN|JUL|AUG|SEP|OCT|NOV|DEC)  # Month abbreviation
        )
        \ (?P<ptimefrom>\d+)                        # Activation time (HHMM)
    """, re.VERBOSE)

    # "15 MAR 1400" — deactivation line (follows the activation line)
    re_period2 = re.compile(r"""
        ^(?P<pto>
            \d+                                     # Day number
            \ (?:JAN|FEB|MAR|APR|MAI|JUN|JUL|AUG|SEP|OCT|NOV|DEC)  # Month abbreviation
        )
        \ (?P<ptimeto>\d+)                          # Deactivation time (HHMM)
    """, re.VERBOSE)

    # "Established for 15 MAR - 20 APR"
    re_period3 = re.compile(r"""
        Established\ for\                           # Date range keyword phrase
        (?P<pfrom>
            \d+                                     # Start day
            \ (?:JAN|FEB|MAR|APR|MAI|JUN|JUL|AUG|SEP|OCT|NOV|DEC)  # Start month
        )
        \ -\ (?P<pto>                               # Dash separator
            \d+                                     # End day
            \ (?:JAN|FEB|MAR|APR|MAI|JUN|JUL|AUG|SEP|OCT|NOV|DEC)  # End month
        )
    """, re.VERBOSE)

    # === Frequency Patterns ===

    # Radio frequency in MHz (e.g. "126.705 MHZ")
    re_freq = re.compile(r"""
        (?P<freq>\d+\.\d+\ MHZ)   # Frequency value with MHz suffix
    """, re.VERBOSE)


# Create global instance for backward compatibility
patterns = RegexPatterns()

# COLUMN PARSING:
# Matches lines that contain N of the standard ENR table column headers.
# The 8 capturing groups correspond to: Name/Identification, Lateral limits,
# Vertical limits, C unit, Freq MHz, Callsign, AFIS unit, Remark.
# Generated for N in [7, 6, 5, 4, 3] so the most specific match wins first.
rexes_header_es_enr = [
    re.compile(r"""
        (?:                                     # Column header group, repeated {mult} times
            (?:
                (Name|Identification)           # Column: airspace name or identifier
                |(Lateral\ limits)              # Column: lateral boundary description
                |(Vertical\ limits)             # Column: altitude limits
                |(C\ unit)                      # Column: control unit
                |(Freq\ MHz)                    # Column: radio frequency
                |(Callsign)                     # Column: ATC callsign
                |(AFIS\ unit)                   # Column: AFIS unit
                |(Remark)                       # Column: remarks
            )
            .*                                  # Remaining content on the line
        ){%i}                                   # Require this many column headers present
    """ % mult, re.VERBOSE)
    for mult in reversed(range(3, 8))
]
