import requests
from bs4 import BeautifulSoup

def get_industry_hierarchy(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, "html.parser")
    
    # Target the section with id='peers' and the specific paragraph with class='sub'
    # The links are children of the <p class="sub"> tag inside the first div of #peers
    peer_section = soup.select_one("#peers p.sub")
    
    if not peer_section:
        return "Could not find the industry hierarchy section."

    # Extract all links and their corresponding titles
    hierarchy = {}
    for link in peer_section.find_all("a"):
        category = link.get("title")  # e.g., "Broad Sector", "Sector", etc.
        value = link.get_text(strip=True) # e.g., "Financial Services", "Banks"
        hierarchy[category] = value
        
    return hierarchy

# Example usage:
# url = "https://www.screener.in/company/HDFCBANK/consolidated/"
# details = get_industry_hierarchy(url)
# print(details)