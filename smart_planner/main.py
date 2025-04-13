# smart_planner/main.py
"""Main entry point for the Smart Personal Planning Assistant."""

import logging
import json
import argparse
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Union

# Configure logging before importing other modules that might log
# Ensure settings are loaded first to get LOG_LEVEL
from .config import settings # noqa sets up logging via basicConfig in settings

from google.adk.sessions.state import State as SessionState # Use alias for minimal code change
from google.adk.models.google_llm import Gemini # Use the Gemini LLM implementation

from .agents.calendar_agent import CalendarAgent
from .agents.email_agent import EmailAgent
from .agents.context_agent import ContextAgent
from .models.schemas import (
    CalendarSummaryOutput, PrioritizedTaskListOutput, ContextOutput,
    ConsolidatedDailyPlanOutput, PlanItem, CalendarEvent, EmailTask, ContextRecommendation
)

logger = logging.getLogger(__name__)

def combine_agent_outputs(
    target_date: date,
    calendar_summary: Optional[CalendarSummaryOutput],
    task_list: Optional[PrioritizedTaskListOutput],
    context_info: Optional[ContextOutput]
) -> ConsolidatedDailyPlanOutput:
    """
    Combines outputs from all agents into a single chronological plan.

    Args:
        target_date: The date for the plan.
        calendar_summary: Output from CalendarAgent.
        task_list: Output from EmailAgent.
        context_info: Output from ContextAgent.

    Returns:
        A ConsolidatedDailyPlanOutput object.
    """
    plan_items: List[PlanItem] = []
    logger.debug("Combining agent outputs...")

    # Add calendar events
    if calendar_summary:
        logger.debug(f"Adding {len(calendar_summary.events)} calendar events.")
        for event in calendar_summary.events:
            try:
                # Ensure time is extracted correctly, handling potential naive/aware issues if necessary
                # Use start_time directly which should be timezone-aware if possible
                event_time = event.start_time.time()
                plan_items.append(PlanItem(
                    time=event_time,
                    item_type="event",
                    details=event # Store the full event object
                ))
            except Exception as e:
                logger.warning(f"Could not process calendar event '{event.summary}' for plan: {e}")


    # Add prioritized tasks (needs scheduling logic - basic version: add without specific time)
    if task_list:
        logger.debug(f"Adding {len(task_list.tasks)} tasks.")
        # Simple approach: Add tasks with a placeholder time or group them
        # Sort by priority: urgent > high > medium > low
        priority_order = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}
        sorted_tasks = sorted(task_list.tasks, key=lambda t: priority_order.get(t.priority, 99))

        # Assign placeholder times, trying to fit into morning/afternoon based on priority
        # This is very basic - a real scheduler is needed for proper time allocation
        task_times = [time(9, 0), time(11, 0), time(14, 0), time(16, 0)] # Example slots
        time_idx = 0
        for task in sorted_tasks:
             # Assign a time, cycling through placeholders
             assigned_time = task_times[time_idx % len(task_times)]
             # Add some minutes based on index to avoid exact time collisions in the list
             assigned_time = (datetime.combine(date.today(), assigned_time) + timedelta(minutes=time_idx)).time()
             time_idx += 1

             plan_items.append(PlanItem(
                 time=assigned_time, # Assign placeholder time - needs improvement
                 item_type="task",
                 details=task,
                 priority=task.priority
             ))

    # Add context recommendations
    if context_info:
        logger.debug(f"Adding {len(context_info.recommendations)} recommendations.")
        for rec in context_info.recommendations:
             try:
                # Use impact time if available, otherwise a default time (e.g., morning)
                rec_time = rec.impact_time.time() if rec.impact_time else time(7, 0)
                plan_items.append(PlanItem(
                    time=rec_time,
                    item_type="recommendation",
                    details=rec # Store the full recommendation object
                ))
             except Exception as e:
                 logger.warning(f"Could not process recommendation for plan: {e}")


    # Sort the combined list chronologically
    plan_items.sort(key=lambda item: item.time)
    logger.debug(f"Total plan items after combining: {len(plan_items)}")


    # Create the final output object
    final_plan = ConsolidatedDailyPlanOutput(
        date=target_date,
        plan=plan_items,
        summary=f"Plan for {target_date.strftime('%Y-%m-%d')}. "
                f"Events: {len(calendar_summary.events) if calendar_summary else 0}. "
                f"Tasks: {len(task_list.tasks) if task_list else 0}. "
                f"Recommendations: {len(context_info.recommendations) if context_info else 0}."
    )
    logger.debug("Final plan object created.")

    return final_plan


def run_planner(target_date_str: str, use_mock_data: bool = True) -> Optional[ConsolidatedDailyPlanOutput]:
    """
    Initializes agents and runs the planning sequence.

    Args:
        target_date_str: The target date in YYYY-MM-DD format.
        use_mock_data: Whether to use mock data for all agents.

    Returns:
        The final ConsolidatedDailyPlanOutput or None if a critical error occurs.
    """
    logger.info(f"Starting Smart Planner for date: {target_date_str}, Use Mock Data: {use_mock_data}")

    try:
        target_date = date.fromisoformat(target_date_str)
    except ValueError:
        logger.error(f"Invalid date format: {target_date_str}. Please use YYYY-MM-DD.")
        return None

    # --- ADK Setup ---
    # Use a concrete LLM provider like GoogleLlm
    # Requires GOOGLE_API_KEY in .env or Application Default Credentials
    # Using flash as it's often available and cost-effective
    llm_provider = Gemini(model="gemini-1.5-flash-latest") # Instantiate Gemini
    session_state = SessionState()
    logger.info("Initialized SessionState.")

    # --- Agent Initialization ---
    calendar_agent = CalendarAgent(llm_provider=llm_provider, session_state=session_state)
    email_agent = EmailAgent(llm_provider=llm_provider, session_state=session_state)
    context_agent = ContextAgent(llm_provider=llm_provider, session_state=session_state)
    logger.info("Initialized Agents: Calendar, Email, Context")

    # --- Agent Invocation Sequence ---
    calendar_summary: Optional[CalendarSummaryOutput] = None
    task_list: Optional[PrioritizedTaskListOutput] = None
    context_info: Optional[ContextOutput] = None

    # 1. Calendar Agent
    logger.info("--- Invoking Calendar Agent ---")
    calendar_input = {"date_str": target_date_str, "use_mock_data": use_mock_data}
    try:
        calendar_summary = calendar_agent.invoke(calendar_input)
        # Check if invoke returned a valid object (it returns empty on error)
        if not calendar_summary or calendar_summary.summary_date != target_date: # Renamed from 'date'
             logger.error("Calendar Agent did not return a valid summary.")
             # Decide if this is critical - perhaps stop? For now, continue.
             calendar_summary = None # Ensure it's None if invalid
        else:
             logger.info(f"Calendar Agent finished. Found {len(calendar_summary.events)} events.")
    except Exception as e:
        logger.exception("Calendar Agent invocation failed catastrophically.")
        # Potentially stop execution here depending on requirements
        return None # Stop if calendar fails badly

    # 2. Email Agent
    logger.info("--- Invoking Email Agent ---")
    email_input = {"use_mock_data": use_mock_data}
    try:
        task_list = email_agent.invoke(email_input)
        logger.info(f"Email Agent finished. Found {len(task_list.tasks)} tasks.")
    except Exception as e:
        logger.exception("Email Agent invocation failed.")
        # Continue even if email fails? Assume yes for now.

    # 3. Context Agent (relies on calendar summary from session state)
    logger.info("--- Invoking Context Agent ---")
    context_input = {}
    try:
        context_info = context_agent.invoke(context_input)
        logger.info(f"Context Agent finished. Generated {len(context_info.recommendations)} recommendations.")
    except Exception as e:
        logger.exception("Context Agent invocation failed.")
        # Continue even if context fails? Assume yes for now.


    # --- Combine Results ---
    logger.info("--- Combining Agent Outputs ---")
    final_plan = combine_agent_outputs(target_date, calendar_summary, task_list, context_info)

    return final_plan


# --- Main Execution & ADK Web Integration ---

def main():
    """Parses arguments and runs the planner."""
    parser = argparse.ArgumentParser(description="Smart Personal Planning Assistant")
    parser.add_argument(
        "date",
        nargs="?",
        default=date.today().isoformat(),
        help="The target date for planning in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="Use live Google APIs and external services instead of mock data.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional file path to save the final plan JSON.",
    )


    args = parser.parse_args()

    # Adjust log level if debug flag is set
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        for handler in logging.getLogger().handlers:
            handler.setLevel(logging.DEBUG)
        logger.info("Debug logging enabled.")

    use_mock = not args.api

    final_plan = run_planner(target_date_str=args.date, use_mock_data=use_mock)

    if final_plan:
        logger.info("--- Consolidated Daily Plan ---")
        try:
            final_plan_json = final_plan.model_dump_json(indent=2)
            print(final_plan_json) # Print to console
            logger.info("Final plan generated and printed.")

            if args.output:
                try:
                    with open(args.output, "w") as f:
                        f.write(final_plan_json)
                    logger.info(f"Saved plan to {args.output}")
                except IOError as e:
                    logger.error(f"Failed to save plan to {args.output}: {e}")

        except Exception as e:
            logger.exception("Failed to serialize or output the final plan.")
    else:
        logger.error("Planner execution failed to produce a final plan.")


# --- ADK Web Entry Point ---
# This allows running the planner via `adk web`
try:
    from adk.web import adk_agent

    @adk_agent
    def smart_planner_agent(input_json: str) -> str:
        """ADK Web entry point."""
        logger.info("Received request via ADK Web.")
        try:
            input_data = json.loads(input_json)
            target_date = input_data.get("date", date.today().isoformat())
            use_mock = input_data.get("use_mock", True)
            logger.debug(f"ADK Web input: date={target_date}, use_mock={use_mock}")

            final_plan = run_planner(target_date_str=target_date, use_mock_data=use_mock)

            if final_plan:
                logger.info("ADK Web request processed successfully.")
                return final_plan.model_dump_json(indent=2)
            else:
                logger.error("ADK Web request failed during planner execution.")
                return json.dumps({"error": "Planner execution failed."})
        except json.JSONDecodeError:
            logger.error("ADK Web: Invalid JSON input.")
            return json.dumps({"error": "Invalid JSON input."})
        except Exception as e:
            logger.exception("ADK Web: Unexpected error during execution.")
            return json.dumps({"error": f"An unexpected error occurred: {e}"})

except ImportError:
    logger.info("ADK Web components not found, skipping web agent definition.")
    # Define a dummy adk_agent if needed for compatibility or just pass
    adk_agent = lambda func: func # Simple decorator bypass


if __name__ == "__main__":
    main()