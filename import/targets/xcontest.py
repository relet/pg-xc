# XCTrack JSON output

import datetime
import json
from geojson import Feature, FeatureCollection, Polygon, load

M_TO_FT = 3.28084

pens = {
        "red": [ 0, 2, 192, 0, 0 ],
        "orange": [ 0, 2, 192, 63, 0 ],
        "yellow": [ 0, 2, 192, 192, 0 ],
        "green": [ 0, 2, 0, 192, 0 ],  
        "blue": [ 0, 2, 0, 0, 192 ],
        "white": [ 0, 1, 255, 255, 255 ],
        "gray": [ 0, 2, 63, 63, 63 ],
        "purple": [ 0, 3, 192, 63, 192 ],
    }

brushes = {        
        "none": [ -1, -1, -1 ],
        "red": [ 192, 0, 0 ],
        "orange": [ 192, 63 , 0 ],
        "yellow": [ 192, 192, 0 ],
        "green": [ 0, 192, 0 ],
        "purple": [ 192, 63, 192 ],
        "white": [ 255, 255, 255 ],
        "gray": [ 63, 63, 63 ],
    }

def reverse_date(s):
    return " ".join(reversed(s.split(" ")))

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
        luftsport  = False
        if class_ == 'Luftsport': 
            class_ = 'W'
            luftsport = True

        name       = p.get('name')
        source     = p.get('source_href')
        notam_only = p.get('notam_only')
        amc_only   = p.get('amc_only')
        temporary  = p.get('temporary')

        airautoid     = None
        inum = 0
        if notam_only or amc_only or ('EN R121' in name):
            if 'ENR' in name or 'END' in name:
                airautoid = "".join(name.split(" ")[0:2])
            elif 'EN R' in name:
                airautoid = "".join(name.split(" ")[0:2])   
            elif 'EN D' in name:
                num = name[name.find("D")+1:].strip().split(" ")[0]
                inum = int(num)
                if inum < 200 and inum != 110 and inum > 106:
                    airautoid = "".join(name.split(" ")[0:2])
                    luftsport = True
            else:
                airautoid = name
        elif luftsport:
            airautoid = name
        
        #if airautoid:
        #    print("AutoID SET:",airautoid,"=",name,"inum=",inum)
        #else:
        #    print("NO autoid for",name, "inum=",inum)

        airchecktype = None
        if class_ in ['C','D','R','G','Q']: airchecktype = 'restrict'
        if luftsport: airchecktype = 'inverse'
        if class_ in ['']: airchecktype = 'ignore'

        from_fl = int(p.get('from (fl)',0))
        to_fl   = int(p.get('to (fl)',0))
        from_ft = int(p.get('from (ft amsl)'))
        to_ft   = int(p.get('to (ft amsl)'))
        from_m  = int(p.get('from (m amsl)'))
        to_m    = int(p.get('to (m amsl)'))

        aircatpg = True
        if from_m >= 4200: aircatpg = False

        if from_fl:
          altype  = 'FL'
          alh     = from_fl * 100
        elif from_ft == 0:
          altype  = 'AGL'
          alh     = 0
        else:
          altype  = 'AMSL'
          alh     = from_ft

        if to_fl:
          ahtype  = 'FL'
          ahh     = to_fl * 100
        elif to_ft >= 999999:
          ahtype  = 'MAX'
          ahh     = 40000
        else:
          ahtype  = 'AMSL'
          ahh     = to_ft
        
        info = info_no = ''
        if luftsport:
            info = 'Air sport box. Must be activated before entering.\n' + \
                   'Contact your local club before flying or keep to regular airspace limits.\n' 
            info_no = 'Luftsportboks. Må aktiveres før bruk.\n' + \
                      'Ta kontakt med din lokale klubb før flyging eller hold deg innenfor fri høyde i øvrig luftrom.\n'
        if notam_only:            
            info = 'Only active if NOTAM is sent. Please check NOTAM for updated altitude limits.\n'
            info_no = 'Bare aktivt hvis NOTAM er sendt. Sjekk NOTAM for oppdaterte høydebegrensninger.\n'
            if from_m == 4114:
                info += 'Lower limit is the lower limit of controlled airspace.\n'
                info_no += 'Nedre grense er nedre grense for kontrollert luftrom.\n'

        airacttime = None
        if temporary:
            datefrom  = p.get('Date from')
            dateuntil = p.get('Date until')
            timefrom  = p.get('Time from (UTC)','0000')
            timeuntil = p.get('Time until (UTC)','2359')
            temporary = '\n'.join([reverse_date(datefrom[i]) + " - " + reverse_date(dateuntil[i]) + " " + timefrom + "-" + timeuntil for i,day in enumerate(datefrom)])

            info = 'Only active in periods: '+str(temporary)+'\n'
            info_no = 'Tidsbegrenset: '+str(temporary)+'\n'
            logger.debug("TEMPORARY is "+str(temporary))
            airacttime = str(temporary) 

        airpen = None
        airbrush = None

        if class_ in ['C', 'D', 'G', 'R', 'Q']:
            if notam_only:
                airpen = pens['gray']
                airbrush = brushes['gray']
            elif alh < (500 * M_TO_FT):
                airpen = pens['red']
                airbrush = brushes['red']
            elif alh < (1000 * M_TO_FT):
                airpen = pens['orange']
                airbrush = brushes['orange']
            elif alh < (2000 * M_TO_FT):
                airpen = pens['yellow']
                airbrush = brushes['yellow']
            elif alh < (4000 * M_TO_FT):
                airpen = pens['green']
                airbrush = brushes['green']
            else:
                airpen = pens['white']
                airbrush = brushes['none']
        if luftsport:
            airpen = pens['purple']
            airbrush = brushes['purple']

        # make temporary dashed
        if temporary:
            airpen[0] = 1

        data = {
            'airpen': airpen,
            #'airendtime': None,   
            #'airparams': {},    
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
            #'airstarttime': None,  
            'airacttime': airacttime,    
            'airupper': {
                'type': ahtype,
                'height': ahh
                },
            'airname': name,
            'components': geom,
            #'notamid': None,       
            #'airemail': None    
        }
        for key,value in list(data.items()):
            if value is None:
                del data[key]
                 
        airspaces.append(data)


    now = str(datetime.datetime.utcnow().isoformat())
    fc = {'airspaces': airspaces,
          'oadescription': 'Automated export from luftrom.info - '+ now,
          'oaname': 'Norway airspace - '+now}

    open(filename+".json","w").write(json.dumps(fc))

