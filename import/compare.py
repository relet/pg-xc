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

for feat in data1.features:
    name = normalize(feat.properties['name'])
    if name in ref:
        logger.error("Duplicate name in reference: %s", name)
    ref[normalize(feat.properties['name'])] = feat
features = sorted(ref.keys())

for feat in data2.features:
    name = normalize(feat.properties['name'])
    if "norway-cta" in name or "more-tma" in name:
        #TODO numbers are messed up, check handling
        continue
    if not name in ref:
        exit(name, None, feat)
        logger.error("Feature NOT found in reference: %s", name)
        continue
    if name in handled:
        logger.error("Duplicate name in result: %s", name)
    handled[name] = feat
    logger.debug("Feature found in reference: %s", name)
    comp = ref[name]
    geom_new = shapely.geometry.Polygon(feat['geometry']['coordinates'][0])
    geom_old = shapely.geometry.Polygon(comp['geometry']['coordinates'][0])
    if abs(geom_new.area - geom_old.area) > 0.001:
        logger.error("SIZE CHANGED: %s from %f to %f", name, geom_old.area, geom_new.area)
        exit(name, comp, feat)
    limits_new = (int(feat['properties']['from (m amsl)']), int(feat['properties']['to (m amsl)']))
    try:
        limits_old = (int(comp['properties']['from (m amsl)']), int(comp['properties']['to (m amsl)']))
    except:
        limits_old = (int(comp['properties']['floor']), int(comp['properties']['ceiling']))
    if abs(limits_new[0]-limits_old[0])>1 and abs(limits_new[1]-limits_old[1])>1:
        logger.error("LIMITS CHANGED: %s from %s to %s", name, limits_old, limits_new)
        exit(name, comp, feat)

for feat in data1.features:
    name = normalize(feat.properties['name'])
    if not name in handled:
        logger.error("Unhandled feature from reference: %s", name)

