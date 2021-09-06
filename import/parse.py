#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# FIXME: Swedish files list all relevant airspace for each airport, ignore duplicates


from codecs import open
from copy import deepcopy
from geojson import load
import os
import re
import sys
import urllib
import logging

from shapely.geometry import Polygon

from targets import geojson, openaip, openair, xcontest
from util.utils import *

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
init_utils(logger)

# Lines containing these are usually recognized as names
re_name   = re.compile("^\s*(?P<name>[^\s]* ((Centre|West|North|South|East| Norway) )?(TRIDENT|ADS|HTZ|AOR|ATZ|FAB|TMA|TIA|TIA/RMZ|CTA|CTR|CTR,|TIZ|FIR|CTR/TIZ|TIZ/RMZ)( (West|Centre|[a-z]))?|[^\s]*( ACC sector| ACC Oslo|ESTRA|EUCBA|RPAS).*)( cont.)?\s*($|\s{5}|.*FIR)")
re_name2  = re.compile("^\s*(?P<name>E[NS] [RD].*)\s*$")
re_name3  = re.compile("^\s*(?P<name>E[NS]D\d.*)\s*$")
re_name4  = re.compile("Navn og utstrekning /\s+(?P<name>.*)$")
re_name5  = re.compile("^(?P<name>Sector .*)$")
re_name6  = re.compile("^(?P<name>Norway ACC .*)$")
re_name_cr  = re.compile("^Area Name: \((?P<name>EN .*)\) (?P<name_cont>.*)$")
re_miscnames  = re.compile("^(?P<name>Hareid .*)$")

# Lines containing these are usually recognized as airspace class
re_class  = re.compile("Class:? (?P<class>.)")
re_class2 = re.compile("^(?P<class>[CDG])$")

# Coordinates format, possibly in brackets
RE_NE     = '(?P<ne>\(?(?P<n>[\d\.]{5,10})N(?: N)?(?:\s+|-)(?P<e>[\d\.]+)[E\)]+)'
RE_NE2    = '(?P<ne2>\(?(?P<n2>\d+)N\s+(?P<e2>\d+)E\)?)'
# Match circle definitions, see log file for examples
re_coord  = re.compile("(?:" + RE_NE + " - )?(?:\d\. )?(?:A circle(?: with|,)? r|R)adius (?:(?P<rad>[\d\.,]+) NM|(?P<rad_m>[\d]+) m)(?: \([\d\.,]+ k?m\))?(?: cente?red on (?P<cn>\d+)N\s+(?P<ce>\d+)E)?")
# Match sector definitions, see log file for examples
RE_SECTOR = u'('+RE_NE + u' - )?((\d\. )?A s|S)ector (?P<secfrom>\d+)° - (?P<secto>\d+)° \(T\), radius ((?P<radfrom>[\d\.,]+) - )?(?P<rad>[\d\.,]+) NM'
re_coord2 = re.compile(RE_SECTOR)
# Match all other formats in a coordinate list, including "along border" syntax
RE_CIRCLE = 'A circle(?: with|,) radius (?P<rad>[\d\.]+) NM cente?red on (?P<cn>\d+)N\s+(?P<ce>\d+)E'
re_coord3_no = re.compile(RE_NE+"|(?P<along>along)|(?P<arc>(?:counter)?clockwise)|(?:\d+)N|(?:\d{4,10})E|"+RE_CIRCLE)
re_coord3_se = re.compile(RE_NE+"|(?P<along>border)|(?P<arc>(?:counter)?clockwise)|(?:\d+)N|(?:\d{4,10})E|"+RE_CIRCLE+"|(?P<circle>A circle)|(?:radius)")
# clockwise along an arc of 16.2 NM radius centred on 550404N 0144448E - 545500N 0142127E
re_arc = re.compile('(?P<dir>(counter)?clockwise) along an arc (?:of (?P<rad1>[\d\.,]+) NM radius )?centred on '+RE_NE+'(?:( and)?( with)?( radius) (?P<rad2>[ \d\.,]+) NM(?: \([\d\.]+ k?m\))?)? (?:- )'+RE_NE2)

#TODO: along the latitude ...

# Lines containing these are box ceilings and floors
re_vertl_upper = re.compile("Upper limit:\s+(FL\s+(?P<flto>\d+)|(?P<ftamsl>\d+)\s+FT\s+AMSL)($|\s{5})")
re_vertl_lower = re.compile("ower limit:\s+(FL\s+(?P<flfrom>\d+)|(?P<ftamsl>\d+)\s+FT\s+AMSL|(?P<msl>MSL))($|\s{5})")
re_vertl  = re.compile("(?P<from>GND|\d{3,6}) (?:(?:til/)?to|-) (?P<to>UNL|\d{3,6})( [Ff][Tt] AMSL)?")
re_vertl_td  = re.compile(u"(?:(?:(?:FL\s?)?(?P<flfrom>\d+))|(?:(?P<ftamsl>\d+) ?FT)) [–-] FL\s?(?P<flto>\d+).*")
re_vertl_td2  = re.compile("(?P<ftamsl>\d+) ?FT")
re_vertl2 = re.compile("((?P<ftamsl>\d+)\s?[Ff][Tt] (A?MSL|GND))|(?P<gnd>GND)|(?P<unl>UNL)|(FL\s?(?P<fl>\d+))|(?P<rmk>See (remark|RMK))")
re_vertl3 = re.compile("((?P<ftamsl>\d+) FT$)")

# temporary airspace 
RE_MONTH = "(?:JAN|FEB|MAR|APR|MAI|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
re_period = re.compile("Active from (?P<pfrom>\d+ "+RE_MONTH+") (?P<ptimefrom>\d+)")
re_period2 = re.compile("^(?P<pto>\d+ "+RE_MONTH+") (?P<ptimeto>\d+)")
re_period3 = re.compile("Established for (?P<pfrom>\d+ "+RE_MONTH+") - (?P<pto>\d+ "+RE_MONTH+")")

# FREQUENCIES
re_freq = re.compile('(?P<freq>\d+\.\d+ MHZ)')

# COLUMN PARSING:
rexes_header_es_enr = [re.compile("(?:(?:(Name|Identification)|(Lateral limits)|(Vertical limits)|(C unit)|(Freq MHz)|(Callsign)|(AFIS unit)|(Remark)).*){%i}" % mult) \
                           for mult in reversed(range(3,8))]

LINEBREAK = '--linebreak--'

# define polygons for the country borders
norway_fc = load(open("norway.geojson","r"))
norway = norway_fc.features[0].geometry.coordinates[0]
logger.debug("Norway has %i points.", len(norway))

sweden_fc = load(open("fastland-sweden.geojson","r"))
sweden = sweden_fc.features[0].geometry.coordinates[0]
logger.debug("Sweden has %i points.", len(sweden))

borders = {
        'norway': norway,
        'sweden': sweden
}

collection = []
completed = {}
names = {} 
accsectors = []

def finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, aip_sup, tia_aip):
    """Complete and sanity check a feature definition"""
    global completed
    global country
    global end_notam

    feature['properties']['source_href']=source
    feature['properties']['country']=country
    feature['geometry'] = obj
    aipname = wstrip(str(aipname))
    if aipname == 'EN D476':
        aipname = 'EN D476 R og B 1'
    if aipname == 'EN D477':
        aipname = 'EN D477 R og B 2'

    if 'ACC' in aipname and country=="ES":
        return {"properties":{}}, []
    for ignore in ['ADS','AOR','FAB',' FIR','HTZ']:
        if ignore in aipname:
            logger.debug("Ignoring: %s", aipname)
            return {"properties":{}}, []
    feature['properties']['name']=aipname
    if cta_aip or aip_sup or tia_aip or 'ACC' in aipname or 'Notodden' in aipname:
        recount = len([f for f in features if aipname in f['properties']['name']])
        recount = recount or len([f for f in accsectors if aipname in f['properties']['name']])
        if recount>0:
            separator = " " 
            if re.search('\d$', aipname): 
                separator="-"
            logger.debug("RECOUNT renamed " + aipname + " INTO " + aipname + separator + str(recount+1))                    
            feature['properties']['name']=aipname + separator + str(recount+1)
    if 'TIZ' in aipname or 'TIA' in aipname or 'CTR' in aipname:
        feature['properties']['class']='G'
    elif 'TRIDENT' in aipname \
        or 'EN D' in aipname or 'END' in aipname \
        or 'ES D' in aipname:
        feature['properties']['class']='D'
    elif 'EN R' in aipname \
      or 'ES R' in aipname or 'ESTRA' in aipname \
      or 'EUCBA' in aipname or 'RPAS' in aipname:
        feature['properties']['class']='R'
    elif 'TMA' in aipname or 'CTA' in aipname or 'FIR' in aipname \
      or 'ACC' in aipname or 'ATZ' in aipname or 'FAB' in aipname \
      or 'Sector' in aipname:
        feature['properties']['class']='C'
    elif '5.5' in source or "Hareid" in aipname:
        if "Nidaros" in aipname:
            #skip old Nidaros airspace
            return {"properties":{}}, []
        feature['properties']['class']='Luftsport'
    index = len(collection)+len(features)

    if names.get(aipname):
        logger.debug("DUPLICATE NAME: %s", aipname)

    if len(obj)>100:
        logger.debug("COMPLEX POLYGON %s with %i points", feature['properties'].get('name'), len(obj))
        obj=simplify_poly(obj, 100)
        feature['geometry'] = obj

    if len(obj)>3:
        logger.debug("Finalizing polygon #%i %s with %i points.", index, feature['properties'].get('name'), len(obj))

        name   = feature['properties'].get('name')
        source = feature['properties'].get('source_href')
        from_  = feature['properties'].get('from (ft amsl)')
        to_    = feature['properties'].get('to (ft amsl)')
        class_ = feature['properties'].get('class')


        if name in completed:
            logger.info("ERROR Duplicate feature name: #%i %s", index, name)
            return {"properties":{}}, []
            #sys.exit(1)
        else:
            if 'ACC' in aipname:
                logger.debug("Writing ACC sector to separate file: %s", aipname)
                accsectors.append(feature)
            else:
                features.append(feature)

        # SANITY CHECK
        if name is None:
            logger.error("Feature without name: #%i", index)
            sys.exit(1)
        if "None" in name:
            logger.error("Feature without name: #%i", index)
            sys.exit(1)
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
        # SPECIAL CASE NOTAM reserved ENR in Oslo area
        if "EN R" in aipname and "Kongsvinger" in aipname:
          feature['properties']['notam_only'] = 'true'
        if "EN R" in aipname and ("Romerike" in aipname or ("Oslo" in aipname and not "102" in aipname)):
          feature['properties']['notam_only'] = 'true'
          feature['properties']['from (ft amsl)'] = '0'
          feature['properties']['to (ft amsl)'] = '99999' # unspecified
          feature['properties']['from (m amsl)'] = '0'
          feature['properties']['to (m amsl)'] = '99999'
          from_ = '0'
          to_ = '0'
        if ("EN D" in aipname or "END" in aipname) and end_notam:
          feature['properties']['notam_only'] = 'true'
        if from_ is None:
            if "en_sup_a_2018_015_en" in source:
                feature['properties']['from (ft amsl)']='0'
                feature['properties']['from (m amsl)']='0'
                from_ = '0'
            else:
                logger.error("Feature without lower limit: #%i (%s)", index, source)
                sys.exit(1)
        if to_ is None:
            if "en_sup_a_2018_015_en" in source:
                feature['properties']['to (ft amsl)']='99999'
                feature['properties']['to (m amsl)']='9999'
                to_ = '99999'
            else:
                logger.error("Feature without upper limit: #%i (%s)", index, source)
                sys.exit(1)
        if int(from_) >= int(to_):
            # SPECIAL CASE NOTAM reserved ENR in Oslo area
            if "en_sup_a_2018_015_en" in source or "Romerike" in aipname or "Oslo" in aipname:
                feature['properties']['from (ft amsl)']=to_
                feature['properties']['to (ft amsl)']=from_
            else:
                logger.error("Lower limit %s > upper limit %s: #%i (%s)", from_, to_, index, source)
                sys.exit(1)
    elif len(obj)>0:
        logger.error("ERROR Finalizing incomplete polygon #%i (%i points)", index, len(obj))

    names[aipname]=True
    logger.debug("OK polygon #%i %s with %i points (%s-%s).", index, feature['properties'].get('name'), 
                                                                     len(obj), 
                                                                     feature['properties'].get('from (ft amsl)'),
                                                                     feature['properties'].get('to (ft amsl)'))
    return {"properties":{}}, []


for filename in os.listdir("./sources/txt"):
    source = urllib.parse.unquote(filename.split(".txt")[0])
    if ".swp" in filename: 
        continue
    logger.info("Reading %s", "./sources/txt/"+filename)

    data = open("./sources/txt/"+filename,"r","utf-8").readlines()

    ad_aip       = "-AD-" in filename or "_AD_" in filename
    cta_aip      = "ENR-2.1" in filename
    tia_aip      = "ENR-2.2" in filename
    restrict_aip = "ENR-5.1" in filename
    military_aip = "ENR-5.2" in filename
    airsport_aip = "ENR-5.5" in filename
    aip_sup      = "en_sup" in filename
    es_aip_sup   = "aro.lfv.se" in filename and "editorial" in filename
    cold_resp    = "en_sup_a_2020" in filename
    valldal      = "valldal" in filename

    # TODO: merge the cases
    es_enr_2_1 = "ES_ENR_2_1" in filename
    es_enr_2_2 = "ES_ENR_2_2" in filename
    es_enr_5_1 = "ES_ENR_5_1" in filename
    es_enr_5_2 = "ES_ENR_5_2" in filename
    en_enr_5_1 = "EN_ENR_5_1" in filename

    airsport_intable = False

    if "EN_" or "en_" in filename:
        country = 'EN'
        border = borders['norway']
        re_coord3 = re_coord3_no
    if "ES_" in filename or "aro.lfv.se" in filename:
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
    sectors = []
    name_cont = False

    feature = {"properties":{}}
    obj = []

    vcut = 999
    vend = 1000

    def parse(line, half=1):
        """Parse a line (or half line) of converted pdftotext"""
        line = line.strip()
        logger.debug("LINE '%s'", line)

        global aipname, alonging, ats_chapter, coords_wrap, obj, feature
        global features, finalcoord, lastn, laste, lastv, airsport_intable
        global border, re_coord3, country 
        global sectors, name_cont, cold_resp

        if line==LINEBREAK:
            # drop current feature, if we don't have vertl by now,
            # then this is just an overview polygon
            feature = {"properties":{}}
            obj = []
            alonging = False
            coords_wrap = ""
            lastv = None
            return


        if ad_aip:
            if not ats_chapter:
                # skip to chapter 2.71
                if "ATS airspace" in line or "ATS AIRSPACE" in line:
                    logger.debug("Found chapter 2.71")
                    ats_chapter=True
                return
            else:
                # then skip everything after
                if "AD 2." in line or "ATS COMM" in line:
                #if "ATS komm" in line or "Kallesignal" in line:
                    logger.debug("End chapter 2.71")
                    ats_chapter=False

        class_=re_class.search(line) or re_class2.search(line)
        if class_:
            logger.debug("Found class in line: %s", line)
            class_=class_.groupdict()
            feature['properties']['class']=class_.get('class')
            if tia_aip:
                feature, obj = finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
            return

        # SPECIAL CASE temporary workaround KRAMFORS
        if aipname and ("KRAMFORS" in aipname) and ("within" in line):
            return
        # SPECIAL CASE workaround SÄLEN/SAAB CTR sectors
        if aipname and (("SÄLEN" in aipname) or ("SAAB" in aipname)) and ("Sector" in line):
            logger.debug("TEST: Breaking up SÄLEN/SAAB, aipname=."+aipname)
            sectors.append((aipname, obj))
            feature, obj =  {"properties":{}}, []
            if "SÄLEN" in aipname:
                aipname = "SÄLEN CTR "+line
            else:
                aipname = "SAAB CTR "+line
        # SPECIAL CASE check for Valldal AIP names
        if valldal and 'Valldal' in line:
            aipname=" ".join(line.strip().split()[0:2])
            logger.debug("Valldal aipname: '%s'", aipname)
            feature['properties']['class']='Luftsport'
            feature['properties']['from (ft amsl)']=0
            feature['properties']['from (m amsl)'] =0

        # IDENTIFY coordinates
        coords = re_coord.search(line)
        coords2 = re_coord2.search(line)
        coords3 = re_coord3.findall(line)

        if (coords or coords2 or coords3):

            logger.debug("Found %i coords in line: %s", coords3 and len(coords3) or 1, line)
            logger.debug(printj(coords3))
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

            if coords and not ("Lyng" in aipname or "Halten" in aipname):
                coords  = coords.groupdict()
                n = coords.get('cn') or coords.get('n')
                e = coords.get('ce') or coords.get('e')
                #n = coords.get('n') or coords.get('cn')
                #e = coords.get('e') or coords.get('ce')
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
                logger.debug("Circle center is %s %s %s %s", coords.get('n'), coords.get('e'), coords.get('cn'), coords.get('ce'))
                logger.debug("COORDS is %s", json.dumps(coords))
                c_gen = gen_circle(n, e, rad)
                logger.debug("LENS %s %s", len(obj), len(c_gen))
                obj = merge_poly(obj, c_gen)
                logger.debug("LENS %s %s", len(obj), len(c_gen))

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
                skip_next = 0
                for blob in coords3:
                    ne,n,e,along,arc,rad,cn,ce = blob[:8]
                    circle = blob[8] if len(blob)==9 else None
                    logger.debug("Coords: %s", (n,e,ne,along,arc,rad,cn,ce,circle))
                    if skip_next > 0 and n:
                        logger.debug("Skipped.")
                        skip_next -= 1
                        continue
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
                        cw = arcdata['dir']
                        logger.debug("ARC IS "+cw)
                        fill = fill_along(obj[-1],(to_n,to_e), arc, (cw=='clockwise'))
                        lastn, laste = None, None

                        for apair in fill:
                            bn, be = ll2c(apair)
                            obj.insert(0,(bn,be))
                        skip_next = 1
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
                        #HACK matching point in the wrong direction - FIXME don't select closest but next point in correct direction
                        if "Sälen TMA b" in aipname or "SÄLEN CTR Sector b" in aipname:
                            fill=fill[1:]
                        for bpair in fill:
                            bn, be = ll2c(bpair)
                            obj.insert(0,(bn,be))

                    if rad and cn and ce:
                        c_gen = gen_circle(cn, ce, rad)
                        logger.debug("Merging circle using cn, ce.")
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
                        logger.debug("Found final coord.")
                    else:
                        finalcoord = False
                    if (airsport_aip or aip_sup or military_aip or cold_resp) and finalcoord:
                        if feature['properties'].get('from (ft amsl)') is not None:
                            logger.debug("Finalizing: finalcoord.")
                            feature, obj = finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
                            lastv = None

            if not valldal:
                return

        # IDENTIFY temporary restrictions
        period = re_period.search(line) or re_period2.search(line) or re_period3.search(line)

        if cold_resp and period:
            period = period.groupdict()
            logger.debug("Found period in line: %s", period)
            feature['properties']['temporary'] = True
            feature['properties']['dashArray'] = "5 5"
            pfrom = period.get('pfrom')
            if pfrom is not None:
                ppfrom = feature['properties'].get('Date from',[])
                feature['properties']['Date from'] = ppfrom + [pfrom]
            pto = period.get('pto')
            if pto is not None:
                ppto = feature['properties'].get('Date until',[])
                feature['properties']['Date until'] = ppto + [pto]
            ptimefrom = period.get('ptimefrom')
            if ptimefrom is not None:
                feature['properties']['Time from (UTC)'] = ptimefrom
            ptimeto = period.get('ptimeto')
            if ptimeto is not None:
                feature['properties']['Time to (UTC)'] = ptimeto
            if pto is not None:
                logger.debug("Finalizing COLD_RESP polygon with time to")
                feature, obj = finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
            return

        # IDENTIFY frequencies
        freq = re_freq.search(line)
        if freq:
            freq = freq.groupdict()
            logger.debug("Found FREQUENCY: %s", freq['freq'])
            feature['properties']['frequency'] = freq.get('freq')

        # IDENTIFY altitude limits
        vertl = re_vertl_upper.search(line) or re_vertl_lower.search(line) or re_vertl.search(line) or re_vertl2.search(line) or (military_aip and re_vertl3.search(line))

        if vertl:
            vertl = vertl.groupdict()
            logger.debug("Found vertl in line: %s", vertl)
            fromamsl, toamsl = None, None

            v = vertl.get('ftamsl')
            flfrom = vertl.get('flfrom')
            flto = vertl.get('flto')
            fl = vertl.get('fl')
            rmk = vertl.get('rmk')

            if rmk is not None:
                v = 14999 # HACK: rmk = "Lower limit of controlled airspace -> does not affect us"
            if fl is not None:
                logger.debug("CHECK 4 read FL")
                v = int(fl) * 100

            if flto is not None:
                logger.debug("CHECK 5 read FL")
                toamsl   = int(flto) * 100
                if flfrom:
                    fromamsl = v or (int(flfrom) * 100)
                    fl = fl or flfrom
            elif flfrom is not None:
                logger.debug("CHECK 6 read FL")
                fromamsl = int(flfrom) * 100
                fl = fl or flfrom
            elif v is not None:
                if lastv is None:
                    toamsl = v
                    if fl is not None:
                        flto = fl
                else:
                    fromamsl = v
            else:
                fromamsl = vertl.get('msl',vertl.get('gnd',vertl.get('from')))
                if fromamsl == "GND": fromamsl = 0
                if fromamsl == "MSL": fromamsl = 0
                toamsl = vertl.get('unl',vertl.get('to'))
                if toamsl == "UNL": toamsl = 999999

            if toamsl is not None:
                lastv = toamsl
                currentv = feature['properties'].get('to (ft amsl)')
                if currentv is not None and currentv != toamsl:
                    logger.warning("attempt to overwrite vertl_to %s with %s." % (currentv, toamsl))
                    if int(currentv) > int(toamsl):
                        logger.warning("skipping.")
                        return
                    logger.warning("ok.")
                if flto is not None:
                    logger.debug("CHECK used FL")
                    feature['properties']['to (fl)']=flto
                feature['properties']['to (ft amsl)']=toamsl
                feature['properties']['to (m amsl)'] = ft2m(toamsl)
                if valldal:
                    feature, obj = finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
                    lastv = None
            if fromamsl is not None:
                currentv = feature['properties'].get('from (ft amsl)')
                if currentv is not None and currentv != fromamsl:
                    logger.warning("attempt to overwrite vertl_from %s with %s." % (currentv, fromamsl))
                    if int(currentv) < int(fromamsl):
                        logger.warning("skipping.")
                        return
                    logger.warning("ok.")
                if fl is not None:
                    logger.debug("CHECK used FL")
                    feature['properties']['from (fl)']=fl
                feature['properties']['from (ft amsl)']=fromamsl
                feature['properties']['from (m amsl)'] = ft2m(fromamsl)
                lastv = None
                if (((cta_aip or airsport_aip or aip_sup or tia_aip or (aipname and ("TIZ" in aipname))) and (finalcoord or tia_aip_acc)) or country != 'EN') and not cold_resp:
                    logger.debug("Finalizing poly: Vertl complete. "+str(cold_resp))
                    if aipname and (("SÄLEN" in aipname) or ("SAAB" in aipname)) and len(sectors)>0:
                        for x in sectors[1:]: # skip the first sector, which is the union of the other sectors in Swedish docs
                            aipname_,  obj_ = x
                            logger.debug("Restoring "+aipname_+" "+str(len(sectors)))
                            feature_ = deepcopy(feature)
                            logger.debug("Finalizing SAAB/SÄLEN: " + aipname_)
                            finalize(feature_, features, obj_, source, aipname_, cta_aip, restrict_aip, aip_sup, tia_aip)
                        sectors = []
                        logger.debug("Finalizing last poly as ."+aipname)
                    feature, obj = finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
            logger.debug("From %s to %s", feature['properties'].get('from (ft amsl)'), feature['properties'].get('to (ft amsl)'))
            return

        # IDENTIFY airspace naming
        name = re_name.search(line) or re_name2.search(line) or re_name3.search(line) or re_name4.search(line) or \
               re_miscnames.search(line) or re_name5.search(line) or re_name_cr.search(line) or re_name6.search(line)

        if name_cont and not 'Real time' in line:
            aipname = aipname + " " + line
            logger.debug("Continuing name as "+aipname)
            if line == '' or 'EN D' in aipname or cold_resp:
                name_cont = False

        if name:
            named=name.groupdict()
            if en_enr_5_1 or "Hareid" in line:
                logger.debug("RESTRICT/HAREID")
                feature, obj = finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
                lastv = None

            name=named.get('name')
            if 'polaris' in name.lower() and 'norway' in name.lower():
                pos = name.lower().index('norway')
                name = name[:pos]

            if name[:6]=="Sector" and "ACC" in aipname:
               return 

            if named.get('name_cont'):
                name += ' '+named.get('name_cont')
                name_cont=True

            if (name == "Sector a") or (name == "Sector b") or (aipname and ("Sector" in aipname) and (("SÄLEN" in aipname) or ("SAAB" in aipname))):
                return
            if "ES R" in name or "ES D" in name:
                name_cont=True
            if "EN D" in name and len(name)<8:
                name_cont=True

            if restrict_aip or military_aip:
                if feature['properties'].get('from (ft amsl)') is not None and (feature['properties'].get('to (ft amsl)') or "Romerike" in aipname or "Oslo" in aipname): 
                    logger.debug("RESTRICT/MILITARY + name and vertl complete")
                    feature, obj = finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
                    lastv = None
                else:
                    logger.debug("RESTRICT/MILITARY + name and vertl NOT complete")

            aipname = name
            logger.debug("Found name '%s' in line: %s", aipname, line)
            return

        # The airsport document doesn't have recognizable airspace names
        # so we just assume every line that isn't otherwise parsed is the name of the next box.
        if airsport_aip and line.strip():
            logger.debug("Unhandled line in airsport_aip: %s", line)
            if wstrip(line)=="1":
                logger.debug("Starting airsport_aip table")
                airsport_intable = True
            elif wstrip(line)[0] != "2" and airsport_intable:
                logger.debug("Considering as new aipname: '%s'", line)
                feature, obj = finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
                aipname = wstrip(line)

    # end def parse

    # IDENTIFY document types
    table = []
    column_parsing = []
    header_cont = False
    cr_areas = False
    end_notam = False
    skip_tia = False
    tia_aip_acc = False
    vcuts = None
    skip_valldal = True

    for line in data:

        if "\f" in line:
            logger.debug("Stop column parsing, \f found")
            column_parsing = []

        if valldal:
            if line.strip() == 'Valldal Midt':
                skip_valldal = False
            if 'Varsling av aktivitet' in line:
                break
            if skip_valldal:
                continue

        if tia_aip:
            if "Norway ACC sectorization" in line:
                logger.debug("SECTORIZATION START")
                tia_aip_acc = True
                skip_tia = False
            if "Functional Airspace block" in line:
                break
            if tia_aip_acc and ("1     " in line):
                logger.debug("VCUT LINE? %s", line)
                vcuts = [m.start() for m in re.finditer('[^\s]', line)]
                vcuts=[(x and (x-2)) for x in vcuts] # HACK around annoying column shift
                logger.debug("vcuts %s", vcuts)
            if "ADS areas" in line:
                skip_tia = True
            if skip_tia:
                continue

        if aip_sup and ("Luftromsklasse" in line):
            logger.debug("Skipping end of SUP")
            break

        if country == 'ES' and 'Vinschning av sk' in line:
            logger.debug("Skipping end of document")
            break

        if cold_resp: 
            if '3. AMC and Danger' in line:
                break
            if 'Restricted areas established' in line:
                cr_areas=True
            elif not cr_areas:
                continue

        if not end_notam and 'active only as notified by NOTAM' in line:
            logger.debug("FOLLOWING danger areas are NOTAM activated.")
            end_notam = True
        
        if not line.strip() or (cold_resp and 'Area Name' in line):
            if column_parsing and table:
                # parse rows first, then cols
                for col in range(0,len(table[0])):
                    for row in table:
                        if not len(row)>col:
                            logger.debug("ERROR not in table format: row=%s, col=%s", row, col)
                            #sys.exit(1)
                        else:
                           parse(row[col])
                parse(LINEBREAK)
                table = []
        headers = None
        if column_parsing and not header_cont:
            row = []
            for i in range(0,len(column_parsing)-1):
                lcut = line[column_parsing[i]:column_parsing[i+1]].strip()
                row.append(lcut)
            table.append(row)
            continue
        elif es_enr_2_1 or es_enr_2_2 or es_enr_5_1 or es_enr_5_2 or cold_resp:
            if line.strip()=='Vertical limits': # hack around ES_ENR_2_2 malformatting
                headers = 'Vertical'
                header_cont = True
            for rex in rexes_header_es_enr:
                headers = headers or rex.findall(line)
                header_cont = False
        elif es_aip_sup and not vcuts:
            headers = True
        if headers:
            logger.debug("Parsed header line as %s.", headers)
            logger.debug("line=%s.", line)
            vcuts = []
            if cold_resp:
                vcuts = [0, 44, 65, 110]
            elif es_aip_sup:
               vcuts = [0, 45, 110]
            else:
                for header in headers[0]:
                    if header:
                        vcuts.append(line.index(header))
                vcuts.append(len(line))
            column_parsing = sorted((column_parsing + vcuts))
            logger.debug("DEBUG: column parsing: %s", vcuts)
            continue

        # parse columns separately for table formatted files
        # use header fields to detect the vcut character limit
        if tia_aip_acc and vcuts:
            for i in range(len(vcuts)-1):
                parse(line[vcuts[i]:vcuts[i+1]])
            parse(line[vcuts[len(vcuts)-1]:])
        elif airsport_aip:
            if "Vertical limits" in line:
                vcut = line.index("Vertical limits")
                vend = vcut+28
            else:
                parse(line[:vcut],1)
                parse(line[vcut:vend],2)
        elif restrict_aip or military_aip:
            if "Vertikale grenser" in line:
                vcut = line.index("Vertikale grenser")
                vend = vcut+16
                if "Aktiviseringstid" in line:
                    vend = line.index("Aktiviseringstid")
            else:
                parse(line[:vcut],1)
                if military_aip:
                    parse(line[vcut:vend],2)
                else:
                    parse(line[vcut:],2)
        elif cta_aip:
            if "Tjenesteenhet" in line:
                vcut = line.index("Tjenesteenhet")
            else:
                parse(line[:vcut],1)
        elif tia_aip and not tia_aip_acc:
            if "Unit providing" in line:
                vcut = line.index("Unit providing")
            else:
                parse(line[:vcut],1)
        else:
            parse(line,1)

    if "nidaros" in source:
        aipname = "Nidaros"
        feature['properties']['from (ft amsl)'] = 0
        feature['properties']['from (m amsl)'] = 0
        feature['properties']['to (ft amsl)']= 3500
        feature['properties']['to (m amsl)'] = ft2m(3500)
        feature['properties']['class'] = 'Luftsport'

    logger.debug("Finalizing: end of doc.")
    feature, obj = finalize(feature, features, obj, source, aipname, cta_aip, restrict_aip, aip_sup, tia_aip)
    collection.extend(features)

logger.info("%i Features", len(collection))

# Add LonLat conversion to each feature

def geoll(feature):
    name=feature['properties']['name']

    geom = feature['geometry']
    geo_ll=[c2ll(c) for c in geom]
    feature['geometry_ll']=geo_ll

    #print("POSTPROCESSING POLYGON",name)
    sh_geo = Polygon(geo_ll)

    if not sh_geo.is_valid:
        print("INVALID POLYGON",name)
        if 'RAVLUNDA' in name:
            # this is hard to fix and far away
            sh_geo = sh_geo.convex_hull
        else:
            sh_geo = sh_geo.buffer(0)

        if not sh_geo.is_valid:
            print("ERROR: POLYGON REMAINS INVALID")
            print(sh_geo.is_valid)
            sys.exit(1)
        feature['geometry_ll']=list(sh_geo.exterior.coords)
    feature['area']=Polygon(geo_ll).area
    
for feature in collection:
    geoll(feature)
for feature in accsectors:
    geoll(feature)

# TEST: intersect all polygons to remove overlaps
# dissection = dissect(collection)

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

# Output file formats
geojson.dumps(logger, "result/luftrom", collection)
openaip.dumps(logger, "result/luftrom", collection)
openair.dumps(logger, "result/luftrom", collection)
xcontest.dumps(logger, "result/xcontest", collection)

# output ACC sectors into a separate file
geojson.dumps(logger, "result/accsectors", accsectors)
