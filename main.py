import os
import requests
import geopandas as gpd
import pandas as pd
from shapely import wkt
import json
import shutil

# --- CONFIGURATIE ---
DRY_RUN = os.getenv('DRY_RUN', 'true') == 'true'
GEMEENTE = "deinze" 
DRIVE_FILE_ID = "12ak6jAlG2AbMvF1Xe56i6gZ_QaRiB9Cd" 
WAGEN_FILE = "trage_wegen.gpkg" 

def download_drive_file(file_id, output_path):
    print(f"Bestand downloaden van Drive...")
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = requests.get(url, stream=True)
    with open(output_path, 'wb') as f:
        shutil.copyfileobj(response.raw, f)
    print("Download voltooid.")

def haal_api_vergunningen(gemeente):
    print(f"API bevragen voor {gemeente}...")
    url = f"https://omgevingsloketinzage.omgeving.vlaanderen.be/proxy-omv-up/rs/v1/inzage/projecten"
    params = {'gemeente': gemeente, 'limit': 100}
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    response = requests.get(url, params=params, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if not data: return None
        df = pd.DataFrame(data)
        if 'wktGeometry' in df.columns:
            df['geometry'] = df['wktGeometry'].apply(wkt.loads)
            gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:31370")
            return gdf.to_crs("EPSG:4326")
    else:
        print(f"API fout: {response.status_code}")
    return None

def sla_alle_data_op(alle_matches):
    print("Resultaten opslaan naar data.json...")
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(alle_matches, f, ensure_ascii=False, indent=4)
    print("data.json succesvol aangemaakt.")

def main():
    print(f"--- Start Analyse (Dry Run: {DRY_RUN}) ---")
    
    # 1. Wegenkaart downloaden
    if not os.path.exists(WAGEN_FILE):
        download_drive_file(DRIVE_FILE_ID, WAGEN_FILE)
    wegen_gdf = gpd.read_file(WAGEN_FILE)
    
    # 2. Vergunningen direct via API ophalen (ipv lokaal bestand)
    print("Vergunningen ophalen via API...")
    verg_gdf = haal_api_vergunningen(GEMEENTE)
    
    if verg_gdf is None or verg_gdf.empty:
        print("Geen vergunningen gevonden of API fout.")
        return
    else:
        print("Geen vergunningen gevonden.")
        return

    # 2. CRS Controle
    print("CRS wegen:", wegen_gdf.crs)
    print("CRS vergunningen:", verg_gdf.crs)
    
    # 3. Ruimtelijke Analyse
    print("Analyse uitvoeren...")
    matches = gpd.sjoin(verg_gdf, wegen_gdf, how="inner", predicate="intersects")
    
    print(f"Aantal gevonden kruisingen: {len(matches)}")

    # 4. Resultaten opslaan
    if not matches.empty:
        # Zet GeoDataFrame om naar een lijst van dicts
        # We droppen de geometrie kolom voor de JSON, anders crasht json.dump
        matches_json = matches.drop(columns=['geometry', 'index_right']).to_dict(orient='records')
        sla_alle_data_op(matches_json)
    else:
        print("Geen kruisende dossiers gevonden. Sla data.json over.")

if __name__ == "__main__":
    main()
