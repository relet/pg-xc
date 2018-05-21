#!/usr/bin/env python
# -*- coding: utf-8 -*-

import geojson
import shapely.geometry
import shapely.ops
import sys

import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


exit_on_error = False
if "-x" in sys.argv:
    exit_on_error = True

files = [x for x in sys.argv[1:] if x[0] != '-']
# reference, old feature collection
data1 = geojson.load(open(files[0],"r"))
# target, new feature collection
data2 = geojson.load(open(files[1],"r"))

def normalize(s):
    return unicode(s).strip().lower().replace(u'å','a').replace(u'ø','o').replace(u'æ','a').replace(' ','-').replace('/','-').replace(',','-').replace('--','-')

def format_area(f):
    return "%.6f" % f

def exit(name, feat_old, feat_new):
    global exit_on_error

    if feat_old:
        geojson.dump(feat_old, open("changes/%s_old.geojson" % name,"w"))
    if feat_new:
        geojson.dump(feat_new, open("changes/%s_new.geojson" % name,"w"))
    if exit_on_error:
        sys.exit(1)

ref = {}
handled = {}
byarea = {}

for feat in data1.features:
    area = shapely.geometry.Polygon(feat['geometry']['coordinates'][0]).area
    feat['area'] = area
    byarea[format_area(area)]=feat
for feat in data2.features:
    feat['area']=shapely.geometry.Polygon(feat['geometry']['coordinates'][0]).area

for feat in data1.features:
    name = normalize(feat.properties['name'])
    if name in ref:
        logger.error("Duplicate name in reference: %s", name)
    ref[normalize(feat.properties['name'])] = feat
features = sorted(ref.keys())

for feat in data2.features:
    name = normalize(feat.properties['name'])
    if not name in ref:
        exit(name, None, feat)
        logger.error("Feature NOT found in reference: %s", name)
        continue
    if name in handled:
        logger.error("Duplicate name in result: %s", name)
    comp = ref[name]
    compname = normalize(comp['properties']['name'])

    if "norway-cta" in compname or 'more-tma' in compname:
        # DEBUG: always print these
        # exit(name, comp, feat)
        comp2 = byarea.get(format_area(feat['area']))
        if comp2:
            #logger.debug("AREA MATCH, comparing %s (%s) with %s (%s) instead of %s (%s)", name, feat['area'], normalize(comp2['properties']['name']), comp2['area'], compname, comp['area'])
            comp=comp2

    compname = normalize(comp['properties']['name'])
    handled[compname] = compname
    #logger.debug("Feature found in reference: %s", name)
    if abs(feat['area'] - comp['area']) > 0.001:
        logger.error("SIZE CHANGED: %s from %f to %f", name, comp['area'], feat['area'])
        exit(name, comp, feat)
    limits_new = (int(feat['properties']['from (m amsl)']), int(feat['properties']['to (m amsl)']))
    try:
        limits_old = (int(comp['properties']['from (m amsl)']), int(comp['properties']['to (m amsl)']))
    except:
        limits_old = (int(comp['properties']['floor']), int(comp['properties']['ceiling']))
    if abs(limits_new[0]-limits_old[0])>1 or abs(limits_new[1]-limits_old[1])>1:
        logger.error("LIMITS CHANGED: %s from %s to %s", name, limits_old, limits_new)
        exit(name, comp, feat)

for feat in data1.features:
    name = normalize(feat.properties['name'])
    if not name in handled:
        logger.error("Unhandled feature from reference: %s", name)
        exit(name, feat, None)

