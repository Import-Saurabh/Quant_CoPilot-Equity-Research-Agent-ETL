import requests
from bs4 import BeautifulSoup
import urllib.parse
import re

# ==========================================
# CONFIGURATION & HEADERS
# ==========================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest"
}

# ==========================================
# UTILITY FUNCTIONS
# ==========================================
def clean_ticker_for_screener(ticker):
    """Removes exchange suffixes like .NS or .BO."""
    cleaned = ticker.upper().strip()
    for suffix in ['.NS', '.BO', ':NS', ':BO']:
        if cleaned.endswith(suffix):
            cleaned = cleaned.replace(suffix, '')
    return cleaned

def get_screener_id_and_slug(ticker):
    """Fetches both the Screener slug and the internal numeric screener_id."""
    clean_symbol = clean_ticker_for_screener(ticker)
    search_url = f"https://www.screener.in/api/company/search/?q={urllib.parse.quote(clean_symbol)}"
    
    try:
        response = requests.get(search_url, headers=HEADERS)
        response.raise_for_status()
        results = response.json()
        
        if not results:
            print(f"[ERROR] No company found on Screener for ticker: {clean_symbol}")
            return None, None
            
        # Try for an exact match first
        match = None
        for item in results:
            raw_url = item.get('url', '')
            slug_candidate = raw_url.replace('/company/', '').replace('/consolidated/', '').strip('/').upper()
            if slug_candidate == clean_symbol:
                match = item
                break
                
        # Fallback to the first result
        if not match:
            match = results[0]
            
        raw_url = match['url']
        slug = raw_url.replace('/company/', '').replace('/consolidated/', '').strip('/')
        
        # Now fetch the actual company page to extract the numerical ID
        company_url = f"https://www.screener.in/company/{slug}/"
        page_response = requests.get(company_url, headers=HEADERS)
        
        screener_id = None
        if page_response.status_code == 200:
            # Look for the follow button or actions that contain the ID in the HTML
            id_match = re.search(r'/api/company/(\d+)/', page_response.text)
            if id_match:
                screener_id = int(id_match.group(1))
            else:
                id_match_alt = re.search(r'data-company-id="(\d+)"', page_response.text)
                if id_match_alt:
                    screener_id = int(id_match_alt.group(1))
                    
        return screener_id, slug
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch Screener ID for {ticker}: {e}")
        return None, None


# ==========================================
# CORE SCRAPER FUNCTION
# ==========================================
def scrape_stock_master_details(ticker):
    print(f"\n=== Fetching Master Details for: {ticker} ===")
    
    screener_id, slug = get_screener_id_and_slug(ticker)
    if not slug:
        return None

    # Try consolidated first, fallback to standalone if 404
    url = f"https://www.screener.in/company/{slug}/consolidated/"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 404:
        url = f"https://www.screener.in/company/{slug}/"
        response = requests.get(url, headers=HEADERS)
        
    if response.status_code != 200:
        print(f"[ERROR] Failed to fetch page for {slug}")
        return None

    soup = BeautifulSoup(response.content, "html.parser")
    
    # --- 1. Extract Industry Hierarchy ---
    hierarchy = {
        "Broad Sector": None,
        "Sector": None,
        "Broad Industry": None,
        "Industry": None
    }
    hierarchy_section = soup.select_one("#peers p.sub")
    if hierarchy_section:
        for link in hierarchy_section.find_all("a"):
            label = link.get("title")
            value = link.get_text(strip=True)
            if label in hierarchy:
                hierarchy[label] = value
                
    # --- 2. Extract Top Ratios (Market Cap, P/E, etc.) ---
    ratios = {}
    ratios_ul = soup.select_one("#top-ratios")
    if ratios_ul:
        for li in ratios_ul.find_all("li"):
            name_tag = li.find("span", class_="name")
            value_tag = li.find("span", class_="value")
            
            if name_tag and value_tag:
                name = name_tag.get_text(strip=True)
                
                # Clean out currency symbols and commas
                raw_value = value_tag.get_text(strip=True).replace('₹', '').replace(',', '').strip()
                
                # Further extract just the number if there's trailing text like "Cr." or "%"
                num_span = value_tag.find("span", class_="number")
                if num_span:
                     raw_value = num_span.get_text(strip=True).replace(',', '')
                     
                try:
                    ratios[name] = float(raw_value)
                except ValueError:
                    ratios[name] = raw_value

    # Compile the final dictionary matching your database needs
    master_data = {
        "symbol": clean_ticker_for_screener(ticker),
        "screener_id": screener_id,
        "broad_sector": hierarchy.get("Broad Sector"),
        "sector": hierarchy.get("Sector"),
        "broad_industry": hierarchy.get("Broad Industry"),
        "industry": hierarchy.get("Industry"),
        "market_cap_cr": ratios.get("Market Cap"),
        "current_price": ratios.get("Current Price"),
        "stock_pe": ratios.get("Stock P/E")
    }

    return master_data


# ==========================================
# TEST RUNNER
# ==========================================
if __name__ == "__main__":
    ticker_to_test = "HAL.NS"
    
    details = scrape_stock_master_details(ticker_to_test)
    
    if details:
        print("\n--- Extracted Master Data ---")
        for key, value in details.items():
            print(f"{key.ljust(20)}: {value}")
            
        print("\n--- Example SQL Update Query ---")
        print(f"UPDATE stocks")
        print(f"SET screener_id = {details['screener_id']},")
        print(f"    broad_sector = '{details['broad_sector']}',")
        print(f"    sector = '{details['sector']}',")
        print(f"    broad_industry = '{details['broad_industry']}',")
        print(f"    industry = '{details['industry']}'")
        print(f"    -- market_cap = {details['market_cap_cr']},")
        print(f"    -- current_price = {details['current_price']}")
        print(f"WHERE symbol = '{details['symbol']}';")