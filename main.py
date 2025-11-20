from bs4 import BeautifulSoup
import requests
import brotli
import random
import string
import json
import re

# ---- Session setup ----
session = requests.Session()
# ---- End setup ----

# ---- URL configurations ----
BASE_URL = "https://airtable.com"
INITIAL_PAGE_URL = f"{BASE_URL}/login"
EMAIL_SUBMIT_URL = f"{BASE_URL}/auth/getLoginTypeForEmail"
LOGIN_ACTION_URL = f"{BASE_URL}/auth/login/"
# ---- End URL configurations ----

# ---- User configurations ----
EMAIL = "lazy1080@outlook.com"
PASSWORD = "K5v-S3gu-Irt3"
APPLICATION_ID = ""
RECORD_ID = "recKBOZiRVxyT66Ir"
# ---- End User configurations ----

# ---- Other constants ----
GEN_HEADERS = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-GB,en;q=0.9',
        'Connection': 'keep-alive',
        'Host': 'airtable.com',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0.1 Safari/605.1.15'
    }
# ---- End constants ----

# ---- Helper methods ----
def get_csrf_token(response):
    try:
        match = re.search(r'window\.initData\s*=\s*(\{.*?})\s*</script>', response.text, re.DOTALL)
        if match:
            # 2. Extract the JSON string
            json_string = match.group(1)
            try:
                # Attempt to load the JSON
                init_data = json.loads(json_string)
                # 3. Extract the csrfToken field
                csrf_token = init_data.get("csrfToken")
                if csrf_token:
                    print(f"✅ CSRF Token retrieved: {csrf_token}")
                    return csrf_token
                else:
                    print("❌ Error: 'csrfToken' key not found in window.initData.")
                    return None
            except json.JSONDecodeError as e:
                print(f"❌ Error decoding JSON from initData: {e}")
                return None
        else:
            print("❌ Error: Could not find 'window.initData' script block.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Error getting CSRF token: {e}")
        return None

def get_socket_id(response):
    match = re.search(r'window\.resolveLiveappDataPromise\((.*?)\);', response.text, re.DOTALL)
    if match:
        # 1. The captured content is in group 1 of the match object
        json_data_string = match.group(1).strip()
        # 2. Parse the extracted string into a Python dictionary
        try:
            # The content is a valid JSON object
            data = json.loads(json_data_string)
            secret_socket_id = data.get("secretSocketId","")
            print("---------------------------")
            print (f"SocketId: {secret_socket_id}")
            print("---------------------------")
        except json.JSONDecodeError as e:
            print(f"\n❌ ERROR: Failed to decode JSON data. Check the extracted string for invalid JSON structure. Error: {e}")
            # print(f"String extracted: {json_data_string[:100]}...") # Uncomment to debug
    else:
        print("\n❌ ERROR: Could not find the 'window.resolveLiveappDataPromise' function call in the response.")
    return secret_socket_id

def generate_request_id(length=15):
    prefix = "req"
    chars = string.ascii_letters + string.digits
    random_part = ''.join(random.choices(chars, k=length))
    return prefix + random_part

def extract_values_from_html(html):
        soup = BeautifulSoup(html, "html.parser")
        column_name = ''
        old_val = ''
        new_val = ''
        print("Given html",soup)
        # Extract Column Name (using the div with columnId)
        column_name_div = soup.find("div", columnid=True)
        if column_name_div:
            column_name = column_name_div.get_text(strip=True)
            diff_div = soup.find("div", class_="historicalCellValue")
            print('---DiffDiv:',diff_div)
            column_type = diff_div['data-columntype']

            if column_type == 'checkbox':
                is_checked = diff_div.find('div', class_='greenLight2')
                is_unchecked = diff_div.find('div', class_='redLight2')
                if is_checked :
                    return column_name, old_val, 'checked'
                elif is_unchecked:
                    return column_name, old_val, 'unchecked'
                else:
                    return column_name, old_val, new_val

            if column_type == 'foreignKey':
                if diff_div.find('div',class_='added'):
                    new_val = 'Added:'
                elif diff_div.find('div',class_='removed'):
                    new_val = 'Removed:'
                else:
                    return column_name,old_val,new_val
                
                all_elements = diff_div.find_all('div', class_=['added','removed'])
                for el in all_elements:
                    classes = el.get('class',[])
                    if 'added'in classes:
                        new_val = new_val+el.get_text(strip=True)+','
                    elif 'removed' in classes:
                        new_val = new_val+el.get_text(strip=True)+','
                return column_name, old_val, new_val  
               
            all_elements = diff_div.find_all('span')
            if not all_elements:
                all_elements = diff_div.find_all(class_ = ["colors-background-success","colors-background-negative"])
            for el in all_elements:
                style = el.get('style', '')
                classes = el.get('class', [])
                if 'line-through' in style or any(cls in classes for cls in ['strikethrough','colors-background-negative']):
                    old_val =old_val+ el.get_text(strip=True) + ','
                else:
                    new_val = new_val + el.get_text(strip=True) + ','
    
        # old_span = diff_div.find("span", style=lambda s: s and "line-through" in s) or diff_div.find("span", class_="strikethrough")

        # if old_span:
        #     old_val = old_span.get_text(strip=True)

        # # Detect new value (non-strikethrough/historic cell value)
        # new_span = diff_div.find("div", class_="historicalCellValue") or soup.find("span", class_="historicalCellValue")
        # if new_span:
        #     new_val = new_span.get_text(strip=True)
        print("Col:",column_name,"Old:",old_val,"New",new_val)
        return column_name, old_val, new_val

def parse_revision_history(data):
    users = data.get("rowActivityOrCommentUserObjById", {})
    activities = data.get("rowActivityInfoById", {})
    comments = data.get("commentsById", {})
    ordered_ids = data.get("orderedActivityAndCommentIds", [])
    parsed = []
    for entry_id in ordered_ids:
        if entry_id.startswith("com"):  # Comment entry
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
        else:  # Activity entry
            activity = activities.get(entry_id, {})
            user = users.get(activity.get("originatingUserId"), {})
            column_name, old_val, new_val = extract_values_from_html(activity.get("diffRowHtml", ""))
            parsed.append({
                "id": entry_id,
                "type": activity.get("groupType"),
                "user": {
                    "id": user.get("id"),
                    "email": user.get("email"),
                    "name": user.get("name")
                },
                "timestamp": activity.get("createdTime"),
                "columnName": column_name,
                "oldValue": old_val,
                "newValue": new_val
            })
    return parsed
# ---- End Helper methods ----

def save_to_file(parsed_data, filename='revision_history.json'):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(parsed_data, f, indent=4, ensure_ascii=False)
    print(f"Revision history saved to {filename}")

def get_record_revision_history(record_id, socket_id):
    print(f"\nFetching revision history for record: {record_id}")
    headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-GB,en;q=0.9',
        'Connection': 'keep-alive',
        'Host': 'airtable.com',
        'Referer': 'https://airtable.com/appcasuo89MRUHWp5/tbliGjVcY63whxkGg/viwAGEHKAEGcdS6Y9/recDRzYc8IchlEqqf?blocks=hide',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0.1 Safari/605.1.15',
        'x-airtable-application-id': 'appcasuo89MRUHWp5',
        'x-airtable-inter-service-client': 'webClient',
        'X-Requested-With': 'XMLHttpRequest',
        'x-time-zone': 'Asia/Calcutta',
        'x-user-locale': 'en'
    }
    params = {
        "stringifiedObjectParams": json.dumps({
            "limit": 10,
            "offsetV2": None,
            "shouldReturnDeserializedActivityItems": True,
            "shouldIncludeRowActivityOrCommentUserObjById": True
        }),
        "requestId": generate_request_id(),
        "secretSocketId": socket_id
    }

    url = f"https://airtable.com/v0.3/row/{record_id}/readRowActivitiesAndComments"
    try:
        response = session.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        # print(data)
        if not data.get("msg") == "SUCCESS":
            print("Failed to fetch revision history")
            return []
            
        print("✅ Revision history fetched successfully.")
        parsed_revision_data = parse_revision_history(data.get("data", {}))
        return parsed_revision_data
          
    except requests.exceptions.RequestException as e:
        print(f"Error fetching revision history: {e}")
        return []

def post_login_req(csrf_token):
    url = LOGIN_ACTION_URL
    headers = GEN_HEADERS

    print(f"\nSending POST request to: {url}")
    login_payload = {
        "_csrf": csrf_token,
        "urlToRedirectTo": "",
        "email": EMAIL,
        "password": PASSWORD
    }
    try:
        response = session.post(url, data=login_payload, headers=headers, allow_redirects=True)
        print(f"Status Code: {response.status_code}")
        if response.status_code in [302, 303]:
            print("\n✅ Login attempt successful! Server initiated a redirect.")
            print(f"Redirecting to: {response.headers.get('Location')}")
        elif response.status_code == 200 and "Sign in" not in response.text:
            print("✅ Login attempt successful! Server returned the destination page.")
        else:
            print("❌ Login failed. The status code or page content suggests an error (e.g., wrong password).")
        return response
    except requests.exceptions.RequestException as e:
        print(f"Error during login POST request: {e}")
        return None

def post_email_req(csrf_token):
    url = EMAIL_SUBMIT_URL
    print(f"\nSending POST request to: {url}")

    headers = GEN_HEADERS
    payload = {
        "_csrf": csrf_token,
        "urlToRedirectTo": "",
        "countryCode": "",
        "didConsentToMarketing": "",
        "email": EMAIL
    }

    try:
        response = session.post(url, data=payload, headers=headers, allow_redirects=True)
        response.raise_for_status()
        print(f"Status Code: {response.status_code}")
        return response
    except requests.exceptions.RequestException as e:
        print(f"Error during email POST request: {e}")
        return None
  
def get_initial_page():
    url = INITIAL_PAGE_URL
    print(f"\nFetching initial page at: {url}")
    
    headers = GEN_HEADERS
    try:
        response = session.get(url,headers=headers)
        response.raise_for_status()
        print(f"Status Code: {response.status_code}")
        return response
    except requests.exceptions.RequestException as e:
        print(f"Error during initial GET request to {url}: {e}")
        return None

# ---- Main ----
def main():
    # 1. Get Login Paget
    initial_response = get_initial_page()
    initial_token = get_csrf_token(initial_response)
    # 2. Send Email Post Request
    print(f"Using CSRF Token: {initial_token}")
    email_response = post_email_req(initial_token)
    login_token = get_csrf_token(email_response)
    # 3. Send Login Post Request
    print(f"Using CSRF Token: {login_token}")
    home_page = post_login_req(login_token)
    # 4. Extract Socket Id after logging
    socketId = get_socket_id(home_page)
    # 5. Get revision history data
    revision_data = get_record_revision_history(RECORD_ID, socketId)
    save_to_file(revision_data)
# ---- End main ----

if __name__ == '__main__':
    main()