import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

# Setup session
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
})

def scrape_and_export_verification(ticker):
    print(f"--- Starting Scrape for: {ticker} ---")
    
    url = f"https://www.screener.in/company/{ticker.upper()}/consolidated/"
    
    try:
        response = session.get(url)
        if response.status_code != 200:
            print(f"Error: Could not reach page. Status: {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        pl_section = soup.find('section', id='profit-loss')
        
        if not pl_section:
            print("Error: Profit & Loss section not found.")
            return None

        table = pl_section.find('table', class_='data-table')
        
        # 1. Extract Years from Header
        thead = table.find('thead')
        headers = [th.text.strip() for th in thead.find_all('th') if th.text.strip()]
        headers.insert(0, "Metric")

        # 2. Extract Data Rows
        rows = []
        for tr in table.find('tbody').find_all('tr'):
            cells = tr.find_all('td')
            # Clean icons/whitespace
            row_data = [cell.get_text(strip=True).replace('+', '').strip() for cell in cells]
            if row_data:
                rows.append(row_data)

        # 3. Create initial DataFrame (Metrics as Rows)
        df_raw = pd.DataFrame(rows, columns=headers)

        # 4. TRANSPOSE (Flip the table)
        # This makes 'Sales', 'Expenses', etc., into Columns
        df_flipped = df_raw.set_index('Metric').T.reset_index()
        
        # 5. Rename 'index' to 'period_end' and add 'symbol'
        df_flipped.rename(columns={'index': 'period_end'}, inplace=True)
        df_flipped.insert(0, 'symbol', ticker.upper())
        
        # 6. Final Clean-up of Column Names
        # We ensure they match your SQL schema exactly
        column_mapping = {
            'Sales': 'sales',
            'Expenses': 'expenses',
            'Operating Profit': 'operating_profit',
            'OPM %': 'opm_pct',
            'Other Income': 'other_income',
            'Interest': 'interest',
            'Depreciation': 'depreciation',
            'Profit before tax': 'profit_before_tax',
            'Tax %': 'tax_pct',
            'Net Profit': 'net_profit',
            'EPS in Rs': 'eps',
            'Dividend Payout %': 'dividend_payout_pct'
        }
        df_flipped.rename(columns=column_mapping, inplace=True)

        return df_flipped

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# Execute for Adani Ports
ticker = "ADANIPORTS"
verification_df = scrape_and_export_verification(ticker)

if verification_df is not None:
    # Save to CSV for you to open in Excel/Notepad
    filename = f"{ticker}_verification.csv"
    verification_df.to_csv(filename, index=False)
    
    print("\n--- VERIFICATION READY ---")
    print(f"File saved as: {filename}")
    print("\nPreview of the first 5 years:")
    print(verification_df.head())