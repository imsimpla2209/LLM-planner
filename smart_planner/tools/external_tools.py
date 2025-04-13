# smart_planner/tools/external_tools.py
"""Tools for fetching external context like weather and traffic."""

import logging
import requests
import datetime
from typing import Optional, Dict, Any, Tuple, List
from cachetools import cached, TTLCache
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from ..config import settings
from ..models.schemas import WeatherInfo, TrafficInfo, ContextRecommendation

logger = logging.getLogger(__name__)

# Cache configuration (e.g., cache weather for 15 minutes, traffic for 5 minutes)
weather_cache = TTLCache(maxsize=100, ttl=15 * 60)
traffic_cache = TTLCache(maxsize=100, ttl=5 * 60)

# Retry configuration for API calls
RETRY_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 2

# --- OpenWeatherMap API Tool ---

@cached(weather_cache)
@retry(
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_fixed(RETRY_WAIT_SECONDS),
    retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.Timeout)),
    reraise=True # Reraise the exception after retries are exhausted
)
def get_weather_data(latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
    """
    Fetches current weather data from OpenWeatherMap API for given coordinates.

    Args:
        latitude (float): Latitude of the location.
        longitude (float): Longitude of the location.

    Returns:
        Optional[Dict[str, Any]]: Raw weather data dictionary from API, or None on failure.
    """
    if not settings.OPENWEATHERMAP_API_KEY:
        logger.warning("OpenWeatherMap API key not configured. Cannot fetch weather.")
        return None

    base_url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": latitude,
        "lon": longitude,
        "appid": settings.OPENWEATHERMAP_API_KEY,
        "units": "metric",  # Get temperature in Celsius
    }

    try:
        logger.info(f"Fetching weather data for lat={latitude}, lon={longitude}")
        response = requests.get(base_url, params=params, timeout=10) # Added timeout
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        weather_data = response.json()
        logger.debug(f"OpenWeatherMap API response: {weather_data}")
        return weather_data
    except requests.exceptions.Timeout:
        logger.error(f"Timeout occurred while fetching weather data for {latitude}, {longitude}.")
        raise # Re-raise for tenacity to handle retries
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching weather data for {latitude}, {longitude}: {e}")
        # Log specific status codes if needed (e.g., 401 for bad API key)
        if e.response is not None:
             logger.error(f"Response status code: {e.response.status_code}, Response body: {e.response.text}")
        raise # Re-raise for tenacity to handle retries
    except Exception as e:
        logger.error(f"An unexpected error occurred during weather fetch: {e}")
        return None # Return None for non-retryable errors after retries

def parse_weather_data(weather_data: Dict[str, Any], location_name: Optional[str] = None) -> Optional[WeatherInfo]:
    """Parses raw OpenWeatherMap data into a WeatherInfo model."""
    if not weather_data or 'weather' not in weather_data or not weather_data['weather']:
        logger.warning("Received incomplete or invalid weather data.")
        return None
    try:
        description = weather_data['weather'][0].get('description', 'No description').capitalize()
        temp = weather_data.get('main', {}).get('temp')
        timestamp = weather_data.get('dt')
        weather_time = datetime.datetime.fromtimestamp(timestamp).time() if timestamp else None

        return WeatherInfo(
            time=weather_time,
            description=description,
            temperature_celsius=temp,
            location=location_name or weather_data.get('name') # Use provided name or API name
        )
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"Error parsing weather data: {e}. Data: {weather_data}")
        return None

# --- Google Maps API Tool (Directions/Distance Matrix) ---

@cached(traffic_cache)
@retry(
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_fixed(RETRY_WAIT_SECONDS),
    retry=retry_if_exception_type((requests.exceptions.RequestException, requests.exceptions.Timeout)),
    reraise=True
)
def get_traffic_data(origin: str, destination: str) -> Optional[Dict[str, Any]]:
    """
    Fetches traffic data (estimated duration) using Google Maps Directions API.

    Args:
        origin (str): Starting address or coordinates (lat,lng).
        destination (str): Ending address or coordinates (lat,lng).

    Returns:
        Optional[Dict[str, Any]]: Raw directions data dictionary from API, or None on failure.
    """
    if not settings.GOOGLE_MAPS_API_KEY:
        logger.warning("Google Maps API key not configured. Cannot fetch traffic data.")
        return None

    base_url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": destination,
        "key": settings.GOOGLE_MAPS_API_KEY,
        "departure_time": "now",  # Get traffic estimate based on current conditions
        "traffic_model": "best_guess", # Factors in current and historical traffic
    }

    try:
        logger.info(f"Fetching traffic data from '{origin}' to '{destination}'")
        response = requests.get(base_url, params=params, timeout=15) # Increased timeout for Directions API
        response.raise_for_status()
        directions_data = response.json()
        logger.debug(f"Google Directions API response: {directions_data}")

        if directions_data.get("status") != "OK":
            logger.error(f"Google Directions API returned status: {directions_data.get('status')}. "
                         f"Error message: {directions_data.get('error_message')}")
            # Consider specific statuses like ZERO_RESULTS as non-errors but empty results
            if directions_data.get("status") == "ZERO_RESULTS":
                return {"status": "ZERO_RESULTS", "routes": []} # Return structure indicating no route
            return None # Treat other non-OK statuses as errors

        return directions_data
    except requests.exceptions.Timeout:
        logger.error(f"Timeout occurred while fetching traffic data for {origin} -> {destination}.")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching traffic data for {origin} -> {destination}: {e}")
        if e.response is not None:
             logger.error(f"Response status code: {e.response.status_code}, Response body: {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during traffic fetch: {e}")
        return None

def parse_traffic_data(directions_data: Dict[str, Any], origin: str, destination: str) -> Optional[TrafficInfo]:
    """Parses raw Google Directions data into a TrafficInfo model."""
    if not directions_data or directions_data.get("status") != "OK" or not directions_data.get("routes"):
        logger.warning(f"No valid routes found or error in traffic data for {origin} -> {destination}.")
        return None

    try:
        # Use the first route provided
        route = directions_data["routes"][0]
        leg = route["legs"][0] # Assuming single leg for simplicity

        duration_sec = leg.get("duration", {}).get("value")
        duration_in_traffic_sec = leg.get("duration_in_traffic", {}).get("value")

        delay_minutes = None
        condition = 'light' # Default
        recommendation = None

        if duration_sec is not None and duration_in_traffic_sec is not None:
            delay_seconds = duration_in_traffic_sec - duration_sec
            delay_minutes = max(0, round(delay_seconds / 60)) # Ensure non-negative delay

            # Simple condition logic based on delay percentage or absolute value
            if delay_minutes > 30:
                condition = 'severe'
                recommendation = f"Significant delay ({delay_minutes} min). Consider alternative routes or times."
            elif delay_minutes > 15:
                condition = 'heavy'
                recommendation = f"Heavy traffic ({delay_minutes} min delay). Leave earlier."
            elif delay_minutes > 5:
                condition = 'moderate'
                recommendation = f"Moderate traffic ({delay_minutes} min delay)."
            else:
                condition = 'light'
                recommendation = "Traffic conditions seem normal."
        else:
             logger.warning(f"Could not determine traffic delay for {origin} -> {destination}. Duration data missing.")
             recommendation = "Could not determine traffic delay."


        return TrafficInfo(
            route_description=f"{origin} to {destination}",
            delay_minutes=delay_minutes,
            condition=condition,
            recommendation=recommendation
        )
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.error(f"Error parsing traffic data: {e}. Data: {directions_data}")
        return None

# --- ADK Tool Definitions ---

def get_current_weather(location_query: str) -> Tuple[Optional[dict], str]:
    """
    Gets current weather for a location (uses geocoding first if not lat/lon).
    Note: Simple implementation, assumes location_query is 'latitude,longitude' for now.
          A robust version would use a geocoding API first.

    Args:
        location_query (str): Location, ideally as "latitude,longitude".

    Returns:
        Tuple[Optional[dict], str]: WeatherInfo dictionary and status message.
    """
    try:
        lat_str, lon_str = location_query.split(',')
        latitude = float(lat_str.strip())
        longitude = float(lon_str.strip())
    except (ValueError, AttributeError):
        logger.error(f"Invalid location_query format: '{location_query}'. Expected 'latitude,longitude'. Geocoding not implemented.")
        # TODO: Implement geocoding lookup here using Google Geocoding API or similar
        return None, "Invalid location format. Please provide 'latitude,longitude'. Geocoding not implemented."

    status_message = ""
    try:
        raw_weather = get_weather_data(latitude, longitude)
        if raw_weather:
            weather_info = parse_weather_data(raw_weather, location_name=f"Lat:{latitude}, Lon:{longitude}")
            if weather_info:
                status_message = f"Successfully fetched weather for {location_query}."
                logger.info(status_message)
                return weather_info.model_dump(mode='json'), status_message
            else:
                status_message = f"Failed to parse weather data for {location_query}."
                logger.warning(status_message)
                return None, status_message
        else:
            status_message = f"Failed to fetch weather data for {location_query} after retries."
            logger.error(status_message)
            return None, status_message
    except Exception as e:
        # Catch errors from retry exhaustion or unexpected issues
        status_message = f"An error occurred fetching weather for {location_query}: {e}"
        logger.exception(status_message) # Log full traceback
        return None, status_message


def get_traffic_info(origin: str, destination: str) -> Tuple[Optional[dict], str]:
    """
    Gets traffic information (delay, conditions) for a route using Google Directions API.

    Args:
        origin (str): Starting address or "lat,lon".
        destination (str): Ending address or "lat,lon".

    Returns:
        Tuple[Optional[dict], str]: TrafficInfo dictionary and status message.
    """
    status_message = ""
    try:
        raw_traffic = get_traffic_data(origin, destination)
        if raw_traffic:
            # Handle ZERO_RESULTS explicitly
            if raw_traffic.get("status") == "ZERO_RESULTS":
                 status_message = f"No route found between '{origin}' and '{destination}'."
                 logger.info(status_message)
                 # Return an empty TrafficInfo or specific indicator? For now, None.
                 return None, status_message

            traffic_info = parse_traffic_data(raw_traffic, origin, destination)
            if traffic_info:
                status_message = f"Successfully fetched traffic info for {origin} -> {destination}."
                logger.info(status_message)
                return traffic_info.model_dump(mode='json'), status_message
            else:
                status_message = f"Failed to parse traffic data for {origin} -> {destination}."
                logger.warning(status_message)
                return None, status_message
        else:
            # This handles API errors after retries or non-OK statuses other than ZERO_RESULTS
            status_message = f"Failed to fetch traffic data for {origin} -> {destination} after retries or due to API error."
            logger.error(status_message)
            return None, status_message
    except Exception as e:
        status_message = f"An error occurred fetching traffic for {origin} -> {destination}: {e}"
        logger.exception(status_message)
        return None, status_message