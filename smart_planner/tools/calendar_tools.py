# smart_planner/tools/calendar_tools.py
"""Tools for interacting with Google Calendar API or mock data."""

import datetime
import json
import logging
import os.path
from typing import List, Optional, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import ValidationError

from ..config import settings
from ..models.schemas import CalendarEvent

logger = logging.getLogger(__name__)

# --- Google Authentication ---

def get_google_credentials() -> Optional[Credentials]:
    """Gets valid Google OAuth credentials.

    Handles the OAuth 2.0 flow for installed applications.
    Stores/refreshes tokens in `token.json`.

    Returns:
        Optional[Credentials]: Valid credentials object or None if auth fails.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if settings.TOKEN_FILE_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(settings.TOKEN_FILE_PATH), settings.GOOGLE_CALENDAR_SCOPES)
            logger.info("Loaded credentials from token file.")
        except Exception as e:
            logger.warning(f"Failed to load credentials from token file: {e}. Will attempt re-authentication.")
            creds = None # Ensure creds is None if loading fails

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired credentials...")
                creds.refresh(Request())
                logger.info("Credentials refreshed successfully.")
            except Exception as e:
                logger.error(f"Failed to refresh credentials: {e}. Need to re-authenticate.")
                creds = None # Force re-authentication
        else:
            if not settings.CREDENTIALS_FILE_PATH.exists():
                logger.error(f"Credentials file not found at {settings.CREDENTIALS_FILE_PATH}. "
                             "Please download your OAuth 2.0 client secrets file and save it there.")
                return None
            try:
                logger.info("Initiating OAuth flow for new credentials...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(settings.CREDENTIALS_FILE_PATH), settings.GOOGLE_CALENDAR_SCOPES
                )
                # Note: Adjust port if needed, ensure it's free
                creds = flow.run_local_server(port=0)
                logger.info("OAuth flow completed successfully.")
            except Exception as e:
                logger.error(f"OAuth flow failed: {e}")
                return None
        # Save the credentials for the next run
        if creds:
            try:
                with open(settings.TOKEN_FILE_PATH, "w") as token_file:
                    token_file.write(creds.to_json())
                logger.info(f"Credentials saved to {settings.TOKEN_FILE_PATH}")
            except Exception as e:
                logger.error(f"Failed to save credentials token: {e}")

    return creds

# --- Calendar API Interaction ---

def fetch_calendar_events_api(target_date: datetime.date) -> Optional[List[CalendarEvent]]:
    """Fetches calendar events for a specific date using the Google Calendar API.

    Args:
        target_date (datetime.date): The date for which to fetch events.

    Returns:
        Optional[List[CalendarEvent]]: A list of CalendarEvent objects or None if an error occurs.
    """
    creds = get_google_credentials()
    if not creds:
        logger.error("Failed to obtain Google credentials. Cannot fetch calendar events via API.")
        return None

    try:
        service = build("calendar", "v3", credentials=creds)
        logger.info(f"Successfully built Google Calendar service for date: {target_date}")

        # Define the time range for the target date (from midnight to midnight in local timezone)
        # Assuming local timezone interpretation for the date
        start_dt = datetime.datetime.combine(target_date, datetime.time.min)
        end_dt = datetime.datetime.combine(target_date, datetime.time.max)

        # Convert to RFC3339 format which Google API expects (usually UTC)
        # Adjust timezone handling as needed based on user's calendar settings / requirements
        # For simplicity, using system's local timezone awareness if available, else assuming UTC
        time_min = start_dt.isoformat() + 'Z' # 'Z' indicates UTC
        time_max = end_dt.isoformat() + 'Z' # 'Z' indicates UTC
        # A more robust solution might involve pytz for explicit timezone handling

        logger.info(f"Fetching events for {target_date} between {time_min} and {time_max}")

        events_result = (
            service.events()
            .list(
                calendarId="primary", # Use 'primary' for the user's main calendar
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True, # Expand recurring events
                orderBy="startTime",
            )
            .execute()
        )
        api_events = events_result.get("items", [])

        if not api_events:
            logger.info(f"No events found for {target_date}.")
            return []

        logger.info(f"Found {len(api_events)} events for {target_date}.")

        parsed_events: List[CalendarEvent] = []
        for event in api_events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            summary = event.get("summary", "No Title")
            location = event.get("location")

            # Handle all-day events vs timed events for datetime parsing
            try:
                # Need robust datetime parsing here
                start_time = datetime.datetime.fromisoformat(start.replace('Z', '+00:00')) if 'T' in start else datetime.datetime.combine(datetime.date.fromisoformat(start), datetime.time.min)
                end_time = datetime.datetime.fromisoformat(end.replace('Z', '+00:00')) if 'T' in end else datetime.datetime.combine(datetime.date.fromisoformat(end), datetime.time.max)

                event_data = {
                    "start_time": start_time,
                    "end_time": end_time,
                    "summary": summary,
                    "location": location,
                }
                parsed_events.append(CalendarEvent(**event_data))
            except (ValidationError, ValueError, TypeError) as e:
                logger.warning(f"Skipping event due to parsing error: {summary} ({start}-{end}). Error: {e}")
            except Exception as e:
                 logger.error(f"Unexpected error parsing event {summary}: {e}")


        logger.info(f"Successfully parsed {len(parsed_events)} events.")
        return parsed_events

    except HttpError as error:
        logger.error(f"An API error occurred: {error}")
        # Handle specific errors like 403 (permissions), 401 (auth) if needed
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching calendar events: {e}")
        return None

# --- Mock Data Handling ---

def load_mock_calendar_events(target_date: datetime.date) -> Optional[List[CalendarEvent]]:
    """Loads mock calendar events for a specific date from a JSON file.

    Args:
        target_date (datetime.date): The date to filter mock events for.

    Returns:
        Optional[List[CalendarEvent]]: A list of CalendarEvent objects or None if an error occurs.
    """
    if not settings.MOCK_CALENDAR_FILE_PATH or not settings.MOCK_CALENDAR_FILE_PATH.exists():
        logger.warning(f"Mock calendar file path not configured or file not found: {settings.MOCK_CALENDAR_FILE_PATH}")
        return None

    try:
        with open(settings.MOCK_CALENDAR_FILE_PATH, 'r') as f:
            all_mock_events_data = json.load(f)

        logger.info(f"Loaded mock data from {settings.MOCK_CALENDAR_FILE_PATH}")

        # Filter events for the target date and parse them
        parsed_events: List[CalendarEvent] = []
        target_date_str = target_date.isoformat()

        for event_data in all_mock_events_data:
            start_str = event_data.get("start_time")
            # Check if the event date matches the target date
            if start_str and start_str.startswith(target_date_str):
                try:
                    # Assume ISO format strings in mock data
                    parsed_event = CalendarEvent(**event_data)
                    parsed_events.append(parsed_event)
                except ValidationError as e:
                    logger.warning(f"Skipping mock event due to validation error: {event_data.get('summary', 'N/A')}. Error: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error parsing mock event {event_data.get('summary', 'N/A')}: {e}")


        logger.info(f"Found and parsed {len(parsed_events)} mock events for {target_date}.")
        return parsed_events

    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from mock calendar file: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading or parsing mock calendar data: {e}")
        return None

# --- ADK Tool Definition ---

# Note: ADK tools are typically defined within Agent classes or registered globally.
# For modularity, we define the core logic here and will wrap it in an @tool
# decorator within the CalendarAgent class later.

def get_daily_calendar_events(date_str: str, use_mock_data: bool = False) -> Tuple[Optional[List[dict]], str]:
    """
    Fetches calendar events for a given date, either from Google Calendar API or mock data.

    Args:
        date_str (str): The target date in YYYY-MM-DD format.
        use_mock_data (bool): If True, uses mock data instead of the API. Defaults to False.

    Returns:
        Tuple[Optional[List[dict]], str]: A tuple containing:
            - A list of event dictionaries (Pydantic model .dict()) on success, or None on failure.
            - A status message string.
    """
    try:
        target_date = datetime.date.fromisoformat(date_str)
    except ValueError:
        logger.error(f"Invalid date format provided: {date_str}. Use YYYY-MM-DD.")
        return None, f"Invalid date format: {date_str}. Please use YYYY-MM-DD."

    logger.info(f"Requesting calendar events for {target_date}, use_mock_data={use_mock_data}")

    events: Optional[List[CalendarEvent]] = None
    status_message = ""

    if use_mock_data:
        logger.info("Attempting to load mock calendar events...")
        events = load_mock_calendar_events(target_date)
        if events is None:
            status_message = f"Failed to load mock calendar events for {target_date}."
            logger.warning(status_message)
        elif not events:
             status_message = f"No mock events found for {target_date}."
             logger.info(status_message)
        else:
            status_message = f"Successfully loaded {len(events)} mock events for {target_date}."
            logger.info(status_message)
    else:
        logger.info("Attempting to fetch calendar events from Google API...")
        events = fetch_calendar_events_api(target_date)
        if events is None:
            status_message = f"Failed to fetch calendar events for {target_date} from API. Check logs and credentials."
            logger.error(status_message)
            # Optionally, fallback to mock data if API fails
            # logger.info("Falling back to mock data due to API failure.")
            # events = load_mock_calendar_events(target_date)
            # status_message += f" | Attempted fallback to mock data: {'Success' if events else 'Failed/None found'}."
        elif not events:
             status_message = f"No events found for {target_date} via Google Calendar API."
             logger.info(status_message)
        else:
            status_message = f"Successfully fetched {len(events)} events for {target_date} from Google Calendar API."
            logger.info(status_message)

    if events is not None:
        # Convert Pydantic models to dictionaries for ADK tool output if needed
        # ADK might handle Pydantic models directly, check documentation
        events_dict = [event.model_dump(mode='json') for event in events] # Use model_dump for Pydantic v2+
        return events_dict, status_message
    else:
        return None, status_message