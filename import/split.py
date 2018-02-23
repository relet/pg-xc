#!/usr/bin/env python
# -*- coding: utf-8 -*-

import geojson
import shapely.geometry
import shapely.ops
import sys

import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

data = geojson.load(open(sys.argv[1],"r"))
features = [shapely.geometry.Polygon(feat['geometry']['coordinates'][0]).buffer(0) for feat in data.features]
try:
    limit = int(sys.argv[2])
except:
    limit = len(features)

polygons = []

for geom in features[:limit]:
    shortlist = [geom]

    while True:
        if not shortlist: break

        item = shortlist.pop()
        todo = polygons[:]
        broken = False
        for poly in todo:
            if item.intersects(poly) and not item.touches(poly):
                inter = poly.intersection(item)
                if inter.area > 0.01:
                    a = poly.difference(item)
                    b = item.difference(poly)
                    shortlist += [inter, a, b]
                    polygons.remove(poly)
                    broken = True
                    break
        if broken:
            continue
        else:
            polygons.append(item)


overlap = {}

for j,poly in enumerate(polygons):
    overlap[j]=[]
    for i,geom in enumerate(features[:limit]):
        if geom.intersects(poly) and not geom.touches(poly):
            laps = overlap.get(j)
            laps.append(i)
            overlap[j]=laps


fc = []

for j,poly in enumerate(polygons):
    layers = []
    lowest = None
    for layer in overlap.get(j):
        p = data[layer]
        if lowest is None or features[layer].area < features[lowest].area:
            lowest = layer
        layers.append(p.properties)

    if lowest:
        layers.remove(data[lowest].properties)
        properties = data[lowest].properties
        properties.update({"layers":layers})
        feature = geojson.Feature(geometry=poly, properties=properties)
        fc.append(feature)

print geojson.dumps(geojson.FeatureCollection(fc))
