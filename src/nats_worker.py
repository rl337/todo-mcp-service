"""
NATS worker implementation for processing task operations.

Handles async task processing, updates, completions, and background jobs.
"""
import asyncio
import logging
from typing import Dict, Any, Optional, Callable
from nats_queue import NATSQueue, NATSWorker, MessageType, nullcontext

logger = logging.getLogger(__name__)


class TaskWorker(NATSWorker):
    """Worker for processing task-related messages."""
    
    def __init__(
        self,
        queue: NATSQueue,
        db,
        worker_id: Optional[str] = None
    ):
        """
        Initialize task worker.
        
        Args:
            queue: NATSQueue instance
            db: Database instance
            worker_id: Worker identifier
        """
        super().__init__(queue, worker_id)
        self.db = db
        self.handlers = {
            MessageType.TASK_PROCESS.value: self._handle_task_process,
            MessageType.TASK_COMPLETE.value: self._handle_task_complete,
            MessageType.TASK_UPDATE.value: self._handle_task_update,
            MessageType.WEBHOOK_DELIVERY.value: self._handle_webhook_delivery,
            MessageType.BACKUP_JOB.value: self._handle_backup_job,
        }
    
    def _get_handler(self, message_type: str) -> Optional[Callable]:
        """Get handler for message type."""
        return self.handlers.get(message_type)
    
    async def _handle_task_process(self, data: Dict[str, Any]) -> None:
        """Handle task processing message."""
        task_id = data.get("task_id")
        operation = data.get("operation")  # e.g., "auto_unlock", "stale_check"
        
        logger.info(f"Processing task {task_id}: {operation}")
        
        if operation == "auto_unlock":
            # Auto-unlock stale tasks
            hours = data.get("hours", 24)
            # Implementation would call db.unlock_stale_tasks(hours)
            logger.debug(f"Auto-unlocking tasks stale for {hours} hours")
        
        elif operation == "stale_check":
            # Check and report stale tasks
            stale_tasks = self.db.get_stale_tasks()
            logger.debug(f"Found {len(stale_tasks)} stale tasks")
    
    async def _handle_task_complete(self, data: Dict[str, Any]) -> None:
        """Handle task completion message."""
        task_id = data.get("task_id")
        agent_id = data.get("agent_id")
        notes = data.get("notes")
        
        logger.info(f"Completing task {task_id} for agent {agent_id}")
        
        # Process completion asynchronously
        try:
            success = self.db.complete_task(
                task_id=task_id,
                agent_id=agent_id,
                notes=notes
            )
            if success:
                logger.info(f"Task {task_id} completed successfully")
            else:
                logger.warning(f"Failed to complete task {task_id}")
        except Exception as e:
            logger.error(f"Error completing task {task_id}: {e}", exc_info=True)
            raise
    
    async def _handle_task_update(self, data: Dict[str, Any]) -> None:
        """Handle task update message."""
        task_id = data.get("task_id")
        agent_id = data.get("agent_id")
        content = data.get("content")
        update_type = data.get("update_type", "progress")
        
        logger.debug(f"Updating task {task_id}: {update_type}")
        
        try:
            update_id = self.db.add_task_update(
                task_id=task_id,
                agent_id=agent_id,
                content=content,
                update_type=update_type
            )
            logger.debug(f"Task update {update_id} created")
        except Exception as e:
            logger.error(f"Error updating task {task_id}: {e}", exc_info=True)
            raise
    
    async def _handle_webhook_delivery(self, data: Dict[str, Any]) -> None:
        """Handle webhook delivery message."""
        import httpx
        from webhooks import notify_webhooks
        
        webhook_id = data.get("webhook_id")
        url = data.get("url")
        payload = data.get("payload", {})
        secret = data.get("secret")
        retry_count = data.get("retry_count", 0)
        
        logger.debug(f"Delivering webhook {webhook_id} to {url} (attempt {retry_count + 1})")
        
        try:
            headers = {"Content-Type": "application/json"}
            if secret:
                import hmac
                import hashlib
                import json as json_lib
                payload_bytes = json_lib.dumps(payload).encode()
                signature = hmac.new(
                    secret.encode(),
                    payload_bytes,
                    hashlib.sha256
                ).hexdigest()
                headers["X-Webhook-Signature"] = f"sha256={signature}"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                
                logger.info(f"Webhook {webhook_id} delivered successfully ({response.status_code})")
        except Exception as e:
            logger.error(f"Webhook {webhook_id} delivery failed: {e}", exc_info=True)
            
            # Retry logic (could republish with incremented retry_count)
            if retry_count < 3:
                logger.debug(f"Will retry webhook {webhook_id}")
                # Could republish message with incremented retry_count
            else:
                logger.error(f"Webhook {webhook_id} failed after {retry_count} retries")
    
    async def _handle_backup_job(self, data: Dict[str, Any]) -> None:
        """Handle backup job message."""
        from backup import BackupManager
        import os
        
        logger.info("Processing backup job")
        
        try:
            db_path = os.getenv("TODO_DB_PATH", "/app/data/todos.db")
            backups_dir = os.getenv("TODO_BACKUPS_DIR", "/app/backups")
            backup_manager = BackupManager(db_path, backups_dir)
            backup_file = backup_manager.create_backup()
            logger.info(f"Backup job completed: {backup_file}")
        except Exception as e:
            logger.error(f"Backup job failed: {e}", exc_info=True)
            raise


async def start_workers(
    db,
    nats_url: Optional[str] = None,
    num_workers: int = 1,
    use_jetstream: bool = False
) -> list[TaskWorker]:
    """
    Start NATS workers for task processing.
    
    Args:
        db: Database instance
        nats_url: NATS server URL
        num_workers: Number of worker instances to start
        use_jetstream: Enable JetStream persistence
        
    Returns:
        List of started workers
    """
    queue = NATSQueue(nats_url=nats_url, use_jetstream=use_jetstream)
    workers = []
    
    # Subjects to subscribe to
    subjects = [
        "task.process",
        "task.complete",
        "task.update",
        "webhook.delivery",
        "backup.job"
    ]
    
    for i in range(num_workers):
        worker = TaskWorker(
            queue=queue,
            db=db,
            worker_id=f"task-worker-{i+1}"
        )
        await worker.start(subjects)
        workers.append(worker)
        logger.info(f"Started worker {worker.worker_id}")
    
    return workers


async def stop_workers(workers: list[TaskWorker]) -> None:
    """Stop all workers."""
    for worker in workers:
        await worker.stop()
