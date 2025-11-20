import os
import logging
from airtable_scraper import AirtableScraper
from config import ALL_CONFIG
from logger import setup_logging


def main():

    # 1. Initialize logging 
    setup_logging(ALL_CONFIG.get('LOGGING'))
    logger = logging.getLogger(__name__)
    
    # 2. Fetching for all critical parameters
    email = os.getenv("AIRTABLE_EMAIL")
    password = os.getenv("AIRTABLE_PASSWORD")
    
    core_config = ALL_CONFIG.get('CORE', {}) 
    record_id = core_config.get('RECORD_ID')
    app_id = core_config.get('APPLICATION_ID')
    view_url = core_config.get('TABLE_VIEW_URL')

    # 3. Validate requried parameters
    missing_vars = []
    if not email: missing_vars.append("AIRTABLE_EMAIL")
    if not password: missing_vars.append("AIRTABLE_PASSWORD")
    if not record_id: missing_vars.append("AIRTABLE_RECORD_ID")
    if not app_id: missing_vars.append("AIRTABLE_APP_ID")
    if not view_url: missing_vars.append("AIRTABLE_TABLE_VIEW_URL")

    if missing_vars:
        logger.critical(
            f"Missing critical configuration variables: {', '.join(missing_vars)}. "
            "Please ensure all required environment variables are set."
        )
        return

    logger.info("All necessary configuration loaded. Starting Airtable Scraper...")
    
    # 3. Star Scraping
    logger.info("Starting Airtable Scraper...")
    scraper = AirtableScraper(email, password)
    scraper.run()

    logger.info("Airtable Scraper finished execution.")


if __name__ == "__main__":
    main()