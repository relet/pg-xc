"""Test cases for regex patterns based on actual Norwegian AIP data.

These test cases document what each regex pattern matches with real examples
from the Norwegian AIP (Aeronautical Information Publication).
"""

import re
import sys

# Pattern definitions
RE_NE = r'(?P<ne>\(?(?P<n>[\d\.]{5,10})\s?N(?: N)?\s*(?:\s*|-)+(?P<e>[\d\.]+)[E\)]+)'
RE_NE2 = r'(?P<ne2>\(?(?P<n2>\d+)N\s*(?P<e2>\d+)E\)?)'
RE_MONTH = r"(?:JAN|FEB|MAR|APR|MAI|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"


def run_tests():
    """Run all test functions and report results."""
    test_classes = [
        TestNamePatterns,
        TestClassPatterns,
        TestCoordinatePatterns,
        TestVerticalLimitPatterns,
        TestPeriodPatterns,
        TestFrequencyPattern
    ]
    
    total = 0
    passed = 0
    failed = 0
    
    for test_class in test_classes:
        instance = test_class()
        test_methods = [m for m in dir(instance) if m.startswith('test_')]
        
        print(f"\n{test_class.__name__}:")
        for method_name in test_methods:
            total += 1
            try:
                method = getattr(instance, method_name)
                method()
                print(f"  ✓ {method_name}")
                passed += 1
            except AssertionError as e:
                print(f"  ✗ {method_name}: {e}")
                failed += 1
            except Exception as e:
                print(f"  ✗ {method_name}: ERROR: {e}")
                failed += 1
    
    print(f"\n{'='*70}")
    print(f"Total: {total}, Passed: {passed}, Failed: {failed}")
    return failed == 0


class TestNamePatterns:
    """Test airspace name pattern matching."""
    
    def test_re_name_standard_airspaces(self):
        """Standard airspace type designators: TMA, CTA, CTR, TIA, etc."""
        pattern = re.compile(r"^\s*(?P<name>[^\s]* ((Centre|West|North|South|East| Norway) )?(TRIDENT|ADS|HTZ|AOR|RMZ|ATZ|FAB|TMA|TIA|TIA/RMZ|CTA|CTR|CTR,|TIZ|FIR|OCEANIC FIR|CTR/TIZ|TIZ/RMZ|RMZ/TMZ)( (West|Centre|[a-z]))?|[^\s]*( ACC sector| ACC Oslo|ESTRA|EUCBA|RPAS).*)( cont.)?\s*($|\s{5}|.*FIR)")
        
        # Terminal Maneuvering Area
        assert pattern.search("Polaris CTA")
        assert pattern.search("Finnmark TIA")
        
        # Control Zone
        assert pattern.search("Oslo CTR")
        
        # With directional qualifier
        assert pattern.search("Bergen TMA West")
        
        # ACC sectors
        assert pattern.search("Norway ACC sector 1")
        
    def test_re_name2_danger_restricted_areas(self):
        """Norwegian/Swedish danger and restricted areas (EN D/R, ES D/R)."""
        pattern = re.compile(r"^\s*(?P<name>E[NS] [RD].*)\s*$")
        
        # Norwegian danger area
        assert pattern.search("EN D478 R og B 3")
        
        # Norwegian restricted area
        assert pattern.search("EN R123")
        
    def test_re_name3_compact_danger_format(self):
        """Compact danger area format without space (END123)."""
        pattern = re.compile(r"^\s*(?P<name>E[NS]D\d.*)\s*$")
        
        # Military danger zones
        assert pattern.search("END542Z E2Z")
        assert pattern.search("END539 D8")
        assert pattern.search("END705Z A15Z")
    
    def test_re_name4_norwegian_format(self):
        """Norwegian 'Navn og utstrekning' (Name and extent) format."""
        pattern = re.compile(r"Navn og utstrekning /\s+(?P<name>.*)$")
        
        assert pattern.search("Navn og utstrekning / Hareid Luftsportområde")


class TestClassPatterns:
    """Test airspace class pattern matching."""
    
    def test_re_class_explicit(self):
        """Explicit 'Class:' or 'Class' followed by letter."""
        pattern = re.compile(r"Class:? (?P<class>.)")
        
        assert pattern.search("Class: C")
        assert pattern.search("Class D")
        match = pattern.search("Class: G")
        assert match.group('class') == 'G'
    
    def test_re_class2_standalone(self):
        """Standalone class letter on its own line."""
        pattern = re.compile(r"^(?P<class>[CDG])$")
        
        assert pattern.search("C")
        assert pattern.search("D")
        assert pattern.search("G")


class TestCoordinatePatterns:
    """Test coordinate and geometry pattern matching."""
    
    def test_re_coord_circle(self):
        """Circle definitions with radius and center point."""
        pattern = re.compile(r"(?:" + RE_NE + r" - )?(?:\d\. )?(?:A circle(?: with|,)? r|R)adius (?:(?P<rad>[\d\.,]+) NM|(?P<rad_m>[\d]+) m)(?: \([\d\.,]+ k?m\))?(?: cente?red on (?P<cn>\d+)N\s+(?P<ce>\d+)E)?")
        
        # Circle with NM radius
        match = pattern.search("Radius 5 NM centered on 600000N 0100000E")
        assert match
        assert match.group('rad') == '5'
        assert match.group('cn') == '600000'
        
        # With "A circle" prefix
        assert pattern.search("A circle with radius 10 NM centred on 590000N 0110000E")
        
        # Typo variant "centerd" vs "centred" (both work due to 'e?')
        assert pattern.search("Radius 3 NM centred on 600000N 0100000E")
        assert pattern.search("Radius 3 NM centered on 600000N 0100000E")
    
    def test_re_arc_clockwise(self):
        """Arc definitions along circle segments."""
        pattern = re.compile(r'(?P<dir>(counter)?clockwise) along an arc (?:of (?P<rad1>[\d\.,]+) NM radius )?centred on '+RE_NE+r'(?:( and)?( with)?( radius) (?P<rad2>[ \d\.,]+) NM(?: \([\d\.]+ k?m\))?)? (?:- )'+RE_NE2)
        
        # Basic arc with radius
        text = "clockwise along an arc of 5 NM radius centred on 600000N 0100000E - 610000N 0110000E"
        match = pattern.search(text)
        assert match
        assert match.group('dir') == 'clockwise'
        assert match.group('rad1') == '5'
        
        # Counterclockwise variant
        assert pattern.search("counterclockwise along an arc centred on 600000N 0100000E - 610000N 0110000E")


class TestVerticalLimitPatterns:
    """Test vertical limit (altitude) pattern matching."""
    
    def test_re_vertl_upper(self):
        """Upper limit: FL xxx or xxxx FT AMSL."""
        pattern = re.compile(r"Upper limit:\s+(FL\s+(?P<flto>\d+)|(?P<ftamsl>\d+)\s+FT\s+(AMSL)?)")
        
        # Flight level
        match = pattern.search("Upper limit: FL 660")
        assert match
        assert match.group('flto') == '660'
        
        # Feet AMSL
        match = pattern.search("Upper limit: 5000 FT AMSL")
        assert match
        assert match.group('ftamsl') == '5000'
    
    def test_re_vertl_lower_typo_workaround(self):
        """Lower limit - matches 'ower' to catch both 'Lower' and 'lower' case-insensitively."""
        pattern = re.compile(r"ower limit:\s+(FL\s+(?P<flfrom>\d+)|(?P<ftamsl>\d+)\s+FT\s+(AMSL|SFC)|(?P<msl>MSL))")
        
        # Uppercase 'Lower limit'
        assert pattern.search("Lower limit: FL 100")
        
        # Lowercase 'lower limit'
        assert pattern.search("lower limit: FL 100")
        
        # MSL (mean sea level)
        match = pattern.search("Lower limit: MSL")
        assert match
        assert match.group('msl') == 'MSL'
        
        # SFC (surface)
        assert pattern.search("Lower limit: 0 FT SFC")
    
    def test_re_vertl_range_format(self):
        """Range format: GND to 4500 FT AMSL or 1000 - 5000."""
        pattern = re.compile(r"(?P<from>GND|\d{3,6}) (?:(?:til/)?to|-) (?P<to>UNL|\d{3,6})( [Ff][Tt] AMSL)?")
        
        # Ground to feet
        match = pattern.search("GND to 4500 Ft AMSL")
        assert match
        assert match.group('from') == 'GND'
        assert match.group('to') == '4500'
        
        # Feet to unlimited
        match = pattern.search("1000 - UNL")
        assert match
        assert match.group('to') == 'UNL'
        
        # Norwegian "til" variant
        assert pattern.search("GND til/to 5000 FT AMSL")
    
    def test_re_vertl2_special_cases(self):
        """Flexible format matching GND, UNL, FT, FL, and 'See RMK' special case."""
        pattern = re.compile(r"((?P<ftamsl>\d+)\s?[Ff][Tt] (A?MSL|GND))|(?P<gnd>GND)|(?P<unl>UNL)|(FL\s?(?P<fl>\d+))|(?P<rmk>See (remark|RMK))")
        
        # Ground
        assert pattern.search("GND")
        
        # Unlimited
        assert pattern.search("UNL")
        
        # Flight level (compact)
        match = pattern.search("FL145")
        assert match
        assert match.group('fl') == '145'
        
        # See RMK special case (placeholder for controlled airspace lower limit)
        match = pattern.search("See RMK")
        assert match
        assert match.group('rmk')
        
        match = pattern.search("See remark")
        assert match
        assert match.group('rmk')


class TestPeriodPatterns:
    """Test temporary airspace period pattern matching."""
    
    def test_re_period_active_from(self):
        """Active from date and time."""
        pattern = re.compile(r"Active from (?P<pfrom>\d+ "+RE_MONTH+r") (?P<ptimefrom>\d+)")
        
        match = pattern.search("Active from 15 MAI 1200")
        assert match
        assert match.group('pfrom') == '15 MAI'
        assert match.group('ptimefrom') == '1200'
    
    def test_re_period3_established_range(self):
        """Established for date range."""
        pattern = re.compile(r"Established for (?P<pfrom>\d+ "+RE_MONTH+r") - (?P<pto>\d+ "+RE_MONTH+")")
        
        match = pattern.search("Established for 1 JUN - 31 AUG")
        assert match
        assert match.group('pfrom') == '1 JUN'
        assert match.group('pto') == '31 AUG'


class TestFrequencyPattern:
    """Test radio frequency pattern matching."""
    
    def test_re_freq(self):
        """Radio frequency in MHz format."""
        pattern = re.compile(r'(?P<freq>\d+\.\d+ MHZ)')
        
        match = pattern.search("Contact on 121.5 MHZ")
        assert match
        assert match.group('freq') == '121.5 MHZ'
        
        match = pattern.search("Frequency: 119.25 MHZ")
        assert match


if __name__ == '__main__':
    # Run tests
    success = run_tests()
    sys.exit(0 if success else 1)
