#!/usr/bin/env python3

from geojson import load, dumps, FeatureCollection
from shapely.geometry import shape, Point

fd = open("takeoffs.geojson","r")
data = load(fd)
fd.close()
takeoffs = data['features']

fd = open("../norway.geojson","r")
norge_json = load(fd)
fd.close()
norge = shape(norge_json['features'][0]['geometry'])

restricted = []

for to in takeoffs:
    name = to['properties']['name']
    if 'PPG' in name:
        continue

    east, north, alt = to['geometry']['coordinates']
    p = Point(east, north)
    if norge.contains(p) or north>75: # accept Norwegian and Svalbard TO
        restricted.append(to)

fd = open("restricted.geojson","w")
fd.write(dumps(restricted))
fd.close()
