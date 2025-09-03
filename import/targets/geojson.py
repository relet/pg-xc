# GeoJSON output

from geojson import Feature, FeatureCollection, Polygon, load

def dumps (logger, filename, features):
    print("Writing", filename+".geojson with", len(features), "features")
    fc = []
    
    for feature in features:
        geom = feature['geometry_ll']
        if not geom:
            logger.error("Feature without geometry: %s", feature)
            continue
        f = Feature()
        f.properties = feature['properties']
        f.properties.update({
              'fillOpacity':0.15,
            })
        class_=f.properties.get('class')
        from_ =int(f.properties.get('from (m amsl)', 0))
        to_ =int(f.properties.get('to (m amsl)', 0))
        if class_ in ['C', 'D', 'G', 'R']:
            if f.properties.get('notam_only'):
                f.properties.update({'fillColor':'#c0c0c0',
                                     'color':'#606060',
                                     'fillOpacity':0.35})
            elif from_ < 500:
                f.properties.update({'fillColor':'#c04040',
                                     'color':'#c04040',
                                     'fillOpacity':0.35})
            elif from_ < 1000:
                f.properties.update({'fillColor':'#c08040',
                                     'color':'#c08040'})
            elif from_ < 2000:
                f.properties.update({'fillColor':'#c0c040',
                                     'color':'#c0c040'})
            elif from_ < 4000:
                f.properties.update({'fillColor':'#40c040',
                                     'color':'#40c040'})
            else:
                f.properties.update({'fillOpacity':0.0,
                                     'opacity':0.0,
                                     'color':'#ffffff'})
        elif class_ in ['Luftsport', 'Q']:
            if to_ < 2000:
                f.properties.update({'fillColor':'#c0c040',
                                     'color':'#c0c040'})
            else:
                f.properties.update({'fillColor':'#40c040',
                                     'color':'#40c040'})
        else:
            logger.debug("Missing color scheme for: %s, %s", class_, from_)
        if geom[0]!=geom[-1]:
            geom.append(geom[0])
        name = f.properties.get('name')
        if from_ < 4200 or (("Lesja" in name) | ("Rondane" in name) | ("Jotunheimen" in name) | ("Oppdal" in name) | ("Dovre" in name) | ("Bjorli" in name) | ("Ringebu" in name) | ("Vågå" in name)):
            f.geometry = Polygon([geom])
            fc.append(f)
    
    result = FeatureCollection(fc)
    open(filename+".geojson","w").write(str(result))

