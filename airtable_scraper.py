import os
import json
import logging
import pickle
import requests
import urllib3
from pathlib import Path
from requests.adapters import HTTPAdapter
from config import ALL_CONFIG 
from utils import (
    get_csrf_token, 
    get_socket_id, 
    generate_request_id,
    parse_revision_history
)

logger = logging.getLogger(__name__)

# --- Retry Setup ---
retry_strategy = urllib3.Retry(
    total=5,
    backoff_factor=1, 
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)


class AirtableScraper:
    def __init__(self, email, password):
        self.email = email
        self.password = password

        self.config = ALL_CONFIG.get('CORE', {})
        self.record_id = self.config.get('RECORD_ID')
        self.app_id = self.config.get('APPLICATION_ID')
        self.table_view_url = self.config.get('TABLE_VIEW_URL')
        self.activity_endpoint_template = self.config.get('ACTIVITY_ENDPOINT_TEMPLATE')
        self.cookies_file = self.config.get('COOKIES_FILE')
        self.output_file = self.config.get('OUTPUT_FILE','results.json')
     
        login_urls = ALL_CONFIG.get('LOGIN_URLS', {})
        self.initial_page_url = login_urls.get('INITIAL_PAGE_URL')
        self.email_submit_url = login_urls.get('EMAIL_SUBMIT_URL')
        self.login_action_url = login_urls.get('LOGIN_ACTION_URL')
        
        self.headers = ALL_CONFIG.get('HEADERS', {})
        self.rev_headers_template = ALL_CONFIG.get('REV_HEADERS', {})

        self.session = requests.Session()
        # Mount the retry adapter to the session
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        


    def save_cookies(self):
        try:
            with open(self.cookies_file, 'wb') as f:
                pickle.dump(self.session.cookies, f)
            logger.info("Cookies saved to file.")
        except Exception as e:
            logger.error(f"Error saving cookies: {e}")

    def load_cookies(self):
        if not Path(self.cookies_file).exists():
            logger.info("Cookies file not found, login required.")
            return False
        try:
            with open(self.cookies_file, 'rb') as f:
                cookies = pickle.load(f)
                self.session.cookies.update(cookies)
            logger.info("Cookies loaded from file.")
            return True
        except Exception as e:
            logger.error(f"Error loading cookies: {e}. Clearing file to force re-login.")
            self.clear_cookies()
            return False

    def clear_cookies(self):
        """Removes the local cookie file and session cookies."""
        if Path(self.cookies_file).exists():
            os.remove(self.cookies_file)
            logger.warning("Invalid cookies file removed. Forced re-login.")
        self.session.cookies.clear()


    # --- Network Methods ---
    def _make_request(self, method, url, **kwargs):
        """Generic request wrapper with error logging."""
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error {e.response.status_code} for {url}: {e.response.text[:100]}...")
            if e.response.status_code in [401, 403]:
                logger.warning("Auth failure detected. Clearing cookies.")
                self.clear_cookies()
            return None
        except Exception as e:
            logger.error(f"Network Error for {url}: {e}")
            return None

    def get_initial_page(self):
        return self._make_request('GET', self.initial_page_url, headers=self.headers)

    def post_email_req(self, csrf_token):
        payload = {
            "_csrf": csrf_token, 
            "urlToRedirectTo": "", 
            "countryCode": "", 
            "didConsentToMarketing": "", 
            "email": self.email
        }
        return self._make_request('POST', self.email_submit_url, data=payload, headers=self.headers, allow_redirects=True
        )

    def post_login_req(self, csrf_token):
        payload = {
            "_csrf": csrf_token, 
            "urlToRedirectTo": "", 
            "email": self.email, 
            "password": self.password
        }
        return self._make_request('POST', self.login_action_url, data=payload, headers=self.headers, allow_redirects=True)

    def get_secret_socket_id(self):
        """Fetches the home page to extract the latest socket ID."""
        homepage_resp = self._make_request('GET', self.config.get('BASE_URL'), headers=self.headers)
        if homepage_resp and homepage_resp.status_code == 200:
            return get_socket_id(homepage_resp)
        return None

    def run_login_flow(self):
        """Executes the full login process and saves cookies."""
        logger.info("Starting login.")
        
        initial_resp = self.get_initial_page()
        csrf_token_1 = get_csrf_token(initial_resp) if initial_resp else None
        if not csrf_token_1: return False
        
        email_resp = self.post_email_req(csrf_token_1)
        csrf_token_2 = get_csrf_token(email_resp) if email_resp else None
        if not csrf_token_2: return False
        
        login_resp = self.post_login_req(csrf_token_2)
        if not login_resp: return False

        self.save_cookies()
        logger.info("Login completed successfully.")
        return True
    
   
    # --- Data Fetching ---
    def get_record_revision_history(self, offset_v2=None):
        headers = self.rev_headers_template.copy()
        headers['Referer'] = f"{self.table_view_url}/{self.record_id}"
        headers['x-airtable-application-id'] = self.app_id
        
        socket_id = self.get_secret_socket_id()
        if not socket_id:
            logger.error("Could not obtain a socket ID, attempting re-login.")
            if not self.run_login_flow():
                 return [], None
            socket_id = self.get_secret_socket_id()
            if not socket_id:
                logger.error("Failed to get socket ID even after re-login.")
                return [], None

        params = {
            "stringifiedObjectParams": json.dumps({
                "limit": 10, "offsetV2": offset_v2,
                "shouldReturnDeserializedActivityItems": True,
                "shouldIncludeRowActivityOrCommentUserObjById": True
            }),
            "requestId": generate_request_id(),
            "secretSocketId": socket_id
        }

        base_url = self.config.get('BASE_URL')
        if not base_url:
            logger.error("Configuration missing BASE_URL")
            return [], None
        
        url_path = self.activity_endpoint_template.format(self.record_id)
        url = f"{base_url}/{url_path}"

        response = self._make_request('GET', url, headers=headers, params=params)
        
        if not response:
            return [], None
        
        try:
            data = response.json()
            if data.get("msg") != "SUCCESS":
                logger.error("Failed to fetch revision history: API message failed.")
                return [], None
            
            logger.info(f"Revision history batch fetched. Offset: {offset_v2}")
            parsed_data = parse_revision_history(data.get("data", {}))
            offset_v2_out = data.get("data", {}).get("offsetV2")
            
            return parsed_data, offset_v2_out
        
        except Exception as e:
            logger.error(f"Error processing revision history response: {e}")
            return [], None

    def get_all_revision_history(self):
        all_results = []
        offset_v2 = None

        while True:
            batch, offset_v2 = self.get_record_revision_history(offset_v2)
            all_results.extend(batch)
            if not offset_v2:
                break
            logger.info(f"Fetched {len(batch)} items. Continuing...")

        try:
            all_results.sort(key=lambda entry: entry.timestamp, reverse=True) 
            logger.info(f"Successfully sorted all {len(all_results)} entries by timestamp.")
        except Exception as e:
            logger.error(f"Failed to sort revision history entries: {e}")     

        return all_results
    
    
    # --- Save File ---
    def save_to_file(self, parsed_data):
        try:
            data_to_save = [entry.to_dict() for entry in parsed_data]
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=4, ensure_ascii=False)
            logger.info(f"Revision history saved to {self.config['OUTPUT_FILE']}")
        except Exception as e:
            logger.error(f"Error saving JSON to file: {e}")

    
    # --- Run ---
    def run(self):
        if not self.load_cookies():
            if not self.run_login_flow():
                logger.critical("Login failed and cookies could not be loaded. Exiting.")
                return

        revision_data = self.get_all_revision_history()
        
        if revision_data:
            self.save_to_file(revision_data)
        else:
            logger.error("No revision data to save.")

