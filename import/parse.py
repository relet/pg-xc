#!/usr/bin/env python
# -*- coding: utf-8 -*-

from geojson import Feature, FeatureCollection, Polygon, load
import math
import os
import re
import sys
import urllib
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

re_name   = re.compile("^(?P<name>.* (TMA|CTA|CTR|TIZ|FIR))( cont.)?$")
re_name2  = re.compile("^(?P<name>EN [RD].*)$")
re_name3  = re.compile("^(?P<name>END.*)$")
re_class  = re.compile("Class (?P<class>.)")
re_class2 = re.compile("^(?P<class>[CDG])$")
RE_NE     = '(?P<ne>\(?(?P<n>\d+)N\s+(?P<e>\d+)E\)?)'
re_coord  = re.compile(RE_NE + " - (A circle(,| with)? r|R)adius (?P<rad>[\d\.,]+) NM")
RE_CIRCLE2 = 'A circle, radius (?P<rad>[\d\.]+) NM cente?red on (?P<cn>\d+)N\s+(?P<ce>\d+)E'
RE_SECTOR = RE_NE + ' - (A s|S)ector (?P<secfrom>\d+)° - (?P<secto>\d+)° \(T\), radius ((?P<radfrom>[\d\.,]+) - )?(?P<rad>[\d\.,]+) NM'
re_coord2 = re.compile(RE_SECTOR)
re_coord3 = re.compile(RE_NE+"|(?P<along>along)|(?P<onlye>\d+)E|"+RE_CIRCLE2)
re_vertl  = re.compile("(?P<from>GND|\d+) to (?P<to>UNL|\d+)( FT AMSL)?")
re_vertl2 = re.compile("((?P<ftamsl>\d+) FT AMSL)|(?P<gnd>GND)|(?P<unl>UNL)|(FL (?P<fl>\d+))|(?P<rmk>See (remark|RMK))")

CIRCLE_APPROX_POINTS = 32
RAD_EARTH = 6371000.0
PI2 = math.pi * 2
DEG2RAD = PI2 / 360.0

def c2ll(c):
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
    return int(float(f) * 0.3048)

def nm2m(nm):
    try:
        return float(nm) * 1852.0
    except:
        return float(nm.replace(",",".")) * 1852.0

def gen_circle(n, e, rad):
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
        circle.append(ll2c((lon2 / DEG2RAD, lat2 / DEG2RAD)))
    return circle

def gen_sector(n, e, secfrom, secto, radfrom, radto):
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
    return isector + osector

def closest_index(ne, points):
    mindist = 99999
    index = None
    lon,lat = c2ll(ne)
    for i in xrange(len(points)):
        plon,plat=c2ll(points[i])
        d = abs(lon-plon)+abs(lat-plat)
        if d < mindist:
            mindist = d
            index = i
    logger.debug("closest_index to %s is %i", ne, index)
    return index

norge_fc = load(open("fastland.geojson","r"))
norge = norge_fc.features[0].geometry.coordinates[0]
logger.debug("Norway has %i points.", len(norge))
def fill_along(llf, llt):
    logger.debug("fill_along %s %s", llf, llt)
    minfrom = 99999
    minto   = 99999
    fromindex = None
    toindex = None
    for i in xrange(len(norge)):
        lon,lat = norge[i]
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
        return norge[fromindex:toindex+1:-1]
    else:
        return norge[fromindex:toindex+1]

collection = []
coords_wrap = ""

def wstrip(s):
    return re.sub(' +',' ',s.strip())

def finalize(feature, features, obj, source, aipname, norway_aip, restrict_aip):
    feature['properties']['source_href']=source
    feature['geometry'] = obj
    aipname = wstrip(str(aipname))
    if norway_aip or restrict_aip or airsport_aip or len(features)==0:
        feature['properties']['name']=aipname
    else:
        feature['properties']['name']=aipname + " " + str(len(features)+1)
    if 'TIZ' in str(aipname):
        feature['properties']['class']='G'
    elif 'CTR' in str(aipname):
        feature['properties']['class']='D'
    elif 'EN R' in str(aipname) or 'EN D' in str(aipname) or 'END' in str(aipname):
        feature['properties']['class']='R'
    elif 'TMA' in str(aipname) or 'CTA' in str(aipname) or 'FIR' in str(aipname):
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

    data = open("./sources/txt/"+filename,"r").readlines()

    main_aip = "EN_AD" in filename
    norway_aip = "ENR_2_1" in filename
    restrict_aip = "ENR_5_1" in filename
    airsport_aip = "ENR_5_5" in filename
    airsport_intable = False

    # this is global for all polygons
    aipname = None
    features = []
    ats_chapter = False
    alonging = False
    lastn, laste = None, None
    lastv = None
    finalcoord = False

    feature = {"properties":{}}
    obj = []

    vcut = 999

    def parse(line):
        logger.debug("LINE '%s'", line)
        # TODO: make this a proper method
        global aipname, alonging, ats_chapter, coords_wrap, obj, feature
        global features, finalcoord, lastn, laste, lastv, airsport_intable

        if main_aip:
            if not ats_chapter:
                # skip to chapter 2.71
                if "ATS luftrom" in line:
                    logger.debug("Found chapter 2.71")
                    ats_chapter=True
                return
            else:
                # then skip everything after
                if "ATS komm" in line or "Kallesignal" in line:
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
            logger.debug("Found coords in line: %s", line)
            if line.strip()[-1] == "N":
                logger.debug("Continuing line after N coordinate")
                coords_wrap += line.strip() + " "
                return
            elif coords_wrap:
                nline = coords_wrap + line
                logger.debug("Continued line after N coordinate: %s", nline)
                coords = re_coord.search(line)
                coords3 = re_coord3.findall(nline)
                coords_wrap = ""

            if coords:
                coords  = coords.groupdict()
                n = coords.get('n')
                e = coords.get('e')
                rad = coords.get('rad')
                c_gen = gen_circle(n, e, rad)

                for cpair in c_gen:
                    obj.insert(0,cpair)

            elif coords2:
                coords  = coords2.groupdict()
                n = coords.get('n')
                e = coords.get('e')
                secfrom = coords.get('secfrom')
                secto = coords.get('secto')
                radfrom = coords.get('radfrom')
                radto = coords.get('rad')
                c_gen = gen_sector(n, e, secfrom, secto, radfrom, radto)

                for cpair in c_gen:
                    obj.insert(0,cpair)

            else:
                for ne,n,e,along,onlye,rad,cn,ce in coords3:
                    logger.debug("Coords: %s", (n,e,along,ne,rad,cn,ce))
                    if alonging:
                        if not n and not e:
                            n, e = lastn, laste
                        fill = fill_along(c2ll(alonging), c2ll((n,e)))
                        alonging = False
                        lastn, laste = None, None
                        for border in fill:
                            bn, be = ll2c(border)
                            obj.insert(0,(bn,be))

                    if rad and cn and ce:
                        c_gen = gen_circle(cn, ce, rad)
                        if len(obj):
                            ci_to=closest_index(obj[-1], c_gen)
                            ci_from=closest_index(obj[0], c_gen)
                        else:
                            ci_from=0
                            ci_to=len(c_gen)
                        if ci_to > ci_from:
                            points = c_gen[ci_from:ci_to]
                        else: 
                            points = c_gen[ci_from:] + c_gen[:ci_to]
                        for cpair in points:
                            obj.insert(0,cpair)
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
                            feature, obj = finalize(feature, features, obj, source, aipname, norway_aip, restrict_aip)
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
                if norway_aip or (airsport_aip and finalcoord):
                    feature, obj = finalize(feature, features, obj, source, aipname, norway_aip, restrict_aip)
            if toamsl is not None:
                lastv = toamsl
                feature['properties']['to (ft amsl)']=toamsl
                feature['properties']['to (m amsl)'] = ft2m(toamsl)
            return

        name = re_name.search(line) or re_name2.search(line) or re_name3.search(line)
        if name:
            name=name.groupdict()

            if restrict_aip:
                feature, obj = finalize(feature, features, obj, source, aipname, norway_aip, restrict_aip)
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
                feature, obj = finalize(feature, features, obj, source, aipname, norway_aip, restrict_aip)
                if to_amsl:
                    feature['properties']['to (ft amsl)']=to_amsl
                    feature['properties']['to (m amsl)']=ft2m(to_amsl)
                aipname = wstrip(line)

    for line in data:
        # parse columns separately for table formatted files
        # use header fields to detect the vcut character limit
        if airsport_aip:
            if "Vertical limits" in line:
                vcut = line.index("Vertical limits")
            else:
                parse(line[:vcut])
                parse(line[vcut:vcut+16])
        elif restrict_aip:
            if "Vertikale grenser" in line:
                vcut = line.index("Vertikale grenser")
            else:
                parse(line[:vcut])
                parse(line[vcut:])
        elif norway_aip:
            if "Tjenesteenhet" in line:
                vcut = line.index("Tjenesteenhet")
            else:
                parse(line[:vcut])
                parse(line[vcut:])
        else:
            parse(line)


    feature, obj = finalize(feature, features, obj, source, aipname, norway_aip, restrict_aip)
    collection.extend(features)

logger.info("%i Features", len(collection))

# TODO: output formats in original coordinates

# GeoJSON output, to KML via ogr2ogr

logger.info("Converting to GeoJSON")
fc = []

if len(sys.argv)>1:
    try:
        x = int(sys.argv[1])
        collection = [collection[x]]
    except:
        filt = sys.argv[1]
        collection = [x for x in collection if x.get('properties',{}).get('name') is not None and filt in x.get('properties').get('name','')]

for feature in collection:
    geom = feature['geometry']
    if not geom:
        logger.error("Feature without geometry: %s", feature)
        continue
    f = Feature()
    f.properties = feature['properties']
    f.properties.update({
          'fill-opacity':0.5,
        })
    class_=f.properties.get('class')
    from_ =int(f.properties.get('from (m amsl)'))
    to_ =int(f.properties.get('to (m amsl)'))
    if class_ in ['C', 'D', 'G', 'R']:
        if from_ < 500:
            f.properties.update({'fill':'#c04040',
                                 'stroke':'#c04040'})
        elif from_ < 1000:
            f.properties.update({'fill':'#c08040',
                                 'stroke':'#c08040'})
        elif from_ < 2000:
            f.properties.update({'fill':'#c0c040',
                                 'stroke':'#c0c040'})
        elif from_ < 4000:
            f.properties.update({'fill':'#40c040',
                                 'stroke':'#40c040'})
        else:
            f.properties.update({'fill-opacity':'0.0',
                                 'stroke-opacity':'0.0'})
    elif class_ in ['Luftsport']:
        if to_ < 2000:
            f.properties.update({'fill':'#c0c040',
                                 'stroke':'#c0c040'})
        else:
            f.properties.update({'fill':'#40c040',
                                 'stroke':'#40c040'})
    else:
        logger.debug("Missing color scheme for: %s, %s", class_, from_)
    if geom[0]!=geom[-1]:
        geom.append(geom[0])
    if from_ < 4000:
        f.geometry = Polygon([[c2ll(c) for c in geom]])
        fc.append(f)

result = FeatureCollection(fc)
if len(sys.argv)>1:
    open("result.geojson","w").write(str(result))
    print 'http://geojson.io/#data=data:application/json,'+urllib.quote(str(result))
else:
    print result