import os
import re
import json
import random
import string
import logging
import pickle
import requests
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    filename='airtable_fetch.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Config - URLs and headers can be updated here if needed
CONFIG = {
    "BASE_URL": "https://airtable.com",
    "INITIAL_PAGE_URL": "https://airtable.com/login",
    "EMAIL_SUBMIT_URL": "https://airtable.com/auth/getLoginTypeForEmail",
    "LOGIN_ACTION_URL": "https://airtable.com/auth/login/",
    "RECORD_ID": "rechNv2gz12OgrESN",
    "APPLICATION_ID":"appqX7ccfJjKQN5gZ",
    "TABLE_VIEW_URL":"https://airtable.com/appqX7ccfJjKQN5gZ/tblTMcLnCsRgUcRlT/viw7Iw69amY4W24e7",
    "HEADERS": {
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
    },
    "REVISION_HISTORY_HEADERS": {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-GB,en;q=0.9',
        'Connection': 'keep-alive',
        'Host': 'airtable.com',
        'Referer': '',  # will set dynamically
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
                      '(KHTML, like Gecko) Version/26.0.1 Safari/605.1.15',
        'x-airtable-application-id': '',  # must be set dynamically
        'x-airtable-inter-service-client': 'webClient',
        'X-Requested-With': 'XMLHttpRequest',
        'x-time-zone': 'Asia/Calcutta',
        'x-user-locale': 'en'
    }
}

class AirtableScraper:
    def __init__(self, email, password, record_id):
        self.email = email
        self.password = password
        self.record_id = record_id
        self.session = requests.Session()
        self.cookies_file = "cookies.pkl"

    def save_cookies(self):
        with open(self.cookies_file, 'wb') as f:
            pickle.dump(self.session.cookies, f)
        logging.info("Cookies saved to file.")

    def load_cookies(self):
        try:
            with open(self.cookies_file, 'rb') as f:
                cookies = pickle.load(f)
                self.session.cookies.update(cookies)
            logging.info("Cookies loaded from file.")
            return True
        except FileNotFoundError:
            logging.info("Cookies file not found, login required.")
            return False

    def get_csrf_token(self, response):
        try:
            match = re.search(r'window\.initData\s*=\s*(\{.*?})\s*</script>', response.text, re.DOTALL)
            if match:
                json_string = match.group(1)
                init_data = json.loads(json_string)
                csrf_token = init_data.get("csrfToken")
                if csrf_token:
                    logging.info("CSRF Token retrieved.")
                    return csrf_token
            logging.error("CSRF token not found in response.")
            return None
        except Exception as e:
            logging.error(f"Error extracting CSRF token: {e}")
            return None

    def get_socket_id(self, response):
        try:
            match = re.search(r'window\.resolveLiveappDataPromise\((.*?)\);', response.text, re.DOTALL)
            if match:
                json_data_string = match.group(1).strip()
                data = json.loads(json_data_string)
                socket_id = data.get("secretSocketId", "")
                logging.info(f"Socket ID extracted: {socket_id}")
                return socket_id
            logging.error("Socket ID not found in response.")
            return None
        except Exception as e:
            logging.error(f"Error extracting socket ID: {e}")
            return None

    def generate_request_id(self, length=15):
        prefix = "req"
        chars = string.ascii_letters + string.digits
        random_part = ''.join(random.choices(chars, k=length))
        return prefix + random_part

    def extract_values_from_html(self, html):
        """
        Extracts column details (ID, Name, Type) along with old and new values
        from the diffRowHtml for all common field types.
        """
        soup = BeautifulSoup(html, "html.parser")

        old_values = []
        new_values = []
        
        # Initialize column details
        column_id = None
        column_name = None
        column_type = None

        # Find the primary historical cell container
        container = soup.select_one('.historicalCellContainer')
        if container:
            # Extract Column Name and ID from the header micro div
            header_div = container.select_one('.micro.strong.caps')
            if header_div:
                column_name = header_div.get_text(strip=True)
                column_id = header_div.get('columnid')
            
            #  Extract Column Type from data-columntype attribute of the historicalCellValue
            cell_value_div = container.select_one('.historicalCellValue')
            if cell_value_div:
                column_type = cell_value_div.get('data-columntype')

        if not column_type:
            return {
                "columnId": column_id,
                "columnName": column_name,
                "columnType": None,
                "oldValue": None,
                "newValue": None
            }
        
        if column_type in ('text', 'multilineText', 'phone', 'number', 'date'):
            # Look for negative background/foreground or strikethrough text
            removed_text_blocks = soup.select(
                '.historicalCellValue [class*="colors-background-negative"],'
                '.historicalCellValue [class*="colors-foreground-accent-negative"],'
                '.historicalCellValue [class*="strikethrough"]'
            )
            for el in removed_text_blocks:
                val = el.get_text(strip=True)
                # Special cleanup for multiline/text diff spans
                if 'textDiff' in el.parent.get('class', []):
                    val = re.sub(r'^\s*$', '', val.replace('\xa0', ' '), flags=re.MULTILINE).strip()
                else:
                    inner_text_el = el.select_one('.url') or el.select_one('.truncate') or el
                    val = inner_text_el.get_text(strip=True)
                if val: old_values.append(val)
        
        elif column_type in ('select', 'multiSelect'):
             # Removed pill is marked with line-through style OR has a Minus SVG
            containers_with_minus = soup.select('div.inline-block:has(svg use[href*="#Minus"])')
            for container in containers_with_minus:
                pill = container.select_one('.choiceToken')
                if pill:
                    old_values.append(pill.get('title') or pill.select_one('.truncate-pre').get_text(strip=True))

            removed_by_style = soup.select('.choiceToken[style*="line-through"]')
            for pill in removed_by_style:
                value = pill.get('title') or pill.select_one('.truncate-pre').get_text(strip=True)
                if value not in old_values: 
                    old_values.append(value)

        elif column_type == 'checkbox':
            # Removed is marked by .redLight2
            if soup.select_one('.historicalCellValue .redLight2'):
                old_values.append("True")

        elif column_type == 'multipleAttachment':
            # Removed attachment has the red border/title "was removed"
            removed_attachments = soup.select('.preview[title*="was removed"], .preview.rounded[class*="border-red-light1"]')
            for att in removed_attachments:
                val = att.get('title')
                if val and val.endswith(" was removed"):
                    old_values.append(val[:-12])
        
        elif column_type == 'rating':
            # Removed rating has negative background
            rating_container = soup.select_one('.ratingContainer[class*="colors-background-negative"]')
            if rating_container:
                # Count the filled rating icons (exclude invisible icons)
                count = len(rating_container.select('svg:not(.invisible) path[fill]'))
                if count > 0:
                    old_values.append(str(count))
        
        # --- Extract New Value (Added) ---

        if column_type in ('text', 'multilineText', 'phone', 'number', 'date'):
            # Look for success background
            added_text_blocks = soup.select('.historicalCellValue [class*="colors-background-success"]')
            for el in added_text_blocks:
                # Handle text diff spans for multiline/text
                if 'textDiff' in el.parent.get('class', []):
                    val = el.get_text(strip=True)
                # Handle simple field values
                else:
                    inner_text_el = el.select_one('.url') or el.select_one('.truncate') or el
                    val = inner_text_el.get_text(strip=True)
                if val: new_values.append(val.strip())

        elif column_type in ('select', 'multiSelect'):
            # Added/Retained pill is NOT line-through AND either has Plus SVG OR is an active pill in a non-diff context
            # We look for all pills that are not marked as removed (no line-through)
            active_pills = soup.select('.choiceToken:not([style*="line-through"])')
            for pill in active_pills:
                # If the pill has a Plus icon, it was added.
                # If it's an active pill, and the parent is a diff container, we include it as the final state.
                if pill.select_one('svg use[href*="#Plus"]') or not soup.select_one('.historicalCellValue.diff'):
                    new_values.append(pill.get('title') or pill.select_one('.truncate-pre').get_text(strip=True))
                # If it's in a diff container but has no Plus/Minus, it's an unchanged value—we should still include it
                # as part of the new state for Multi-select fields.
                elif soup.select_one('.historicalCellValue.diff'):
                    new_values.append(pill.get('title') or pill.select_one('.truncate-pre').get_text(strip=True))
        
        elif column_type == 'checkbox':
            # Added is marked by .greenLight2
            if soup.select_one('.historicalCellValue .greenLight2'):
                new_values.append("True")

        elif column_type == 'multipleAttachment':
            # Added attachment has the green border/title "was added"
            added_attachments = soup.select('.preview[title*="was added"], .preview.rounded[class*="border-green-light1"]')
            for att in added_attachments:
                val = att.get('title')
                if val and val.endswith(" was added"):
                    new_values.append(val[:-10])
        
        elif column_type == 'rating':
            # Added rating has success background
            rating_container = soup.select_one('.ratingContainer[class*="colors-background-success"]') or soup.select_one('.ratingContainer:not([class*="colors-background-negative"])')
            if rating_container:
                count = len(rating_container.select('svg:not(.invisible) path[fill]'))
                if count > 0:
                    new_values.append(str(count))
        
        # --- 4. Final Formatting ---
    
        # Use " | " joining for multi-value fields (Multi-Select, Attachment)
        if column_type in ('multiSelect', 'multipleAttachment', 'select'):
            old_val = " | ".join(sorted(list(set(filter(None, old_values))))) or None
            new_val = " | ".join(sorted(list(set(filter(None, new_values))))) or None
        else:
            # Simple fields (Text, Number, Date, Checkbox, Rating) take the single determined value
            old_val = old_values[0] if old_values else None
            new_val = new_values[0] if new_values else None

        # Final check for multiline text formatting (preserve full string structure)
        if column_type == 'multilineText':
            old_val = old_values[0] if old_values else None
            new_val = new_values[0] if new_values else None

        # Special case: If it was a simple change (diff), the whole value might be concatenated
        # This acts as a fallback if the CSS selectors failed to separate old/new cleanly.
        if not old_val and not new_val:
            diff_container = soup.select_one('.historicalCellValue')
            if diff_container:
                # Attempt to find the full old value (strikethrough) and full new value separately
                old_el = diff_container.select_one('[class*="strikethrough"]')
                new_el = diff_container.select_one(':not([class*="strikethrough"]) > .flex-auto')
                
                old_val = old_el.get_text(strip=True) if old_el else None
                new_val = new_el.get_text(strip=True) if new_el else None
            
        # Handle Column Config changes (which often only have an old value in valueToNull)
        if not new_val and old_val and "columnConfig" in html:
            new_val = None
        
        return {
            "columnId": column_id,
            "columnName": column_name,
            "columnType": column_type,
            "oldValue": old_val,
            "newValue": new_val
        }

    def parse_revision_history(self, data):
        users = data.get("rowActivityOrCommentUserObjById", {})
        activities = data.get("rowActivityInfoById", {})
        comments = data.get("commentsById", {})
        ordered_ids = data.get("orderedActivityAndCommentIds", [])
        parsed = []
        for entry_id in ordered_ids:
            if entry_id.startswith("com"):  # Comment
                comment = comments.get(entry_id, {})
                user = users.get(comment.get("userId"), {})
                parsed.append({
                    "id": comment.get("id"),
                    "type": "comment",
                    "user": {
                        "id": user.get("id"),
                        "email": user.get("email"),
                        "name": user.get("name")
                    },
                    "timestamp": comment.get("createdTime"),
                    "comment": comment.get("text")
                })
            else:  # Activity
                activity = activities.get(entry_id, {})
                user = users.get(activity.get("originatingUserId"), {})
                details = self.extract_values_from_html(activity.get("diffRowHtml", ""))
                parsed.append({
                    "id": entry_id,
                    "type": activity.get("groupType"),
                    "user": {
                        "id": user.get("id"),
                        "email": user.get("email"),
                        "name": user.get("name")
                    },
                    "timestamp": activity.get("createdTime"),
                    "columnId": details.get("columnId"),      
                    "columnName": details.get("columnName"),  
                    "columnType": details.get("columnType"), 
                    "oldValue": details.get("oldValue"),
                    "newValue": details.get("newValue")
                })
        return parsed

    def save_to_file(self, parsed_data, filename='revision_history_full.json'):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(parsed_data, f, indent=4, ensure_ascii=False)
            logging.info(f"Revision history saved to {filename}")
        except Exception as e:
            logging.error(f"Error saving JSON to file: {e}")

    def get_initial_page(self):
        try:
            response = self.session.get(CONFIG['INITIAL_PAGE_URL'], headers=CONFIG['HEADERS'])
            response.raise_for_status()
            logging.info("Initial login page fetched.")
            return response
        except Exception as e:
            logging.error(f"Error fetching initial page: {e}")
            return None

    def post_email_req(self, csrf_token):
        payload = {
            "_csrf": csrf_token,
            "urlToRedirectTo": "",
            "countryCode": "",
            "didConsentToMarketing": "",
            "email": self.email
        }
        try:
            response = self.session.post(CONFIG['EMAIL_SUBMIT_URL'], data=payload, headers=CONFIG['HEADERS'], allow_redirects=True)
            response.raise_for_status()
            logging.info("Email POST request successful.")
            return response
        except Exception as e:
            logging.error(f"Error during email POST request: {e}")
            return None

    def post_login_req(self, csrf_token):
        payload = {
            "_csrf": csrf_token,
            "urlToRedirectTo": "",
            "email": self.email,
            "password": self.password
        }
        try:
            response = self.session.post(CONFIG['LOGIN_ACTION_URL'], data=payload, headers=CONFIG['HEADERS'], allow_redirects=True)
            logging.info(f"Login POST request status: {response.status_code}")
            return response
        except Exception as e:
            logging.error(f"Error during login POST request: {e}")
            return None

    def get_record_revision_history(self, record_id, socket_id, app_id, offset_v2=None):
        try:
            headers = CONFIG['REVISION_HISTORY_HEADERS'].copy()
            headers['Referer'] = f"{CONFIG['TABLE_VIEW_URL']}/{record_id}?blocks=hide"
            headers['x-airtable-application-id'] = app_id

            params = {
                "stringifiedObjectParams": json.dumps({
                    "limit": 10,
                    "offsetV2": offset_v2,
                    "shouldReturnDeserializedActivityItems": True,
                    "shouldIncludeRowActivityOrCommentUserObjById": True
                }),
                "requestId": self.generate_request_id(),
                "secretSocketId": socket_id
            }
            url = f"https://airtable.com/v0.3/row/{record_id}/readRowActivitiesAndComments"
            response = self.session.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("msg") != "SUCCESS":
                logging.error("Failed to fetch revision history.")
                return [], None
            logging.info("Revision history fetched successfully.")
            parsed_data = self.parse_revision_history(data.get("data", {}))
            offset_v2_out = data.get("data", {}).get("offsetV2")
            return parsed_data, offset_v2_out
       
        except Exception as e:
            logging.error(f"Error fetching revision history: {e}")
            return [], None

    def get_all_revision_history(self, record_id, socket_id, app_id):
        all_results = []
        offset_v2 = None

        while True:
            batch, offset_v2 = self.get_record_revision_history(record_id, socket_id, app_id, offset_v2)
            all_results.extend(batch)
            if not offset_v2:
                break
        return all_results
    
    def run(self):
        if not self.load_cookies():
            # Login flow
            initial_resp = self.get_initial_page()
            if not initial_resp:
                logging.error("Failed initial page fetch, exiting.")
                return
            csrf_token = self.get_csrf_token(initial_resp)
            if not csrf_token:
                logging.error("CSRF token missing, exiting.")
                return
            email_resp = self.post_email_req(csrf_token)
            csrf_token_login = self.get_csrf_token(email_resp)
            login_resp = self.post_login_req(csrf_token_login)
            if not login_resp or login_resp.status_code not in [200, 302, 303]:
                logging.error("Login failed, exiting.")
                return

            self.save_cookies()
            socket_id = self.get_socket_id(login_resp)
        else:
            # Assume logged in, fetch homepage to get socket id
            homepage_resp = self.session.get(CONFIG['BASE_URL'], headers=CONFIG['HEADERS'])
            socket_id = self.get_socket_id(homepage_resp)

        app_id = CONFIG["APPLICATION_ID"] 
        
        revision_data = self.get_all_revision_history(self.record_id, socket_id, app_id)
        if revision_data:
            self.save_to_file(revision_data)
        else:
            logging.error("No revision data to save.")

def main():
    email = os.getenv("AIRTABLE_EMAIL")
    password = os.getenv("AIRTABLE_PASSWORD")
    record_id = CONFIG['RECORD_ID']

    if not email or not password or not record_id:
        logging.error("Missing environment variables AIRTABLE_EMAIL, AIRTABLE_PASSWORD, or AIRTABLE_RECORD_ID")
        return

    scraper = AirtableScraper(email, password, record_id)
    scraper.run()


if __name__ == "__main__":
    main()
