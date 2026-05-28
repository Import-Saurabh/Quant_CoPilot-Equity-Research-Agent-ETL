import requests
from bs4 import BeautifulSoup
import urllib.parse
import re

# Standard browser headers to prevent 403 Forbidden errors
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest"
}

# ── Labels that map to parent columns in balance_sheet ───────────────────────
# Any row from Screener NOT in this set is an extra/sector-specific line
# (e.g. Gross NPA %, Net NPA %, Capital Adequacy Ratio) and is routed to
# balance_sheet_items under the pseudo-parent "Extra Metrics – <label>".
KNOWN_BS_LABELS = {
    "Equity Capital", "Reserves",
    # "Total Equity" intentionally excluded — column dropped from balance_sheet
    "Borrowings", "Other Liabilities", "Total Liabilities",
    "Fixed Assets", "CWIP", "Investments", "Other Assets",
    "Inventories", "Trade Receivables",
    "Cash Equivalents", "Cash & Equivalents",
    "Loans & Advances", "Total Assets", "Net Debt",
}


def clean_ticker_for_screener(ticker):
    """
    Removes exchange suffixes like .NS or .BO (e.g., 'HAL.NS' -> 'HAL')
    to ensure clean searches on Screener.
    """
    cleaned = ticker.upper().strip()
    for suffix in ['.NS', '.BO', ':NS', ':BO']:
        if cleaned.endswith(suffix):
            cleaned = cleaned.replace(suffix, '')
    return cleaned

def get_screener_id_and_slug(ticker):
    """Automatically search for the ticker and fetch its Screener Slug."""
    clean_symbol = clean_ticker_for_screener(ticker)
    search_url = f"https://www.screener.in/api/company/search/?q={urllib.parse.quote(clean_symbol)}"
    
    try:
        response = requests.get(search_url, headers=HEADERS)
        response.raise_for_status()
        results = response.json()
        
        if not results:
            print(f"[ERROR] No company found on Screener for ticker query: {clean_symbol}")
            return None, None
            
        match = None
        for item in results:
            raw_url = item.get('url', '')
            # FIX: Safely strip out the structural parts of the URL to isolate JUST the slug
            slug_candidate = raw_url.replace('/company/', '').replace('/consolidated/', '').strip('/').upper()
            
            if slug_candidate == clean_symbol:
                match = item
                break
        
        # Fallback to the first option only if an exact ticker match isn't found
        if not match:
            print(f"  [INFO] Exact slug match for '{clean_symbol}' not found. Defaulting to best search result: {results[0].get('name')}")
            match = results[0]
            
        raw_url = match['url']
        slug = raw_url.replace('/company/', '').replace('/consolidated/', '').strip('/')
        
        # Fetch the internal numeric 'screener_id' by scraping the company page
        company_url = f"https://www.screener.in/company/{slug}/"
        page_response = requests.get(company_url, headers=HEADERS)
        
        screener_id = None
        if page_response.status_code == 200:
            # Look for common ID structures inside the HTML buttons/links
            id_match = re.search(r'/company/actions/(\d+)/', page_response.text)
            if id_match:
                screener_id = id_match.group(1)
            else:
                id_match_alt = re.search(r'/api/company/(\d+)/', page_response.text)
                if id_match_alt:
                    screener_id = id_match_alt.group(1)
                    
        # Final emergency fallback
        if not screener_id:
            screener_id = slug

        return screener_id, slug
    except Exception as e:
        print(f"[ERROR] Failed to fetch Screener ID for {ticker}: {e}")
        return None, None

def parse_html_table(table_soup):
    """Parses a standard Screener data table into dates and row dictionaries."""
    dates = []
    thead = table_soup.find('thead')
    if thead:
        headers = thead.find_all('th')
        for th in headers:
            date_key = th.get('data-date-key')
            text = th.get_text(strip=True)
            if date_key:
                dates.append(date_key)
            elif text:
                dates.append(text)

    # Clean out empty labels from the parsed header mapping array
    dates = [d for d in dates if d and d != ""]

    rows_data = {}
    tbody = table_soup.find('tbody')
    if tbody:
        for tr in tbody.find_all('tr'):
            tds = tr.find_all('td')
            if not tds:
                continue
            row_label = tds[0].get_text(strip=True).replace('+', '').strip()
            
            values = []
            for td in tds[1:]:
                val_text = td.get_text(strip=True).replace(',', '')
                # Handle empty, reference, dash, or nan strings cleanly
                if val_text in ('', 'Reference', '-', 'nan'):
                    values.append(None)
                else:
                    try:
                        values.append(float(val_text))
                    except ValueError:
                        values.append(val_text)
            
            rows_data[row_label] = values
            
    return dates, rows_data

def fetch_schedule_item(screener_id, parent_name):
    """Hits the schedule API and extracts rows successfully from JSON or HTML data variants."""
    encoded_parent = urllib.parse.quote_plus(parent_name)
    schedule_url = f"https://www.screener.in/api/company/{screener_id}/schedules/?parent={encoded_parent}&section=balance-sheet&consolidated="
    
    try:
        res = requests.get(schedule_url, headers=HEADERS)
        res.raise_for_status()
        data = res.json()
        
        # Case A: If API yields a nested HTML component inside the JSON dictionary wrapper
        if isinstance(data, dict) and "html" in data:
            html_snippet = data.get("html", "")
            if not html_snippet.strip():
                return {}
            soup = BeautifulSoup(f"<table>{html_snippet}</table>", "html.parser")
            _, schedule_rows = parse_html_table(soup)
            return schedule_rows
            
        # Case B: If API returns structured key-value maps directly
        elif isinstance(data, dict):
            schedule_rows = {}
            for item_key, values_dict in data.items():
                cleaned_key = item_key.strip()
                sorted_vals = [values_dict[k] for k in sorted(values_dict.keys())]
                schedule_rows[cleaned_key] = sorted_vals
            return schedule_rows
            
        return {}
    except Exception as e:
        print(f"  [WARN] Failed to fetch schedule for '{parent_name}': {e}")
        return {}

def scrape_balance_sheet(ticker):
    print(f"=== Starting Data Extraction for Ticker: {ticker} ===")
    
    screener_id, slug = get_screener_id_and_slug(ticker)
    if not screener_id or not slug:
        print(f"[ABORT] Could not resolve identity for {ticker}.\n")
        return
        
    print(f"[SUCCESS] Resolved Screener ID: {screener_id} | Slug: {slug}")
    
    company_url = f"https://www.screener.in/company/{slug}/consolidated/"
    response = requests.get(company_url, headers=HEADERS)
    
    if response.status_code == 404:
        company_url = f"https://www.screener.in/company/{slug}/"
        response = requests.get(company_url, headers=HEADERS)
        
    soup = BeautifulSoup(response.content, "html.parser")
    bs_section = soup.find("section", id="balance-sheet")
    
    if not bs_section:
        print("[ERROR] Could not find Balance Sheet section on this page.")
        return
        
    table = bs_section.find("table")
    dates, main_rows = parse_html_table(table)
    
    print("\n--- Parent Framework Matrix Rows ---")
    print(f"Timeline Columns: {dates}")
    for label, values in main_rows.items():
        print(f"  {label.ljust(25)}: {values}")

    # ── Detect extra / sector-specific rows ────────────────────────────────
    # e.g. Gross NPA %, Net NPA %, Capital Adequacy Ratio for banks/NBFCs.
    # "Total Equity" is also excluded here since the column has been dropped.
    extra_rows: dict[str, list] = {}
    for label in main_rows:
        if label.strip() not in KNOWN_BS_LABELS:
            extra_rows[label] = main_rows[label]

    if extra_rows:
        print("\n--- Extra / Sector-Specific Rows (→ balance_sheet_items) ---")
        for label, values in extra_rows.items():
            print(f"  [EXTRA]  {label.ljust(35)}: {values}")

    # ── Standard schedule breakdowns ───────────────────────────────────────
    schedule_parents = ["Borrowings", "Other Liabilities", "Other Assets", "Fixed Assets"]
    # Also fetch dedicated schedules for every extra row
    extra_schedule_parents = list(extra_rows.keys())

    print("\n--- Child Line Schedule Breakdowns ---")
    
    all_child_items: dict[str, dict] = {}

    for parent in schedule_parents:
        print(f"\nQuerying Sub-Schedule Endpoints for: [{parent}]...")
        child_items = fetch_schedule_item(screener_id, parent)
        
        if not child_items:
            print(f"  No breakdown sub-items extracted for '{parent}'.")
            continue
        
        all_child_items[parent] = child_items
        for child_label, child_values in child_items.items():
            padded_values = (child_values + [None] * len(dates))[:len(dates)]
            print(f"  ↳ {child_label.ljust(35)}: {padded_values}")

    # Extra-row schedules — each stored under "Extra Metrics – <label>"
    for parent in extra_schedule_parents:
        print(f"\nQuerying Extra-Row Schedule for: [{parent}]...")
        child_items = fetch_schedule_item(screener_id, parent)
        group_key = f"Extra Metrics – {parent}"

        if group_key not in all_child_items:
            all_child_items[group_key] = {}

        if child_items:
            all_child_items[group_key].update(child_items)
            for child_label, child_values in child_items.items():
                padded_values = (child_values + [None] * len(dates))[:len(dates)]
                print(f"  ↳ {child_label.ljust(35)}: {padded_values}")
        else:
            print(f"  No sub-items; the row value itself will be stored as an item.")

    # Store the top-level extra row value itself as an item so nothing is lost
    for label, values in extra_rows.items():
        group_key = f"Extra Metrics – {label}"
        if group_key not in all_child_items:
            all_child_items[group_key] = {}
        all_child_items[group_key].setdefault(label, values)

    print("\n=== Extraction Cycle Finished ===\n")

    return {
        "screener_id": screener_id,
        "slug":        slug,
        "dates":       dates,
        "main_rows":   main_rows,
        "child_items": all_child_items,
    }