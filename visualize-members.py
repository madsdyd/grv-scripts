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
from dataclasses import dataclass
from typing import List
from folium import MacroElement
from jinja2 import Template



# Customizable constants for municipality-specific details
MUNICIPALITY_NAME = "Gladsaxe"
START_LOCATION = [55.7333, 12.4667]  # Latitude and longitude for initial map center

# Constants - this really needs to be options, but no time for that right now.
CACHE_FILE = ".geocache"
MUNICIPALITIES_FILE = ".municipalities.json"
ADDRESS_REWRITE_FILE = ".address_rewrites.json"
MATCHGROUPS_FILE = ".match_groups.json"
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
    
    # Remove extra spaces from Navn column
    df['Navn'] = df['Navn'].str.replace(r'\s+', ' ', regex=True)
    
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
            print(f"If you have a rewrite, add to {ADDRESS_REWRITE_FILE}: \"{address}\":\"{address} + correction\",")
            return None, None
    except Exception as e:
        print(f"Error geocoding address '{address}': {e}")
        return None, None

def load_address_rewrites():
    if os.path.exists(ADDRESS_REWRITE_FILE):
        with open(ADDRESS_REWRITE_FILE, 'r') as f:
            print(f"Loading address rewrites from {ADDRESS_REWRITE_FILE}")
            return json.load(f)
    else:
        return {}


# MATCHGROUPS
@dataclass
class MatchGroup:
    name: str
    matches: List[str]
    color: str

def load_match_groups() -> List[MatchGroup]:
    if os.path.exists(MATCHGROUPS_FILE):
        with open(MATCHGROUPS_FILE, 'r', encoding="utf-8") as f:
            print(f"Loading match groups from {MATCHGROUPS_FILE}")
            data = json.load(f)
            return [MatchGroup(**item) for item in data]
    else:
        return []
    

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


# This is used to control zoom steps in folium. Somewhat tricky. Gets inserted below.
class ZoomControl(MacroElement):
    _template = Template("""
        {% macro script(this, kwargs) %}
            // Ændrer zoomSnap og zoomDelta til 0.25 for finere zoom
            {{ this._parent.get_name() }}.options.zoomSnap = 0.25;
            {{ this._parent.get_name() }}.options.zoomDelta = 0.25;
        {% endmacro %}
    """)


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
    
    # Load any known address rewrites or additional info
    address_rewrites = load_address_rewrites()
    match_groups = load_match_groups()

    #print(f"Dumping match_groups: {match_groups}")

    # Geocode addresses and store results
    address_dict = defaultdict(list)  # To collect members by address
    failed_geocodes = []  # List for members whose addresses couldn't be geocoded
    for index, row in df.iterrows():
        raw_address = row['Vej, husnr. og evt. etage']
        city = row['Postnummer og by']
        
        if pd.notnull(raw_address) and pd.notnull(city):
            clean_address = f"{get_clean_address(raw_address)}, {city}"

            # Check for rewrites
            clean_address = address_rewrites.get(clean_address, clean_address)
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
    m = folium.Map(location=START_LOCATION, zoom_start=12)
    folium.TileLayer('openstreetmap').add_to(m)
    # folium.TileLayer('cartodbdark_matter').add_to(m)

    # Add groups for layers. We alywas add a Medlemmer layer, but if there are additional layers, add them.
    f_member_group = folium.FeatureGroup(name="Medlemmer")
    keyed_match_groups = {}
    for match_group in match_groups:
        key = match_group.name
        keyed_match_groups[key] = folium.FeatureGroup(name=key)
    
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
        
    # Add markers for each unique address
    for (lat, lon), members in address_dict.items():
        # Combine member information for popup without labels
        member_info = "<br>".join(
            [f"{name}<br>{address}<br>{birthday.strftime('%d-%m-%Y') if pd.notnull(birthday) else 'Fødselsdato ukendt'}"
             for name, address, birthday in members]
        )
        # Members are always added, as blue
        folium.Marker(
            [lat, lon],
            popup=member_info,
            icon=folium.Icon(color="blue")
        ).add_to(f_member_group)

        # We may need add to other groups
        for name, _, _ in members:
            for match_group in match_groups:
                if name in match_group.matches:
                    folium.Marker(
                        [lat, lon],
                        popup=member_info,
                        icon=folium.Icon(color=match_group.color)
                ).add_to(keyed_match_groups[match_group.name])
                    match_group.matches.remove(name)  # Remove after match

    # Dump names that did not match
    for match_group in match_groups:
        if match_group.matches:
            print(f"Warning: Non-matched names in '{match_group.name}': {match_group.matches}")
        
    # Add the layers to the map    
    m.add_child(f_member_group)
    for match_group in match_groups:
        m.add_child(keyed_match_groups[match_group.name])

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

    # Add layer control
    folium.LayerControl().add_to(m)

    # Add finegrained zoom control
    m.add_child(ZoomControl())


    m.save(output_file)
    print(f"Map saved to {output_file}")
    print(f"To use map, run 'python -m http.server' in the directory of the output file, then point your browser to http://localhost:8000/{output_file}")

if __name__ == "__main__":
    main()
