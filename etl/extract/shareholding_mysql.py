import requests
from bs4 import BeautifulSoup
import urllib.parse
import re

# =========================================================
# HEADERS
# =========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest"
}

# =========================================================
# UTILITY FUNCTIONS
# =========================================================

def clean_ticker_for_screener(ticker):
    """
    Removes exchange suffixes like:
    .NS .BO :NS :BO
    """

    cleaned = ticker.upper().strip()

    for suffix in [".NS", ".BO", ":NS", ":BO"]:
        if cleaned.endswith(suffix):
            cleaned = cleaned.replace(suffix, "")

    return cleaned


def get_screener_id_and_slug(ticker):
    """
    Automatically resolve Screener slug + company id
    from ticker symbol.
    """

    clean_symbol = clean_ticker_for_screener(ticker)

    search_url = (
        f"https://www.screener.in/api/company/search/?q="
        f"{urllib.parse.quote(clean_symbol)}"
    )

    try:
        response = requests.get(search_url, headers=HEADERS)
        response.raise_for_status()

        results = response.json()

        if not results:
            print(f"[ERROR] No company found for {clean_symbol}")
            return None, None

        match = None

        # Try exact slug match first
        for item in results:

            raw_url = item.get("url", "")

            slug_candidate = (
                raw_url
                .replace("/company/", "")
                .replace("/consolidated/", "")
                .strip("/")
                .upper()
            )

            if slug_candidate == clean_symbol:
                match = item
                break

        # fallback
        if not match:
            print(
                f"[INFO] Exact slug not found. "
                f"Using: {results[0].get('name')}"
            )

            match = results[0]

        raw_url = match["url"]

        slug = (
            raw_url
            .replace("/company/", "")
            .replace("/consolidated/", "")
            .strip("/")
        )

        company_url = f"https://www.screener.in/company/{slug}/"

        page_response = requests.get(
            company_url,
            headers=HEADERS
        )

        screener_id = None

        if page_response.status_code == 200:

            id_match = re.search(
                r"/company/actions/(\d+)/",
                page_response.text
            )

            if id_match:
                screener_id = id_match.group(1)

            else:

                id_match_alt = re.search(
                    r"/api/company/(\d+)/",
                    page_response.text
                )

                if id_match_alt:
                    screener_id = id_match_alt.group(1)

        if not screener_id:
            screener_id = slug

        return screener_id, slug

    except Exception as e:
        print(f"[ERROR] Failed resolving company: {e}")
        return None, None


# =========================================================
# GENERIC TABLE PARSER
# =========================================================

def parse_html_table(table_soup):
    """
    Parse Screener table into:
    - dates
    - row dictionary
    """

    dates = []

    thead = table_soup.find("thead")

    if thead:

        headers = thead.find_all("th")

        for th in headers:

            date_key = th.get("data-date-key")
            text = th.get_text(strip=True)

            if date_key:
                dates.append(date_key)

            elif text:
                dates.append(text)

    dates = [d for d in dates if d and d != ""]

    rows_data = {}

    tbody = table_soup.find("tbody")

    if tbody:

        for tr in tbody.find_all("tr"):

            tds = tr.find_all("td")

            if not tds:
                continue

            row_label = (
                tds[0]
                .get_text(strip=True)
                .replace("+", "")
                .replace("-", "")
                .strip()
            )

            values = []

            for td in tds[1:]:

                val_text = (
                    td.get_text(strip=True)
                    .replace(",", "")
                    .replace("%", "")
                )

                if val_text in ("", "-", "Reference", "nan"):
                    values.append(None)

                else:

                    try:
                        values.append(float(val_text))

                    except ValueError:
                        values.append(val_text)

            rows_data[row_label] = values

    return dates, rows_data


# =========================================================
# SECTION TABLE EXTRACTOR
# =========================================================

def extract_section_table(soup, section_id):
    """
    Generic reusable extractor for:
    - quarterly
    - shareholding
    - balance sheet
    - cash flow
    """

    section = soup.find("section", id=section_id)

    if not section:
        return None, None

    table = section.find("table", class_="data-table")

    if not table:
        return None, None

    dates, rows = parse_html_table(table)

    return dates, rows


# =========================================================
# SHAREHOLDING SCRAPER
# =========================================================

def scrape_shareholding_pattern(ticker):

    print(
        f"\n================================================="
    )

    print(
        f" SHAREHOLDING PATTERN EXTRACTION : {ticker}"
    )

    print(
        f"=================================================\n"
    )

    screener_id, slug = get_screener_id_and_slug(ticker)

    if not screener_id or not slug:
        print("[ABORT] Could not resolve company")
        return None

    # -----------------------------------------------------
    # TRY CONSOLIDATED PAGE FIRST
    # -----------------------------------------------------

    company_url = (
        f"https://www.screener.in/company/"
        f"{slug}/consolidated/"
    )

    response = requests.get(
        company_url,
        headers=HEADERS
    )

    # fallback
    if response.status_code == 404:

        company_url = (
            f"https://www.screener.in/company/{slug}/"
        )

        response = requests.get(
            company_url,
            headers=HEADERS
        )

    if response.status_code != 200:
        print("[ERROR] Failed fetching company page")
        return None

    soup = BeautifulSoup(
        response.content,
        "html.parser"
    )

    # -----------------------------------------------------
    # EXTRACT SHAREHOLDING SECTION
    # -----------------------------------------------------

    dates, rows = extract_section_table(
        soup,
        section_id="shareholding"
    )

    if not dates or not rows:
        print("[ERROR] Shareholding section not found")
        return None

    # -----------------------------------------------------
    # PRINT OUTPUT
    # -----------------------------------------------------

    print("Timeline Columns:\n")

    print(dates)

    print("\n=================================================")
    print(" SHAREHOLDING DATA")
    print("=================================================\n")

    for label, values in rows.items():

        padded_values = (
            values + [None] * len(dates)
        )[:len(dates)]

        print(
            f"{label.ljust(35)} : {padded_values}"
        )

    # -----------------------------------------------------
    # RETURN STRUCTURED DATA
    # -----------------------------------------------------

    return {
        "ticker": ticker,
        "slug": slug,
        "dates": dates,
        "shareholding": rows
    }


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    ticker_to_test = "HAL"

    data = scrape_shareholding_pattern(
        ticker_to_test
    )

    print("\n=================================================")
    print(" FINAL JSON OUTPUT")
    print("=================================================\n")

    print(data)