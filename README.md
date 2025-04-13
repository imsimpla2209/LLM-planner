# Smart Personal Planning Assistant (ADK Demo)

This project demonstrates a multi-agent system built with Google's Agent Development Kit (ADK) v0.1.0+ to assist users with daily planning. It combines information from Google Calendar, emails (mock data or Gmail API), and external context (weather, traffic) to generate a consolidated daily plan.

## Features

*   **Multi-Agent System:** Uses three distinct agents:
    *   `CalendarAgent`: Fetches and analyzes Google Calendar events.
    *   `EmailAgent`: Extracts and prioritizes tasks from emails.
    *   `ContextAgent`: Provides weather and traffic recommendations.
*   **Google API Integration:** Connects to Google Calendar (read-only) and optionally Gmail (read-only, send). Requires OAuth 2.0 setup.
*   **External APIs:** Integrates with OpenWeatherMap for weather and Google Maps Directions API for traffic estimates.
*   **Mock Data Support:** Can run entirely using mock calendar events and emails for testing without API keys.
*   **Structured Output:** Generates a consolidated daily plan in JSON format using Pydantic models for validation.
*   **ADK Integration:** Leverages ADK core components (`LlmAgent`, `SessionState`, `agent_tool`) and is runnable via `python main.py` or the ADK Dev UI (`adk web`).
*   **Configuration Management:** Uses `.env` file for secure API key management.
*   **Logging:** Implements structured logging for monitoring and debugging.

## Project Structure

```
smart_planner/
├── agents/             # Agent logic (Calendar, Email, Context)
│   ├── __init__.py
│   ├── calendar_agent.py
│   ├── email_agent.py
│   └── context_agent.py
├── tools/              # Tools used by agents (API wrappers, data parsing)
│   ├── __init__.py
│   ├── calendar_tools.py
│   ├── email_tools.py
│   └── external_tools.py
├── models/             # Pydantic data models/schemas
│   ├── __init__.py
│   └── schemas.py
├── config/             # Configuration loading
│   ├── __init__.py
│   └── settings.py
├── tests/              # Unit tests (pytest) - TODO
│   ├── __init__.py
│   ├── test_calendar.py
│   ├── test_email.py
│   └── test_context.py
├── mock_data/          # Mock data files
│   ├── calendar_events.json
│   └── emails.json
├── main.py             # Main script entry point & ADK web agent
├── requirements.txt    # Python dependencies
├── .env.example        # Example environment variables file
├── credentials.json    # Placeholder for Google OAuth client secrets
└── README.md           # This file
```

## Setup

1.  **Clone the Repository:**
    ```bash
    git clone <repository_url>
    cd smart_planner
    ```

2.  **Create a Virtual Environment:** (Recommended)
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    *   Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    *   Edit the `.env` file and fill in your API keys and credentials:
        *   `OPENWEATHERMAP_API_KEY`: Get from [OpenWeatherMap](https://openweathermap.org/appid).
        *   `GOOGLE_MAPS_API_KEY`: Get from [Google Cloud Console](https://developers.google.com/maps/documentation/directions/get-api-key). Enable the "Directions API".
        *   **Google Calendar/Gmail API (Optional - needed for `--api` flag):**
            *   Follow the [Google Workspace guide](https://developers.google.com/workspace/guides/create-credentials) to create OAuth 2.0 Credentials (select "Desktop app").
            *   Download the `client_secret_....json` file.
            *   **Rename the downloaded file to `credentials.json` and place it in the `smart_planner/` project root directory.**
            *   Open `credentials.json` and copy the `client_id` and `client_secret` into your `.env` file under `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
            *   Optionally add your `GOOGLE_PROJECT_ID`.

5.  **Google API Authentication (First Run with `--api`):**
    *   When you run the script with the `--api` flag for the first time (`python main.py --api`), it will open a browser window asking you to authorize access to your Google Calendar (and potentially Gmail if implemented).
    *   Follow the prompts to grant permission.
    *   This will create a `token.json` file in the project root, storing your authorization tokens for future runs. **Do not share this file.**

## Running the Assistant

You can run the planner in two main ways:

1.  **Directly via Command Line:**
    *   **Using Mock Data (Default):** (Run from the parent directory, e.g., `ADK-test`)
        ```bash
        python3 -m smart_planner.main [YYYY-MM-DD]
        ```
        (If date is omitted, it defaults to today.)
        Example: `python3 -m smart_planner.main 2025-04-14`
    *   **Using Live APIs:** (Requires `.env` and `credentials.json` setup. Run from parent directory)
        ```bash
        python3 -m smart_planner.main --api [YYYY-MM-DD]
        ```
        Example: `python3 -m smart_planner.main --api 2025-04-14`
    *   **Enable Debug Logging:**
        ```bash
        python3 -m smart_planner.main --debug [--api] [YYYY-MM-DD]
        ```
    *   **Save Output to File:**
        ```bash
        python3 -m smart_planner.main [--api] [YYYY-MM-DD] --output my_plan.json
        ```

2.  **Using ADK Dev UI:**
    *   Ensure you have the ADK CLI installed (`pip install google-adk`).
    *   Run the ADK web server from the directory *containing* the `smart_planner` folder:
        ```bash
        adk web smart_planner/main.py
        ```
    *   Open your browser to `http://localhost:8000`.
    *   Select the `smart_planner_agent`.
    *   Enter input JSON in the format:
        ```json
        {
          "date": "YYYY-MM-DD",
          "use_mock": true
        }
        ```
        (Set `"use_mock": false` to use live APIs - requires prior command-line authentication via `python main.py --api` to generate `token.json`).
    *   Click "Run Agent". The consolidated plan JSON will be displayed in the output.

## Output Format

The script prints a consolidated daily plan in JSON format to the console (and optionally saves it to a file). Example:

```json
{
  "date": "2025-04-14",
  "plan": [
    {
      "time": "07:00:00", // Default time for recommendations without specific impact
      "item_type": "recommendation",
      "details": {
        "type": "weather",
        "details": {
          "time": "08:15:30", // Actual weather report time
          "description": "Light rain",
          "temperature_celsius": 15.5,
          "location": "Lat:40.7128, Lon:-74.0060"
        },
        "impact_time": "2025-04-14T08:00:00+00:00" // General morning impact
      },
      "priority": null
    },
    {
      "time": "09:00:00", // Placeholder time for high-priority task
      "item_type": "task",
      "details": {
        "description": "URGENT: Finalize Q2 Report",
        "priority": "urgent",
        "due_date": null,
        "source_email_id": "email_001"
      },
      "priority": "urgent"
    },
    {
      "time": "10:00:00",
      "item_type": "event",
      "details": {
        "start_time": "2025-04-14T10:00:00+07:00",
        "end_time": "2025-04-14T11:00:00+07:00",
        "summary": "Team Sync Meeting",
        "location": "Meeting Room 3B"
      },
      "priority": null
    },
    // ... other plan items ...
  ],
  "summary": "Plan for 2025-04-14. Events: 3. Tasks: 3. Recommendations: 1."
}
```

## Testing (TODO)

Unit tests using `pytest` should be added to the `tests/` directory to validate the functionality of individual tools and agents.

```bash
# Navigate to the smart_planner directory if not already there
pytest tests/
```

## Future Improvements

*   Implement actual scheduling logic to fit tasks into free calendar slots.
*   Add proper geocoding for location names in calendar events and traffic requests.
*   Implement Gmail API integration for reading real emails (requires careful scope handling).
*   Implement optional Gmail notification feature.
*   Add more sophisticated NLP/LLM capabilities for email task extraction and summarization.
*   Make default locations (home/work) configurable.
*   Improve error handling and resilience.
*   Add comprehensive unit tests.
