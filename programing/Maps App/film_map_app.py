# Final Streamlit App Code
import streamlit as st
import folium
import pandas as pd
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import io
import xml.etree.ElementTree as ET
import re # For cleaning HTML tags

# --- Configuration ---
DEFAULT_CENTER = [40.7128, -74.0060] # NYC
DEFAULT_ZOOM = 11
FILE_PATH = "Interactive_Map_Data.xml" # Path to your file

# --- Data Loading and Parsing Function ---
@st.cache_data # Cache the data loading
def load_and_parse_xml_data(xml_file_path):
    """Loads and parses the specific XML Spreadsheet file."""
    locations_data = []
    try:
        namespaces = {'ss': 'urn:schemas-microsoft-com:office:spreadsheet'}
        tree = ET.parse(xml_file_path)
        root = tree.getroot()
        worksheet = None
        for ws in root.findall('.//ss:Worksheet', namespaces):
            if ws.get('{urn:schemas-microsoft-com:office:spreadsheet}Name') == 'Full Map List':
                worksheet = ws
                break

        if worksheet is None: return None # Worksheet not found

        table = worksheet.find('.//ss:Table', namespaces)
        if table is None: return None # Table not found

        rows = table.findall('.//ss:Row', namespaces)
        if len(rows) <= 3: return None # Not enough rows

        for row_index, row in enumerate(rows[3:]): # Skip headers
            cells = row.findall('ss:Cell', namespaces)
            if len(cells) >= 13:
                try:
                    film_cell = cells[0].find('ss:Data', namespaces)
                    film = film_cell.text if film_cell is not None else 'N/A'

                    location_text_cell = cells[8].find('ss:Data', namespaces)
                    location_text = location_text_cell.text if location_text_cell is not None else ''
                    # Basic HTML tag cleaning
                    location_text = re.sub('<[^>]+>', ', ', location_text).replace(', ,', ', ').strip(', ')

                    lat_cell = cells[9].find('ss:Data', namespaces)
                    lat_str = lat_cell.text if lat_cell is not None else None

                    lon_cell = cells[10].find('ss:Data', namespaces)
                    lon_str = lon_cell.text if lon_cell is not None else None

                    borough_cell = cells[11].find('ss:Data', namespaces)
                    borough = borough_cell.text if borough_cell is not None else 'N/A'

                    neighborhood_cell = cells[12].find('ss:Data', namespaces)
                    neighborhood = neighborhood_cell.text if neighborhood_cell is not None else 'N/A'

                    lat = float(lat_str) if lat_str else None
                    lon = float(lon_str) if lon_str else None

                    if lat is not None and lon is not None and film != 'N/A':
                         locations_data.append({
                            'Film': film,
                            'Location Display Text': location_text,
                            'LATITUDE': lat,
                            'LONGITUDE': lon,
                            'Borough': borough,
                            'Neighborhood': neighborhood
                        })
                except (ValueError, IndexError, AttributeError):
                    continue # Skip rows with errors

        if locations_data:
            return pd.DataFrame(locations_data)
        else:
            return None

    except Exception as e:
        st.error(f"Error during XML processing: {e}")
        return None

# --- Geocoding Setup ---
@st.cache_resource # Cache the geocoder resource
def get_geocoder():
    """Cached geocoder instance."""
    return Nominatim(user_agent="streamlit_map_explorer_xml_final")

@st.cache_data(show_spinner=False) # Cache geocoding results
def geocode_location(_geolocator, query): # Pass geolocator explicitly
    """Geocode location with rate limiting."""
    if not query: return None
    try:
        # Use RateLimiter directly within the function
        geocode_func = RateLimiter(_geolocator.geocode, min_delay_seconds=1)
        location = geocode_func(query, timeout=10)
        if location:
            return location.latitude, location.longitude
        else:
            st.sidebar.warning(f"Location not found: {query}")
            return None
    except Exception as e:
        st.sidebar.error(f"Geocoding error for '{query}': {e}")
        return None

# --- Streamlit App Layout ---
st.set_page_config(layout="wide")
st.title("Film Locations Map (from XML File)")

# --- Load Data ---
data_df = load_and_parse_xml_data(FILE_PATH)

# --- Sidebar Controls ---
st.sidebar.header("Controls")
if data_df is not None:
    st.sidebar.success(f"Loaded {len(data_df)} locations.")
else:
    st.sidebar.error("Failed to load or parse location data from the file.")
    st.stop() # Stop execution if data loading failed

# Location Search
search_query = st.sidebar.text_input("Search for a location:", "")
geolocator_instance = get_geocoder() # Get the cached geocoder
map_center = DEFAULT_CENTER
map_zoom = DEFAULT_ZOOM

if search_query:
    coords = geocode_location(geolocator_instance, search_query)
    if coords:
        map_center = coords
        map_zoom = 14 # Zoom in closer on search results
        st.sidebar.info(f"Map centered on: ({coords[0]:.4f}, {coords[1]:.4f})")

# --- Create and Display Map ---
st.subheader("Map View")

# Initialize map
m = folium.Map(location=map_center, zoom_start=map_zoom, tiles="CartoDB positron")

# Add location data points
st.write(f"Plotting {len(data_df)} film locations...")
count = 0
for idx, row in data_df.iterrows():
    try:
        lat = row['LATITUDE']
        lon = row['LONGITUDE']
        film_title = row['Film']
        location_text = row['Location Display Text']
        borough = row['Borough']
        neighborhood = row['Neighborhood']

        # Create popup content
        popup_html = f"""
        <b>Film:</b> {film_title}<br>
        <b>Location:</b> {location_text}<br>
        <b>Neighborhood:</b> {neighborhood} ({borough})<br>
        <b>Coords:</b> ({lat:.5f}, {lon:.5f})
        """
        popup = folium.Popup(popup_html, max_width=350)

        # Create tooltip
        tooltip_text = f"{film_title}: {location_text}"

        # Add marker
        folium.Marker(
            location=[lat, lon],
            popup=popup,
            tooltip=tooltip_text,
            icon=folium.Icon(color='darkblue', icon='film', prefix='fa') # Font Awesome film icon
        ).add_to(m)
        count += 1

    except Exception as e:
        st.warning(f"Error plotting row {idx} ('{row.get('Film', 'N/A')}'): {e}")

st.write(f"Successfully plotted {count} locations.")

# Add marker for the searched location (if applicable)
if map_center != DEFAULT_CENTER and search_query:
     folium.Marker(
         location=map_center,
         tooltip=f"Searched: {search_query}",
         icon=folium.Icon(color='green', icon='search', prefix='fa')
     ).add_to(m)

# Render the map in Streamlit
# Use key to force redraw if map center changes significantly due to search
map_key = f"{map_center[0]}-{map_center[1]}"
st_folium(m, center=map_center, zoom=map_zoom, width='100%', height=600, key=map_key)

# Optionally display the data table
if st.checkbox("Show Raw Data Table"):
    st.dataframe(data_df)