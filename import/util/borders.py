"""Border following utilities for airspace boundary generation.

Handles the special case where airspace boundaries follow national borders.
Loads border data from GeoJSON files and provides path-finding between
coordinates along the border.
"""

import logging
from typing import List, Tuple, Optional
from geojson import load

logger = logging.getLogger(__name__)


class BorderLoader:
    """Loads and caches national border data from GeoJSON files.
    
    Border data is used when airspace boundaries follow national borders
    instead of straight lines or geometric shapes.
    """
    
    def __init__(self, border_dir: str = "geojson"):
        """Initialize border loader.
        
        Args:
            border_dir: Directory containing border GeoJSON files
        """
        self.border_dir = border_dir
        self._cache = {}
    
    def load_border(self, country: str = "no") -> List[Tuple[float, float]]:
        """Load border coordinates from GeoJSON file.
        
        Args:
            country: Country code (default: "no" for Norway)
            
        Returns:
            List of (lon, lat) coordinate pairs forming the border
        """
        if country in self._cache:
            logger.debug(f"Using cached border data for {country}")
            return self._cache[country]
        
        filename = f"{self.border_dir}/{country}.geojson"
        try:
            with open(filename, 'r') as f:
                border_geojson = load(f)
            
            # Extract coordinates from GeoJSON
            # Assuming MultiLineString or LineString geometry
            coords = []
            if border_geojson['type'] == 'FeatureCollection':
                for feature in border_geojson['features']:
                    coords.extend(self._extract_coordinates(feature['geometry']))
            else:
                coords = self._extract_coordinates(border_geojson['geometry'])
            
            self._cache[country] = coords
            logger.info(f"Loaded {len(coords)} border points from {filename}")
            return coords
            
        except FileNotFoundError:
            logger.error(f"Border file not found: {filename}")
            return []
        except Exception as e:
            logger.error(f"Failed to load border from {filename}: {e}")
            return []
    
    def _extract_coordinates(self, geometry):
        """Extract coordinates from GeoJSON geometry."""
        if geometry['type'] == 'LineString':
            return geometry['coordinates']
        elif geometry['type'] == 'MultiLineString':
            coords = []
            for line in geometry['coordinates']:
                coords.extend(line)
            return coords
        elif geometry['type'] == 'Polygon':
            # Take exterior ring
            return geometry['coordinates'][0]
        else:
            logger.warning(f"Unsupported geometry type: {geometry['type']}")
            return []


def fill_along(from_coord: Tuple[str, str], 
               to_coord: Tuple[str, str], 
               border: List[Tuple[float, float]], 
               clockwise: Optional[bool] = None) -> List[Tuple[float, float]]:
    """Fill coordinates between two points along a border.
    
    Finds the closest points on the border to the start and end coordinates,
    then returns all border coordinates between them.
    
    Algorithm:
    1. Find closest border point to start coordinate
    2. Find closest border point to end coordinate  
    3. Determine direction (clockwise or counter-clockwise) to minimize distance
    4. Return all border points between start and end in that direction
    
    Args:
        from_coord: Starting coordinate (n, e) in DMS format
        to_coord: Ending coordinate (n, e) in DMS format
        border: List of (lon, lat) border coordinates
        clockwise: Force direction (None = auto-detect shortest path)
        
    Returns:
        List of (lon, lat) coordinates along the border
        
    Example:
        from_coord = ('600000', '100000')  # North Norway
        to_coord = ('590000', '095000')
        border = load_border('no')
        path = fill_along(from_coord, to_coord, border)
        # Returns border coordinates between the two points
    """
    if not border:
        logger.warning("Border data is empty, cannot fill along border")
        return []
    
    # Convert DMS to decimal degrees for distance calculation
    from util.geometry import CoordinateConverter
    converter = CoordinateConverter()
    
    from_decimal = converter.dms_to_decimal(from_coord)
    to_decimal = converter.dms_to_decimal(to_coord)
    
    if not from_decimal or not to_decimal:
        logger.error(f"Failed to convert coordinates: from={from_coord}, to={to_coord}")
        return []
    
    # Find closest border points
    from_idx = _find_closest_point(from_decimal, border)
    to_idx = _find_closest_point(to_decimal, border)
    
    if from_idx is None or to_idx is None:
        logger.error("Failed to find border points")
        return []
    
    logger.debug(f"Border fill: from_idx={from_idx}, to_idx={to_idx}, border_len={len(border)}")
    
    # Determine direction if not specified
    if clockwise is None:
        # Calculate distances - use same logic as original
        blen = abs(to_idx - from_idx)
        revlen = len(border) - blen
        
        # Original logic: prefer direction based on index comparison,
        # then flip if reverse path is shorter
        clockwise = (to_idx > from_idx)
        if blen > revlen:
            clockwise = not clockwise
        
        logger.debug(f"Auto-detected direction: {'clockwise' if clockwise else 'counter-clockwise'} (blen={blen}, revlen={revlen})")
    
    # Extract border segment - match original logic exactly
    if clockwise:
        logger.debug(f"Filling fwd from index {from_idx} to {to_idx}")
        if to_idx < from_idx:
            # Wrap around end (but don't include start/end points themselves)
            logger.debug("Filling fwd, wraparound")
            segment = border[from_idx+1:] + border[:to_idx]
        else:
            # Forward (don't include start point, don't include end point)
            segment = border[from_idx+1:to_idx]
    else:
        logger.debug(f"Filling bkw from index {from_idx} to {to_idx}")
        if to_idx > from_idx:
            # Backward with wraparound
            logger.debug("Filling bkw, wraparound")
            segment = border[from_idx-1::-1] + border[:to_idx+1:-1]
        else:
            # Backward (from from_idx-1 down to to_idx+1)
            segment = border[from_idx-1:to_idx:-1]
    
    logger.debug(f"Filled border with {len(segment)} points")
    return segment


def _find_closest_point(target: Tuple[float, float], 
                       points: List[Tuple[float, float]]) -> Optional[int]:
    """Find index of closest point in list to target.
    
    Uses Euclidean distance in lat/lon space (approximation).
    
    Args:
        target: (lon, lat) target coordinate
        points: List of (lon, lat) points to search
        
    Returns:
        Index of closest point, or None if points is empty
    """
    if not points:
        return None
    
    target_lon, target_lat = target
    min_dist = float('inf')
    min_idx = 0
    
    for i, (lon, lat) in enumerate(points):
        # Simple Euclidean distance (good enough for close points)
        dist = (lon - target_lon)**2 + (lat - target_lat)**2
        if dist < min_dist:
            min_dist = dist
            min_idx = i
    
    return min_idx


# Backward compatibility - keep original function signature
def load_border(filename: str = "geojson/no.geojson") -> List[Tuple[float, float]]:
    """Load border from file (backward compatibility).
    
    Args:
        filename: Path to GeoJSON border file
        
    Returns:
        List of (lon, lat) coordinate pairs
    """
    loader = BorderLoader()
    # Extract country code from filename
    country = "no"  # Default to Norway
    if "/" in filename:
        parts = filename.split("/")
        if len(parts) > 1:
            country_file = parts[-1]
            if "." in country_file:
                country = country_file.split(".")[0]
    
    return loader.load_border(country)
