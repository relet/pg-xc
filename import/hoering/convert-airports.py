def main():
    # create GeoJSON object
    geojson = {
        "type": "FeatureCollection",
        "features": []
    }

    # open airports.csv
    for line in open('airports.csv'):
        data = line.strip().split(",")
        id_, ident, type_, name, latitude_deg, longitude_deg, elevation_ft, continent, iso_country = data[0], data[1], data[2], data[3], data[4], data[5], data[6], data[8], data[8]
        iso_region, municipality, scheduled_service, icao_code, iata_code, gps_code, local_code, home_link, wikipedia_link, keywords = data[9], data[10], data[11], data[12], data[13], data[14], data[15], data[16], data[17], data[18]
        
        #strip quotes from name\
        name = name.strip('"')
        iso_country = iso_country.strip('"')
        iso_region = iso_region.strip('"')
        municipality = municipality.strip('"')
        scheduled_service = scheduled_service.strip('"')
        icao_code = icao_code.strip('"')
        iata_code = iata_code.strip('"')
        gps_code = gps_code.strip('"')
        local_code = local_code.strip('"')
        home_link = home_link.strip('"')
        wikipedia_link = wikipedia_link.strip('"')
        keywords = keywords.strip('"')
        ident = ident.strip('"')
        continent = continent.strip('"')
        type_ = type_.strip('"')


        if iso_country == "NO":
            print(f"Processing airport: {name} ({ident})")
            feature = {
                "type": "Feature",
                "properties": {
                    "id": id_,
                    "ident": ident,
                    "type": type_,
                    "name": name,
                    "elevation_ft": elevation_ft,
                    "continent": continent,
                    "iso_country": iso_country,
                    "iso_region": iso_region,
                    "municipality": municipality,
                    "scheduled_service": scheduled_service,
                    "icao_code": icao_code,
                    "iata_code": iata_code,
                    "gps_code": gps_code,
                    "local_code": local_code,
                    "home_link": home_link,
                    "wikipedia_link": wikipedia_link,
                    "keywords": keywords
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(longitude_deg), float(latitude_deg)]
                }
            }
            geojson["features"].append(feature)

    # write to airports_no.geojson
    with open('airports_no.geojson', 'w') as f:
        import json
        json.dump(geojson, f, indent=4)

    print("GeoJSON file 'airports_no.geojson' created successfully.")
    return

if __name__ == "__main__":
    main()
            
