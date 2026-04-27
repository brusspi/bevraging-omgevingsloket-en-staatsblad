import os
import requests
import geopandas as gpd
import pandas as pd
from shapely import wkt
import json
import shutil

# --- CONFIGURATIE ---
DRY_RUN = os.getenv('DRY_RUN', 'true') == 'true'
GEMEENTE = "deinze" # Zorg dat dit overeenkomt met je doelgemeente
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
            # Zet WKT om naar geometrie
            df['geometry'] = df['wktGeometry'].apply(wkt.loads)
            gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:31370")
            return gdf.to_crs("EPSG:4326")
    return None

def main():
    print(f"--- Analyse gestart (DRY_RUN: {DRY_RUN}) ---")
    
    # 1. Wegenkaart ophalen
    if not os.path.exists(WAGEN_FILE):
        download_drive_file(DRIVE_FILE_ID, WAGEN_FILE)
    wegen_gdf = gpd.read_file(WAGEN_FILE)
    
    # 2. Vergunningen ophalen (Direct via API, zonder lokaal bestand!)
    verg_gdf = haal_api_vergunningen(GEMEENTE)
    
    if verg_gdf is None or verg_gdf.empty:
        print("Geen vergunningen gevonden via API.")
        return

    # 3. Analyse
    wegen_gdf = wegen_gdf.to_crs("EPSG:4326")
    matches = gpd.sjoin(verg_gdf, wegen_gdf, how="inner", predicate="intersects")
    
    print(f"Aantal gevonden kruisingen: {len(matches)}")

    # 4. Resultaat opslaan
    if not matches.empty:
        matches_json = matches.drop(columns=['geometry', 'index_right'], errors='ignore').to_dict(orient='records')
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(matches_json, f, ensure_ascii=False, indent=4)
        print("data.json aangemaakt.")

if __name__ == "__main__":
    main()
