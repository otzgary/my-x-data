import os
from dotenv import load_dotenv

load_dotenv()

TWITTER_API_KEY = os.environ["TWITTER_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GOOGLE_CREDENTIALS_JSON = os.environ["GOOGLE_CREDENTIALS_JSON"]
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
TWITTER_USERNAME = os.getenv("TWITTER_USERNAME", "garyintern")
