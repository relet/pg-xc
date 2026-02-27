#!/usr/bin/env python3
"""Extract examples of regex matches from source AIP data.

Runs through all source files and collects unique examples of what each
regex pattern matches. Useful for documentation and creating test cases.
"""

import re
import os
from collections import defaultdict

# Define patterns directly (copied from parse.py RegexPatterns class)
RE_NE = r'(?P<ne>\(?(?P<n>[\d\.]{5,10})\s?N(?: N)?\s*(?:\s*|-)+(?P<e>[\d\.]+)[E\)]+)'
RE_NE2 = r'(?P<ne2>\(?(?P<n2>\d+)N\s*(?P<e2>\d+)E\)?)'
RE_CIRCLE = r'A circle(?: with|,) radius (?P<rad>[\d\.]+) NM cente?red on (?P<cn>\d+)N\s+(?P<ce>\d+)E'
RE_SECTOR = u'('+RE_NE + r' - )?((\d\. )?A s|S)ector (?P<secfrom>\d+)° - (?P<secto>\d+)° \(T\), radius ((?P<radfrom>[\d\.,]+) - )?(?P<rad>[\d\.,]+) NM'
RE_MONTH = r"(?:JAN|FEB|MAR|APR|MAI|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"

class RegexPatterns:
    """Regex patterns for parsing Norwegian AIP documents."""
    
    re_name = re.compile(r"^\s*(?P<name>[^\s]* ((Centre|West|North|South|East| Norway) )?(TRIDENT|ADS|HTZ|AOR|RMZ|ATZ|FAB|TMA|TIA|TIA/RMZ|CTA|CTR|CTR,|TIZ|FIR|OCEANIC FIR|CTR/TIZ|TIZ/RMZ|RMZ/TMZ)( (West|Centre|[a-z]))?|[^\s]*( ACC sector| ACC Oslo|ESTRA|EUCBA|RPAS).*)( cont.)?\s*($|\s{5}|.*FIR)")
    re_name2 = re.compile(r"^\s*(?P<name>E[NS] [RD].*)\s*$")
    re_name3 = re.compile(r"^\s*(?P<name>E[NS]D\d.*)\s*$")
    re_name4 = re.compile(r"Navn og utstrekning /\s+(?P<name>.*)$")
    re_name5 = re.compile(r"^(?P<name>Sector .*)$")
    re_name6 = re.compile(r"^(?P<name>Norway ACC .*)$")
    re_name_cr = re.compile(r"^Area Name: \((?P<name>EN .*)\) (?P<name_cont>.*)$")
    re_miscnames = re.compile(r"^(?P<name>Hareid .*)$")
    re_class = re.compile(r"Class:? (?P<class>.)")
    re_class2 = re.compile(r"^(?P<class>[CDG])$")
    re_coord = re.compile(r"(?:" + RE_NE + r" - )?(?:\d\. )?(?:A circle(?: with|,)? r|R)adius (?:(?P<rad>[\d\.,]+) NM|(?P<rad_m>[\d]+) m)(?: \([\d\.,]+ k?m\))?(?: cente?red on (?P<cn>\d+)N\s+(?P<ce>\d+)E)?")
    re_coord2 = re.compile(RE_SECTOR)
    re_arc = re.compile(r'(?P<dir>(counter)?clockwise) along an arc (?:of (?P<rad1>[\d\.,]+) NM radius )?centred on '+RE_NE+r'(?:( and)?( with)?( radius) (?P<rad2>[ \d\.,]+) NM(?: \([\d\.]+ k?m\))?)? (?:- )'+RE_NE2)
    re_vertl_upper = re.compile(r"Upper limit:\s+(FL\s+(?P<flto>\d+)|(?P<ftamsl>\d+)\s+FT\s+(AMSL)?)")
    re_vertl_lower = re.compile(r"ower limit:\s+(FL\s+(?P<flfrom>\d+)|(?P<ftamsl>\d+)\s+FT\s+(AMSL|SFC)|(?P<msl>MSL))")
    re_vertl = re.compile(r"(?P<from>GND|\d{3,6}) (?:(?:til/)?to|-) (?P<to>UNL|\d{3,6})( [Ff][Tt] AMSL)?")
    re_vertl2 = re.compile(r"((?P<ftamsl>\d+)\s?[Ff][Tt] (A?MSL|GND))|(?P<gnd>GND)|(?P<unl>UNL)|(FL\s?(?P<fl>\d+))|(?P<rmk>See (remark|RMK))")
    re_period = re.compile(r"Active from (?P<pfrom>\d+ "+RE_MONTH+r") (?P<ptimefrom>\d+)")
    re_period3 = re.compile(r"Established for (?P<pfrom>\d+ "+RE_MONTH+r") - (?P<pto>\d+ "+RE_MONTH+")")
    re_freq = re.compile(r'(?P<freq>\d+\.\d+ MHZ)')

def extract_examples(source_dir="./sources/txt", max_examples=5):
    """Extract examples of regex matches from source files.
    
    Args:
        source_dir: Directory containing source text files
        max_examples: Maximum number of unique examples per pattern
        
    Returns:
        Dict mapping pattern names to lists of matched examples
    """
    patterns = RegexPatterns()
    examples = defaultdict(set)
    
    # Define patterns to test
    test_patterns = {
        # Names
        're_name': patterns.re_name,
        're_name2': patterns.re_name2,
        're_name3': patterns.re_name3,
        're_name4': patterns.re_name4,
        're_name_cr': patterns.re_name_cr,
        're_miscnames': patterns.re_miscnames,
        
        # Classes
        're_class': patterns.re_class,
        're_class2': patterns.re_class2,
        
        # Coordinates
        're_coord': patterns.re_coord,
        're_coord2': patterns.re_coord2,
        're_arc': patterns.re_arc,
        
        # Vertical limits
        're_vertl_upper': patterns.re_vertl_upper,
        're_vertl_lower': patterns.re_vertl_lower,
        're_vertl': patterns.re_vertl,
        're_vertl2': patterns.re_vertl2,
        
        # Periods
        're_period': patterns.re_period,
        're_period3': patterns.re_period3,
        
        # Frequency
        're_freq': patterns.re_freq,
    }
    
    if not os.path.exists(source_dir):
        print(f"Source directory {source_dir} not found")
        return examples
    
    # Process all source files
    for filename in os.listdir(source_dir):
        if not filename.endswith('.txt') or '.swp' in filename:
            continue
        
        filepath = os.path.join(source_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Test each pattern
                    for pattern_name, pattern in test_patterns.items():
                        match = pattern.search(line)
                        if match:
                            # Store the matched portion or full line if short
                            matched_text = match.group(0) if len(match.group(0)) < 120 else line[:120] + "..."
                            if len(examples[pattern_name]) < max_examples:
                                examples[pattern_name].add(matched_text)
        except Exception as e:
            print(f"Error processing {filename}: {e}")
    
    return examples

def print_examples(examples):
    """Print examples in a readable format."""
    for pattern_name in sorted(examples.keys()):
        pattern_examples = sorted(examples[pattern_name])
        if pattern_examples:
            print(f"\n{'='*70}")
            print(f"{pattern_name}:")
            print('='*70)
            for i, example in enumerate(pattern_examples, 1):
                print(f"  {i}. {example}")

if __name__ == '__main__':
    print("Extracting regex pattern examples from source files...")
    print("This may take a minute...")
    
    examples = extract_examples(max_examples=10)
    print_examples(examples)
    
    print(f"\n\nTotal patterns with matches: {len(examples)}")
    print("Total examples collected:", sum(len(v) for v in examples.values()))
