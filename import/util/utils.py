# utility methods for conversion
# This module is deprecated - functionality moved to:
# - util.geometry (coordinate conversion, shape generation)
# - util.units (unit conversions)
# - util.borders (border following)
# Backward compatibility wrappers are provided below.

import json
import geojson as gj
import math
import re
import sys
import logging
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree
from sys import exit

# Import new modules
from util.geometry import CoordinateConverter, GeometryGenerator, GeometryConfig
from util.units import UnitConverter
from util.borders import fill_along as _fill_along, BorderLoader

CIRCLE_APPROX_POINTS = 64

PI2 = math.pi * 2
DEG2RAD = PI2 / 360.0
RAD_EARTH = 6371000.0

logger = logging.getLogger(__name__)

def init_utils(l):
    """Initialize utils logger (deprecated - uses standard logging now)."""
    global logger
    logger = l

def printj(s):
    return json.dumps(s)

def c2ll(c):
    """DegMinSec to decimal degrees (backward compatibility wrapper)."""
    return CoordinateConverter.dms_to_decimal(c)

def ll2c(ll):
    """Decimal degrees to DegMinSec (backward compatibility wrapper)."""
    return CoordinateConverter.decimal_to_dms(ll)

def ft2m(f):
    """Foot to Meters (backward compatibility wrapper)."""
    return int(UnitConverter.feet_to_meters(float(f)))

def nm2m(nm):
    """Nautical miles to meters (backward compatibility wrapper)."""
    try:
        return UnitConverter.nautical_miles_to_meters(float(nm))
    except (ValueError, AttributeError):
        # Handle comma decimal separator
        return UnitConverter.nautical_miles_to_meters(float(nm.replace(",", ".")))

def m2nm(m):
    """Meters to nautical miles (backward compatibility wrapper)."""
    return UnitConverter.meters_to_nautical_miles(float(m))

def gen_circle(n, e, rad, convert=True):
    """Generate a circle (refactored - uses geometry module)."""
    gen = GeometryGenerator()
    return gen.generate_circle(n, e, rad, as_dms=convert)
    d      = rad/RAD_EARTH # angular distance
    for i in range(0,CIRCLE_APPROX_POINTS):
        brng = i * PI2 / CIRCLE_APPROX_POINTS # bearing (rad)
        lat2 = math.asin(math.sin(lat) * math.cos(d) +
                            math.cos(lat) * math.sin(d) * math.cos(brng))
        lon2 = lon + math.atan2(math.sin(brng)*math.sin(d)*math.cos(lat),
                                math.cos(d)-math.sin(lat)*math.sin(lat2))
        if convert:
            circle.append(ll2c((lon2 / DEG2RAD, lat2 / DEG2RAD)))
        else:
            circle.append((lon2 / DEG2RAD, lat2 / DEG2RAD))
    circle.append(circle[0])
    return circle


def gen_sector(n, e, secfrom, secto, radfrom, radto):
    """Generate a sector (refactored - uses geometry module)."""
    gen = GeometryGenerator()
    return gen.generate_sector(n, e, secfrom, secto, radfrom, radto)

def simplify_poly(p, target):
    """Simplify a polygon to target point count"""
    poly = Polygon([c2ll(c) for c in p])
    tolerance = 0.001
    while len(poly.exterior.coords)>target:
        poly = poly.simplify(tolerance)
        logger.debug("Simplified to %i points using tolerance %d", len(poly.exterior.coords), tolerance)
        tolerance += 0.0002
    return [ll2c(ll) for ll in poly.buffer(0).exterior.coords]

def merge_poly(p1, p2):
    """Merge two polygons using shapely ops"""
    if not p1:
        return p2
    logger.debug("Merging %s and %s", p1, p2)
    poly1 = Polygon([c2ll(c) for c in p1])
    poly2 = Polygon([c2ll(c) for c in p2])
    union = unary_union([poly1, poly2])
    try:
      return [ll2c(ll) for ll in union.exterior.coords]
    except:
      logger.debug("Polygon union is still a MultiPolygon.")
      sys.exit(1)
      return [ll2c(ll) for part in union for ll in part.exterior.coords]

def wstrip(s):
    """Remove double whitespaces, and strip"""
    """also skip trailing sections"""
    if "      " in s:
        s = s.split("      ")[0]
    return re.sub(r'\s+', ' ', s.strip())

def fill_along(from_, to_, border, clockwise=None):
    """Follow a country border (backward compatibility wrapper)."""
    return _fill_along(from_, to_, border, clockwise)

def dissect(collection):
    return

    #TBD intersect all overlapping polygons and return merged results

    index = {}
    geometries = []
    results = []

    for feature in collection:
        geom = Polygon(feature['geometry_ll'])
        geometries.append(geom)
        index[geom.wkt]=feature
    tree = STRtree(geometries)

    for geom in geometries:
        feature = index[geom.wkt]
        overlaps = tree.query(geom)

        for match in overlaps:
            match_feat = index[match.wkt]
            if not match.is_valid:
                match=match.buffer(0)

            if not match.is_valid:
                print("INVALID POLYGON")
                print(match_feat)
                print()
                print(gj.dumps(gj.Feature(geometry=match, properties={})))
                sys.exit(1)


            print("---")
            gname = feature['properties']['name']
            xname = match_feat['properties']['name']
            print("A ",gname, geom.is_valid)
            print("B ",xname, match.is_valid)
            if match.contains(geom):
                # The two features fully overlap/contain each other, we can just mention each other
                print ("CONTAINED")
                feature['properties']['cover'] = feature['properties'].get('cover',[]) + [match_feat['properties']]
                print("A (B)")
                index[geom.wkt] = feature # needed?
            elif geom.contains(match):
                print ("CONTAINS")
                sys.exit(1)
            elif geom.touches(match):
                print ("TOUCHES")
                sys.exit(1)
            elif geom.overlaps(match):
                print ("OVERLAPS")
                g1 = geom.difference(match)
                g2 = match.difference(geom)
                gu = geom.intersection(match)

                #TBD: name A-B, B-A, AuB and adjust the properties.
                print(gname," - ",xname)
                print(gname," x ",xname)
                print(xname," - ",gname)

                #print (gj.Feature(gj.Polygon(geom)))
                #sys.exit(1)
            elif geom.intersects(match):
                print ("INTERSECTS")
                sys.exit(1)

        results.append(feature)
        print("APPENDED")




