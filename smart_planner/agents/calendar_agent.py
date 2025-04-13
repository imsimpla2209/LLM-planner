# smart_planner/agents/calendar_agent.py
"""Calendar Agent: Fetches and summarizes daily calendar events."""

import logging
from datetime import date, datetime, time, timedelta
from typing import List, Optional
import json # Import json

from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool # Corrected case
from google.adk.models.base_llm import BaseLlm
from google.adk.sessions.state import State as SessionState # Use alias
from pydantic import ValidationError

from ..models.schemas import (CalendarEvent, CalendarSummaryOutput,
                              FreeTimeSlot, CalendarConflict)
from ..tools import calendar_tools

logger = logging.getLogger(__name__)

class CalendarAgent(LlmAgent):
    """
    An agent responsible for fetching, summarizing, and analyzing calendar events for a given day.
    """
    def __init__(self, llm_provider: BaseLlm, session_state: Optional[SessionState] = None):
        super().__init__(
            name="CalendarAgent",
            description="Fetches and analyzes daily calendar events.",
            llm_provider=llm_provider,
            session_state=session_state
        )

    @AgentTool # Corrected case
    def get_calendar_events_tool(self, date_str: str, use_mock_data: bool = False) -> str:
        """
        Tool to fetch calendar events for a specific date (YYYY-MM-DD).

        Args:
            date_str: The target date in YYYY-MM-DD format.
            use_mock_data: Set to True to use mock data instead of Google Calendar API.

        Returns:
            A JSON string representing the list of CalendarEvent dictionaries, or an error message.
        """
        logger.info(f"CalendarAgent tool called for date: {date_str}, mock: {use_mock_data}")
        events_dict, status_message = calendar_tools.get_daily_calendar_events(date_str, use_mock_data)

        if events_dict is not None:
            # Successfully fetched events, return as JSON string for LLM or further processing
            # We might return the status message as well if needed by the LLM part
            logger.info(f"Tool status: {status_message}")
            # Combine results and status for clarity if needed, or just return events
            # return json.dumps({"events": events_dict, "status": status_message})
            return json.dumps(events_dict)
        else:
            # Failed to fetch events, return the error status message
            logger.error(f"Tool failed: {status_message}")
            return json.dumps({"error": status_message}) # Return error clearly

    def analyze_schedule(self, target_date: date, events: List[CalendarEvent]) -> CalendarSummaryOutput:
        """
        Analyzes the fetched events to find free slots and conflicts.

        Args:
            target_date: The date being analyzed.
            events: List of CalendarEvent objects for the day.

        Returns:
            A CalendarSummaryOutput object containing events, free slots, and conflicts.
        """
        logger.info(f"Analyzing schedule for {target_date} with {len(events)} events.")
        free_slots: List[FreeTimeSlot] = []
        conflicts: List[CalendarConflict] = []

        # Sort events by start time
        events.sort(key=lambda x: x.start_time)

        # Define working hours for free slot calculation (e.g., 9 AM to 5 PM)
        # This could be made configurable
        # Ensure timezone consistency - use timezone from first event if available, else assume naive/local
        tz_info = events[0].start_time.tzinfo if events and events[0].start_time.tzinfo else None
        day_start_time = datetime.combine(target_date, time(9, 0), tzinfo=tz_info)
        day_end_time = datetime.combine(target_date, time(17, 0), tzinfo=tz_info)


        current_time = day_start_time

        # Calculate free slots
        for event in events:
             # Ensure event times are timezone-aware if day_start/end are
            if tz_info:
                event_start_aware = event.start_time.astimezone(tz_info) if event.start_time.tzinfo else event.start_time.replace(tzinfo=tz_info)
                event_end_aware = event.end_time.astimezone(tz_info) if event.end_time.tzinfo else event.end_time.replace(tzinfo=tz_info)
            else: # Handle naive comparison
                event_start_aware = event.start_time
                event_end_aware = event.end_time


            # Clamp event times to working hours for calculation
            event_start_clamped = max(event_start_aware, day_start_time)
            event_end_clamped = min(event_end_aware, day_end_time)

            # Only consider events that actually fall within working hours after clamping
            if event_start_clamped < event_end_clamped:
                if event_start_clamped > current_time:
                    free_duration = event_start_clamped - current_time
                    if free_duration >= timedelta(minutes=15): # Minimum free slot duration
                        free_slots.append(FreeTimeSlot(
                            start_time=current_time,
                            end_time=event_start_clamped,
                            duration_minutes=int(free_duration.total_seconds() / 60)
                        ))
                current_time = max(current_time, event_end_clamped) # Move pointer to the end of the clamped event

        # Check for free slot after the last event until end of working day
        if day_end_time > current_time:
            free_duration = day_end_time - current_time
            if free_duration >= timedelta(minutes=15):
                free_slots.append(FreeTimeSlot(
                    start_time=current_time,
                    end_time=day_end_time,
                    duration_minutes=int(free_duration.total_seconds() / 60)
                ))

        # Detect conflicts (simple overlap check)
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                event1 = events[i]
                event2 = events[j]
                # Check for overlap: max(start1, start2) < min(end1, end2)
                if max(event1.start_time, event2.start_time) < min(event1.end_time, event2.end_time):
                    conflict_exists = False
                    # Avoid adding duplicate conflicts involving the same events
                    for existing_conflict in conflicts:
                        if event1 in existing_conflict.conflicting_events and \
                           event2 in existing_conflict.conflicting_events:
                            conflict_exists = True
                            break
                    if not conflict_exists:
                        conflicts.append(CalendarConflict(
                            conflicting_events=[event1, event2],
                            details=f"Overlap between '{event1.summary}' ({event1.start_time.strftime('%H:%M')}-{event1.end_time.strftime('%H:%M')}) "
                                    f"and '{event2.summary}' ({event2.start_time.strftime('%H:%M')}-{event2.end_time.strftime('%H:%M')})"
                        ))
                        logger.warning(f"Conflict detected: {conflicts[-1].details}")


        return CalendarSummaryOutput(
            summary_date=target_date, # Renamed from 'date'
            events=events, # Return original events list
            free_slots=free_slots,
            conflicts=conflicts
        )

    def invoke(self, input_data: dict) -> CalendarSummaryOutput:
        """
        Main execution logic for the Calendar Agent.

        Args:
            input_data (dict): Dictionary containing 'date_str' (YYYY-MM-DD)
                               and optionally 'use_mock_data' (bool).

        Returns:
            CalendarSummaryOutput: The structured summary of the calendar for the given date.
                                   Returns an empty summary on failure.
        """
        target_date_str = input_data.get("date_str")
        use_mock = input_data.get("use_mock_data", False) # Default to API

        # Determine a default date if none provided (e.g., today)
        if not target_date_str:
            target_date = date.today()
            target_date_str = target_date.isoformat()
            logger.warning(f"No date_str provided, defaulting to today: {target_date_str}")
        else:
            try:
                target_date = date.fromisoformat(target_date_str)
            except ValueError:
                logger.error(f"Invalid date format in invoke: {target_date_str}")
                # Return empty summary with a placeholder date or raise error
                return CalendarSummaryOutput(summary_date=date.today(), events=[], free_slots=[], conflicts=[]) # Renamed from 'date'


        logger.info(f"CalendarAgent invoking for date: {target_date_str}, mock: {use_mock}")

        # Call the tool to get raw event data
        events_json_str = self.get_calendar_events_tool(date_str=target_date_str, use_mock_data=use_mock)

        try:
            events_data = json.loads(events_json_str)

            if isinstance(events_data, dict) and "error" in events_data:
                logger.error(f"Tool returned an error: {events_data['error']}")
                # Return empty summary on tool error
                return CalendarSummaryOutput(summary_date=target_date, events=[], free_slots=[], conflicts=[]) # Renamed from 'date'

            # Validate and parse events using Pydantic
            parsed_events: List[CalendarEvent] = []
            if isinstance(events_data, list):
                 for event_dict in events_data:
                     try:
                         # Ensure datetime objects are created correctly if tool returns strings
                         # The CalendarEvent validator should handle ISO strings
                         parsed_events.append(CalendarEvent(**event_dict))
                     except ValidationError as e:
                         logger.warning(f"Skipping event due to validation error: {event_dict.get('summary', 'N/A')}. Error: {e}")
                     except Exception as e:
                         logger.error(f"Unexpected error parsing event dict: {event_dict}. Error: {e}")

            logger.info(f"Successfully parsed {len(parsed_events)} events from tool output.")

            # Analyze the schedule
            summary = self.analyze_schedule(target_date, parsed_events)
            logger.info(f"Schedule analysis complete for {target_date}. Found {len(summary.free_slots)} free slots and {len(summary.conflicts)} conflicts.")

            # Store result in session state if needed for other agents
            if self.session_state:
                # Use model_dump for Pydantic V2
                self.session_state.set("calendar_summary", summary.model_dump(mode='json'))
                logger.debug("Stored calendar summary in session state.")

            return summary

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response from tool: {e}. Response: {events_json_str}")
            return CalendarSummaryOutput(summary_date=target_date, events=[], free_slots=[], conflicts=[]) # Renamed from 'date'
        except Exception as e:
            logger.exception(f"An unexpected error occurred during CalendarAgent invocation for {target_date_str}: {e}")
            return CalendarSummaryOutput(summary_date=target_date, events=[], free_slots=[], conflicts=[]) # Renamed from 'date'