#!/usr/bin/env python3
"""
This script geocodes addresses of members from an Excel file and creates an interactive map using Folium. 
It caches geocoded addresses to avoid redundant API calls on subsequent runs. Additionally, it adds 
municipality boundaries for a specified kommune using data from a GeoJSON file, cached locally.

Municipality boundaries sourced from:
Geodatastyrelsen & Danske Kommuner - FOT data set - 2014-02-13 - Scale 1:500,000

Usage: visualize-members.py <input_excel_file> <output_html_file>
"""

import sys
import os
import pandas as pd
import folium
from geopy.geocoders import Nominatim
import time
import pickle
import requests
import json
from collections import defaultdict

# Customizable constants for municipality-specific details
MUNICIPALITY_NAME = "Gladsaxe"
START_LOCATION = [55.7333, 12.4667]  # Latitude and longitude for initial map center

# Constants
CACHE_FILE = ".geocache"
MUNICIPALITIES_FILE = ".municipalities.json"
# This is where we get data about the danish municipalities from.
GEOJSON_URL = 'https://raw.githubusercontent.com/magnuslarsen/geoJSON-Danish-municipalities/refs/heads/master/municipalities/municipalities.geojson'

def load_data(file_path):
    """
    Loads membership data from an Excel file.
    """
    if not os.path.exists(file_path):
        print(f"Error: Input file '{file_path}' does not exist.")
        sys.exit(1)
    
    try:
        df = pd.read_excel(file_path, skiprows=1)
    except Exception as e:
        print(f"Error loading Excel file: {e}")
        sys.exit(1)
    
    return df

def load_cache():
    """
    Loads the geocode cache from file, if it exists.
    """
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'rb') as f:
            return pickle.load(f)
    return {}

def save_cache(cache):
    """
    Saves the geocode cache to file.
    """
    with open(CACHE_FILE, 'wb') as f:
        pickle.dump(cache, f)

def get_clean_address(raw_address):
    """
    Cleans the address by removing details after the first comma.
    """
    return raw_address.split(',')[0].strip() if isinstance(raw_address, str) else raw_address

def geocode_address(address, geolocator, cache):
    """
    Geocodes an address, using cache if available.
    """
    if address in cache:
        return cache[address]
    
    try:
        print(f"Geocoding: {address}")
        location = geolocator.geocode(address)
        time.sleep(1)  # Avoid overloading the API
        if location:
            cache[address] = (location.latitude, location.longitude)
            print(f"Geocoded: {address}")
            return location.latitude, location.longitude
        else:
            print(f"Warning: Could not geocode address '{address}'")
            return None, None
    except Exception as e:
        print(f"Error geocoding address '{address}': {e}")
        return None, None

def load_municipalities():
    """
    Loads the municipalities GeoJSON data from a local cache file if it exists. 
    If not, downloads the data from a specified URL and saves it to the cache file.
    """
    if os.path.exists(MUNICIPALITIES_FILE):
        with open(MUNICIPALITIES_FILE, 'r') as f:
            print(f"Loading municipality boundaries from cache in {MUNICIPALITIES_FILE}")
            return json.load(f)
    
    try:
        print("Downloading municipality boundaries...")
        geojson_data = requests.get(GEOJSON_URL).json()
        with open(MUNICIPALITIES_FILE, 'w') as f:
            json.dump(geojson_data, f)
        print(f"Municipality boundaries downloaded and cached in {MUNICIPALITIES_FILE}")
        return geojson_data
    except Exception as e:
        print(f"Warning: Could not download GeoJSON data for municipalities: {e}")
        return None

def main():
    if len(sys.argv) < 3 or sys.argv[1] in ("-h", "--help"):
        print("Usage: script.py <input_excel_file> <output_html_file>")
        print("This script geocodes addresses and generates an interactive Folium map.")
        sys.exit(0)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]

    # Load data
    print(f"Loading data from {input_file} and starting geolocator using cache in {CACHE_FILE}")
    df = load_data(input_file)
    geolocator = Nominatim(user_agent="member_geocoder")
    cache = load_cache()
    
    # Geocode addresses and store results
    address_dict = defaultdict(list)  # To collect members by address
    failed_geocodes = []  # List for members whose addresses couldn't be geocoded
    for index, row in df.iterrows():
        raw_address = row['Vej, husnr. og evt. etage']
        city = row['Postnummer og by']
        
        if pd.notnull(raw_address) and pd.notnull(city):
            clean_address = f"{get_clean_address(raw_address)}, {city}"
            lat, lon = geocode_address(clean_address, geolocator, cache)
            
            if lat and lon:
                row['latitude'] = lat
                row['longitude'] = lon
                address_dict[(lat, lon)].append((row['Navn'], clean_address, row['Fødselsdag']))
            else:
                failed_geocodes.append((row['Navn'], clean_address, row['Fødselsdag']))
        else:
            failed_geocodes.append((row['Navn'], f"{raw_address}, {city}", row['Fødselsdag']))

    # Save cache
    save_cache(cache)

    # Create Folium map centered on the specified municipality location
    m = folium.Map(location=START_LOCATION, zoom_start=12, tiles="OpenStreetMap")
    
    # Load and add municipalities GeoJSON layer
    municipalities_geojson = load_municipalities()
    if municipalities_geojson:
        folium.GeoJson(
            municipalities_geojson,
            name="Kommuner",
            style_function=lambda feature: {
                'fillColor': 'none',
                'color': 'blue' if feature['properties']['label_dk'] == MUNICIPALITY_NAME else 'gray',
                'weight': 2 if feature['properties']['label_dk'] == MUNICIPALITY_NAME else 1,
                'dashArray': '5, 5' if feature['properties']['label_dk'] == MUNICIPALITY_NAME else '1, 1'
            },
            highlight_function=lambda feature: {
                'weight': 3,
                'color': 'darkblue' if feature['properties']['label_dk'] == MUNICIPALITY_NAME else 'gray'
            },
            tooltip=folium.GeoJsonTooltip(fields=['label_dk'], aliases=['Kommune:'])
        ).add_to(m)
        
        # Add a layer control to toggle municipality boundaries
        folium.LayerControl().add_to(m)

    # Add markers for each unique address
    for (lat, lon), members in address_dict.items():
        # Combine member information for popup without labels
        member_info = "<br>".join(
            [f"{name}<br>{address}<br>{birthday.strftime('%d-%m-%Y') if pd.notnull(birthday) else 'Fødselsdato ukendt'}"
             for name, address, birthday in members]
        )
        folium.Marker(
            [lat, lon],
            popup=member_info,
        ).add_to(m)
    
    # Save map to HTML with dynamic title
    html_header = f"""
    <h1>{MUNICIPALITY_NAME} Radikale Venstres medlemmer</h1>
    <p><b>OBS: Denne HTML side indeholder personlige oplysninger om medlemmerne og bør under ingen omstændigheder videregives til andre eller eksponeres på internettet.</b></p>
    """
    
    # Add failed geocode list to HTML
    if failed_geocodes:
        failed_list_html = "<h3>Medlemmer hvis adresse ikke kunne geokodes</h3><ul>"
        for name, address, birthday in failed_geocodes:
            failed_list_html += f"<li>{name}, {address}, {birthday.strftime('%d-%m-%Y') if pd.notnull(birthday) else 'Fødselsdato ukendt'}</li>"
        failed_list_html += "</ul>"
        html_header += failed_list_html
    
    m.get_root().html.add_child(folium.Element(html_header))
    m.save(output_file)
    print(f"Map saved to {output_file}")
    print(f"To use map, run 'python -m http.server' in the directory of the output file, then point your browser to http://localhost:8000/{output_file}")

if __name__ == "__main__":
    main()
