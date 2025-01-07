import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
from typing import Dict, List, Tuple

class RinkScraper:
    def __init__(self):
        self.OSM_BASE_URL = "https://nominatim.openstreetmap.org/search"
        self.MONTREAL_RINKS_URL = "https://montreal2.qc.ca/ski/en/conditions_patinoires_arr.php"
        
    def get_address(self, rink_name: str, borough: str) -> Dict:
        """Get address details from OpenStreetMap."""
        query = f"{rink_name} park, {borough}, Montreal, QC"
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
                return address_data
            else:
                print(f"    No results found for {rink_name}")
                
        except Exception as e:
            print(f"    Error getting address for {rink_name}: {str(e)}")
            
        return {"display_name": "", "lat": "", "lon": "", "borough": ""}

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
        soup = BeautifulSoup(response.text, 'html.parser')
        
        rinks_data = []
        current_borough = None
        current_rinks = []
        
        # Find all borough headers and their associated tables
        for element in soup.find_all(['h2', 'table']):
            if element.name == 'h2':
                # If we were processing a borough, save its data
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
                # Process each row in the table
                for row in element.find_all('tr'):
                    rink_data = self.parse_rink_row(row)
                    if rink_data:
                        print(f"  Looking up address for: {rink_data['name']}")
                        # Get address from OSM
                        address = self.get_address(rink_data["name"], current_borough)
                        rink_data["address"] = address
                        current_rinks.append(rink_data)
                        # Be nice to OSM servers
                        time.sleep(1)
        
        # Don't forget to add the last borough
        if current_borough:
            rinks_data.append({
                "borough": current_borough,
                "rinks": current_rinks
            })
        
        return self.create_xml(rinks_data)

if __name__ == "__main__":
    scraper = RinkScraper()
    xml_output = scraper.scrape_rinks()
    
    # Save to file
    with open("montreal_rinks.xml", "w", encoding="utf-8") as f:
        f.write(xml_output) 