import logging
import sys

def setup_logging(config):
    """
    Sets up the application-wide logging configuration.
    Accepts the LOGGING_CONFIG dictionary from config.py.
    """
    log_file = config.get('filename')
    log_level = config.get('level', logging.INFO)
    log_format = config.get('format')
 
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout) 
        ]
    )
    logging.info("Logging configured successfully.")