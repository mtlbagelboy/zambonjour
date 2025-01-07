import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
from typing import Dict, List, Tuple
import os

class RinkScraper:
    def __init__(self):
        self.OSM_BASE_URL = "https://nominatim.openstreetmap.org/search"
        self.GOOGLE_MAPS_URL = "https://maps.googleapis.com/maps/api/geocode/json"
        self.MONTREAL_RINKS_URL = "https://montreal2.qc.ca/ski/en/conditions_patinoires_arr.php"
        self.GOOGLE_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')  # Get from environment variable
        self.existing_addresses = self.load_existing_addresses()
        
    def load_existing_addresses(self) -> dict:
        """Load existing addresses from XML file if it exists."""
        addresses = {}
        if os.path.exists("montreal_rinks.xml"):
            print("Loading existing addresses from montreal_rinks.xml...")
            try:
                tree = ET.parse("montreal_rinks.xml")
                root = tree.getroot()
                for borough in root.findall(".//borough"):
                    for rink in borough.findall(".//rink"):
                        name = rink.find("name").text
                        location = rink.find("location")
                        if location is not None:
                            address = location.find("address").text
                            coords = location.find("coordinates")
                            if address and coords.get("lat") and coords.get("lon"):
                                addresses[name] = {
                                    "display_name": address,
                                    "lat": coords.get("lat"),
                                    "lon": coords.get("lon"),
                                    "borough": borough.get("name")
                                }
                print(f"Loaded {len(addresses)} existing addresses")
            except Exception as e:
                print(f"Error loading existing addresses: {e}")
        return addresses

    def query_google_maps(self, rink_name: str, borough: str) -> Dict:
        """Query Google Maps API for address data."""
        if not self.GOOGLE_API_KEY:
            print("    No Google Maps API key found. Skipping Google Maps lookup.")
            return {"display_name": "", "lat": "", "lon": "", "borough": ""}

        # Try different query formats
        queries = [
            f"Parc {rink_name}, {borough}, Montreal, QC",
            f"{rink_name}, {borough}, Montreal, QC",  # Try without "Parc"
            f"{rink_name}, Montreal, QC"  # Try without borough
        ]

        for query in queries:
            params = {
                "address": query,
                "key": self.GOOGLE_API_KEY
            }

            try:
                print(f"    Trying Google Maps with: {query}")
                response = requests.get(self.GOOGLE_MAPS_URL, params=params)
                response.raise_for_status()
                results = response.json()
                
                # Debug: print raw response
                print(f"    Google API Response: {results}")

                if results.get("status") == "REQUEST_DENIED":
                    print(f"    Google API Error: {results.get('error_message', 'Unknown error')}")
                    return {"display_name": "", "lat": "", "lon": "", "borough": ""}

                if results.get("results"):
                    result = results["results"][0]
                    location = result["geometry"]["location"]
                    address_data = {
                        "display_name": result["formatted_address"],
                        "lat": str(location["lat"]),
                        "lon": str(location["lng"]),
                        "borough": next((
                            component["long_name"]
                            for component in result["address_components"]
                            if "sublocality" in component["types"]
                        ), "")
                    }
                    print(f"    Found via Google Maps: {address_data['display_name']}")
                    return address_data

            except Exception as e:
                print(f"    Error querying Google Maps for {rink_name}: {str(e)}")

        print(f"    No results found in Google Maps for {rink_name} after trying all query formats")
        return {"display_name": "", "lat": "", "lon": "", "borough": ""}

    def get_address(self, rink_name: str, borough: str) -> Dict:
        """Get address details from OpenStreetMap or cached data."""
        # Check if we already have this rink's address
        if rink_name in self.existing_addresses:
            print(f"    Using cached address for: {rink_name}")
            return self.existing_addresses[rink_name]

        # Try OSM first
        replacements = {
            # Basic French accents
            'Ã©': 'é',
            'Ã¨': 'è',
            'Ã¢': 'â',
            'Ã®': 'î',
            'Ã´': 'ô',
            'Ã»': 'û',
            'Ã«': 'ë',
            'Ã§': 'ç',
            # Alternative encodings
            'é´': 'é',
            'é¢': 'â',
            'é©': 'é',
            'é¨': 'è',
            'é®': 'î',
            'é´': 'ô',
            'é«': 'ë',
            'é§': 'ç'
        }
        
        # Clean up the names before querying
        for wrong, right in replacements.items():
            rink_name = rink_name.replace(wrong, right)
            borough = borough.replace(wrong, right)
        
        # Remove duplicate "park" or "parc" mentions
        rink_name = rink_name.replace('Parc ', '')
        query = f"Parc {rink_name}, {borough}, Montreal, QC"
        
        print(f"    Cleaned rink name: {rink_name}")
        print(f"    Cleaned borough: {borough}")
        print(f"    Final query: {query}")
        
        params = {
            "q": query,
            "format": "json",
            "addressdetails": 1,
            "limit": 1
        }
        
        try:
            print(f"    Querying OSM with: {query}")
            response = requests.get(
                self.OSM_BASE_URL, 
                params=params,
                headers={"User-Agent": "RinkStatusBot/1.0"}
            )
            response.raise_for_status()
            results = response.json()
            
            if results:
                address_data = {
                    "display_name": results[0].get("display_name", ""),
                    "lat": results[0].get("lat", ""),
                    "lon": results[0].get("lon", ""),
                    "borough": results[0].get("address", {}).get("borough", "")
                }
                print(f"    Found: {address_data['display_name']}")
                print(f"    Coordinates: {address_data['lat']}, {address_data['lon']}")
                print(f"    OSM Borough: {address_data['borough']}")
                
                # Cache the result for future use
                self.existing_addresses[rink_name] = address_data
                return address_data
            else:
                print(f"    No results found in OSM for {rink_name}")
                # Try Google Maps as fallback
                return self.query_google_maps(rink_name, borough)
                
        except Exception as e:
            print(f"    Error getting address for {rink_name}: {str(e)}")
            # Try Google Maps as fallback
            return self.query_google_maps(rink_name, borough)

    def parse_rink_row(self, row: BeautifulSoup) -> Dict:
        """Parse a single rink row from the table."""
        cells = row.find_all('td')
        if not cells:
            return None
            
        # Parse the first cell which contains rink type and name
        name_cell = cells[0].get_text(strip=True)
        rink_type, name = name_cell.split(',', 1) if ',' in name_cell else ("Unknown", name_cell)
        
        # Extract the name and code (TSR/LR) if present
        name = name.strip()
        code = ""
        if "(" in name and ")" in name:
            name, code = name.rsplit("(", 1)
            code = code.rstrip(")")
            name = name.strip()

        return {
            "type": rink_type.strip(),
            "name": name,
            "code": code,
            "status": {
                "open": cells[1].get_text(strip=True) if len(cells) > 1 else "N/A",
                "cleared": cells[2].get_text(strip=True) if len(cells) > 2 else "N/A",
                "sprayed": cells[3].get_text(strip=True) if len(cells) > 3 else "N/A",
                "resurfaced": cells[4].get_text(strip=True) if len(cells) > 4 else "N/A",
                "condition": cells[5].get_text(strip=True) if len(cells) > 5 else "N/A"
            }
        }

    def create_xml(self, rinks_data: List[Dict]) -> str:
        """Create XML structure from rinks data."""
        root = ET.Element("rinks")
        root.set("updated", time.strftime("%Y-%m-%d %H:%M:%S"))
        
        for borough_data in rinks_data:
            borough = ET.SubElement(root, "borough")
            borough.set("name", borough_data["borough"])
            
            for rink in borough_data["rinks"]:
                rink_elem = ET.SubElement(borough, "rink")
                rink_elem.set("type", rink["type"])
                rink_elem.set("code", rink["code"])
                
                name = ET.SubElement(rink_elem, "name")
                name.text = rink["name"]
                
                location = ET.SubElement(rink_elem, "location")
                address = ET.SubElement(location, "address")
                address.text = rink["address"]["display_name"]
                coords = ET.SubElement(location, "coordinates")
                coords.set("lat", str(rink["address"]["lat"]))
                coords.set("lon", str(rink["address"]["lon"]))
                
                status = ET.SubElement(rink_elem, "status")
                for key, value in rink["status"].items():
                    status_elem = ET.SubElement(status, key)
                    status_elem.text = value
                
        # Pretty print the XML
        xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
        return xml_str

    def scrape_rinks(self) -> str:
        """Main method to scrape rink data and generate XML."""
        print("Fetching rink data from Montreal website...")
        response = requests.get(self.MONTREAL_RINKS_URL)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        rinks_data = []
        current_borough = None
        current_rinks = []
        rinks_needing_addresses = []  # Track rinks that need OSM lookup
        
        # First pass: collect all rinks and identify which need addresses
        for element in soup.find_all(['h2', 'table']):
            if element.name == 'h2':
                if current_borough:
                    print(f"Finished processing borough: {current_borough}")
                    rinks_data.append({
                        "borough": current_borough,
                        "rinks": current_rinks
                    })
                
                current_borough = element.get_text(strip=True)
                print(f"\nProcessing borough: {current_borough}")
                current_rinks = []
                
            elif element.name == 'table' and current_borough:
                for row in element.find_all('tr'):
                    rink_data = self.parse_rink_row(row)
                    if rink_data:
                        if rink_data["name"] not in self.existing_addresses:
                            rinks_needing_addresses.append((rink_data["name"], current_borough))
                            print(f"  Will need to lookup address for: {rink_data['name']}")
                        else:
                            print(f"  Using cached address for: {rink_data['name']}")
                        
                        # Use existing address or empty placeholder
                        rink_data["address"] = self.existing_addresses.get(rink_data["name"], 
                            {"display_name": "", "lat": "", "lon": "", "borough": ""})
                        current_rinks.append(rink_data)
        
        # Don't forget to add the last borough
        if current_borough:
            rinks_data.append({
                "borough": current_borough,
                "rinks": current_rinks
            })
        
        # Second pass: lookup addresses only for rinks that need them
        print(f"\nNeed to lookup {len(rinks_needing_addresses)} addresses...")
        for rink_name, borough in rinks_needing_addresses:
            print(f"\nLooking up address for: {rink_name}")
            address = self.get_address(rink_name, borough)
            
            # Update the address in our data structure
            for borough_data in rinks_data:
                for rink in borough_data["rinks"]:
                    if rink["name"] == rink_name:
                        rink["address"] = address
            time.sleep(1)  # Only sleep when we actually query OSM
        
        return self.create_xml(rinks_data)

if __name__ == "__main__":
    scraper = RinkScraper()
    xml_output = scraper.scrape_rinks()
    
    # Save to file
    with open("montreal_rinks.xml", "w", encoding="utf-8") as f:
        f.write(xml_output)