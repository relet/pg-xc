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

  geodata += [feature for feature in data["features"]]

print geojson.dumps(geojson.FeatureCollection(geodata))
  
