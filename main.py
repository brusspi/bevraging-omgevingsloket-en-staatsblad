import os
import geopandas as gpd
import pandas as pd
from shapely import wkt
import requests

def download_laatste_vergunningen(gemeente):
    url = f"https://omgevingsloketinzage.omgeving.vlaanderen.be/proxy-omv-up/rs/v1/inzage/projecten?gemeente={gemeente}&limit=100"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        # Converteer API-data naar een DataFrame en dan GeoDataFrame
        import pandas as pd
        df = pd.DataFrame(data)
        # Stel: de API geeft 'wktGeometry' terug
        if 'wktGeometry' in df.columns:
            df['geometry'] = df['wktGeometry'].apply(wkt.loads)
            gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:31370")
            gdf = gdf.to_crs("EPSG:4326")
            gdf.to_file('temp_vergunningen.geojson', driver='GeoJSON')
            print("Vergunningen succesvol opgehaald van loket.")
    else:
        print(f"API fout: {response.status_code}")

# Instellingen
DRY_RUN = os.getenv('DRY_RUN', 'true') == 'true'

import requests
import os

def download_bestand(url, lokaal_pad):
    if not os.path.exists(lokaal_pad):
        print(f"Bestand niet gevonden, downloaden van {url}...")
        response = requests.get(url)
        with open(lokaal_pad, 'wb') as f:
            f.write(response.content)
        print("Download voltooid.")

# Gebruik dit in je main functie
download_bestand("https://drive.google.com/uc?export=download&id=12ak6jAlG2AbMvF1Xe56i6gZ_QaRiB9Cd", "trage_wegen_register.geojson")

def main():
    print(f"--- Analyse gestart (Dry Run: {DRY_RUN}) ---")
    
    # 1. Laad trage wegen (zorg dat dit bestand in je repo staat)
    # We laden dit als een GeoDataFrame
    wegen_gdf = gpd.read_file('trage_wegen_register.geojson')
    
    # 2. Laad je vergunningen data (bijv. uit de JSON die je via API ophaalt)
    # Stel dat 'vergunningen_brakel.geojson' het bestand is dat we net hebben gegenereerd
    if not os.path.exists('vergunningen_brakel.geojson'):
        print("Fout: Bestand vergunningen_brakel.geojson niet gevonden!")
        return
        
    verg_gdf = gpd.read_file('vergunningen_brakel.geojson')

    # 3. Zorg voor hetzelfde coördinatensysteem (EPSG:4326 is WGS84)
    if wegen_gdf.crs != "EPSG:4326":
        wegen_gdf = wegen_gdf.to_crs("EPSG:4326")
    if verg_gdf.crs != "EPSG:4326":
        verg_gdf = verg_gdf.to_crs("EPSG:4326")

    # 4. Voer de ruimtelijke 'join' uit
    # Dit zoekt alle vergunningen die de wegen snijden
    print("Ruimtelijke analyse uitvoeren...")
    matches = gpd.sjoin(verg_gdf, wegen_gdf, how="inner", predicate="intersects")

    # 5. Resultaten
    if matches.empty:
        print("Geen kruisende dossiers gevonden.")
    else:
        print(f"Gevonden matches: {len(matches)}")
        for idx, row in matches.iterrows():
            dossier_nr = row.get('projectnummer', 'Onbekend')
            print(f"Match gevonden voor dossier: {dossier_nr}")
            
            if not DRY_RUN:
                # Hier zou je de email-logica aanroepen
                print(f"Versturen van mail voor {dossier_nr}...")

if __name__ == "__main__":
    main()
