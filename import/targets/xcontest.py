# XCTrack JSON output

import datetime
import json
from geojson import Feature, FeatureCollection, Polygon, load

pens = {
        "C": [ 0, 2, 0, 0, 255 ],
        "D": [ 0, 2, 0, 0, 255 ],
        "G": [ 0, 2, 0, 0, 255 ],
        "R": [ 0, 2, 0, 0, 255 ],
        "W": [ 0, 2, 0, 255, 0 ],
    }

brushes = {        
        "C": [ -1, -1, -1 ],
        "D": [ -1, -1, -1 ],
        "G": [ -1, -1, -1 ],
        "R": [ -1, -1, -1 ],
        "W": [ 0, 255, 0 ],
    }


def dumps (logger, filename, features):
    fc = {}
    airspaces = []

    for feature in features:
        p = feature['properties']

        if (p.get('country') == 'ES'):
            #HACK: ESKS CTR is defined in Sweden
            if ('SÄLEN CTR' not in p.get('name')):
                continue

        geom = feature['geometry_ll']
        if geom[0]!=geom[-1]:
            geom.append(geom[0])
        # reverse coordinates
        geom = [(round(y,5),round(x,5)) for (x,y) in geom]


        class_     = p.get('class')
        if class_ == 'Luftsport': 
            class_ = 'W'

        name       = p.get('name')
        source     = p.get('source_href')
        notam_only = p.get('notam_only')
        temporary  = p.get('temporary')

        airautoid     = None
        if notam_only:
            if 'EN R' in name or 'EN D' in name:
                airautoid = " ".join(name.split(" ")[0:2])
            else:
                airautoid = name

        airchecktype = None
        if class_ in ['C','D','R','G']: airchecktype = 'restrict'
        if class_ in ['W']: airchecktype = 'inverse'
        if class_ in ['']: airchecktype = 'ignore'

        from_fl = int(p.get('from (fl)',0))
        to_fl   = int(p.get('to (fl)',0))
        from_ft = int(p.get('from (ft amsl)'))
        to_ft   = int(p.get('to (ft amsl)'))
        from_m  = int(p.get('from (m amsl)'))
        to_m    = int(p.get('to (m amsl)'))

        aircatpg = True
        if from_m >= 4200: aircatpg = False

        airpen = None
        if aircatpg:
            airpen = pens[class_]
            airbrush = brushes[class_]

        if from_fl:
          altype  = 'FL'
          alh     = from_fl
        elif from_ft == 0:
          altype  = 'AGL'
          alh     = 0
        else:
          altype  = 'AMSL'
          alh     = from_ft

        if to_fl:
          ahtype  = 'FL'
          ahh     = to_fl
        elif to_ft >= 999999:
          ahtype  = 'MAX'
          ahh     = 40000
        else:
          ahtype  = 'AMSL'
          ahh     = to_ft
        
        info = info_no = ''
        if class_ == 'W':
            info = 'Air sport box. Must be activated before entering.\n' + \
                   'Contact your local club before flying or keep to regular airspace limits.\n' 
            info_no = 'Luftsportboks. Må aktiveres før bruk.\n' + \
                      'Ta kontakt med din lokale klubb før flyging eller hold deg innenfor fri høyde i øvrig luftrom.\n'
        if notam_only:
            info = 'Only active if NOTAM is sent. Please check NOTAM for updated altitude limits.\n'
            info_no = 'Bare aktivt hvis NOTAM er sendt. Sjekk NOTAM for oppdaterte høydebegrensninger.\n'
        if temporary:
            info = 'Only active in periods: '+str(temporary)+'\n'
            info = 'Tidsbegrenset: '+str(temporary)+'\n'

        data = {
            'airpen': airpen,
            'airendtime': None,   
            'airparams': {},    
            'airautoid': airautoid,
            'descriptions': {
                'en': info + 'Source: ' + source,
                'no': info_no + 'Kilde: ' + source
                },
            'aircatpg': aircatpg,   
            'airclass': class_,
            'airchecktype': airchecktype, 
            'airlower': {
                'type': altype,
                'height': alh
                },
            'airbrush': airbrush,
            'airstarttime': None,  
            'airacttime': None,    
            'airupper': {
                'type': ahtype,
                'height': ahh
                },
            'airname': name,
            'components': geom,
            'notamid': None,       
            'airemail': None    
        }
        airspaces.append(data)


    now = str(datetime.datetime.utcnow().isoformat())
    fc = {'airspaces': airspaces,
          'oadescription': 'Automated export from luftrom.info - '+ now,
          'oaname': 'Norway airspace - '+now}

    open(filename+".json","w").write(json.dumps(fc))

