


# smart_planner/agents/email_agent.py
"""Email Agent: Analyzes emails to extract and prioritize tasks."""

import logging
import json
from typing import List, Optional

from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool # Corrected case
from google.adk.models.base_llm import BaseLlm
from google.adk.sessions.state import State as SessionState # Use alias
from pydantic import ValidationError

from ..models.schemas import EmailTask, PrioritizedTaskListOutput
from ..tools import email_tools

logger = logging.getLogger(__name__)

class EmailAgent(LlmAgent):
    """
    An agent responsible for analyzing emails to extract tasks and assign priorities.
    """
    def __init__(self, llm_provider: BaseLlm, session_state: Optional[SessionState] = None):
        super().__init__(
            name="EmailAgent",
            description="Analyzes emails to find and prioritize tasks.",
            llm_provider=llm_provider,
            session_state=session_state
        )

    @AgentTool # Corrected case
    def get_email_tasks_tool(self, use_mock_data: bool = True, max_emails_api: int = 20) -> str:
        """
        Tool to fetch emails (mock or API) and extract a prioritized list of tasks.

        Args:
            use_mock_data: Set to True to use mock email data. Defaults to True.
            max_emails_api: Max emails to fetch if using Gmail API. Defaults to 20.

        Returns:
            A JSON string representing the PrioritizedTaskListOutput (list of tasks),
            or an error message.
        """
        logger.info(f"EmailAgent tool called, mock: {use_mock_data}, max_api: {max_emails_api}")
        tasks_dict, status_message = email_tools.get_prioritized_tasks_from_emails(use_mock_data, max_emails_api)

        if tasks_dict is not None:
            logger.info(f"Tool status: {status_message}")
            # Return the list of task dictionaries directly
            return json.dumps(tasks_dict)
        else:
            logger.error(f"Tool failed: {status_message}")
            return json.dumps({"error": status_message})

    def invoke(self, input_data: dict) -> PrioritizedTaskListOutput:
        """
        Main execution logic for the Email Agent.

        Args:
            input_data (dict): Dictionary containing optionally 'use_mock_data' (bool)
                               and 'max_emails_api' (int).

        Returns:
            PrioritizedTaskListOutput: The structured list of prioritized tasks.
                                       Returns an empty list on failure.
        """
        use_mock = input_data.get("use_mock_data", True) # Default to mock for emails
        max_api = input_data.get("max_emails_api", 20)

        logger.info(f"EmailAgent invoking, mock: {use_mock}, max_api: {max_api}")

        # Call the tool to get task data
        tasks_json_str = self.get_email_tasks_tool(use_mock_data=use_mock, max_emails_api=max_api)

        try:
            tasks_data = json.loads(tasks_json_str)

            if isinstance(tasks_data, dict) and "error" in tasks_data:
                logger.error(f"Tool returned an error: {tasks_data['error']}")
                return PrioritizedTaskListOutput(tasks=[]) # Return empty list on tool error

            # Validate and parse tasks using Pydantic
            parsed_tasks: List[EmailTask] = []
            if isinstance(tasks_data, list):
                for task_dict in tasks_data:
                    try:
                        parsed_tasks.append(EmailTask(**task_dict))
                    except ValidationError as e:
                        logger.warning(f"Skipping task due to validation error: {task_dict.get('description', 'N/A')}. Error: {e}")
                    except Exception as e:
                         logger.error(f"Unexpected error parsing task dict: {task_dict}. Error: {e}")


            logger.info(f"Successfully parsed {len(parsed_tasks)} tasks from tool output.")

            output = PrioritizedTaskListOutput(tasks=parsed_tasks)

            # Store result in session state
            if self.session_state:
                # Use model_dump for Pydantic V2
                self.session_state.set("prioritized_tasks", output.model_dump(mode='json'))
                logger.debug("Stored prioritized tasks in session state.")

            return output

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response from tool: {e}. Response: {tasks_json_str}")
            return PrioritizedTaskListOutput(tasks=[])
        except Exception as e:
            logger.exception(f"An unexpected error occurred during EmailAgent invocation: {e}")
            return PrioritizedTaskListOutput(tasks=[])
