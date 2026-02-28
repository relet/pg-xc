#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NOTAM Parser for Norwegian Airspace

Fetches and parses NOTAMs from notaminfo.com that ESTABLISH new airspace.
Extracts geometry, designation, altitude bounds, and validity periods.
"""

import re
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    HAS_REQUESTS = False

logger = logging.getLogger(__name__)


class NotamParser:
    """Parse NOTAMs that establish new airspace."""
    
    NOTAM_URL = "https://notaminfo.com/latest?country=Norway"
    NOTAM_TXT_FILE = "sources/txt/notam.txt"
    
    # Regex patterns for text-based NOTAM parsing
    RE_NOTAM_ID = re.compile(r'^([AE]\d{4}/\d{2})$')
    RE_DATE_FROM = re.compile(r'FROM:\s+(\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2})')
    RE_DATE_TO = re.compile(r'TO:\s+(PERM|\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}(?:\s+EST)?)')
    RE_ESTABLISH = re.compile(r'(RESTRICTED AREA|DANGER AREA|TEMPO RESTRICTED AREA|TEMP RESTRICTED AREA)\s+(?:ESTABLISHED\s+[\'"]?([A-Z]{2,6}\s*[RD]?\d+[A-Z]?)|([A-Z]{2,6}\s*[RD]?\d+[A-Z]?)\s+.*?\s+ESTABLISHED)', re.IGNORECASE)
    RE_AREA_NAME = re.compile(r'[\'"]([^\'\"]+)[\'"]')
    RE_COORDINATES = re.compile(r'(\d{6}N\s+\d{7}E)')
    RE_LOWER = re.compile(r'^LOWER:\s*(GND|SFC|\d+FT\s+(?:AMSL|AGL)|FL\d+)', re.IGNORECASE)
    RE_UPPER = re.compile(r'^UPPER:\s*(\d+FT\s+(?:AMSL|AGL)|FL\d+)', re.IGNORECASE)
    RE_SCHEDULE = re.compile(r'^SCHEDULE:\s+(.+)$')
    RE_PSN = re.compile(r'PSN\s+([\d\sNE\-\(\)]+?)(?:\.|MAX HGT|LOWER:|UPPER:|SCHEDULE:|ALL FLYING|CTC|$)', re.DOTALL)
    
    @staticmethod
    def fetch_notams() -> str:
        """
        Load NOTAM text file from cache.
        
        Returns text content of NOTAM file.
        """
        import os
        
        # Load from text cache
        cache_path = NotamParser.NOTAM_TXT_FILE
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                logger.info(f"Loaded NOTAMs from {cache_path} ({len(text)} bytes)")
                return text
            except Exception as e:
                logger.error(f"Failed to read {cache_path}: {e}")
                return ""
        else:
            logger.warning(f"NOTAM cache not found: {cache_path}. Run sources/sources.sh first.")
            return ""
    
    @staticmethod
    def parse_altitude(alt_str: str) -> Tuple[int, str]:
        """
        Parse altitude string to meters AMSL.
        
        Args:
            alt_str: Altitude string like "GND", "1500FT AMSL", "FL130"
            
        Returns:
            Tuple of (altitude_meters, original_string)
        """
        alt_str = alt_str.strip().upper()
        
        if alt_str in ('GND', 'SFC'):
            return (0, alt_str)
        
        # Flight level (FL130 = 13000 feet)
        fl_match = re.match(r'FL(\d+)', alt_str)
        if fl_match:
            feet = int(fl_match.group(1)) * 100
            return (int(feet * 0.3048), alt_str)
        
        # Feet AMSL/AGL
        ft_match = re.match(r'(\d+)\s*FT\s+(AMSL|AGL)', alt_str)
        if ft_match:
            feet = int(ft_match.group(1))
            # For AGL, we'd need terrain elevation - for now treat as AMSL
            # This is safe for paragliding as AGL is more restrictive
            return (int(feet * 0.3048), alt_str)
        
        logger.warning(f"Could not parse altitude: {alt_str}")
        return (0, alt_str)
    
    @staticmethod
    def parse_coordinates(coord_str: str) -> List[Tuple[str, str]]:
        """
        Parse coordinate string to list of (lat_dms, lon_dms) tuples.
        
        Args:
            coord_str: String containing coordinates like "594106N 0103158E - 594109N 0103219E"
            
        Returns:
            List of (lat, lon) tuples in DMS format (without N/E suffixes)
        """
        coords = []
        # Find all coordinate pairs
        matches = NotamParser.RE_COORDINATES.findall(coord_str)
        
        for match in matches:
            # Split into lat/lon: "594106N 0103158E"
            parts = match.split()
            if len(parts) == 2:
                lat = parts[0].strip().rstrip('N')  # Remove N suffix
                lon = parts[1].strip().rstrip('E')  # Remove E suffix
                coords.append((lat, lon))
        
        return coords
    
    @staticmethod
    def parse_date(date_str: str) -> Optional[str]:
        """
        Parse NOTAM date format to ISO 8601.
        
        Args:
            date_str: Date like "26/02/12 12:19" or "PERM"
            
        Returns:
            ISO 8601 date string or None
        """
        if date_str.strip().upper() == 'PERM':
            return 'PERM'
        
        # Remove "EST" suffix
        date_str = date_str.replace(' EST', '').strip()
        
        try:
            # Format: YY/MM/DD HH:MM
            dt = datetime.strptime(date_str, '%y/%m/%d %H:%M')
            return dt.strftime('%Y-%m-%d %H:%M')
        except ValueError:
            logger.warning(f"Could not parse date: {date_str}")
            return None
    
    @staticmethod
    def extract_notam_blocks(text: str) -> List[Dict]:
        """
        Extract individual NOTAM blocks from text.
        
        Args:
            text: Full text file content
            
        Returns:
            List of dictionaries with NOTAM data
        """
        notams = []
        lines = text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Look for NOTAM ID (e.g., "A8297/25")
            id_match = NotamParser.RE_NOTAM_ID.match(line)
            if not id_match:
                i += 1
                continue
            
            notam_id = id_match.group(1)
            
            # Collect the next ~20 lines as the NOTAM block
            block_lines = [line]
            j = i + 1
            while j < len(lines) and j < i + 25:
                block_lines.append(lines[j])
                # Stop at next NOTAM ID
                if j > i + 1 and NotamParser.RE_NOTAM_ID.match(lines[j].strip()):
                    break
                j += 1
            
            block = '\n'.join(block_lines)
            
            # Check if this NOTAM establishes new airspace
            establish_match = NotamParser.RE_ESTABLISH.search(block)
            if not establish_match:
                i = j
                continue
            
            area_type = establish_match.group(1)
            # Handle two formats: "ESTABLISHED 'ENR138...'" or "ENR123 NAME ESTABLISHED"
            if establish_match.group(2):
                # Format 1: ESTABLISHED 'ENR138 LOMMEDALEN'
                area_designation = establish_match.group(2).strip()
                area_name = ""
                # Extract name from quotes if present
                name_match = NotamParser.RE_AREA_NAME.search(block)
                if name_match:
                    quoted_str = name_match.group(1)
                    # If it starts with the designation, extract just the name part
                    if quoted_str.startswith(area_designation):
                        area_name = quoted_str[len(area_designation):].strip()
                    else:
                        area_name = quoted_str
            else:
                # Format 2: ENR123 CHEMRING NOBEL ESTABLISHED
                # group(3) contains "ENR123", full match contains "ENR123 NAME ESTABLISHED"
                area_designation = establish_match.group(3).strip()
                # Extract the name from between designation and ESTABLISHED
                full_match = establish_match.group(0)
                # Remove area type prefix and ESTABLISHED suffix
                middle_part = full_match.replace(area_type, '', 1).replace('ESTABLISHED', '').strip()
                # Now we have "ENR123 CHEMRING NOBEL", split to get name
                parts = middle_part.split(None, 1)  # Split into designation and rest
                area_name = parts[1] if len(parts) > 1 else ""
            
            # Extract validity dates
            date_from_match = NotamParser.RE_DATE_FROM.search(block)
            date_to_match = NotamParser.RE_DATE_TO.search(block)
            
            date_from = None
            date_to = None
            if date_from_match:
                date_from = NotamParser.parse_date(date_from_match.group(1))
            if date_to_match:
                date_to = NotamParser.parse_date(date_to_match.group(1))
            
            # Extract coordinates
            psn_match = NotamParser.RE_PSN.search(block)
            coordinates = []
            if psn_match:
                coord_text = psn_match.group(1)
                coordinates = NotamParser.parse_coordinates(coord_text)
            
            # Extract altitude bounds
            lower_alt = 0
            lower_str = "GND"
            upper_alt = 9999
            upper_str = "9999m"
            
            for block_line in block_lines:
                lower_match = NotamParser.RE_LOWER.match(block_line.strip())
                if lower_match:
                    lower_alt, lower_str = NotamParser.parse_altitude(lower_match.group(1))
                
                upper_match = NotamParser.RE_UPPER.match(block_line.strip())
                if upper_match:
                    upper_alt, upper_str = NotamParser.parse_altitude(upper_match.group(1))
            
            # Extract schedule if present
            schedule = None
            for block_line in block_lines:
                schedule_match = NotamParser.RE_SCHEDULE.match(block_line.strip())
                if schedule_match:
                    schedule = schedule_match.group(1).strip()
                    break
            
            # Only add if we have coordinates
            if coordinates:
                notam = {
                    'notam_id': notam_id,
                    'area_type': area_type,
                    'designation': area_designation,
                    'name': area_name,
                    'coordinates': coordinates,
                    'lower_alt_m': lower_alt,
                    'lower_str': lower_str,
                    'upper_alt_m': upper_alt,
                    'upper_str': upper_str,
                    'date_from': date_from,
                    'date_to': date_to,
                    'schedule': schedule,
                    'temporary': date_to != 'PERM',
                    'raw_block': block
                }
                notams.append(notam)
                logger.info(f"Found NOTAM {notam_id}: {area_designation} {area_name} ({len(coordinates)} coords)")
            else:
                logger.warning(f"NOTAM {notam_id} ({area_designation}) has no coordinates, skipping")
            
            i = j
        
        return notams
    
    @staticmethod
    def notam_to_feature(notam: Dict) -> Dict:
        """
        Convert NOTAM data to GeoJSON-style feature dictionary.
        
        Args:
            notam: NOTAM dictionary from extract_notam_blocks
            
        Returns:
            Feature dictionary compatible with parse.py output format
        """
        # Build full name
        full_name = notam['designation']
        if notam['name']:
            full_name += f" {notam['name']}"
        
        # Determine airspace class
        area_type = notam['area_type'].upper()
        if 'RESTRICTED' in area_type:
            airspace_class = 'R'
        elif 'DANGER' in area_type:
            airspace_class = 'D'
        else:
            airspace_class = 'Q'  # Other/unknown
        
        feature = {
            'geometry': {
                'type': 'Polygon',
                'coordinates': [[]]
            },
            'properties': {
                'name': full_name,
                'class': airspace_class,
                'from (m amsl)': notam['lower_alt_m'],
                'from (ft amsl)': int(notam['lower_alt_m'] / 0.3048),  # Convert m to ft
                'to (m amsl)': notam['upper_alt_m'],
                'to (ft amsl)': int(notam['upper_alt_m'] / 0.3048),  # Convert m to ft
                'aip': f"NOTAM {notam['notam_id']}",
                'source': NotamParser.NOTAM_URL,
                'source_href': NotamParser.NOTAM_URL,
                'temporary': notam['temporary'],
                'fillOpacity': 0.25,
                'color': '#ff6600' if notam['temporary'] else '#cc0000'
            }
        }
        
        # Add date/time information for temporary areas
        if notam['temporary']:
            feature['properties']['Date from'] = [notam['date_from']] if notam['date_from'] else []
            feature['properties']['Date until'] = [notam['date_to']] if notam['date_to'] else []
            if notam['schedule']:
                feature['properties']['Time (UTC)'] = notam['schedule']
        
        # Convert coordinates to decimal degrees
        # Using c2ll from utils
        from util.utils import c2ll
        
        coords_decimal = []
        for lat_dms, lon_dms in notam['coordinates']:
            try:
                lat_dec, lon_dec = c2ll((lat_dms, lon_dms))
                coords_decimal.append([lon_dec, lat_dec])  # GeoJSON is [lon, lat]
            except Exception as e:
                logger.error(f"Failed to convert coordinates {lat_dms} {lon_dms}: {e}")
        
        # Close the polygon if not already closed
        if coords_decimal and coords_decimal[0] != coords_decimal[-1]:
            coords_decimal.append(coords_decimal[0])
        
        feature['geometry']['coordinates'] = [coords_decimal]
        
        return feature
    
    @classmethod
    def fetch_and_parse(cls) -> List[Dict]:
        """
        Main entry point: fetch NOTAMs and convert to feature list.
        
        Returns:
            List of feature dictionaries ready for output formatters
        """
        html = cls.fetch_notams()
        if not html:
            logger.warning("No NOTAM data fetched, returning empty list")
            return []
        
        notams = cls.extract_notam_blocks(html)
        logger.info(f"Parsed {len(notams)} NOTAMs with established airspace")
        
        features = []
        for notam in notams:
            try:
                feature = cls.notam_to_feature(notam)
                features.append(feature)
            except Exception as e:
                logger.error(f"Failed to convert NOTAM {notam['notam_id']} to feature: {e}")
        
        logger.info(f"Converted {len(features)} NOTAMs to features")
        return features


if __name__ == '__main__':
    # Test the parser
    logging.basicConfig(level=logging.INFO)
    features = NotamParser.fetch_and_parse()
    
    print(f"\nFound {len(features)} NOTAM-established airspaces:\n")
    for feat in features:
        props = feat['properties']
        coords = feat['geometry']['coordinates'][0]
        print(f"  {props['name']}")
        print(f"    Class: {props['class']}, Alt: {props['from (m amsl)']}m - {props['to (m amsl)']}m")
        print(f"    Temporary: {props['temporary']}")
        if props['temporary']:
            print(f"    Valid: {props.get('Date from', ['?'])[0]} to {props.get('Date until', ['?'])[0]}")
        print(f"    Coordinates: {len(coords)} points")
        print()
