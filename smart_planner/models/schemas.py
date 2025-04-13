# smart_planner/models/schemas.py
"""Pydantic models for data validation and serialization."""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Literal, Union
from datetime import datetime, date, time

# --- Calendar Agent Models ---

class CalendarEvent(BaseModel):
    """Represents a single event retrieved from Google Calendar."""
    start_time: datetime = Field(..., description="Start time of the event")
    end_time: datetime = Field(..., description="End time of the event")
    summary: str = Field(..., description="Event title or summary")
    location: Optional[str] = Field(None, description="Event location, if available")

    @validator('start_time', 'end_time', pre=True, always=True)
    def parse_datetime(cls, value):
        """Ensure datetime objects are timezone-aware or handle string parsing if needed."""
        # Basic handling, assumes ISO format or datetime objects already
        if isinstance(value, str):
            try:
                # Attempt to parse common ISO formats
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                raise ValueError(f"Invalid datetime format: {value}")
        elif isinstance(value, datetime):
            # Ensure timezone awareness if needed, or handle naive datetimes appropriately
            # For simplicity here, we assume correct datetime objects are passed
            return value
        raise TypeError("datetime must be a string or datetime object")

class FreeTimeSlot(BaseModel):
    """Represents a block of free time in the schedule."""
    start_time: datetime = Field(..., description="Start of the free slot")
    end_time: datetime = Field(..., description="End of the free slot")
    duration_minutes: int = Field(..., description="Duration of the free slot in minutes")

class CalendarConflict(BaseModel):
    """Represents a potential conflict between events."""
    conflicting_events: List[CalendarEvent] = Field(..., description="List of events that overlap")
    details: str = Field(..., description="Description of the conflict")

class CalendarSummaryOutput(BaseModel):
    """Structured output from the Calendar Agent."""
    summary_date: date = Field(..., description="The date for which the schedule is summarized") # Renamed from 'date'
    events: List[CalendarEvent] = Field(default_factory=list, description="List of scheduled events for the day")
    free_slots: List[FreeTimeSlot] = Field(default_factory=list, description="Identified free time slots")
    conflicts: List[CalendarConflict] = Field(default_factory=list, description="Detected schedule conflicts")

# --- Email Agent Models ---

class EmailTask(BaseModel):
    """Represents a task extracted from email content."""
    description: str = Field(..., description="Description of the task")
    priority: Literal['low', 'medium', 'high', 'urgent'] = Field(..., description="Priority level assigned to the task")
    due_date: Optional[date] = Field(None, description="Optional due date for the task")
    source_email_id: Optional[str] = Field(None, description="ID of the source email, if applicable")

class PrioritizedTaskListOutput(BaseModel):
    """Structured output from the Email Agent."""
    tasks: List[EmailTask] = Field(default_factory=list, description="List of prioritized tasks")

# --- Context Agent Models ---

class WeatherInfo(BaseModel):
    """Represents weather information for a specific time or location."""
    time: Optional[time] = Field(None, description="Time the weather applies to (e.g., for hourly forecast)")
    description: str = Field(..., description="Brief weather description (e.g., 'Rain expected')")
    temperature_celsius: Optional[float] = Field(None, description="Temperature in Celsius")
    location: Optional[str] = Field(None, description="Location the weather applies to")

class TrafficInfo(BaseModel):
    """Represents traffic information for a route or area."""
    route_description: Optional[str] = Field(None, description="Description of the affected route (e.g., 'Home to Office')")
    delay_minutes: Optional[int] = Field(None, description="Estimated traffic delay in minutes")
    condition: Literal['light', 'moderate', 'heavy', 'severe'] = Field(..., description="General traffic condition")
    recommendation: Optional[str] = Field(None, description="Suggestion based on traffic (e.g., 'Leave 15 minutes earlier')")

class ContextRecommendation(BaseModel):
    """Represents a single recommendation from the Context Agent."""
    type: Literal['weather', 'traffic', 'general'] = Field(..., description="Type of recommendation")
    # Use forward references (strings) for types within Union to avoid potential recursion issues
    details: Union['WeatherInfo', 'TrafficInfo', str] = Field(..., description="Specific details of the recommendation")
    impact_time: Optional[datetime] = Field(None, description="Time the recommendation is most relevant")

class ContextOutput(BaseModel):
    """Structured output from the Context Agent."""
    recommendations: List[ContextRecommendation] = Field(default_factory=list, description="List of contextual recommendations")

# --- Consolidated Plan Models ---

class PlanItem(BaseModel):
    """Represents a single item in the consolidated daily plan."""
    time: time = Field(..., description="Time of the event, task start, or recommendation relevance")
    item_type: Literal['event', 'task', 'recommendation'] = Field(..., description="Type of plan item")
    details: Union['CalendarEvent', 'EmailTask', 'ContextRecommendation', str] = Field(..., description="Details of the plan item")
    priority: Optional[Literal['low', 'medium', 'high', 'urgent']] = Field(None, description="Priority, applicable mainly to tasks")

class ConsolidatedDailyPlanOutput(BaseModel):
    """Final structured output combining all agent inputs."""
    date: date = Field(..., description="The date of the plan")
    plan: List[PlanItem] = Field(..., description="Chronologically sorted list of plan items for the day")
    summary: Optional[str] = Field(None, description="Optional high-level summary or key highlights")

    @validator('plan')
    def sort_plan_by_time(cls, v):
        """Ensure the plan items are sorted chronologically."""
        return sorted(v, key=lambda item: item.time)

# Rebuild models that use forward references
ContextRecommendation.model_rebuild()
PlanItem.model_rebuild()
ContextOutput.model_rebuild() # Rebuild models that contain the updated models
ConsolidatedDailyPlanOutput.model_rebuild()