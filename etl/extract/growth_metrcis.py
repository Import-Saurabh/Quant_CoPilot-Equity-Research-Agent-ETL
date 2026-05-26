import requests
from bs4 import BeautifulSoup
import urllib.parse

# Standard browser headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest"
}

def clean_ticker_for_screener(ticker):
    """Removes exchange suffixes like .NS or .BO."""
    cleaned = ticker.upper().strip()
    for suffix in ['.NS', '.BO', ':NS', ':BO']:
        if cleaned.endswith(suffix):
            cleaned = cleaned.replace(suffix, '')
    return cleaned

def get_screener_slug(ticker):
    """Fetches the Screener slug for a ticker."""
    clean_symbol = clean_ticker_for_screener(ticker)
    search_url = f"https://www.screener.in/api/company/search/?q={urllib.parse.quote(clean_symbol)}"
    try:
        response = requests.get(search_url, headers=HEADERS)
        results = response.json()
        if results:
            raw_url = results[0]['url']
            return raw_url.replace('/company/', '').strip('/')
    except Exception as e:
        print(f"[ERROR] Failed to get slug: {e}")
    return None

def parse_growth_table(table):
    """Parses an individual growth table into a dictionary."""
    data = {}
    rows = table.find_all('tr')
    # Skip the header (first row)
    for row in rows[1:]:
        cells = row.find_all('td')
        if len(cells) == 2:
            key = cells[0].get_text(strip=True).replace(':', '')
            val = cells[1].get_text(strip=True)
            data[key] = val
    return data

def scrape_growth_metrics(ticker):
    print(f"\n=== Scraping Growth Metrics for: {ticker} ===")
    slug = get_screener_slug(ticker)
    if not slug:
        print(f"[ERROR] Could not find {ticker} on Screener.")
        return

    url = f"https://www.screener.in/company/{slug}/"
    response = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(response.content, "html.parser")

    # The growth metrics are usually contained in a grid/flex container with class 'ranges-table'
    tables = soup.find_all('table', class_='ranges-table')
    
    if not tables:
        print("[ERROR] Could not find growth tables on the page.")
        return

    # Map table headers to data
    results = {}
    for table in tables:
        header = table.find('th').get_text(strip=True)
        results[header] = parse_growth_table(table)

    # Print extracted data
    for category, metrics in results.items():
        print(f"\n--- {category} ---")
        for period, value in metrics.items():
            print(f"{period.ljust(15)}: {value}")

    return results

if __name__ == "__main__":
    scrape_growth_metrics("HAL")