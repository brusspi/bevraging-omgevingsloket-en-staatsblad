import os
import json
import requests
import geopandas as gpd
import pandas as pd
from shapely.validation import make_valid
from datetime import datetime, timedelta
import urllib.parse
import time

# --- CONFIGURATIE ---
WFS_GEMEENTE_GRENS = "https://geo.api.vlaanderen.be/VRBG2025/wfs"
WFS_WEGEN = "https://geoservices.vlaamsbrabant.be/TrageWegen/MapServer/WFSServer"
WFS_MERCATOR = "https://www.mercator.vlaanderen.be/raadpleegdienstenmercatorpubliek/wfs"
LAGEN_DOSSIERS = ["lu:lu_omv_gd_v2", "lu:lu_omv_vk_v2"]

BUFFER_METERS = 5 
DATUM_KOLOM = 'datum_huidige_toestand'
ID_KOLOM_NAAM = 'projectnummer'
UUID_KOLOM_NAAM = 'voorwerp_uuid'

RESULT_BASE_MAP = "resultaten_analyse"

def get_alle_gemeenten():
    """Haalt de lijst van alle Vlaamse gemeenten op via VRBG"""
    print("📋 Lijst van gemeenten ophalen...")
    params = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeName": "VRBG2025:Refgem", "outputFormat": "application/json",
        "propertyName": "NAAM"
    }
    try:
        res = requests.get(WFS_GEMEENTE_GRENS, params=params)
        features = res.json()['features']
        namen = sorted([f['properties']['NAAM'] for f in features])
        return namen
    except Exception as e:
        print(f"❌ Fout bij ophalen gemeentelijst: {e}")
        return []

def get_municipality_bbox(gemeente_naam):
    """Haalt de BBOX van de specifieke gemeente op"""
    cql_filter = f"NAAM='{gemeente_naam}'"
    params = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeName": "VRBG2025:Refgem", "outputFormat": "application/json",
        "cql_filter": cql_filter, "srsName": "EPSG:31370"
    }
    try:
        url = f"{WFS_GEMEENTE_GRENS}?{urllib.parse.urlencode(params)}"
        gdf = gpd.read_file(url)
        if gdf.empty: return None
        bounds = gdf.total_bounds
        return {"minX": int(bounds[0]), "minY": int(bounds[1]), "maxX": int(bounds[2]), "maxY": int(bounds[3])}
    except:
        return None

def download_en_analyseer(gemeente_naam, output_dir):
    bbox = get_municipality_bbox(gemeente_naam)
    if not bbox: return
    
    bbox_str = f"{bbox['minX']},{bbox['minY']},{bbox['maxX']},{bbox['maxY']}"
    
    # 1. Wegen downloaden
    try:
        p = {"service": "WFS", "version": "1.0.0", "request": "GetFeature", 
             "typeName": "dataservices_TrageWegen:F_TrageWegen", "bbox": bbox_str, "srsName": "EPSG:31370"}
        res = requests.get(WFS_WEGEN, params=p, timeout=30)
        with open("temp_wegen.xml", "w", encoding="utf-8") as f: f.write(res.text)
        gdf_wegen = gpd.read_file("temp_wegen.xml").set_crs("EPSG:31370", allow_override=True)
    except:
        print(f"      ⚠️  Wegen niet beschikbaar voor {gemeente_naam}")
        return

    # 2. Dossiers downloaden en filteren
    vandaag = datetime.now()
    drempel = vandaag - timedelta(days=30)
    dossier_gdfs = []

    for laag in LAGEN_DOSSIERS:
        try:
            p = {"service": "WFS", "version": "1.0.0", "request": "GetFeature", 
                 "typeName": laag, "bbox": bbox_str, "srsName": "EPSG:31370"}
            res = requests.get(WFS_MERCATOR, params=p, timeout=40)
            with open("temp_dossier.xml", "w", encoding="utf-8") as f: f.write(res.text)
            temp_gdf = gpd.read_file("temp_dossier.xml").set_crs("EPSG:31370", allow_override=True)
            
            if not temp_gdf.empty:
                temp_gdf.columns = map(str.lower, temp_gdf.columns)
                if DATUM_KOLOM in temp_gdf.columns:
                    temp_gdf[DATUM_KOLOM] = pd.to_datetime(temp_gdf[DATUM_KOLOM], errors='coerce').dt.tz_localize(None)
                    recent = temp_gdf[temp_gdf[DATUM_KOLOM] >= drempel].copy()
                    if not recent.empty:
                        recent['type_dossier'] = "Verkaveling" if "vk" in laag else "Stedenbouw"
                        dossier_gdfs.append(recent)
        except: continue

    if not dossier_gdfs:
        print(f"      ℹ️  Geen recente dossiers.")
        return

    # 3. Analyse
    gdf_dossiers = gpd.GeoDataFrame(pd.concat(dossier_gdfs, ignore_index=True), crs="EPSG:31370")
    gdf_dossiers['geometry'] = gdf_dossiers['geometry'].apply(make_valid)
    
    gdf_buf = gdf_dossiers.copy()
    gdf_buf['geometry'] = gdf_buf.buffer(BUFFER_METERS)
    matches = gpd.sjoin(gdf_wegen, gdf_buf, predicate='intersects', how='inner')

    if not matches.empty:
        unieke_ids = matches[ID_KOLOM_NAAM].unique()
        d_final = gdf_dossiers[gdf_dossiers[ID_KOLOM_NAAM].isin(unieke_ids)].to_crs(epsg=4326)
        w_final = matches.to_crs(epsg=4326)

        overzicht = []
        for _, row in d_final.iterrows():
            nr = str(row[ID_KOLOM_NAAM])
            uuid = str(row.get(UUID_KOLOM_NAAM, ''))
            overzicht.append({
                "projectnummer": nr,
                "datum": row[DATUM_KOLOM].strftime('%d-%m-%Y'),
                "url": f"https://omgevingsloketinzage.omgeving.vlaanderen.be/{nr}/inhoud-aanvraag/{uuid}"
            })

        # Opslaan
        d_final.to_file(os.path.join(output_dir, "matches_dossiers.geojson"), driver='GeoJSON')
        w_final.to_file(os.path.join(output_dir, "matches_wegen.geojson"), driver='GeoJSON')
        with open(os.path.join(output_dir, "overzicht_lijst.json"), "w", encoding="utf-8") as f:
            json.dump(overzicht, f, indent=4)
        print(f"      ✅ {len(overzicht)} kruisingen gevonden!")

if __name__ == "__main__":
    if not os.path.exists(RESULT_BASE_MAP): os.makedirs(RESULT_BASE_MAP)
    
    gemeenten = get_alle_gemeenten()
    verwerkte_gemeenten = []

    for g in gemeenten:
        safe_name = g.replace(" ", "_").replace("'", "")
        print(f"🏙️  Verwerken: {g}...")
        
        g_pad = os.path.join(RESULT_BASE_MAP, safe_name)
        if not os.path.exists(g_pad): os.makedirs(g_pad)
        
        try:
            download_en_analyseer(g, g_pad)
            # Check of er data is gegenereerd voor deze gemeente
            if os.path.exists(os.path.join(g_pad, "overzicht_lijst.json")):
                verwerkte_gemeenten.append(g)
        except Exception as e:
            print(f"❌ Fout bij {g}: {e}")
        
        # Opruimen temp bestanden
        for f in ["temp_wegen.xml", "temp_dossier.xml"]:
            if os.path.exists(f): os.remove(f)

    # Schrijf een lijst van alle succesvolle gemeenten voor de frontend
    with open(os.path.join(RESULT_BASE_MAP, "gemeenten.json"), "w", encoding="utf-8") as f:
        json.dump(verwerkte_gemeenten, f, indent=4)
    
    print("\n🏁 Analyse voor heel Vlaanderen voltooid!")