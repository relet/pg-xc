#!/usr/bin/env python
# -*- coding: utf-8 -*-

# FIXME: Swedish files list all relevant airspace for each airport, ignore duplicates


from codecs import open
from geojson import Feature, FeatureCollection, Polygon, load
import math
import os
import re
import sys
import urllib
import logging

import shapely.ops      as shops
import shapely.geometry as shgeo

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Lines containing these are usually recognized as names
re_name   = re.compile("^\s*(?P<name>[^\s]* (ADS|AOR|ATZ|FAB|TMA|TIA|CTA|CTR|TIZ|FIR)( (West|Centre))?|[^\s]*( ACC sector|ESTRA|EUCBA).*)( cont.)?\s*$")
re_name2  = re.compile("^\s*(?P<name>E[NS] [RD].*)\s*$")
re_name3  = re.compile("^\s*(?P<name>E[NS]D\d.*)\s*$")

# Lines containing these are usually recognized as airspace class
re_class  = re.compile("Class (?P<class>.)")
re_class2 = re.compile("^(?P<class>[CDG])$")

# Coordinates format, possibly in brackets
RE_NE     = '(?P<ne>\(?(?P<n>\d+)N\s+(?P<e>\d+)E\)?)'
RE_NE2    = '(?P<ne2>\(?(?P<n2>\d+)N\s+(?P<e2>\d+)E\)?)'
# Match circle definitions, see log file for examples
re_coord  = re.compile("(?:" + RE_NE + " - )?(?:\d\. )?(?:A circle(?: with|,)? r|R)adius (?:(?P<rad>[\d\.,]+) NM|(?P<rad_m>[\d]+) m)(?: \([\d\.,]+ k?m\))?(?: cente?red on (?P<cn>\d+)N\s+(?P<ce>\d+)E)?")
# Match sector definitions, see log file for examples
RE_SECTOR = u'('+RE_NE + u' - )?((\d\. )?A s|S)ector (?P<secfrom>\d+)° - (?P<secto>\d+)° \(T\), radius ((?P<radfrom>[\d\.,]+) - )?(?P<rad>[\d\.,]+) NM'
re_coord2 = re.compile(RE_SECTOR)
# Match all other formats in a coordinate list, including "along border" syntax
RE_CIRCLE = 'A circle(?: with|,) radius (?P<rad>[\d\.]+) NM cente?red on (?P<cn>\d+)N\s+(?P<ce>\d+)E'
re_coord3_no = re.compile(RE_NE+"|(?P<along>along)|(?P<arc>(?:counter)?clockwise)|(?:\d+)N|(?:\d+)E|"+RE_CIRCLE)
re_coord3_se = re.compile(RE_NE+"|(?P<along>border)|(?P<arc>(?:counter)?clockwise)|(?:\d+)N|(?:\d+)E|"+RE_CIRCLE+"|(?P<circle>A circle)|(?:radius)")
# clockwise along an arc of 16.2 NM radius centred on 550404N 0144448E - 545500N 0142127E
re_arc = re.compile('(?P<dir>(counter)?clockwise) along an arc (?:of (?P<rad1>[\d\.,]+) NM radius )?centred on '+RE_NE+'(?:( and)?( with)?( radius) (?P<rad2>[ \d\.,]+) NM(?: \([\d\.]+ k?m\))?)? (?:- )'+RE_NE2)

#TODO: along the latitude ...


# Lines containing these are box ceilings and floors
re_vertl  = re.compile("(?P<from>GND|\d+) to (?P<to>UNL|\d+)( [Ff][Tt] AMSL)?")
re_vertl2 = re.compile("((?P<ftamsl>\d+) [Ff][Tt] AMSL)|(?P<gnd>GND)|(?P<unl>UNL)|(FL (?P<fl>\d+))|(?P<rmk>See (remark|RMK))")

# COLUMN PARSING:
rexes_header_es_enr = [re.compile("(?:(?:(Name|Identification)|(Lateral limits)|(Vertical limits)|(ATC unit)|(Freq MHz)|(Callsign)|(AFIS unit)|(Remark)).*){%i}" % mult) \
                           for mult in reversed(xrange(3,8))]


CIRCLE_APPROX_POINTS = 32
RAD_EARTH = 6371000.0
PI2 = math.pi * 2
DEG2RAD = PI2 / 360.0

LINEBREAK = '--linebreak--'

def c2ll(c):
    """DegMinSec to decimal degrees"""
    ndeg = float(c[0][0:2])
    edeg = float(c[1][0:3])
    nmin = float(c[0][2:4])
    emin = float(c[1][3:5])
    nsec = float(c[0][4:])
    esec = float(c[1][5:])
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

def c2air(c):
    """DegMinSec to OpenAIR format (Deg:Min:Sec)"""
    n,e = c
    return "%s:%s:%s N  %s:%s:%s E" % (n[0:2],n[2:4],n[4:],e[0:3],e[3:5],e[5:])

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
    for i in xrange(0,CIRCLE_APPROX_POINTS):
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
    for i in xrange(0,CIRCLE_APPROX_POINTS+1): # bearings are inclusive
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

def merge_poly(p1, p2):
    """Merge two polygons using shapely ops"""
    if not p1:
        return p2
    logger.debug("Merging %s and %s", p1, p2)
    poly1 = shgeo.Polygon([c2ll(c) for c in p1])
    poly2 = shgeo.Polygon([c2ll(c) for c in p2])
    union = shops.cascaded_union([poly1, poly2])
    return [ll2c(ll) for ll in union.exterior.coords]

norway_fc = load(open("fastland.geojson","r"))
norway = norway_fc.features[0].geometry.coordinates[0]
logger.debug("Norway has %i points.", len(norway))
sweden_fc = load(open("fastland-sweden.geojson","r"))
sweden = sweden_fc.features[0].geometry.coordinates[0]
logger.debug("Sweden has %i points.", len(sweden))
borders = {
        'norway': norway,
        'sweden': sweden
}

def fill_along(from_, to_, border):
    """Follow a country border or other line"""
    logger.debug("fill_along %s %s %s (%i)", from_, to_, border[0], len(border))
    llf = c2ll(from_)
    llt = c2ll(to_)
    minfrom = 99999
    minto   = 99999
    fromindex = None
    toindex = None
    for i in xrange(len(border)):
        lon,lat = border[i]
        d = abs(lon-llf[0])+abs(lat-llf[1])
        if d < minfrom:
            minfrom = d
            fromindex = i
        d = abs(lon-llt[0])+abs(lat-llt[1])
        if d < minto:
            minto = d
            toindex = i
    logger.debug("Filling from index %i to %i", fromindex, toindex)
    if toindex < fromindex:
        return border[fromindex:toindex+1:-1]
    else:
        return border[fromindex:toindex+1]

collection = []
completed = {}

def wstrip(s):
    """Remove double whitespaces, and strip"""
    return re.sub('\s+',' ',s.strip())

def finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, sup_aip, tia_aip):
    """Complete and sanity check a feature definition"""
    global completed

    feature['properties']['source_href']=source
    feature['geometry'] = obj
    aipname = wstrip(unicode(aipname))
    for ignore in ['ACC','ADS','AOR','FIR']: 
        if ignore in aipname:
            logger.debug("Ignoring: %s", aipname)
            return {"properties":{}}, []
    feature['properties']['name']=aipname
    if cta_aip or sup_aip or tia_aip:
        recount = len([f for f in features if aipname in f['properties']['name']])
        if recount>0:
            feature['properties']['name']=aipname + " " + str(recount+1)
    elif not restrict_aip and not airsport_aip and len(features)>0:
        feature['properties']['name']=aipname + " " + str(len(features)+1)
    if 'TIZ' in aipname or 'TIA' in aipname:
        feature['properties']['class']='G'
    elif 'CTR' in aipname:
        feature['properties']['class']='D'
    elif 'EN R' in aipname or 'EN D' in aipname or 'END' in aipname   \
      or 'ES R' in aipname or 'ES D' in aipname or 'ESTRA' in aipname \
      or 'EUCBA' in aipname:
        feature['properties']['class']='R'
    elif 'TMA' in aipname or 'CTA' in aipname or 'FIR' in aipname \
      or 'ACC' in aipname or 'ATZ' in aipname or 'FAB' in aipname:
        feature['properties']['class']='C'
    elif '5_5' in source:
        feature['properties']['class']='Luftsport'
    index = len(collection)+len(features)
    if len(obj)>3:
        logger.debug("Created polygon #%i %s with %i points.", index, feature['properties'].get('name'), len(obj))
        features.append(feature)

        # SANITY CHECK
        name   = feature['properties'].get('name')
        source = feature['properties'].get('source_href')
        from_  = feature['properties'].get('from (ft amsl)')
        to_    = feature['properties'].get('to (ft amsl)')
        class_ = feature['properties'].get('class')
        if name is None:
            logger.error("Feature without name: #%i", index)
            sys.exit(1)
        if "None" in name:
            logger.error("Feature without name: #%i", index)
            sys.exit(1)
        if name in completed:
            logger.info("Duplicate feature name, skipping: #%i %s", index, name)
            return {"properties":{}}, []
            #sys.exit(1)
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
        if from_ is None:
            logger.error("Feature without lower limit: #%i (%s)", index, source)
            sys.exit(1)
        if to_ is None:
            logger.error("Feature without upper limit: #%i (%s)", index, source)
            sys.exit(1)
        if int(from_) >= int(to_):
            logger.error("Lower limit %s > upper limit %s: #%i (%s)", from_, to_, index, source)
            sys.exit(1)
    elif len(obj)>0:
        logger.error("Finalizing incomplete polygon #%i (%i points)", index, len(obj))
        sys.exit(1)
    return {"properties":{}}, []


for filename in os.listdir("./sources/txt"):
    source = urllib.unquote(filename.split(".txt")[0])
    logger.info("Reading %s", "./sources/txt/"+filename)

    data = open("./sources/txt/"+filename,"r","utf-8").readlines()

    main_aip     = "EN_AD" in filename
    cta_aip      = "ENR_2_1" in filename
    tia_aip      = "ENR_2_2" in filename
    restrict_aip = "ENR_5_1" in filename
    airsport_aip = "ENR_5_5" in filename
    sup_aip      = "en_sup" in filename

    # TODO: merge the cases
    es_enr_2_1 = "ES_ENR_2_1" in filename
    es_enr_2_2 = "ES_ENR_2_2" in filename
    es_enr_5_1 = "ES_ENR_5_1" in filename
    es_enr_5_2 = "ES_ENR_5_2" in filename

    airsport_intable = False

    if "EN_" in filename:
        country = 'EN'
        border = borders['norway']
        re_coord3 = re_coord3_no
    if "ES_" in filename:
        country = 'ES'
        border = borders['sweden']
        re_coord3 = re_coord3_se
    logger.debug("Country is %s", country)

    # this is global for all polygons
    aipname = None
    features = []
    ats_chapter = False
    alonging = False
    lastn, laste = None, None
    lastv = None
    finalcoord = False
    coords_wrap = ""

    feature = {"properties":{}}
    obj = []

    vcut = 999

    def parse(line, half=1):
        """Parse a line (or half line) of converted pdftotext"""
        line = line.strip()
        logger.debug("LINE '%s'", line)
        # TODO: make this a proper method
        global aipname, alonging, ats_chapter, coords_wrap, obj, feature
        global features, finalcoord, lastn, laste, lastv, airsport_intable
        global border, re_coord3, country

        if line==LINEBREAK:
            # drop current feature, if we don't have vertl by now, 
            # then this is just an overview polygon
            feature = {"properties":{}}
            obj = []
            alonging = False
            coords_wrap = ""
            lastv = None
            return

        if main_aip:
            if not ats_chapter:
                # skip to chapter 2.71
                if "ATS airspace" in line:
                    logger.debug("Found chapter 2.71")
                    ats_chapter=True
                return
            else:
                # then skip everything after
                if "AD 2." in line:
                #if "ATS komm" in line or "Kallesignal" in line:
                    logger.debug("End chapter 2.71")
                    ats_chapter=False

        class_=re_class.search(line) or re_class2.search(line)
        if class_:
            logger.debug("Found class in line: %s", line)
            class_=class_.groupdict()
            feature['properties']['class']=class_.get('class')

            return

        coords = re_coord.search(line)
        coords2 = re_coord2.search(line)
        coords3 = re_coord3.findall(line)
        if coords or coords2 or coords3:
            logger.debug("Found %i coords in line: %s", coords3 and len(coords3) or 1, line)
            if line.strip()[-1] == "N":
                coords_wrap += line.strip() + " "
                logger.debug("Continuing line after N coordinate: %s", coords_wrap)
                return
            elif coords_wrap:
                nline = coords_wrap + line
                logger.debug("Continued line: %s", nline)
                coords = re_coord.search(nline)
                coords2 = re_coord2.search(nline)
                coords3 = re_coord3.findall(nline)
                logger.debug("Found %i coords in merged line: %s", coords3 and len(coords3) or '1', nline)
                line = nline
                coords_wrap = ""

            if coords:
                coords  = coords.groupdict()
                n = coords.get('n') or coords.get('cn')
                e = coords.get('e') or coords.get('ce')
                rad = coords.get('rad') 
                if not rad:
                    rad_m = coords.get('rad_m')
                    if rad_m:
                        rad = m2nm(rad_m)
                if not n or not e or not rad:
                    coords_wrap += line.strip() + " "
                    # FIXME: incomplete circle continuation is broken
                    logger.debug("Continuing line after incomplete circle: %s", coords_wrap)
                    return
                lastn, laste = n, e
                c_gen = gen_circle(n, e, rad)

                obj = merge_poly(obj, c_gen)

            elif coords2:
                coords  = coords2.groupdict()
                n = coords.get('n')
                e = coords.get('e')
                if n is None and e is None:
                    n,e = lastn, laste
                secfrom = coords.get('secfrom')
                secto = coords.get('secto')
                radfrom = coords.get('radfrom')
                radto = coords.get('rad')
                c_gen = gen_sector(n, e, secfrom, secto, radfrom, radto)

                obj = merge_poly(obj, c_gen)

            else:
                for blob in coords3:
                    ne,n,e,along,arc,rad,cn,ce = blob[:8]
                    circle = blob[8] if len(blob)==9 else None
                    logger.debug("Coords: %s", (n,e,ne,along,arc,rad,cn,ce,circle))
                    if arc:
                        arcdata = re_arc.search(line)
                        if not arcdata:
                            coords_wrap += line.strip() + " "
                            logger.debug("Continuing line after incomplete arc: %s", coords_wrap)
                            return
                        arcdata = arcdata.groupdict()
                        logger.debug("Completed arc: %s", arcdata)
                        n = arcdata['n']
                        e = arcdata['e']
                        rad = arcdata.get('rad1') or arcdata.get('rad2')
                        arc = gen_circle(n, e, rad, convert=False)
                        to_n = arcdata['n2']
                        to_e = arcdata['e2']
                        fill = fill_along((n,e),(to_n,to_e), arc)
                        lastn, laste = None, None

                        for apair in fill:
                            bn, be = ll2c(apair)
                            obj.insert(0,(bn,be))
                    elif circle:
                        coords_wrap += line.strip() + " "
                        # FIXME: incomplete circle continuation is broken
                        logger.debug("Continuing line after incomplete circle (3): %s", coords_wrap)
                        return


                    if alonging:
                        if not n and not e:
                            n, e = lastn, laste
                        fill = fill_along(alonging, (n,e), border)
                        alonging = False
                        lastn, laste = None, None
                        for bpair in fill:
                            bn, be = ll2c(bpair)
                            obj.insert(0,(bn,be))

                    if rad and cn and ce:
                        c_gen = gen_circle(cn, ce, rad)
                        obj = merge_poly(obj, c_gen)
                    if n and e:
                        lastn, laste = n, e
                        obj.insert(0,(n,e))
                    if along:
                        if not n and not e:
                            n, e = lastn, laste
                        alonging = (n,e)
                    if '(' in ne:
                        finalcoord = True
                    else:
                        finalcoord = False
                    if airsport_aip and finalcoord:
                        if feature['properties'].get('from (ft masl)') is not None:
                            feature, obj = finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, sup_aip, tia_aip)
                            lastv = None

            return

        vertl = re_vertl.search(line) or re_vertl2.search(line)
        if vertl:
            vertl=vertl.groupdict()
            logger.debug("Found vertl in line: %s\n%s", line, vertl)
            fromamsl, toamsl = None, None

            v = vertl.get('ftamsl')
            fl = vertl.get('fl')
            rmk = vertl.get('rmk')
            if rmk is not None:
                v = 15000 # HACK: rmk = "Lower limit of controlled airspace -> does not affect us"
            if fl is not None:
                v = int(fl) * 100
            if v is not None:
                if lastv is None:
                    toamsl = v
                else:
                    fromamsl = v
            else:
                fromamsl = vertl.get('gnd',vertl.get('from'))
                if fromamsl == "GND": fromamsl = 0
                toamsl = vertl.get('unl',vertl.get('to'))
                if toamsl == "UNL": toamsl = 999999
            logger.debug("From %s to %s", fromamsl, toamsl)
            if fromamsl is not None:
                feature['properties']['from (ft amsl)']=fromamsl
                feature['properties']['from (m amsl)'] = ft2m(fromamsl)
                lastv = None
                if ((cta_aip or airsport_aip or sup_aip or tia_aip) and finalcoord) or country != 'EN':
                    logger.debug("Finalizing poly: Vertl complete.")
                    feature, obj = finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, sup_aip, tia_aip)
            if toamsl is not None:
                lastv = toamsl
                feature['properties']['to (ft amsl)']=toamsl
                feature['properties']['to (m amsl)'] = ft2m(toamsl)
            return

        name = re_name.search(line) or re_name2.search(line) or re_name3.search(line)
        if name:
            name=name.groupdict()

            if restrict_aip:
                feature, obj = finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, sup_aip, tia_aip)
                lastv = None

            aipname = name.get('name')
            logger.debug("Found name '%s' in line: %s", aipname, line)
            return
        if airsport_aip and line.strip():
            logger.debug("Unhandled line in airsport_aip: %s", line)
            if wstrip(line)=="1":
                airsport_intable = True
            elif wstrip(line)=="Avinor":
                airsport_intable = False
            elif wstrip(line) != "2" and airsport_intable:
                to_amsl = feature['properties'].get('to (ft amsl)')
                logger.debug("Considering as new aipname, wrapping to_amsl (just in case): %s, %s", line, to_amsl)
                feature, obj = finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, sup_aip, tia_aip)
                if to_amsl:
                    feature['properties']['to (ft amsl)']=to_amsl
                    feature['properties']['to (m amsl)']=ft2m(to_amsl)
                aipname = wstrip(line)

    table = []
    column_parsing = []
    header_cont = False
    for line in data:
        if "\f" in line:
            column_parsing = []
        if not line.strip():
            if column_parsing and table:
                # parse rows first, then cols
                for col in xrange(0,len(table[0])):
                    for row in table:
                        parse(row[col])
                parse(LINEBREAK)
                table = []
        headers = None
        if column_parsing and not header_cont:
            row = []
            for i in xrange(0,len(column_parsing)-1):
                lcut = line[column_parsing[i]:column_parsing[i+1]].strip()
                #logger.debug("Cutting %i to %i as %s", column_parsing[i], column_parsing[i+1], lcut)
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
        if headers:
            logger.debug("Parsed header line as %s.", headers)
            logger.debug("line=%s.", line)
            vcuts = []
            for header in headers[0]:
                if header:
                    vcuts.append(line.index(header))
            vcuts.append(len(line))
            column_parsing = sorted((column_parsing + vcuts))
            continue

        # parse columns separately for table formatted files
        # use header fields to detect the vcut character limit
        if airsport_aip:
            if "Vertical limits" in line:
                vcut = line.index("Vertical limits")
            else:
                parse(line[:vcut],1)
                parse(line[vcut:vcut+16],2)
        elif restrict_aip:
            if "Vertikale grenser" in line:
                vcut = line.index("Vertikale grenser")
            else:
                parse(line[:vcut],1)
                parse(line[vcut:],2)
        elif cta_aip:
            if "Tjenesteenhet" in line:
                vcut = line.index("Tjenesteenhet")
            else:
                parse(line[:vcut],1)
                #parse(line[vcut:],2)
        elif tia_aip:
            if "Unit providing" in line:
                vcut = line.index("Unit providing")
            else:
                parse(line[:vcut],1)
                #parse(line[vcut:],2)
        else:
            parse(line,1)


    feature, obj = finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, sup_aip, tia_aip)
    collection.extend(features)

logger.info("%i Features", len(collection))

# Add LonLat conversion to each feature

for feature in collection:
    geom = feature['geometry']
    geo_ll=[c2ll(c) for c in geom]
    feature['geometry_ll']=geo_ll
    feature['area']=shgeo.Polygon(geo_ll).area

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

# OpenAIR output

logger.info("Converting to OpenAIR")
airft = open("result/luftrom.ft.txt","w","utf-8")
airm = open("result/luftrom.m.txt","w","utf-8")

for feature in collection:
    properties = feature['properties']
    geom       = feature['geometry']
    class_ = properties.get('class')
    source = properties.get('source_href')
    name   = properties.get('name')
    from_  = int(properties.get('from (ft amsl)'))
    to_    = int(properties.get('to (ft amsl)'))
    from_m = int(properties.get('from (m amsl)'))
    to_m   = int(properties.get('to (m amsl)'))

    #FIXME Airspace classes according to OpenAIR:
    # *     R restricted
    # *     Q danger
    # *     P prohibited
    # *     A Class A
    # *     B Class B
    # *     C Class C
    # *     D Class D
    # *     GP glider prohibited
    # *     CTR CTR
    # *     W Wave Window
    # (TODO: G is used in the old files, is it ok to keep using it?)
    translate = {
            "A":"A",
            "B":"B",
            "C":"C",
            "D":"D",
            "R":"R",
            "P":"P",
            "G":"G",
            "Luftrom": "W"
    }
    class_ = translate.get(class_,"Q")

    for air in (airft, airm):
        air.write("AC %s\n" % class_)
        air.write("AN %s\n" % name)
    airft.write("AL %s ft\n" % from_)
    airft.write("AH %s ft\n" % to_)
    airm.write("AL %s MSL\n" % from_m)
    airm.write("AH %s MSL\n" % to_m)
    for air in (airft, airm):
        for point in geom:
            air.write("DP %s\n" % c2air(point))
        air.write("* Source: %s\n" % source)
        air.write("*\n*\n")

for air in (airft, airm):
    air.close()


# GeoJSON output, to KML via ogr2ogr

logger.info("Converting to GeoJSON")
fc = []

for feature in collection:
    geom = feature['geometry_ll']
    if not geom:
        logger.error("Feature without geometry: %s", feature)
        continue
    f = Feature()
    f.properties = feature['properties']
    f.properties.update({
          'fillOpacity':0.15,
        })
    class_=f.properties.get('class')
    from_ =int(f.properties.get('from (m amsl)'))
    to_ =int(f.properties.get('to (m amsl)'))
    if class_ in ['C', 'D', 'G', 'R']:
        if from_ < 500:
            f.properties.update({'fillColor':'#c04040',
                                 'color':'#c04040',
                                 'fillOpacity':0.35})
        elif from_ < 1000:
            f.properties.update({'fillColor':'#c08040',
                                 'color':'#c08040'})
        elif from_ < 2000:
            f.properties.update({'fillColor':'#c0c040',
                                 'color':'#c0c040'})
        elif from_ < 4000:
            f.properties.update({'fillColor':'#40c040',
                                 'color':'#40c040'})
        else:
            f.properties.update({'fillOpacity':0.0,
                                 'opacity':0.0,
                                 'color':'#ffffff'})
    elif class_ in ['Luftsport']:
        if to_ < 2000:
            f.properties.update({'fillColor':'#c0c040',
                                 'color':'#c0c040'})
        else:
            f.properties.update({'fillColor':'#40c040',
                                 'color':'#40c040'})
    else:
        logger.debug("Missing color scheme for: %s, %s", class_, from_)
    if geom[0]!=geom[-1]:
        geom.append(geom[0])
    if from_ < 4200:
        f.geometry = Polygon([geom])
        fc.append(f)

result = FeatureCollection(fc)
if len(sys.argv)>1:
    print 'http://geojson.io/#data=data:application/json,'+urllib.quote(str(result))
open("result/luftrom.geojson","w","utf-8").write(str(result))

# OpenAIP output

logger.info("Converting to OpenAIP")
out = open("result/luftrom.openaip","w","utf-8")

out.write("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<OPENAIP VERSION="367810a0f94887bf79cd9432d2a01142b0426795" DATAFORMAT="1.1">
<AIRSPACES>
""")

# TODO: OpenAIP airspace categories
#A
#B
#C
#CTR
#D
#DANGER
#E
#F
#G
#GLIDING
#OTH #Use for uncommon or unknown airspace category
#RESTRICTED
#TMA
#TMZ
#WAVE
#PROHIBITED
#FIR
#UIR
#RMZ

# TODO: use fl as unit where meaningful
for i,feature in enumerate(collection):
    poly = ",".join([" ".join([str(x) for x in pair]) for pair in feature['geometry_ll']])
    aipdata = {
            'id': i,
            'category': feature['properties']['class'],
            'name': feature['properties']['name'],
            'alt_from_unit': 'F',
            'alt_to_unit': 'F',
            'alt_from': feature['properties']['from (ft amsl)'],
            'alt_to': feature['properties']['to (ft amsl)'],
            'polygon': poly
        }
    out.write(u"""<ASP CATEGORY="{category}">
<VERSION>367810a0f94887bf79cd9432d2a01142b0426795</VERSION>
<ID>{id}</ID>
<COUNTRY>NO</COUNTRY>
<NAME>{name}</NAME>
<ALTLIMIT_TOP REFERENCE="MSL">
<ALT UNIT="{alt_to_unit}">{alt_to}</ALT>
</ALTLIMIT_TOP>
<ALTLIMIT_BOTTOM REFERENCE="MSL">
<ALT UNIT="{alt_from_unit}">{alt_from}</ALT>
</ALTLIMIT_BOTTOM>
<GEOMETRY>
<POLYGON>{polygon}</POLYGON>
</GEOMETRY>
</ASP>""".format(**aipdata))

out.write("""</AIRSPACES>
</OPENAIP>
""")
out.close()
