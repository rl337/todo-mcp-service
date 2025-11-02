"""
Webhook notification system for task events.

Handles sending webhook notifications with retry logic and error handling.
"""
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import hmac
import hashlib

import httpx

logger = logging.getLogger(__name__)


async def send_webhook_notification(
    db,
    webhook: Dict[str, Any],
    event_type: str,
    payload: Dict[str, Any],
    max_retries: Optional[int] = None
) -> bool:
    """
    Send a webhook notification with retry logic.
    
    Args:
        db: Database instance
        webhook: Webhook configuration dictionary
        event_type: Type of event (e.g., 'task.created', 'task.completed')
        payload: Payload to send
        max_retries: Maximum number of retries (defaults to webhook['retry_count'])
        
    Returns:
        True if successful, False otherwise
    """
    webhook_id = webhook["id"]
    url = webhook["url"]
    timeout = webhook.get("timeout_seconds", 10)
    secret = webhook.get("secret")
    retry_count = max_retries if max_retries is not None else webhook.get("retry_count", 3)
    
    # Prepare payload
    payload_json = json.dumps(payload)
    
    # Add signature if secret is provided
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": event_type,
        "X-Webhook-Timestamp": datetime.utcnow().isoformat()
    }
    
    if secret:
        # Create HMAC signature
        signature = hmac.new(
            secret.encode("utf-8"),
            payload_json.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={signature}"
    
    # Try sending with retries
    last_error = None
    for attempt in range(1, retry_count + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, content=payload_json, headers=headers)
                
                # Record delivery attempt
                db.record_webhook_delivery(
                    webhook_id=webhook_id,
                    event_type=event_type,
                    payload=payload_json,
                    status="success" if response.status_code < 400 else "failed",
                    response_code=response.status_code,
                    response_body=response.text[:1000] if response.text else None,  # Truncate long responses
                    attempt_number=attempt
                )
                
                if response.status_code < 400:
                    logger.info(f"Webhook {webhook_id} delivered successfully (attempt {attempt})")
                    return True
                else:
                    logger.warning(
                        f"Webhook {webhook_id} returned status {response.status_code} "
                        f"(attempt {attempt}/{retry_count})"
                    )
                    last_error = f"HTTP {response.status_code}"
                    
        except httpx.TimeoutException:
            logger.warning(f"Webhook {webhook_id} timed out (attempt {attempt}/{retry_count})")
            db.record_webhook_delivery(
                webhook_id=webhook_id,
                event_type=event_type,
                payload=payload_json,
                status="failed",
                response_code=None,
                response_body="Request timeout",
                attempt_number=attempt
            )
            last_error = "Timeout"
            
        except httpx.RequestError as e:
            logger.warning(f"Webhook {webhook_id} request error: {str(e)} (attempt {attempt}/{retry_count})")
            db.record_webhook_delivery(
                webhook_id=webhook_id,
                event_type=event_type,
                payload=payload_json,
                status="failed",
                response_code=None,
                response_body=str(e)[:1000],
                attempt_number=attempt
            )
            last_error = str(e)
            
        except Exception as e:
            logger.error(f"Unexpected error sending webhook {webhook_id}: {str(e)}", exc_info=True)
            db.record_webhook_delivery(
                webhook_id=webhook_id,
                event_type=event_type,
                payload=payload_json,
                status="failed",
                response_code=None,
                response_body=str(e)[:1000],
                attempt_number=attempt
            )
            last_error = str(e)
        
        # Wait before retry (exponential backoff: 1s, 2s, 4s...)
        if attempt < retry_count:
            wait_time = min(2 ** (attempt - 1), 60)  # Cap at 60 seconds
            await asyncio.sleep(wait_time)
    
    logger.error(f"Webhook {webhook_id} failed after {retry_count} attempts. Last error: {last_error}")
    return False


async def notify_webhooks(
    db,
    project_id: Optional[int],
    event_type: str,
    payload: Dict[str, Any]
):
    """
    Notify all webhooks subscribed to an event.
    
    Args:
        db: Database instance
        project_id: Project ID (None for global webhooks)
        event_type: Type of event (e.g., 'task.created', 'task.completed', 'task.status_changed')
        payload: Payload to send
    """
    # Get webhooks subscribed to this event
    webhooks = db.get_webhooks_for_event(project_id, event_type)
    
    if not webhooks:
        return
    
    logger.info(f"Notifying {len(webhooks)} webhook(s) for event {event_type}")
    
    # Send notifications concurrently (fire and forget - don't block on webhook delivery)
    for webhook in webhooks:
        # Create task for each webhook notification (fire and forget)
        asyncio.create_task(send_webhook_notification(db, webhook, event_type, payload))
