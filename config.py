import logging
import os


# --- Logging Configuration ---
LOGGING_CONFIG = {
    'filename': 'airtable_fetch.log',
    'level': logging.INFO,
    'format': '%(asctime)s - %(levelname)s - %(message)s'
}

# --- Core Configuration ---
CONFIG = {
    "BASE_URL": "https://airtable.com",
    
    "LOGIN_PATHS": {
        "INITIAL_PAGE": "/login",
        "EMAIL_SUBMIT": "/auth/getLoginTypeForEmail",
        "LOGIN_ACTION": "/auth/login/"
    },
    
    "RECORD_ID": os.getenv("AIRTABLE_RECORD_ID"),
    "APPLICATION_ID": os.getenv("AIRTABLE_APP_ID"),
    "TABLE_VIEW_URL": os.getenv("AIRTABLE_TABLE_VIEW_URL"),

    "ACTIVITY_ENDPOINT_TEMPLATE": "v0.3/row/{}/readRowActivitiesAndComments",

    "COOKIES_FILE": "cookies.pkl",
    "OUTPUT_FILE": "revision_history_full.json"
}

def build_login_url(key):
    """Constructs a full login URL from the base URL and a path key."""
    base = CONFIG.get("BASE_URL")
    path = CONFIG.get("LOGIN_PATHS", {}).get(key)
    
    if base and path:
        return f"{base.rstrip('/')}{path}"
    return ""

# --- Headers ---
DEFAULT_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-GB,en;q=0.9',
    'Connection': 'keep-alive',
    'Host': 'airtable.com',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
                  '(KHTML, like Gecko) Version/26.0.1 Safari/605.1.15'
}

REVISION_HISTORY_HEADERS = {
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-GB,en;q=0.9',
    'Connection': 'keep-alive',
    'Host': 'airtable.com',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
                  '(KHTML, like Gecko) Version=26.0.1 Safari/605.1.15',
    'x-airtable-inter-service-client': 'webClient',
    'X-Requested-With': 'XMLHttpRequest',
    'x-time-zone': 'Asia/Calcutta',
    'x-user-locale': 'en'
}


ALL_CONFIG = {
    "LOGGING": LOGGING_CONFIG,
    "CORE": CONFIG,
    "LOGIN_URLS": {
        "INITIAL_PAGE_URL": build_login_url("INITIAL_PAGE"),
        "EMAIL_SUBMIT_URL": build_login_url("EMAIL_SUBMIT"),
        "LOGIN_ACTION_URL": build_login_url("LOGIN_ACTION")
    },
    "HEADERS": DEFAULT_HEADERS,
    "REV_HEADERS": REVISION_HISTORY_HEADERS
}
