# utility methods for conversion

import json
import geojson as gj
import math
import re
import sys
from shapely.geometry import Polygon
from shapely.ops import cascaded_union
from shapely.strtree import STRtree
from sys import exit

CIRCLE_APPROX_POINTS = 64

PI2 = math.pi * 2
DEG2RAD = PI2 / 360.0
RAD_EARTH = 6371000.0

logger=None

def init_utils(l):
    global logger
    logger=l

def printj(s):
    return json.dumps(s)

def c2ll(c):
    if len(c[0])<5 or len(c[1])<5:
        print("WARNING: MISFORMATTED COORDINATE ",c)
        #exit(1)
        return None
    """DegMinSec to decimal degrees"""
    ndeg = float(c[0][0:2])
    nmin = float(c[0][2:4])
    nsec = float(c[0][4:])
    print(c[0][4])
    if c[0][4] == '.':
        nmin = float(c[0][2:])
        nsec = 0.0
    edeg = float(c[1][0:3])
    emin = float(c[1][3:5])
    esec = float(c[1][5:])
    if c[1][5] == '.':
        emin = float(c[1][3:])
        esec = 0.0
    if len(c[1])==6: # east is only 2 digits here
        edeg = float(c[1][0:2])
        emin = float(c[1][2:4])
        esec = float(c[1][4:])
    coo = (edeg + emin / 60.0 + esec / 3600.0,
           ndeg + nmin / 60.0 + nsec / 3600.0)
    return coo

def ll2c(ll):
    """Decimal degrees to DegMinSec"""
    lon, lat = ll
    ndeg = int(lat)
    edeg = int(lon)
    nmin = int((lat - ndeg) * 60)
    emin = int((lon - edeg) * 60)
    nsec = int(((lat - ndeg) * 60 - nmin) * 60)
    esec = int(((lon - edeg) * 60 - emin) * 60)

    n = "%02d%02d%02d" % (ndeg, nmin, nsec)
    e = "%03d%02d%02d" % (edeg, emin, esec)
    return (n,e)

def ft2m(f):
    """Foot to Meters"""
    return int(float(f) * 0.3048)

def nm2m(nm):
    """Nautical miles to meters"""
    try:
        return float(nm) * 1852.0
    except:
        return float(nm.replace(",",".")) * 1852.0

def m2nm(m):
    """Meters to nautical miles"""
    return float(m) / 1852.0

def gen_circle(n, e, rad, convert=True):
    """Generate a circle"""
    logger.debug("Generating circle around %s, %s, radius %s", n, e, rad)
    circle = []
    lon,lat = c2ll((n,e))
    rad     = float(nm2m(rad))
    lon     = lon * DEG2RAD # deg -> rad
    lat     = lat * DEG2RAD # deg -> rad
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
    """Generate a sector, possibly with an inner radius"""
    logger.debug("Generating sector around %s, %s, sec from %s to %s, radius %s to %s", n, e, secfrom, secto, radfrom, radto)
    isector = []
    osector = []
    lon,lat = c2ll((n,e))
    lon     = lon * DEG2RAD # deg -> rad
    lat     = lat * DEG2RAD # deg -> rad
    secdiff = float((int(secto) - int(secfrom) + 360) % 360) * DEG2RAD
    logger.debug("%s sector range", (int(secto) - int(secfrom) + 360) % 360)
    secfrom = float(secfrom) * DEG2RAD
    secto   = float(secto) * DEG2RAD
    if radfrom is None:
        radfrom = 0
    radfrom = float(nm2m(radfrom))
    radto   = float(nm2m(radto))
    dfrom   = radfrom/RAD_EARTH # angular distance
    dto     = radto/RAD_EARTH # angular distance
    if radfrom == 0:
        isector = [(n,e)]
    for i in range(0,CIRCLE_APPROX_POINTS+1): # bearings are inclusive
        brng = secfrom + i * secdiff / CIRCLE_APPROX_POINTS # bearing (rad)
        if radfrom > 0:
            d = dfrom
            lat2 = math.asin(math.sin(lat) * math.cos(d) +
                                math.cos(lat) * math.sin(d) * math.cos(brng))
            lon2 = lon + math.atan2(math.sin(brng)*math.sin(d)*math.cos(lat),
                                    math.cos(d)-math.sin(lat)*math.sin(lat2))
            isector.insert(0,ll2c((lon2 / DEG2RAD, lat2 / DEG2RAD)))
        d = dto
        lat2 = math.asin(math.sin(lat) * math.cos(d) +
                            math.cos(lat) * math.sin(d) * math.cos(brng))
        lon2 = lon + math.atan2(math.sin(brng)*math.sin(d)*math.cos(lat),
                                math.cos(d)-math.sin(lat)*math.sin(lat2))
        osector.append(ll2c((lon2 / DEG2RAD, lat2 / DEG2RAD)))
    return isector + osector + [isector[0]]

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
    union = cascaded_union([poly1, poly2])
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
    return re.sub('\s+',' ',s.strip())

def fill_along(from_, to_, border, clockwise=None):
    """Follow a country border or other line"""

    global logger
    logger.debug("fill_along %s %s %s (%i) %s", from_, to_, border[0], len(border), clockwise and "clockwise")

    llf = c2ll(from_)
    llt = c2ll(to_)
    minfrom = 99999
    minto   = 99999
    fromindex = None
    toindex = None
    for i in range(len(border)):
        lon,lat = border[i]
        d = abs(lon-llf[0])+abs(lat-llf[1])
        if d < minfrom:
            minfrom = d
            fromindex = i
        d = abs(lon-llt[0])+abs(lat-llt[1])
        if d < minto:
            minto = d
            toindex = i
    blen   = abs(toindex-fromindex)
    revlen = len(border)-blen
    # FIXME:correctly handle clockwise/counterclockwise/southwards/northwards etc.
    # currently we just select whichever path is shortest
    if clockwise is None:
        clockwise = (toindex > fromindex)
        if blen>revlen:
            clockwise = not clockwise
    if clockwise:
        logger.debug("Filling fwd from index %i to %i (%i points, %i reverse)", fromindex, toindex, blen, revlen)
        if toindex < fromindex:
            logger.debug("Filling fwd, wraparound")
            result = border[fromindex+1:]+border[:toindex]
        else:
            logger.debug("Filling fwd")
            result = border[fromindex+1:toindex]
    else:
        logger.debug("Filling bkw from index %i to %i (%i points, %i reverse)", fromindex, toindex, blen, revlen)
        if toindex > fromindex:
            logger.debug("Filling bkw, wraparound")
            result = border[fromindex-1::-1]+border[:toindex+1:-1]
        else:
            logger.debug("Filling bkw")
            result = border[fromindex-1:toindex+1:-1]
    logger.debug("Resulting in a polygon with %i points.", len(result))
    return result

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




