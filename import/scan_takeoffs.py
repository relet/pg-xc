#!/usr/bin/env python
# -*- coding: utf-8 -*-

from codecs import open
import json
import sys
import geojson

takeoffs = json.load(open('takeoffs.geojson','r','utf-8'))
winddirs = json.load(open('winddirs.json','r','utf-8'))

result = []

broken_unicode = {
        u'\u00c3\u00b8': u'ø',
        u'\u00c3\u00a5': u'å',
        u'\u00c3\u00a6': u'æ',
        u'\u00c3\u00a9': u'é',
        u'\u00c3\u0098': u'Ø',
        u'\u00c3\u0086': u'Æ',
        u'\u00c3\u0085': u'Å',
        u'\u00e2\u0080\u0099': u'\'',
        u'\u00c3\u0086': u'Æ'
}

broken_names = {
        u'Hovdfjellet(Hovden),Stamnan,Berkåk': True,
        u'Bardu - Setermoen - Vesleala': True,
        u'Storgalten, Lyngen': True,
        u'Voss, Bulken - Røthe': True,
        u'Løten, Rokosjøen (Opptrekk)': True,
        u'Førdsnipa - Førde': True,
        u'Kollaren (Nuvsvåg': True,
        u'Mikkeldalsrabben (Nuvsvåg)': True,
        u'Svartfjellet (Nuvsvåg)': True
}

def fix_broken_unicode(u):
    # aka windows-1525 to utf-8
    for key,rep in broken_unicode.iteritems():
        u = u.replace(key,rep)
    if '\u00c3' in u or '\u00c2' in u or '\u00c5' in u or '\u00e2' in u:
        print "Missing conversion: ", u
    return u

features = []

for takeoff in takeoffs['features']:
    del takeoff['properties']['extrude']
    del takeoff['properties']['tessellate']
    del takeoff['properties']['visibility']
    takeoff['properties']['description'] = fix_broken_unicode(takeoff['properties']['description'])
    takeoff['properties']['Name'] = fix_broken_unicode(takeoff['properties']['Name'])
    name = takeoff['properties']['Name']
    if name in broken_names or float(takeoff['geometry']['coordinates'][0])==70.2175: 
        print "Skipping", name
        continue
    dirs = winddirs.get(name,{})
    if dirs:
        takeoff['properties']['directions']=dirs
        features.append(takeoff)

fc = geojson.FeatureCollection(features=features)
fd = open('takeoffs_winddir.geojson','w','utf-8')
geojson.dump(fc,fd,indent=2,sort_keys=True)
fd.close()

