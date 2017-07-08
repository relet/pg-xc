#!/usr/bin/env python
# -*- coding: utf-8 -*-


import geojson
import sys, codecs


files = sys.argv[1:]

geodata = []

for file in files:
  fd = codecs.open(file, "r", "utf-8")
  data = geojson.loads(fd.read())
  fd.close()

  if "features" in data: # FeatureCollections
      geodata += [feature for feature in data["features"]]
  elif "geometry" in data:
      geodata += [data]


print geojson.dumps(geojson.FeatureCollection(geodata))
  
