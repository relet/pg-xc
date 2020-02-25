#!/usr/bin/python3

import re
import requests
import sys
from geojson import Point, Feature, FeatureCollection, dumps, loads

takeoffs=[]
names = {}

re_coordinates = re.compile('DMS: ([NS]) (\d+)&deg; (\d+)&#039; (\d+)&#039;&#039; &nbsp;([EW]) (\d+)&deg; (\d+)&#039; (\d+)&#039;&#039;')
re_title       = re.compile("span style='\s.*?'>([^<>]*?)</span", re.MULTILINE|re.DOTALL)
re_altitude    = re.compile("(\d+) meters asl")
re_description = re.compile("Description</td><td bgcolor='white'>(.*)</td></tr><tr><td bgcolor='white'>Coordinates", re.MULTILINE|re.DOTALL)
re_directions  = re.compile("rqtid=17&w=(\d+)&r=30")

headers = {
    'User-agent': 'Takeoff importer 1.0'
}

previous = []
try:
    fd = open("takeoffs.geojson","r")
    previous = loads(fd.read())
    takeoffs = previous['features']
    names = {t['properties']['name']:True for t in takeoffs}
    fd.close()
except Exception as ex:
    print(ex)
    print("Reading file failed")
    pass

print(names)

try:
    fd = open("lastid","r")
    start = int(fd.read())
    fd.close()
except Exception as ex:
    print(ex)
    start = 0

for id in range(start,9000):
    print(id)

    fd = open("lastid","w")
    fd.write(str(id))
    fd.close()

    takeoff = {}
    src = 'https://flightlog.org/fl.html?l=1&country_id=160&a=22&start_id='+str(id)
    r = requests.get(src,headers=headers)
    data = r.text

    coo = re_coordinates.findall(data)
    title = re_title.findall(data)
    print(title)
    alt = re_altitude.findall(data)
    desc = re_description.findall(data)
    dirc = re_directions.findall(data)

    if len(coo)>0 and len(title)>0:

      coo=coo[0]
      if coo[0] != 'N' or coo[4]!= 'E':
          continue

      if len(dirc)>0:
          dirc = int(dirc[0])
      else:
          dirc = 0

      desc = (desc or [''])[0]
      desc = desc.replace('/fl.html','https://flightlog.org/fl.html')

      if not desc:
          print("MISSING DESCRIPTION")
          print(dumps(takeoff))
          sys.exit(1)

      north = int(coo[1])+int(coo[2])/60.0+int(coo[3])/3600.0
      east = int(coo[5])+int(coo[6])/60.0+int(coo[7])/3600.0
      alt = int((alt or ['0'])[0])

      p = Point((east, north, alt))
      f = Feature(geometry=p)

      f.properties = {
          'name':title[0],
          'description':desc,
          'href':src,
          'directions':{
              'n':(dirc & 128 > 0),
              'ne':(dirc & 64 > 0),
              'e':(dirc & 32 > 0),
              'se':(dirc & 16 > 0),
              's':(dirc & 8 > 0),
              'sw':(dirc & 4 > 0),
              'w':(dirc & 2 > 0),
              'nw':(dirc & 1 > 0)
          }
      }

      if title[0] in names:
        print("KNOWN")
      else:
        takeoffs.append(f)
        names[title[0]]=True
        print("ADDED")

        json = dumps(FeatureCollection(takeoffs),indent=2)
        fd = open("takeoffs.geojson","w")
        fd.write(json)
        fd.close()

print(len(takeoffs))


