#!/usr/bin/env python

from codecs import open
import json
import re
import requests
import sys

re_name = re.compile('<title>.*Norway - (?P<name>.*)</title>')
re_winddir = re.compile('fl\.html\?rqtid=17\&w=(?P<dirs>\d+)&r=30')

wind_dirs = ['nw','w','sw','s','se','e','ne','n']
takeoffs = {}

for i in xrange(1,7600):
    url = 'http://flightlog.org/fl.html?l=2&a=22&country_id=160&start_id={}'.format(i)
    data = requests.get('http://flightlog.org/fl.html?l=2&a=22&country_id=160&start_id=%i' % i).text
    name = re_name.search(data)
    dirs = re_winddir.search(data)

    if dirs and name:
        name = name.groupdict()['name']
        dirs = int(dirs.groupdict()['dirs'])
        wind_values = [dirs & 2 ** shift > 0 for shift in xrange(8)]
        dirs = dict(zip(wind_dirs, wind_values))
        takeoffs[name] = dirs
        print i, name, dirs

fd = open('winddirs.json','w','utf-8')
fd.write( json.dumps(takeoffs, sort_keys=True, indent=2) )
fd.close()
