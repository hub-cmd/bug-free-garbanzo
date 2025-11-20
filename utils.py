import re
import json
import string
import random
import logging
from data_models import RevisionEntry
from airtable_parser import AirtableHtmlParser 

logger = logging.getLogger(__name__)

def get_csrf_token(response):
    """Extracts the CSRF token from the HTML response."""
    try:
        match = re.search(r'window\.initData\s*=\s*(\{.*?})\s*</script>', response.text, re.DOTALL)
        if match:
            json_string = match.group(1)
            init_data = json.loads(json_string)
            csrf_token = init_data.get("csrfToken")
            if csrf_token:
                logger.debug("CSRF Token retrieved.")
                return csrf_token
        logger.error("CSRF token not found in response.")
        return None
    except Exception as e:
        logger.error(f"Error extracting CSRF token: {e}")
        return None

def get_socket_id(response):
    """Extracts the secretSocketId from the HTML response."""
    try:
        match = re.search(r'window\.resolveLiveappDataPromise\((.*?)\);', response.text, re.DOTALL)
        if match:
            json_data_string = match.group(1).strip()
            data = json.loads(json_data_string)
            socket_id = data.get("secretSocketId", "")
            logger.debug(f"Socket ID extracted: {socket_id}")
            return socket_id
        logger.error("Socket ID not found in response.")
        return None
    except Exception as e:
        logger.error(f"Error extracting socket ID: {e}")
        return None
    
def generate_request_id(length=15):
    """Generates a random request ID for the private API."""
    prefix = "req"
    chars = string.ascii_letters + string.digits
    random_part = ''.join(random.choices(chars, k=length))
    return prefix + random_part

def parse_revision_history(data):
    """
    Parses the raw JSON API response into a structured list of activities/comments
    and uses AirtableHtmlParser for field-level diffs.
    """
    users = data.get("rowActivityOrCommentUserObjById", {})
    activities = data.get("rowActivityInfoById", {})
    comments = data.get("commentsById", {})
    ordered_ids = data.get("orderedActivityAndCommentIds", [])
    parsed = []
    
    for entry_id in ordered_ids:
        if entry_id.startswith("com"):  # Comment
            comment = comments.get(entry_id, {})
            user = users.get(comment.get("userId"), {})
            entry_data = {
                "id": comment.get("id"),
                "type": "comment",
                "createdTime": comment.get("createdTime"),
                "comment": comment.get("text"),
                "user": user
            }
            parsed.append(RevisionEntry(entry_data))

        else:  # Activity
            activity = activities.get(entry_id, {})
            user = users.get(activity.get("originatingUserId"), {})
            
            # Use the parser class
            parser = AirtableHtmlParser(activity.get("diffRowHtml", ""))
            details = parser.parse_diff()
            
            entry_data = {
                "id": entry_id,
                "type": activity.get("groupType"),
                "createdTime": activity.get("createdTime"),
                "user": user,
                **details # Unpack the results from the HTML parser
            }
            parsed.append(RevisionEntry(entry_data))
    return parsed