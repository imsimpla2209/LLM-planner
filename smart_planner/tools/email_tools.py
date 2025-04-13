# smart_planner/tools/email_tools.py
"""Tools for processing email data (mock or potentially Gmail API)."""

import json
import logging
import re
from datetime import date, datetime
from typing import List, Optional, Tuple, Dict, Any

from pydantic import ValidationError

from ..config import settings
from ..models.schemas import EmailTask

logger = logging.getLogger(__name__)

# --- Mock Email Data Handling ---

def load_mock_emails() -> Optional[List[Dict[str, Any]]]:
    """Loads mock email data from the JSON file specified in settings.

    Returns:
        Optional[List[Dict[str, Any]]]: A list of dictionaries representing emails,
                                         or None if loading fails.
    """
    if not settings.MOCK_EMAIL_FILE_PATH or not settings.MOCK_EMAIL_FILE_PATH.exists():
        logger.warning(f"Mock email file path not configured or file not found: {settings.MOCK_EMAIL_FILE_PATH}")
        return None

    try:
        with open(settings.MOCK_EMAIL_FILE_PATH, 'r') as f:
            mock_emails = json.load(f)
        logger.info(f"Loaded {len(mock_emails)} mock emails from {settings.MOCK_EMAIL_FILE_PATH}")
        return mock_emails
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from mock email file: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading mock email data: {e}")
        return None

def parse_emails_for_tasks(emails: List[Dict[str, Any]]) -> List[EmailTask]:
    """
    Analyzes a list of email dictionaries to extract potential tasks and assign priorities.

    Args:
        emails (List[Dict[str, Any]]): A list of email dictionaries (from mock data or API).
                                       Expected keys: 'id', 'sender', 'subject', 'body', 'received_date'.

    Returns:
        List[EmailTask]: A list of extracted EmailTask objects.
    """
    tasks: List[EmailTask] = []
    if not emails:
        return tasks

    # Simple keyword-based priority assignment (customize as needed)
    priority_keywords = {
        'urgent': ['urgent', 'asap', 'immediately', 'critical'],
        'high': ['important', 'priority', 'deadline', 'due soon'],
        'medium': ['task', 'action required', 'follow up', 'please review'],
        'low': ['fyi', 'update', 'info', 'suggestion'],
    }

    # Simple regex for potential due dates (example: "due by YYYY-MM-DD")
    due_date_pattern = re.compile(r'due (?:by|on|before) (\d{4}-\d{2}-\d{2})', re.IGNORECASE)

    for email in emails:
        email_id = email.get('id', 'unknown')
        subject = email.get('subject', '').lower()
        body = email.get('body', '').lower()
        sender = email.get('sender', 'unknown')
        content = subject + " " + body # Combine subject and body for keyword search

        priority: Optional[str] = None
        description: Optional[str] = None
        due_date: Optional[date] = None

        # Determine priority
        for p_level, keywords in priority_keywords.items():
            if any(keyword in content for keyword in keywords):
                priority = p_level
                break
        if not priority:
            priority = 'medium' # Default priority if no keywords match

        # Extract description (simple approach: use subject, or first sentence of body)
        # A more sophisticated approach would involve NLP/LLM summarization
        description = email.get('subject', 'Task from email') # Default to subject
        if not description and email.get('body'):
             # Basic sentence split, take the first one containing a potential action verb
             sentences = re.split(r'[.!?]', email['body'])
             action_verbs = ['complete', 'finish', 'submit', 'review', 'reply', 'send', 'prepare']
             for sentence in sentences:
                 if sentence.strip() and any(verb in sentence.lower() for verb in action_verbs):
                     description = sentence.strip()
                     break
             if description == email.get('subject', 'Task from email'): # If still default
                 description = sentences[0].strip() if sentences else 'Task from email'


        # Extract due date
        match = due_date_pattern.search(content)
        if match:
            try:
                due_date = date.fromisoformat(match.group(1))
            except ValueError:
                logger.warning(f"Invalid date format found in email {email_id}: {match.group(1)}")

        # Create task object if we have a description
        if description:
            try:
                task_data = {
                    "description": description[:200], # Truncate long descriptions
                    "priority": priority,
                    "due_date": due_date,
                    "source_email_id": str(email_id)
                }
                task = EmailTask(**task_data)
                tasks.append(task)
                logger.debug(f"Extracted task: {task.model_dump_json()}")
            except ValidationError as e:
                logger.warning(f"Skipping task creation due to validation error for email {email_id}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error creating task for email {email_id}: {e}")


    logger.info(f"Extracted {len(tasks)} potential tasks from {len(emails)} emails.")
    return tasks

# --- Gmail API Interaction (Placeholder/Optional) ---

def fetch_emails_gmail_api(max_results: int = 20) -> Optional[List[Dict[str, Any]]]:
    """
    Fetches recent emails using the Gmail API. (Requires OAuth setup for Gmail scopes)

    Args:
        max_results (int): Maximum number of emails to fetch.

    Returns:
        Optional[List[Dict[str, Any]]]: List of email dictionaries or None on failure.
    """
    logger.warning("Gmail API integration is not fully implemented in this version. Requires OAuth setup.")
    # Placeholder: Implement Gmail API logic here if needed
    # 1. Get credentials using get_google_credentials() with GMAIL_SCOPES (need to import/modify get_google_credentials)
    # 2. Build Gmail service: service = build('gmail', 'v1', credentials=creds)
    # 3. List messages: results = service.users().messages().list(userId='me', maxResults=max_results).execute()
    # 4. Get individual messages: msg = service.users().messages().get(userId='me', id=message['id']).execute()
    # 5. Parse message payload (handle different MIME types, decoding)
    # 6. Extract sender, subject, body, date, id
    # 7. Return list of dictionaries similar to mock data format
    return None # Return None as it's not implemented yet

# --- ADK Tool Definition ---

def get_prioritized_tasks_from_emails(use_mock_data: bool = True, max_emails_api: int = 20) -> Tuple[Optional[List[dict]], str]:
    """
    Fetches emails (mock or API) and extracts a prioritized list of tasks.

    Args:
        use_mock_data (bool): If True, uses mock email data. Defaults to True.
        max_emails_api (int): Max emails to fetch if using Gmail API. Defaults to 20.

    Returns:
        Tuple[Optional[List[dict]], str]: A tuple containing:
            - A list of task dictionaries (EmailTask model .dict()) on success, or None on failure.
            - A status message string.
    """
    logger.info(f"Requesting prioritized tasks from emails, use_mock_data={use_mock_data}")

    emails: Optional[List[Dict[str, Any]]] = None
    status_message = ""

    if use_mock_data:
        logger.info("Attempting to load mock emails...")
        emails = load_mock_emails()
        if emails is None:
            status_message = "Failed to load mock emails. Check file path and format."
            logger.error(status_message)
            return None, status_message
        status_message = f"Loaded {len(emails)} mock emails. "
    else:
        logger.info("Attempting to fetch emails from Gmail API...")
        emails = fetch_emails_gmail_api(max_results=max_emails_api)
        if emails is None:
            status_message = "Failed to fetch emails via Gmail API (or feature not implemented)."
            logger.warning(status_message)
            # Optionally fallback to mock data
            # emails = load_mock_emails()
            # status_message += " Falling back to mock data." if emails else " Mock data also unavailable."
            return None, status_message # Return failure if API is expected but fails/not implemented
        status_message = f"Fetched {len(emails)} emails via Gmail API. "

    if emails is not None:
        tasks = parse_emails_for_tasks(emails)
        status_message += f"Extracted {len(tasks)} potential tasks."
        logger.info(status_message)
        tasks_dict = [task.model_dump(mode='json') for task in tasks]
        return tasks_dict, status_message
    else:
        # This case should ideally be handled above, but as a safeguard:
        status_message = "Could not obtain email data (mock or API)."
        logger.error(status_message)
        return None, status_message