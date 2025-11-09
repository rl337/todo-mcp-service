"""
Slack integration for task notifications and interactions.

Provides:
- Task notifications to Slack channels (created, completed, blocked)
- Slash commands for task operations (/todo reserve, /todo complete)
- Interactive components (buttons) for task actions
- Slack request signature verification
"""
import os
import logging
import hmac
import hashlib
import time
import json
from typing import Dict, Any, Optional, List
from urllib.parse import parse_qs

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    SLACK_SDK_AVAILABLE = True
except ImportError:
    SLACK_SDK_AVAILABLE = False
    WebClient = None

logger = logging.getLogger(__name__)


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    signature: str,
    body: str
) -> bool:
    """
    Verify Slack request signature.
    
    Args:
        signing_secret: Slack signing secret
        timestamp: Request timestamp from X-Slack-Request-Timestamp header
        signature: Request signature from X-Slack-Signature header
        body: Raw request body
        
    Returns:
        True if signature is valid, False otherwise
    """
    # Check timestamp is within 5 minutes (prevent replay attacks)
    current_time = int(time.time())
    request_time = int(timestamp) if timestamp else 0
    if abs(current_time - request_time) > 60 * 5:
        logger.warning(f"Slack request timestamp too old: {request_time} (current: {current_time})")
        return False
    
    # Create signature base string
    sig_basestring = f"v0:{timestamp}:{body}"
    
    # Compute signature
    computed_signature = hmac.new(
        signing_secret.encode('utf-8'),
        sig_basestring.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Compare signatures
    expected_signature = f"v0={computed_signature}"
    is_valid = hmac.compare_digest(expected_signature, signature)
    
    if not is_valid:
        logger.warning("Slack signature verification failed")
    
    return is_valid


class SlackNotifier:
    """Handles sending Slack notifications for task events."""
    
    def __init__(self, bot_token: Optional[str] = None, default_channel: Optional[str] = None):
        """
        Initialize Slack notifier.
        
        Args:
            bot_token: Slack bot token (xoxb-...)
            default_channel: Default channel for notifications (e.g., "#general")
        """
        self.bot_token = bot_token or os.getenv("SLACK_BOT_TOKEN")
        self.default_channel = default_channel or os.getenv("SLACK_DEFAULT_CHANNEL", "#general")
        self.client = None
        
        if SLACK_SDK_AVAILABLE and self.bot_token:
            try:
                self.client = WebClient(token=self.bot_token)
                logger.info("Slack notifier initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Slack client: {str(e)}")
        else:
            if not SLACK_SDK_AVAILABLE:
                logger.warning("slack-sdk not installed. Slack notifications will be disabled.")
            if not self.bot_token:
                logger.warning("SLACK_BOT_TOKEN not set. Slack notifications will be disabled.")
    
    def _format_task_message(self, event_type: str, task: Dict[str, Any], project: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Format a task notification as a Slack message.
        
        Args:
            event_type: Type of event (task.created, task.completed, task.blocked)
            task: Task dictionary
            project: Optional project dictionary
            
        Returns:
            Slack message blocks dictionary
        """
        task_id = task.get("id")
        title = task.get("title", "Untitled Task")
        task_type = task.get("task_type", "concrete")
        status = task.get("task_status", "available")
        agent_id = task.get("assigned_agent")
        
        # Determine emoji and color based on event type
        if event_type == "task.created":
            emoji = "??"
            color = "#36a64f"  # Green
            action_text = "Task Created"
        elif event_type == "task.completed":
            emoji = "?"
            color = "#2eb886"  # Bright green
            action_text = "Task Completed"
        elif event_type == "task.blocked":
            emoji = "??"
            color = "#ff0000"  # Red
            action_text = "Task Blocked"
        else:
            emoji = "??"
            color = "#439fe0"  # Blue
            action_text = "Task Updated"
        
        # Build message blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {action_text}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title}*\n\n*Task ID:* {task_id}\n*Type:* {task_type}\n*Status:* {status}"
                }
            }
        ]
        
        # Add project info if available
        if project:
            project_name = project.get("name", "Unknown Project")
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"?? Project: {project_name}"
                    }
                ]
            })
        
        # Add assigned agent if present
        if agent_id:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"?? Agent: {agent_id}"
                    }
                ]
            })
        
        # Add action buttons for available tasks
        if status == "available" and event_type == "task.created":
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Reserve Task"
                        },
                        "style": "primary",
                        "action_id": "reserve_task",
                        "value": str(task_id)
                    }
                ]
            })
        elif status == "in_progress" and event_type == "task.completed":
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Task"
                        },
                        "action_id": "view_task",
                        "value": str(task_id),
                        "url": f"{os.getenv('TODO_SERVICE_URL', 'http://localhost:8004')}/tasks/{task_id}"
                    }
                ]
            })
        
        return {
            "blocks": blocks,
            "text": f"{action_text}: {title}"  # Fallback text for notifications
        }
    
    def send_notification(
        self,
        channel: Optional[str],
        event_type: str,
        task: Dict[str, Any],
        project: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send a task notification to Slack.
        
        Args:
            channel: Slack channel ID or name (e.g., "#general", "C123456")
            event_type: Type of event (task.created, task.completed, task.blocked)
            task: Task dictionary
            project: Optional project dictionary
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.client:
            logger.debug("Slack client not available, skipping notification")
            return False
        
        target_channel = channel or self.default_channel
        
        try:
            message = self._format_task_message(event_type, task, project)
            response = self.client.chat_postMessage(
                channel=target_channel,
                blocks=message["blocks"],
                text=message["text"]
            )
            
            if response["ok"]:
                logger.info(f"Slack notification sent to {target_channel} for {event_type} (task {task.get('id')})")
                return True
            else:
                logger.error(f"Slack API error: {response.get('error', 'Unknown error')}")
                return False
                
        except SlackApiError as e:
            logger.error(f"Slack API error sending notification: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Slack notification: {str(e)}", exc_info=True)
            return False


# Global Slack notifier instance
_slack_notifier: Optional[SlackNotifier] = None


def get_slack_notifier() -> Optional[SlackNotifier]:
    """Get or create global Slack notifier instance."""
    global _slack_notifier
    if _slack_notifier is None:
        _slack_notifier = SlackNotifier()
    return _slack_notifier


def send_task_notification(
    channel: Optional[str],
    event_type: str,
    task: Dict[str, Any],
    project: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Send a task notification to Slack (convenience function).
    
    Args:
        channel: Slack channel ID or name
        event_type: Type of event
        task: Task dictionary
        project: Optional project dictionary
        
    Returns:
        True if sent successfully, False otherwise
    """
    notifier = get_slack_notifier()
    if notifier:
        return notifier.send_notification(channel, event_type, task, project)
    return False
