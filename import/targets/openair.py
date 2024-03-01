# OpenAIR target module

def c2air(c):
    """DegMinSec to OpenAIR format (Deg:Min:Sec)"""
    n,e = c
    return "%s:%s:%s N  %s:%s:%s E" % (n[0:2],n[2:4],n[4:],e[0:3],e[3:5],e[5:])

def dumps (logger, filename, features):
    airft = open(filename+".ft.txt","w")
    airm = open(filename+".m.txt","w")
    airfl = open(filename+".fl.txt","w")

    for feature in features:
        properties = feature['properties']
        geom       = feature['geometry']
        class_  = properties.get('class')
        source  = properties.get('source_href')
        name    = properties.get('name')
        from_fl = int(properties.get('from (fl)',0))
        from_   = int(properties.get('from (ft amsl)'))
        to_     = int(properties.get('to (ft amsl)'))
        to_fl   = int(properties.get('to (fl)',0))
        from_m  = int(properties.get('from (m amsl)'))
        to_m    = int(properties.get('to (m amsl)'))

        if from_m > 3500 and not "CTA" in name:
            # explicitly allow Ringebu, Rondane, Vågå, Jotunheimen, Oppdal, Dovre, Lesja, Bjorli. (bølgeflyområder)
            if not (("Lesja" in name) | ("Rondane" in name) | ("Jotunheimen" in name) | ("Oppdal" in name) | ("Dovre" in name) | ("Bjorli" in name) | ("Ringebu" in name) | ("Vågå" in name)):
                continue

        #FIXME Airspace classes according to OpenAIR:
        # *     R restricted
        # *     Q danger
        # *     P prohibited
        # *     A Class A
        # *     B Class B
        # *     C Class C
        # *     D Class D
        # *     GP glider prohibited
        # *     CTR CTR
        # *     W Wave Window
        # (TODO: G is used in the old files, is it ok to keep using it?)
        translate = {
                "A":"A",
                "B":"B",
                "C":"C",
                "D":"D",
                "R":"R",
                "P":"P",
                "G":"G",
                "Luftsport": "W"
        }
        class_ = translate.get(class_,"Q")

        for air in (airft, airm, airfl):
            air.write("AC %s\n" % class_)
            air.write("AN %s\n" % name)

        # use FL if provided, otherwise values in M or ft
        if from_ == "0":
            airft.write("AL GND\n")
            airfl.write("AL GND\n")
            airm.write("AL GND\n")
        elif from_fl:
            airft.write("AL %sft AMSL\n" % from_)
            airfl.write("AL FL%s\n" % from_fl)
            airm.write("AL %s MSL\n" % from_m)
        else:
            airft.write("AL %sft AMSL\n" % from_)
            airfl.write("AL %sft AMSL\n" % from_)
            airm.write("AL %s MSL\n" % from_m)
        if to_fl:
            airft.write("AH %sft AMSL\n" % to_)
            airfl.write("AH FL%s\n" % to_fl)
            airm.write("AH %s MSL\n" % to_m)
        else:
            airft.write("AH %sft AMSL\n" % to_)
            airfl.write("AH %sft AMSL\n" % to_)
            airm.write("AH %s MSL\n" % to_m)

        for air in (airft, airm, airfl):
            for point in geom:
                air.write("DP %s\n" % c2air(point))
            air.write("* Source: %s\n" % source)
            air.write("*\n*\n")

    for air in (airft, airm, airfl):
        air.close()
