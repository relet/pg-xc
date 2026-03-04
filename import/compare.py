#!/usr/bin/env python3
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
    return str(s).strip().lower().replace(u'å','a').replace(u'ø','o').replace(u'æ','a').replace(' ','-').replace('/','-').replace(',','-').replace('--','-').replace('en-d','end')

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

# Track changes for summary
changes_summary = {
    'size_changes': [],
    'limit_changes': [],
    'property_changes': {},
    'new_properties': {},
    'removed_properties': {}
}

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
    
    # Check geometry changes
    if abs(feat['area'] - comp['area']) > 0.001:
        changes_summary['size_changes'].append((name, comp['area'], feat['area']))
        logger.error("SIZE CHANGED: %s from %f to %f", name, comp['area'], feat['area'])
        exit(name, comp, feat)
    
    # Check altitude limits
    limits_new = (int(feat['properties']['from (m amsl)']), int(feat['properties']['to (m amsl)']))
    try:
        limits_old = (int(comp['properties']['from (m amsl)']), int(comp['properties']['to (m amsl)']))
    except:
        limits_old = (int(comp['properties']['floor']), int(comp['properties']['ceiling']))
    if abs(limits_new[0]-limits_old[0])>1 or abs(limits_new[1]-limits_old[1])>1:
        changes_summary['limit_changes'].append((name, limits_old, limits_new))
        logger.error("LIMITS CHANGED: %s from %s to %s", name, limits_old, limits_new)
        exit(name, comp, feat)
    
    # Check all other property changes (without logging each one)
    props_old = comp['properties']
    props_new = feat['properties']
    
    # Track fields to compare
    compare_fields = ['class', 'notam_only', 'amc_only', 'temporary', 
                     'Date from', 'Date until', 'Time from (UTC)', 'Time until (UTC)']
    
    for field in compare_fields:
        old_val = props_old.get(field)
        new_val = props_new.get(field)
        if old_val != new_val:
            if field not in changes_summary['property_changes']:
                changes_summary['property_changes'][field] = []
            changes_summary['property_changes'][field].append((name, old_val, new_val))
    
    # Track new/removed properties (without logging)
    new_props = set(props_new.keys()) - set(props_old.keys())
    if new_props:
        for prop in new_props:
            if prop not in changes_summary['new_properties']:
                changes_summary['new_properties'][prop] = []
            changes_summary['new_properties'][prop].append(name)
    
    removed_props = set(props_old.keys()) - set(props_new.keys())
    if removed_props:
        for prop in removed_props:
            if prop not in changes_summary['removed_properties']:
                changes_summary['removed_properties'][prop] = []
            changes_summary['removed_properties'][prop].append(name)

for feat in data1.features:
    name = normalize(feat.properties['name'])
    if not name in handled:
        logger.error("Unhandled feature from reference: %s", name)
        exit(name, feat, None)

# Print summary
logger.info("=" * 80)
logger.info("COMPARISON SUMMARY")
logger.info("=" * 80)
logger.info("Features compared: %d", len(handled))
logger.info("New features: %d", len([f for f in data2.features if normalize(f['properties']['name']) not in ref]))
logger.info("Removed features: %d", len([f for f in data1.features if normalize(f['properties']['name']) not in handled]))

if changes_summary['size_changes']:
    logger.info("\nGeometry changes: %d", len(changes_summary['size_changes']))
    for name, old_area, new_area in changes_summary['size_changes'][:5]:
        logger.info("  %s: %.6f -> %.6f", name, old_area, new_area)

if changes_summary['limit_changes']:
    logger.info("\nAltitude limit changes: %d", len(changes_summary['limit_changes']))
    for name, old_lim, new_lim in changes_summary['limit_changes'][:5]:
        logger.info("  %s: %s -> %s", name, old_lim, new_lim)

for field, changes in sorted(changes_summary['property_changes'].items()):
    logger.info("\nProperty '%s' changed: %d airspaces", field, len(changes))
    # Group by change type
    added = [(n, o, v) for n, o, v in changes if o is None and v is not None]
    removed = [(n, o, v) for n, o, v in changes if o is not None and v is None]
    modified = [(n, o, v) for n, o, v in changes if o is not None and v is not None]
    
    if added:
        logger.info("  Added (%d): %s", len(added), ', '.join([n for n, o, v in added]))
    if removed:
        logger.info("  Removed (%d): %s", len(removed), ', '.join([n for n, o, v in removed]))
    if modified:
        logger.info("  Modified (%d): %s", len(modified), ', '.join([n for n, o, v in modified]))

logger.info("=" * 80)

