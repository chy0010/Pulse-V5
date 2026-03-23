"""
Ticker resolution for MarketPulse.

COMPANY_TICKER  — entity name (lowercase) → ticker symbol
GEO_TICKERS     — political/geo entity (lowercase) → list of affected tickers
PRIVATE_PARENTS — private company → list of publicly-traded parent/investor tickers
"""

# ---------------------------------------------------------------------------
# Company → Ticker (static, authoritative)
# ---------------------------------------------------------------------------
COMPANY_TICKER = {
    # Big Tech
    "apple": "AAPL", "apple inc": "AAPL",
    "microsoft": "MSFT", "windows": "MSFT", "azure": "MSFT", "office 365": "MSFT",
    "google": "GOOGL", "alphabet": "GOOGL", "google deepmind": "GOOGL",
    "meta": "META", "facebook": "META", "instagram": "META", "whatsapp": "META",
    "amazon": "AMZN", "aws": "AMZN",
    "tesla": "TSLA",
    "netflix": "NFLX",
    "nvidia": "NVDA",
    "amd": "AMD", "advanced micro devices": "AMD",
    "intel": "INTC",
    "qualcomm": "QCOM",
    "broadcom": "AVGO",
    "tsmc": "TSM", "taiwan semiconductor": "TSM", "taiwan semiconductor manufacturing": "TSM",
    "samsung": "005930.KS",
    "asml": "ASML",
    "arm": "ARM", "arm holdings": "ARM",
    "micron": "MU", "micron technology": "MU",
    "ibm": "IBM",
    "oracle": "ORCL",
    "salesforce": "CRM",
    "adobe": "ADBE",
    "palantir": "PLTR",
    "snowflake": "SNOW",
    "cloudflare": "NET",
    "mongodb": "MDB",
    "datadog": "DDOG",
    "twilio": "TWLO",
    "zoom": "ZM",
    "slack": "CRM",  # acquired by Salesforce
    "uber": "UBER",
    "lyft": "LYFT",
    "airbnb": "ABNB",
    "doordash": "DASH",
    "shopify": "SHOP",
    "square": "SQ", "block": "SQ",
    "paypal": "PYPL",
    "stripe": None,  # private
    "coinbase": "COIN",
    "robinhood": "HOOD",
    "spotify": "SPOT",
    "twitter": "X",  # private now
    "x": None,  # private
    "sap": "SAP",
    "dell": "DELL",
    "hp": "HPQ", "hewlett packard": "HPQ",
    "hpe": "HPE",
    "cisco": "CSCO",
    "palo alto networks": "PANW",
    "crowdstrike": "CRWD",
    "fortinet": "FTNT",
    "servicenow": "NOW",
    "workday": "WDAY",
    "intuit": "INTU",

    # Finance
    "jpmorgan": "JPM", "jp morgan": "JPM", "jpmorgan chase": "JPM",
    "goldman sachs": "GS",
    "bank of america": "BAC",
    "wells fargo": "WFC",
    "morgan stanley": "MS",
    "blackrock": "BLK",
    "berkshire hathaway": "BRK-B",
    "visa": "V",
    "mastercard": "MA",
    "american express": "AXP",
    "citigroup": "C", "citi": "C",
    "hsbc": "HSBC",
    "hdfc": "HDB", "hdfc bank": "HDB",
    "icici bank": "IBN",
    "charles schwab": "SCHW",
    "fidelity": None,  # private
    "vanguard": None,  # private
    "blackstone": "BX",
    "kkr": "KKR",
    "apollo": "APO",

    # Energy & Oil
    "exxonmobil": "XOM", "exxon": "XOM",
    "chevron": "CVX",
    "shell": "SHEL",
    "bp": "BP",
    "conocophillips": "COP",
    "aramco": "2222.SR", "saudi aramco": "2222.SR",
    "halliburton": "HAL",
    "schlumberger": "SLB",
    "pioneer natural resources": "PXD",
    "nexterra energy": "NEE", "nextera": "NEE",
    "enphase": "ENPH",
    "first solar": "FSLR",
    "rivian": "RIVN",
    "lucid": "LCID",

    # Defense
    "lockheed martin": "LMT",
    "rtx": "RTX", "raytheon": "RTX",
    "northrop grumman": "NOC",
    "general dynamics": "GD",
    "boeing": "BA",
    "l3harris": "LHX",
    "bae systems": "BAESY",

    # Auto
    "gm": "GM", "general motors": "GM",
    "ford": "F",
    "toyota": "TM",
    "volkswagen": "VWAGY",
    "bmw": "BMWYY",
    "stellantis": "STLA",

    # Consumer / Media
    "disney": "DIS",
    "walmart": "WMT",
    "target": "TGT",
    "costco": "COST",
    "starbucks": "SBUX",
    "mcdonald's": "MCD", "mcdonalds": "MCD",
    "nike": "NKE",
    "adidas": "ADDYY",
    "coca-cola": "KO", "coca cola": "KO",
    "pepsi": "PEP", "pepsico": "PEP",
    "lvmh": "LVMHF",
    "richemont": "CFRUY",

    # Pharma / Health
    "pfizer": "PFE",
    "moderna": "MRNA",
    "johnson & johnson": "JNJ", "j&j": "JNJ",
    "unitedhealth": "UNH",
    "abbvie": "ABBV",
    "eli lilly": "LLY", "lilly": "LLY",
    "novo nordisk": "NVO",
    "merck": "MRK",
    "cvs": "CVS",

    # Telecom
    "at&t": "T",
    "verizon": "VZ",
    "t-mobile": "TMUS",
    "comcast": "CMCSA",

    # Crypto (ETFs/proxies)
    "bitcoin": "IBIT",   # iShares Bitcoin ETF as proxy
    "ethereum": "ETHA",
    "solana": None,

    # Indian market
    "reliance": "RELIANCE.NS", "reliance industries": "RELIANCE.NS",
    "tata": "TATAMOTORS.NS",
    "infosys": "INFY",
    "wipro": "WIT",
    "tcs": "TCS.NS", "tata consultancy": "TCS.NS",
    "hdfc life": "HDFCLIFE.NS",
    "bajaj": "BAJFINANCE.NS",
    "zerodha": None,  # private
    "groww": None,    # private
}

# ---------------------------------------------------------------------------
# Political / Geopolitical entity → affected tickers
# ---------------------------------------------------------------------------
GEO_TICKERS = {
    # US Political
    "donald trump": ["LMT", "RTX", "NOC", "XOM", "CVX", "JPM", "GS"],
    "joe biden": ["NEE", "ENPH", "FSLR", "JNJ", "PFE"],
    "jd vance": ["LMT", "RTX", "XOM"],
    "kamala harris": ["NEE", "ENPH", "JNJ"],
    "rand paul": ["XOM", "CVX"],
    "elon musk": ["TSLA", "SPCE", "AMZN"],

    # US Institutions
    "federal reserve": ["JPM", "BAC", "GS", "WFC", "MS", "O", "AMT"],
    "jerome powell": ["JPM", "BAC", "GS", "WFC", "MS"],
    "treasury": ["JPM", "GS", "BAC"],
    "sec": ["COIN", "HOOD", "GS", "JPM"],
    "ftc": ["GOOGL", "META", "AMZN", "MSFT", "AAPL"],
    "congress": ["LMT", "RTX", "NOC", "XOM", "JPM"],
    "democrats": ["NEE", "ENPH", "FSLR", "JNJ", "PFE", "UNH"],
    "republicans": ["LMT", "RTX", "NOC", "XOM", "CVX", "JPM", "GS"],

    # Countries / Regions
    "china": ["NVDA", "AMD", "QCOM", "AAPL", "TSM", "AVGO"],
    "iran": ["XOM", "CVX", "LMT", "RTX", "NOC", "HAL"],
    "israel": ["LMT", "RTX", "NOC", "XOM", "CVX"],
    "russia": ["XOM", "CVX", "SHEL", "LMT", "RTX", "NOC"],
    "india": ["INFY", "WIT", "HDB", "IBN"],
    "taiwan": ["TSM", "NVDA", "AMD", "QCOM", "AAPL"],
    "saudi arabia": ["XOM", "CVX", "2222.SR", "LMT"],
    "ukraine": ["LMT", "RTX", "NOC", "GD", "XOM", "CVX"],
    "europe": ["SHEL", "BP", "ASML", "SAP", "NVO"],
    "north korea": ["LMT", "RTX", "NOC"],

    # Geopolitical events / themes
    "nato": ["LMT", "RTX", "NOC", "GD", "BA"],
    "trade war": ["NVDA", "AMD", "TSM", "QCOM", "AAPL", "F", "GM"],
    "tariffs": ["AAPL", "NVDA", "TSM", "F", "GM", "NKE", "WMT"],
    "sanctions": ["XOM", "CVX", "SHEL", "BP"],
    "opec": ["XOM", "CVX", "COP", "HAL"],
    "middle east": ["XOM", "CVX", "LMT", "RTX", "NOC", "DAL", "UAL"],
    "strait of hormuz": ["XOM", "CVX", "DAL", "UAL", "LMT"],
    "red sea": ["XOM", "CVX", "DAL", "UAL"],
    "interest rates": ["JPM", "BAC", "GS", "WFC", "O", "AMT", "UNH"],
    "inflation": ["JPM", "GS", "XOM", "CVX", "WMT", "COST"],
    "recession": ["JPM", "GS", "WMT", "COST", "DG"],
    "ai regulation": ["GOOGL", "META", "MSFT", "AAPL", "AMZN", "NVDA"],
    "tech regulation": ["GOOGL", "META", "MSFT", "AAPL", "AMZN"],
    "crypto regulation": ["COIN", "HOOD", "MSTR"],
    "antitrust": ["GOOGL", "META", "AMZN", "MSFT", "AAPL"],

    # Macro concepts
    "federal budget": ["LMT", "RTX", "NOC", "JPM", "GS"],
    "debt ceiling": ["JPM", "GS", "BAC", "TLT"],
    "oil prices": ["XOM", "CVX", "COP", "HAL", "DAL", "UAL"],
    "semiconductor shortage": ["NVDA", "AMD", "INTC", "TSM", "QCOM"],
}

# ---------------------------------------------------------------------------
# Private AI companies → publicly traded investor/partner tickers
# ---------------------------------------------------------------------------
PRIVATE_PARENTS = {
    "anthropic":   ["GOOGL", "AMZN"],
    "openai":      ["MSFT"],
    "xai":         ["TSLA"],
    "grok":        ["TSLA"],
    "mistral":     [],
    "databricks":  [],
    "hugging face": [],
    "perplexity":  [],
    "cohere":      [],
    "stability ai": [],
}


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------
_VALID_TICKER_RE = __import__("re").compile(r"^[A-Z0-9.\-]{1,7}$")

def resolve_ticker(name: str, llm_ticker: str | None) -> str | None:
    """
    Return the best ticker for an entity.
    Priority: static map > validated LLM ticker > None
    """
    key = name.lower().strip()
    if key in COMPANY_TICKER:
        return COMPANY_TICKER[key]

    # Partial match — try if any key is a substring of the name
    for map_key, ticker in COMPANY_TICKER.items():
        if map_key and map_key in key:
            return ticker

    # Validate LLM-supplied ticker (reject obvious garbage)
    if llm_ticker:
        t = llm_ticker.strip().upper()
        if _VALID_TICKER_RE.match(t) and len(t) <= 6:
            return t

    return None


def get_affected_tickers(name: str) -> list[str]:
    """Return list of tickers affected by a geopolitical/political entity."""
    key = name.lower().strip()
    if key in GEO_TICKERS:
        return GEO_TICKERS[key]
    for geo_key, tickers in GEO_TICKERS.items():
        if geo_key in key or key in geo_key:
            return tickers
    return []


def get_investor_tickers(name: str) -> list[str]:
    """For private AI companies, return public investor/partner tickers."""
    key = name.lower().strip()
    return PRIVATE_PARENTS.get(key, [])

