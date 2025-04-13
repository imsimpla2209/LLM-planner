# smart_planner/agents/context_agent.py
"""Context Agent: Fetches weather/traffic data and provides recommendations."""

import logging
import json
from datetime import datetime, time, timedelta
from typing import List, Optional, Dict, Any

from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool # Corrected case
from google.adk.models.base_llm import BaseLlm
from google.adk.sessions.state import State as SessionState # Use alias
from pydantic import ValidationError

from ..models.schemas import (ContextOutput, ContextRecommendation, WeatherInfo,
                              TrafficInfo, CalendarSummaryOutput, CalendarEvent)
from ..tools import external_tools

logger = logging.getLogger(__name__)

# Default locations (Consider making these configurable or user-provided via .env or input)
DEFAULT_HOME_LOCATION = "40.7128,-74.0060" # Example: NYC lat/lon
DEFAULT_WORK_LOCATION = "40.7580,-73.9855" # Example: Times Square lat/lon

class ContextAgent(LlmAgent):
    """
    An agent responsible for fetching contextual information (weather, traffic)
    and generating relevant recommendations for the daily plan.
    """
    def __init__(self, llm_provider: BaseLlm, session_state: Optional[SessionState] = None):
        super().__init__(
            name="ContextAgent",
            description="Provides weather and traffic context and recommendations.",
            llm_provider=llm_provider,
            session_state=session_state
        )

    @AgentTool # Corrected case
    def get_weather_tool(self, location_query: str) -> str:
        """
        Tool to get current weather for a location.

        Args:
            location_query: Location query, ideally "latitude,longitude".

        Returns:
            JSON string of WeatherInfo or error message.
        """
        logger.info(f"ContextAgent weather tool called for location: {location_query}")
        weather_dict, status_message = external_tools.get_current_weather(location_query)
        if weather_dict:
            logger.info(f"Weather tool status: {status_message}")
            return json.dumps(weather_dict)
        else:
            logger.error(f"Weather tool failed: {status_message}")
            return json.dumps({"error": status_message})

    @AgentTool # Corrected case
    def get_traffic_tool(self, origin: str, destination: str) -> str:
        """
        Tool to get traffic information between two locations.

        Args:
            origin: Starting address or "lat,lon".
            destination: Ending address or "lat,lon".

        Returns:
            JSON string of TrafficInfo or error message.
        """
        logger.info(f"ContextAgent traffic tool called for: {origin} -> {destination}")
        traffic_dict, status_message = external_tools.get_traffic_info(origin, destination)
        if traffic_dict:
            logger.info(f"Traffic tool status: {status_message}")
            return json.dumps(traffic_dict)
        else:
            logger.error(f"Traffic tool failed: {status_message}")
            # Handle specific case of "No route found" differently if needed
            if "No route found" in status_message:
                 return json.dumps({"status": "ZERO_RESULTS", "message": status_message})
            return json.dumps({"error": status_message})

    def generate_recommendations(self, calendar_summary: Optional[CalendarSummaryOutput]) -> List[ContextRecommendation]:
        """
        Generates context-based recommendations using weather and traffic tools.

        Args:
            calendar_summary: The calendar summary obtained from session state.

        Returns:
            A list of ContextRecommendation objects.
        """
        recommendations: List[ContextRecommendation] = []
        target_date = calendar_summary.summary_date if calendar_summary else datetime.now().date() # Renamed from 'date'
        logger.info(f"Generating context recommendations for {target_date}")

        # 1. Get General Weather for the Day (e.g., for home location)
        try:
            weather_json_str = self.get_weather_tool(location_query=DEFAULT_HOME_LOCATION)
            weather_data = json.loads(weather_json_str)
            if "error" not in weather_data:
                weather_info = WeatherInfo(**weather_data)
                # Simple recommendation based on weather description
                rec_detail_text = f"General weather today ({weather_info.location or 'default location'}): {weather_info.description}"
                if weather_info.temperature_celsius is not None:
                    rec_detail_text += f", Temp: {weather_info.temperature_celsius:.1f}°C"
                if "rain" in weather_info.description.lower() or "snow" in weather_info.description.lower():
                    rec_detail_text += ". Consider bringing an umbrella or adjusting travel plans."

                recommendations.append(ContextRecommendation(
                    type="weather",
                    details=weather_info, # Store the full info object
                    impact_time=datetime.combine(target_date, time(8,0), tzinfo=weather_info.time.tzinfo if weather_info.time else None) # General morning impact, try to match timezone
                ))
                logger.info(f"Added general weather recommendation: {rec_detail_text}") # Log the text summary
            else:
                logger.warning(f"Could not get general weather: {weather_data.get('error')}")
        except Exception as e:
            logger.error(f"Error processing general weather: {e}")


        # 2. Get Traffic for Commute (if applicable based on calendar events)
        first_event_location = None
        first_event_time = None
        if calendar_summary and calendar_summary.events:
            # Sort events to find the earliest one with a location
            sorted_events = sorted(calendar_summary.events, key=lambda x: x.start_time)
            for event in sorted_events:
                 event_start_hour = event.start_time.hour
                 # Check if event is within a reasonable morning commute window and has a location
                 if 8 <= event_start_hour < 12 and event.location:
                     # Need to convert location name to lat/lon or use address directly
                     # A geocoding step would be needed here for addresses
                     if ',' in event.location: # Basic check for lat/lon format
                         first_event_location = event.location
                         first_event_time = event.start_time
                         logger.info(f"Found first event with coordinates: '{event.summary}' at {event.location}")
                         break
                     else:
                         # Placeholder: Use default work location if event location isn't coordinates
                         logger.warning(f"Event location '{event.location}' for '{event.summary}' is not coordinates. Using default work location for traffic check.")
                         first_event_location = DEFAULT_WORK_LOCATION
                         first_event_time = event.start_time
                         break # Found the first relevant event

        if first_event_location and first_event_time:
            origin = DEFAULT_HOME_LOCATION
            destination = first_event_location
            try:
                logger.info(f"Checking morning commute traffic: {origin} -> {destination}")
                traffic_json_str = self.get_traffic_tool(origin=origin, destination=destination)
                traffic_data = json.loads(traffic_json_str)

                if "error" not in traffic_data and traffic_data.get("status") != "ZERO_RESULTS":
                    traffic_info = TrafficInfo(**traffic_data)
                    # Only add recommendation if there's a notable condition/delay
                    if traffic_info.condition in ['moderate', 'heavy', 'severe'] or traffic_info.delay_minutes > 5:
                        recommendations.append(ContextRecommendation(
                            type="traffic",
                            details=traffic_info, # Store the full info object
                            impact_time=first_event_time - timedelta(minutes=traffic_info.delay_minutes + 30) if traffic_info.delay_minutes else first_event_time - timedelta(hours=1) # Impact time relative to event start and delay
                        ))
                        logger.info(f"Added traffic recommendation: {traffic_info.recommendation}")
                elif traffic_data.get("status") == "ZERO_RESULTS":
                     logger.info(f"No route found for morning commute: {origin} -> {destination}")
                else:
                    logger.warning(f"Could not get traffic data: {traffic_data.get('error') or 'Unknown error'}")
            except Exception as e:
                logger.error(f"Error processing traffic data: {e}")

        # TODO: Add more sophisticated logic:
        # - Check traffic before each event with a location.
        # - Check weather forecast for specific event times (requires forecast API).
        # - Use event locations for weather checks if different from home.
        # - Allow user configuration for home/work/common locations.
        # - Implement geocoding for address-based locations.

        return recommendations


    def invoke(self, input_data: dict) -> ContextOutput:
        """
        Main execution logic for the Context Agent.

        Args:
            input_data (dict): Potentially contains user preferences or specific locations,
                               but primarily relies on session state for calendar data.

        Returns:
            ContextOutput: The structured list of contextual recommendations.
                           Returns an empty list on failure or if no context is available.
        """
        logger.info("ContextAgent invoking...")
        calendar_summary_data: Optional[Dict[str, Any]] = None
        calendar_summary: Optional[CalendarSummaryOutput] = None

        # Retrieve calendar summary from session state
        if self.session_state:
            calendar_summary_data = self.session_state.get("calendar_summary")
            if calendar_summary_data and isinstance(calendar_summary_data, dict):
                try:
                    # Re-parse from dict to handle potential datetime string serialization
                    calendar_summary = CalendarSummaryOutput.model_validate(calendar_summary_data)
                    logger.info("Successfully retrieved and validated calendar summary from session state.")
                except ValidationError as e:
                    logger.error(f"Failed to validate calendar summary from session state: {e}")
                    calendar_summary = None # Proceed without calendar context
                except Exception as e:
                    logger.error(f"Unexpected error loading calendar summary from session state: {e}")
                    calendar_summary = None
            else:
                logger.warning("No valid calendar summary found in session state.")
        else:
            logger.warning("No session state available for ContextAgent.")

        # Generate recommendations based on available context
        recommendations = self.generate_recommendations(calendar_summary)

        output = ContextOutput(recommendations=recommendations)
        logger.info(f"ContextAgent generated {len(recommendations)} recommendations.")

        # Store result in session state
        if self.session_state:
            self.session_state.set("context_recommendations", output.model_dump(mode='json'))
            logger.debug("Stored context recommendations in session state.")

        return output