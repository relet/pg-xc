"""Geometry utility functions for airspace coordinate conversion and generation.

Provides coordinate conversion between different formats and geometric shape
generation (circles, sectors) commonly used in aviation airspace definitions.
"""

import math
from dataclasses import dataclass
from typing import Tuple, List, Optional
import logging

logger = logging.getLogger(__name__)


# Constants
PI2 = math.pi * 2
DEG2RAD = PI2 / 360.0
RAD_EARTH = 6371000.0  # Earth radius in meters


@dataclass
class GeometryConfig:
    """Configuration for geometry generation."""
    circle_points: int = 64  # Number of points to approximate a circle
    
    
class CoordinateConverter:
    """Converts between different coordinate formats.
    
    Handles conversion between:
    - DegMinSec (DDMMSS format used in AIP)
    - Decimal degrees (lat/lon floats)
    
    Example:
        converter = CoordinateConverter()
        lat_lon = converter.dms_to_decimal(('600000', '0100000'))
        # Returns (10.0, 60.0)  # (lon, lat)
    """
    
    @staticmethod
    def dms_to_decimal(coord: Tuple[str, str]) -> Optional[Tuple[float, float]]:
        """Convert DegMinSec to decimal degrees.
        
        Args:
            coord: Tuple of (north, east) strings in DDMMSS format
                  N: DDMMSS (6+ digits)
                  E: DDDMMSS (7+ digits)
        
        Returns:
            Tuple of (lon, lat) in decimal degrees, or None if invalid
        """
        n, e = coord
        
        if len(n) < 5 or len(e) < 5:
            logger.warning(f"Misformatted coordinate: {coord}")
            return None
        
        try:
            # Parse north coordinate (DDMMSS)
            n_deg = float(n[0:2])
            n_min = float(n[2:4])
            n_sec = float(n[4:]) if len(n) > 4 else 0.0
            
            # Parse east coordinate (DDDMMSS)
            e_deg = float(e[0:3])
            e_min = float(e[3:5])
            e_sec = float(e[5:]) if len(e) > 5 else 0.0
            
            lat = n_deg + n_min / 60.0 + n_sec / 3600.0
            lon = e_deg + e_min / 60.0 + e_sec / 3600.0
            
            return (lon, lat)
        except (ValueError, IndexError) as e:
            logger.error(f"Failed to convert coordinate {coord}: {e}")
            return None
    
    @staticmethod
    def decimal_to_dms(coord: Tuple[float, float]) -> Tuple[str, str]:
        """Convert decimal degrees to DegMinSec.
        
        Args:
            coord: Tuple of (lon, lat) in decimal degrees
            
        Returns:
            Tuple of (north, east) strings in DDMMSS format
        """
        lon, lat = coord
        
        # Convert latitude
        n_deg = int(lat)
        n_min = int((lat - n_deg) * 60)
        n_sec = int(((lat - n_deg) * 60 - n_min) * 60)
        
        # Convert longitude
        e_deg = int(lon)
        e_min = int((lon - e_deg) * 60)
        e_sec = int(((lon - e_deg) * 60 - e_min) * 60)
        
        n = f"{n_deg:02d}{n_min:02d}{n_sec:02d}"
        e = f"{e_deg:03d}{e_min:02d}{e_sec:02d}"
        
        return (n, e)


class GeometryGenerator:
    """Generates geometric shapes for airspace boundaries.
    
    Creates circles, sectors, and other shapes commonly used in aviation
    airspace definitions.
    """
    
    def __init__(self, config: GeometryConfig = None):
        """Initialize with optional configuration."""
        self.config = config or GeometryConfig()
        self.converter = CoordinateConverter()
    
    def generate_circle(self, 
                       center_n: str, 
                       center_e: str, 
                       radius_nm: float,
                       as_dms: bool = True) -> List[Tuple]:
        """Generate a circular boundary.
        
        Args:
            center_n: Center north coordinate (DDMMSS)
            center_e: Center east coordinate (DDDMMSS)
            radius_nm: Radius in nautical miles
            as_dms: Return coordinates in DMS format (default True)
            
        Returns:
            List of coordinate tuples (closed polygon)
        """
        logger.debug(f"Generating circle: center=({center_n}, {center_e}), radius={radius_nm}nm")
        
        # Convert center to decimal
        center_decimal = self.converter.dms_to_decimal((center_n, center_e))
        if not center_decimal:
            return []
        
        lon, lat = center_decimal
        radius_m = float(radius_nm) * 1852.0  # Convert NM to meters
        
        # Convert to radians
        lon_rad = lon * DEG2RAD
        lat_rad = lat * DEG2RAD
        d = radius_m / RAD_EARTH  # Angular distance
        
        circle = []
        for i in range(self.config.circle_points):
            bearing = i * PI2 / self.config.circle_points
            
            # Calculate point on circle using spherical geometry
            lat2 = math.asin(
                math.sin(lat_rad) * math.cos(d) +
                math.cos(lat_rad) * math.sin(d) * math.cos(bearing)
            )
            lon2 = lon_rad + math.atan2(
                math.sin(bearing) * math.sin(d) * math.cos(lat_rad),
                math.cos(d) - math.sin(lat_rad) * math.sin(lat2)
            )
            
            # Convert back to degrees
            point_decimal = (lon2 / DEG2RAD, lat2 / DEG2RAD)
            
            if as_dms:
                circle.append(self.converter.decimal_to_dms(point_decimal))
            else:
                circle.append(point_decimal)
        
        # Close the circle
        circle.append(circle[0])
        return circle
    
    def generate_sector(self,
                       center_n: str,
                       center_e: str,
                       bearing_from: float,
                       bearing_to: float,
                       radius_inner_nm: Optional[float],
                       radius_outer_nm: float) -> List[Tuple]:
        """Generate a sector (pie slice) boundary.
        
        Args:
            center_n: Center north coordinate
            center_e: Center east coordinate
            bearing_from: Start bearing in degrees
            bearing_to: End bearing in degrees
            radius_inner_nm: Inner radius in NM (None for center point)
            radius_outer_nm: Outer radius in NM
            
        Returns:
            List of coordinate tuples forming sector boundary
        """
        logger.debug(
            f"Generating sector: center=({center_n}, {center_e}), "
            f"bearings={bearing_from}°-{bearing_to}°, "
            f"radius={radius_inner_nm}-{radius_outer_nm}nm"
        )
        
        center_decimal = self.converter.dms_to_decimal((center_n, center_e))
        if not center_decimal:
            return []
        
        lon, lat = center_decimal
        lon_rad = lon * DEG2RAD
        lat_rad = lat * DEG2RAD
        
        # Calculate sector arc length
        sector_range = ((bearing_to - bearing_from + 360) % 360) * DEG2RAD
        bearing_from_rad = bearing_from * DEG2RAD
        
        # Convert radii
        radius_inner_m = float(radius_inner_nm or 0) * 1852.0
        radius_outer_m = float(radius_outer_nm) * 1852.0
        
        inner_points = []
        outer_points = []
        
        # Generate center point if no inner radius
        if radius_inner_nm is None or radius_inner_nm == 0:
            inner_points = [(center_n, center_e)]
        
        # Generate arc points
        for i in range(self.config.circle_points + 1):
            bearing = bearing_from_rad + i * sector_range / self.config.circle_points
            
            # Outer arc
            d_outer = radius_outer_m / RAD_EARTH
            lat2 = math.asin(
                math.sin(lat_rad) * math.cos(d_outer) +
                math.cos(lat_rad) * math.sin(d_outer) * math.cos(bearing)
            )
            lon2 = lon_rad + math.atan2(
                math.sin(bearing) * math.sin(d_outer) * math.cos(lat_rad),
                math.cos(d_outer) - math.sin(lat_rad) * math.sin(lat2)
            )
            outer_points.append(
                self.converter.decimal_to_dms((lon2 / DEG2RAD, lat2 / DEG2RAD))
            )
            
            # Inner arc (if exists)
            if radius_inner_nm and radius_inner_nm > 0:
                d_inner = radius_inner_m / RAD_EARTH
                lat2 = math.asin(
                    math.sin(lat_rad) * math.cos(d_inner) +
                    math.cos(lat_rad) * math.sin(d_inner) * math.cos(bearing)
                )
                lon2 = lon_rad + math.atan2(
                    math.sin(bearing) * math.sin(d_inner) * math.cos(lat_rad),
                    math.cos(d_inner) - math.sin(lat_rad) * math.sin(lat2)
                )
                inner_points.insert(
                    0,
                    self.converter.decimal_to_dms((lon2 / DEG2RAD, lat2 / DEG2RAD))
                )
        
        # Combine inner and outer arcs
        sector = inner_points + outer_points + [inner_points[0]]
        return sector


# Backward compatibility functions
def c2ll(c: Tuple[str, str]) -> Optional[Tuple[float, float]]:
    """Convert DMS to decimal (backward compatibility)."""
    return CoordinateConverter.dms_to_decimal(c)


def ll2c(ll: Tuple[float, float]) -> Tuple[str, str]:
    """Convert decimal to DMS (backward compatibility)."""
    return CoordinateConverter.decimal_to_dms(ll)


def gen_circle(n: str, e: str, rad: float, convert: bool = True) -> List[Tuple]:
    """Generate circle (backward compatibility)."""
    gen = GeometryGenerator()
    return gen.generate_circle(n, e, rad, as_dms=convert)


def gen_sector(n: str, e: str, secfrom: float, secto: float, 
               radfrom: Optional[float], radto: float) -> List[Tuple]:
    """Generate sector (backward compatibility)."""
    gen = GeometryGenerator()
    return gen.generate_sector(n, e, secfrom, secto, radfrom, radto)
