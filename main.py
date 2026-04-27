import json
import os
import requests
import geopandas as gpd
import pandas as pd
from shapely import wkt

# --- CONFIGURATIE ---
GEMEENTE = "deinze"
WFS_URL = "https://geoservices.informatievlaanderen.be/overdrachtdiensten/TrageWegen/wfs"
WFS_LAYER = "TrageWegen:TrageWegen"

def get_bbox_voor_gemeente(gemeente):
    with open('gemeente_bbox.json', 'r') as f:
        bboxes = json.load(f)
    # Geeft (minx, miny, maxx, maxy) terug
    return tuple(bboxes.get(gemeente.lower()))

def haal_api_vergunningen(gemeente):
    print(f"API bevragen voor {gemeente}...")
    url = "https://omgevingsloketinzage.omgeving.vlaanderen.be/proxy-omv-up/rs/v1/inzage/projecten"
    params = {'gemeente': gemeente, 'limit': 100}
    response = requests.get(url, params=params, headers={'User-Agent': 'Mozilla/5.0'})
    if response.status_code == 200:
        data = response.json()
        df = pd.DataFrame(data)
        if 'wktGeometry' in df.columns:
            df['geometry'] = df['wktGeometry'].apply(wkt.loads)
            gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:31370")
            return gdf.to_crs("EPSG:4326")
    return None

def main():
    print("--- Analyse gestart via WFS ---")
    
    # 1. BBOX en Wegen ophalen
    bbox = get_bbox_voor_gemeente(GEMEENTE)
    print(f"Ophalen wegen voor bbox: {bbox}")
    wegen_gdf = gpd.read_file(WFS_URL, bbox=bbox, layer=WFS_LAYER)
    
    # 2. Vergunningen ophalen
    verg_gdf = haal_api_vergunningen(GEMEENTE)
    if verg_gdf is None or verg_gdf.empty:
        print("Geen vergunningen gevonden.")
        return

    # 3. Analyse
    matches = gpd.sjoin(verg_gdf, wegen_gdf, how="inner", predicate="intersects")
    print(f"Aantal kruisingen: {len(matches)}")

    # 4. Resultaat opslaan
    if not matches.empty:
        resultaat = matches.drop(columns=['geometry', 'index_right'], errors='ignore').to_dict(orient='records')
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(resultaat, f, ensure_ascii=False, indent=4)
        print("data.json bijgewerkt.")

if __name__ == "__main__":
    main()
