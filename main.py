import json
import requests
import geopandas as gpd
import pandas as pd
from shapely import wkt
import os

# --- CONFIGURATIE ---
# De specifieke WFS van Vlaams-Brabant
WFS_URL = "https://geoservices.vlaamsbrabant.be/TrageWegen/MapServer/WFSServer"
WFS_LAYER = "dataservices_TrageWegen:F_TrageWegen"
OMV_API_URL = "https://omgevingsloketinzage.omgeving.vlaanderen.be/proxy-omv-up/rs/v1/inzage/projecten"

def get_bboxes():
    """Laadt de BBOXen van alle gemeenten uit de lokale JSON"""
    if not os.path.exists('gemeente_bbox.json'):
        print("FOUT: gemeente_bbox.json niet gevonden!")
        return {}
    with open('gemeente_bbox.json', 'r') as f:
        return json.load(f)

def haal_api_vergunningen(gemeente):
    """Haalt de meest recente vergunningsaanvragen op via de API"""
    print(f"  > API bevragen voor {gemeente}...")
    params = {'gemeente': gemeente, 'limit': 100}
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(OMV_API_URL, params=params, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if not data: 
                return None
            df = pd.DataFrame(data)
            if 'wktGeometry' in df.columns:
                # API data komt vaak in Lambert 72 (31370)
                df['geometry'] = df['wktGeometry'].apply(wkt.loads)
                gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:31370")
                # Omzetten naar WGS84 voor de kaart/webpagina
                return gdf.to_crs("EPSG:4326")
        else:
            print(f"  > API Fout: Status {response.status_code}")
    except Exception as e:
        print(f"  > Fout bij API call: {e}")
    return None

def main():
    print("--- Start Gecombineerde Analyse (WFS & API) ---")
    gemeenten = get_bboxes()
    
    if not gemeenten:
        print("Geen gemeenten om te verwerken.")
        return

    alle_resultaten = []

    for naam, bbox in gemeenten.items():
        print(f"\n--- Verwerken: {naam.upper()} ---")
        
        # 1. Wegen ophalen via WFS (Vlaams-Brabant)
        try:
            # We vragen de data op binnen de bbox en forceren WGS84
            # ESRI MapServers verwachten vaak de bbox als tuple: (minx, miny, maxx, maxy)
            wegen_gdf = gpd.read_file(WFS_URL, bbox=tuple(bbox), layer=WFS_LAYER)
            
            if wegen_gdf.empty:
                print(f"  > Geen wegen gevonden in de bbox voor {naam}.")
                continue
            
            # Zorg dat wegen in WGS84 staan voor de join
            if wegen_gdf.crs != "EPSG:4326":
                wegen_gdf = wegen_gdf.to_crs("EPSG:4326")
                
        except Exception as e:
            print(f"  > Fout bij ophalen WFS wegen: {e}")
            continue

        # 2. Vergunningen ophalen
        verg_gdf = haal_api_vergunningen(naam)
        
        # 3. Ruimtelijke Analyse (Kruising)
        if verg_gdf is not None and not verg_gdf.empty:
            # Join de twee lagen
            matches = gpd.sjoin(verg_gdf, wegen_gdf, how="inner", predicate="intersects")
            
            if not matches.empty:
                # Voeg gemeentenaam toe voor de frontend filter
                matches['gemeente_naam'] = naam
                # Verwijder kolommen die niet in JSON kunnen (zoals de geometrie zelf)
                resultaat_voor_json = matches.drop(columns=['geometry', 'index_right'], errors='ignore')
                alle_resultaten.append(resultaat_voor_json)
                print(f"  > SUCCESS: {len(matches)} kruisingen gevonden!")
            else:
                print("  > Resultaat: Geen kruisingen met trage wegen.")
        else:
            print("  > Resultaat: Geen vergunningen gevonden voor deze gemeente.")

    # 4. Data exporteren voor de webpagina
    if alle_resultaten:
        final_df = pd.concat(alle_resultaten)
        output_data = final_df.to_dict(orient='records')
        
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
        print(f"\n✅
