# OpenAIP output

def dumps(logger, filename, features):

    out = open(filename+".openaip","w")

    out.write("""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <OPENAIP VERSION="367810a0f94887bf79cd9432d2a01142b0426795" DATAFORMAT="1.1">
    <AIRSPACES>
    """)

    # TODO: OpenAIP airspace categories
    #A
    #B
    #C
    #CTR
    #D
    #DANGER
    #E
    #F
    #G
    #GLIDING
    #OTH #Use for uncommon or unknown airspace category
    #RESTRICTED
    #TMA
    #TMZ
    #WAVE
    #PROHIBITED
    #FIR
    #UIR
    #RMZ

    # TODO: use fl as unit where meaningful
    for i,feature in enumerate(features):
        poly = ",".join([" ".join([str(x) for x in pair]) for pair in feature['geometry_ll']])
        aipdata = {
                'id': i,
                'category': feature['properties']['class'],
                'name': feature['properties']['name'],
                'alt_from_unit': 'F',
                'alt_to_unit': 'F',
                'alt_from': feature['properties']['from (ft amsl)'],
                'alt_to': feature['properties']['to (ft amsl)'],
                'polygon': poly
            }
        out.write(u"""<ASP CATEGORY="{category}">
    <VERSION>367810a0f94887bf79cd9432d2a01142b0426795</VERSION>
    <ID>{id}</ID>
    <COUNTRY>NO</COUNTRY>
    <NAME>{name}</NAME>
    <ALTLIMIT_TOP REFERENCE="MSL">
    <ALT UNIT="{alt_to_unit}">{alt_to}</ALT>
    </ALTLIMIT_TOP>
    <ALTLIMIT_BOTTOM REFERENCE="MSL">
    <ALT UNIT="{alt_from_unit}">{alt_from}</ALT>
    </ALTLIMIT_BOTTOM>
    <GEOMETRY>
    <POLYGON>{polygon}</POLYGON>
    </GEOMETRY>
    </ASP>""".format(**aipdata))
    
    out.write("""</AIRSPACES>
    </OPENAIP>
    """)
    out.close()
