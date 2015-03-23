#!/usr/bin/env python
# -*- coding: utf-8 -*-


import geojson
import sys, codecs


try: 
  file  = sys.argv[1]
  field = sys.argv[2]
except:
  print "usage: split file attribute"
  sys.exit(1)


fd = codecs.open(file, "r", "utf-8")
data = geojson.loads(fd.read())
fd.close()

geodata = {}
for feature in data["features"]:
  property = feature['properties'][field]
  bucket = geodata.get(property, [])
  bucket.append(feature)
  geodata[property] = bucket

for bucket in geodata:
  filename = bucket+"."+file
  print "writing bucket ",filename
  fd = codecs.open(filename, "w", "utf-8")
  fd.write(geojson.dumps(geojson.FeatureCollection(geodata[bucket])))
  fd.close()
  
