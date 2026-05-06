import requests
from bs4 import BeautifulSoup
import pandas as pd

def get_screener_data(ticker):
    # Construct URL (using consolidated view as requested)
    url = f"https://www.screener.in/company/{ticker.upper()}/consolidated/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Failed to fetch data for {ticker}. Status Code: {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # This section contains the CAGR and ROE tables
        growth_section = soup.find('section', {'id': 'profit-loss'})
        if not growth_section:
            print(f"Could not find growth section for {ticker}")
            return None

        # Screener uses a specific class for these small summary tables
        tables = growth_section.find_all('table', class_='ranges-table')
        
        all_data = {"Ticker": ticker}
        
        for table in tables:
            # The header (th) tells us if it's Sales Growth, Profit Growth, or ROE
            header = table.find('th').text.strip()
            
            # Map the rows (e.g., "10 Years:" -> "18%")
            rows = table.find_all('tr')[1:] # Skip the header row
            for row in rows:
                cols = row.find_all('td')
                if len(cols) == 2:
                    period = cols[0].text.strip().replace(":", "")
                    value = cols[1].text.strip()
                    # Create a unique key like "Sales Growth 10 Years"
                    all_data[f"{header} {period}"] = value
                    
        return all_data

    except Exception as e:
        print(f"Error scraping {ticker}: {e}")
        return None

# Example usage for Nifty 50 tickers
nifty_50_tickers = ["ADANIPORTS"]
results = []

for ticker in nifty_50_tickers:
    print(f"Fetching data for {ticker}...")
    data = get_screener_data(ticker)
    if data:
        results.append(data)

# Convert to DataFrame for easy viewing/export
df = pd.DataFrame(results)
print("\nScraped Data:")
print(df.head())

# To save to CSV:
df.to_csv("nifty_50_growth_data.csv", index=False)