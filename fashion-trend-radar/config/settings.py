import os
from dotenv import load_dotenv

load_dotenv()

BRIGHTDATA_API_TOKEN = os.getenv("BRIGHTDATA_API_TOKEN")
BRIGHTDATA_ZONE = os.getenv("BRIGHTDATA_ZONE", "serp_api1")

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")

DEFAULT_GEO = os.getenv("DEFAULT_GEO", "US")
DEFAULT_HL = os.getenv("DEFAULT_HL", "en-US")
DEFAULT_TIMEFRAME = os.getenv("DEFAULT_TIMEFRAME", "today 12-m")

RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"
EXPORT_DIR = "data/exports"
KEYWORDS_FILE = "config/keywords.csv"
