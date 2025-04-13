# smart_planner/config/settings.py
"""Loads application settings from environment variables."""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional

# Determine the project root directory (assuming settings.py is in smart_planner/config)
# Project root is two levels up from this file's directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load environment variables from .env file located in the project root
dotenv_path = PROJECT_ROOT / '.env'
load_dotenv(dotenv_path=dotenv_path)

# --- Google API Credentials ---
GOOGLE_CLIENT_ID: Optional[str] = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_PROJECT_ID: Optional[str] = os.getenv("GOOGLE_PROJECT_ID")

# --- External API Keys ---
GOOGLE_MAPS_API_KEY: Optional[str] = os.getenv("GOOGLE_MAPS_API_KEY")
OPENWEATHERMAP_API_KEY: Optional[str] = os.getenv("OPENWEATHERMAP_API_KEY")

# --- Mock Data Paths ---
# Construct absolute paths from relative paths defined in .env
MOCK_EMAIL_FILE_PATH_STR: Optional[str] = os.getenv("MOCK_EMAIL_FILE_PATH", "mock_data/emails.json")
MOCK_CALENDAR_FILE_PATH_STR: Optional[str] = os.getenv("MOCK_CALENDAR_FILE_PATH", "mock_data/calendar_events.json")

MOCK_EMAIL_FILE_PATH: Optional[Path] = PROJECT_ROOT / MOCK_EMAIL_FILE_PATH_STR if MOCK_EMAIL_FILE_PATH_STR else None
MOCK_CALENDAR_FILE_PATH: Optional[Path] = PROJECT_ROOT / MOCK_CALENDAR_FILE_PATH_STR if MOCK_CALENDAR_FILE_PATH_STR else None


# --- Logging Configuration ---
LOG_LEVEL_STR: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL: int = getattr(logging, LOG_LEVEL_STR, logging.INFO)

# --- Optional Gmail Settings ---
GMAIL_USER_EMAIL: Optional[str] = os.getenv("GMAIL_USER_EMAIL")

# --- Google OAuth Scopes ---
# Define required scopes for Google APIs
GOOGLE_CALENDAR_SCOPES: list[str] = ['https://www.googleapis.com/auth/calendar.readonly']
GOOGLE_GMAIL_SCOPES: list[str] = [
    'https://www.googleapis.com/auth/gmail.readonly', # For reading emails
    'https://www.googleapis.com/auth/gmail.send'      # For sending notifications (optional)
]
ALL_GOOGLE_SCOPES = list(set(GOOGLE_CALENDAR_SCOPES + GOOGLE_GMAIL_SCOPES))

# --- Token File Path for OAuth ---
# Store OAuth tokens locally for persistence between runs
TOKEN_FILE_PATH: Path = PROJECT_ROOT / 'token.json'
CREDENTIALS_FILE_PATH: Path = PROJECT_ROOT / 'credentials.json' # Expected location for downloaded OAuth client secrets file

# --- Validation (Optional but recommended) ---
# You could add checks here to ensure critical variables are set,
# raising an informative error if something is missing.
# Example:
# if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
#     raise ValueError("Google Client ID and Secret must be set in the .env file.")
# if not OPENWEATHERMAP_API_KEY:
#     logging.warning("OPENWEATHERMAP_API_KEY not set. Weather features will be disabled.")


# --- Basic Logging Setup ---
# Configure root logger
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# Get a logger instance for this module
logger = logging.getLogger(__name__)
logger.info(f"Configuration loaded. Log level set to {LOG_LEVEL_STR}.")
logger.debug(f"Project Root: {PROJECT_ROOT}")
logger.debug(f"Mock Email Path: {MOCK_EMAIL_FILE_PATH}")
logger.debug(f"Mock Calendar Path: {MOCK_CALENDAR_FILE_PATH}")
logger.debug(f"Token File Path: {TOKEN_FILE_PATH}")
logger.debug(f"Credentials File Path: {CREDENTIALS_FILE_PATH}")