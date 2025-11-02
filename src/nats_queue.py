"""
NATS message queue system for handling high concurrent task operations.

Provides async message queue using NATS for:
- Task processing operations
- Background job execution
- Horizontal scaling via worker processes
- Message durability and reliability
"""
import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional, Callable, Awaitable
from datetime import datetime
from enum import Enum

try:
    import nats
    from nats.aio.client import Client as NATS
    from nats.aio.msg import Msg
    NATS_AVAILABLE = True
except ImportError:
    NATS_AVAILABLE = False
    nats = None
    NATS = None
    Msg = None

from tracing import trace_span, add_span_attribute

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Message type enumeration."""
    TASK_PROCESS = "task.process"
    TASK_COMPLETE = "task.complete"
    TASK_UPDATE = "task.update"
    WEBHOOK_DELIVERY = "webhook.delivery"
    BACKUP_JOB = "backup.job"
    CLEANUP_JOB = "cleanup.job"


class NATSQueue:
    """
    NATS message queue for async task processing.
    
    Features:
    - Async message publishing and subscription
    - Subject-based routing
    - Horizontal scaling via multiple workers
    - Message durability (via NATS JetStream if enabled)
    - Error handling and retries
    """
    
    def __init__(
        self,
        nats_url: Optional[str] = None,
        nats_client: Optional[NATS] = None,
        use_jetstream: bool = False,
        enable_tracing: bool = True
    ):
        """
        Initialize NATS queue.
        
        Args:
            nats_url: NATS server URL (e.g., 'nats://localhost:4222')
            nats_client: Optional existing NATS client instance
            use_jetstream: Enable JetStream for persistence (requires NATS 2.2+)
            enable_tracing: Enable OpenTelemetry tracing
        """
        if not NATS_AVAILABLE:
            raise ImportError(
                "nats-py package is required. Install with: pip install nats-py>=2.7.0"
            )
        
        self.nats_url = nats_url or os.getenv("NATS_URL", "nats://localhost:4222")
        self.nats_client = nats_client
        self.use_jetstream = use_jetstream
        self.enable_tracing = enable_tracing
        self.js_context = None
        self.connected = False
        
    async def connect(self) -> None:
        """Connect to NATS server."""
        if self.connected and self.nats_client:
            return
        
        try:
            if self.nats_client:
                self.nc = self.nats_client
            else:
                self.nc = await nats.connect(self.nats_url)
            
            if self.use_jetstream:
                self.js_context = self.nc.jetstream()
                # Create streams if they don't exist
                try:
                    await self.js_context.add_stream(
                        name="tasks",
                        subjects=["task.>"]
                    )
                    await self.js_context.add_stream(
                        name="jobs",
                        subjects=["job.>"]
                    )
                    logger.info("NATS JetStream streams configured")
                except Exception as e:
                    logger.warning(f"Could not create JetStream streams (may already exist): {e}")
            
            self.connected = True
            logger.info(f"Connected to NATS server: {self.nats_url}")
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from NATS server."""
        if self.nc and self.connected:
            await self.nc.close()
            self.connected = False
            logger.info("Disconnected from NATS server")
    
    async def publish(
        self,
        subject: str,
        data: Dict[str, Any],
        reply_to: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Publish a message to NATS.
        
        Args:
            subject: NATS subject (e.g., 'task.process')
            data: Message payload dictionary
            reply_to: Optional reply subject
            headers: Optional message headers
        """
        if not self.connected:
            await self.connect()
        
        span_context = trace_span("nats_queue.publish", attributes={
            "nats.subject": subject,
            "message.type": data.get("type", "unknown")
        }) if self.enable_tracing else nullcontext()
        
        with span_context:
            try:
                payload = json.dumps(data).encode()
                
                if self.use_jetstream and self.js_context:
                    # Use JetStream for durability
                    await self.js_context.publish(
                        subject,
                        payload,
                        headers=headers
                    )
                else:
                    # Regular NATS publish
                    await self.nc.publish(
                        subject,
                        payload,
                        reply=reply_to,
                        headers=headers
                    )
                
                logger.debug(f"Published message to {subject}: {data.get('type', 'unknown')}")
            except Exception as e:
                logger.error(f"Failed to publish message to {subject}: {e}", exc_info=True)
                raise
    
    async def subscribe(
        self,
        subject: str,
        handler: Callable[[Dict[str, Any], Msg], Awaitable[None]],
        queue_group: Optional[str] = None
    ) -> None:
        """
        Subscribe to messages on a subject.
        
        Args:
            subject: NATS subject pattern (supports wildcards)
            handler: Async function to handle messages (receives data dict and Msg)
            queue_group: Optional queue group name for load balancing
        """
        if not self.connected:
            await self.connect()
        
        async def message_handler(msg: Msg) -> None:
            """Internal message handler that decodes and routes messages."""
            try:
                # Decode message
                try:
                    data = json.loads(msg.data.decode())
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    logger.error(f"Failed to decode message: {e}")
                    return
                
                # Extract message metadata
                message_id = data.get("id") or msg.reply or "unknown"
                message_type = data.get("type", "unknown")
                timestamp = data.get("timestamp", datetime.utcnow().isoformat())
                
                span_context = trace_span(
                    "nats_queue.message_handler",
                    attributes={
                        "nats.subject": msg.subject,
                        "message.id": message_id,
                        "message.type": message_type
                    }
                ) if self.enable_tracing else nullcontext()
                
                with span_context:
                    logger.debug(
                        f"Received message: {message_type} on {msg.subject} "
                        f"(reply: {msg.reply})"
                    )
                    
                    # Call user handler
                    await handler(data, msg)
                    
            except Exception as e:
                logger.error(
                    f"Error processing message on {msg.subject}: {e}",
                    exc_info=True
                )
                # Don't ack if using JetStream and handler fails
                if not (self.use_jetstream and msg.reply):
                    # For regular NATS, we can't really retry without manual handling
                    pass
        
        try:
            if self.use_jetstream and self.js_context:
                # Use JetStream consumer for durability
                await self.js_context.subscribe(
                    subject,
                    queue=queue_group,
                    cb=message_handler,
                    durable=queue_group or "default"
                )
            else:
                # Regular NATS subscription
                subscription = await self.nc.subscribe(
                    subject,
                    queue=queue_group,
                    cb=message_handler
                )
                logger.info(f"Subscribed to {subject} (queue_group: {queue_group})")
        except Exception as e:
            logger.error(f"Failed to subscribe to {subject}: {e}", exc_info=True)
            raise
    
    async def request(
        self,
        subject: str,
        data: Dict[str, Any],
        timeout: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        """
        Send a request and wait for reply (request-reply pattern).
        
        Args:
            subject: NATS subject
            data: Request payload
            timeout: Response timeout in seconds
            
        Returns:
            Reply data dictionary or None if timeout
        """
        if not self.connected:
            await self.connect()
        
        try:
            payload = json.dumps(data).encode()
            response = await self.nc.request(subject, payload, timeout=timeout)
            return json.loads(response.data.decode())
        except asyncio.TimeoutError:
            logger.warning(f"Request to {subject} timed out after {timeout}s")
            return None
        except Exception as e:
            logger.error(f"Request to {subject} failed: {e}", exc_info=True)
            return None


class NATSWorker:
    """
    Worker process for processing NATS messages.
    
    Supports horizontal scaling - run multiple workers to process
    messages concurrently from the same queue group.
    """
    
    def __init__(
        self,
        queue: NATSQueue,
        worker_id: Optional[str] = None,
        max_concurrent: int = 10
    ):
        """
        Initialize worker.
        
        Args:
            queue: NATSQueue instance
            worker_id: Unique worker identifier
            max_concurrent: Maximum concurrent message processing
        """
        self.queue = queue
        self.worker_id = worker_id or f"worker-{os.getpid()}"
        self.max_concurrent = max_concurrent
        self.running = False
        self.processed_count = 0
        self.error_count = 0
    
    async def start(self, subjects: list[str]) -> None:
        """
        Start worker and subscribe to subjects.
        
        Args:
            subjects: List of subject patterns to subscribe to
        """
        await self.queue.connect()
        self.running = True
        
        # Subscribe to each subject
        for subject in subjects:
            await self.queue.subscribe(
                subject,
                self._handle_message,
                queue_group="task-workers"  # All workers in same queue group for load balancing
            )
        
        logger.info(f"Worker {self.worker_id} started, subscribed to {len(subjects)} subjects")
    
    async def stop(self) -> None:
        """Stop worker."""
        self.running = False
        await self.queue.disconnect()
        logger.info(
            f"Worker {self.worker_id} stopped "
            f"(processed: {self.processed_count}, errors: {self.error_count})"
        )
    
    async def _handle_message(self, data: Dict[str, Any], msg: Msg) -> None:
        """Internal message handler."""
        self.processed_count += 1
        message_type = data.get("type", "unknown")
        
        try:
            logger.debug(
                f"Worker {self.worker_id} processing {message_type} "
                f"(total: {self.processed_count})"
            )
            
            # Route to appropriate handler based on message type
            handler = self._get_handler(message_type)
            if handler:
                await handler(data)
            else:
                logger.warning(f"No handler for message type: {message_type}")
            
            # Ack message if using JetStream
            if self.queue.use_jetstream and hasattr(msg, 'ack'):
                await msg.ack()
            
        except Exception as e:
            self.error_count += 1
            logger.error(
                f"Worker {self.worker_id} error processing message: {e}",
                exc_info=True
            )
            # Could implement retry logic here
    
    def _get_handler(self, message_type: str) -> Optional[Callable]:
        """Get handler function for message type."""
        # This would be overridden by subclasses or configured externally
        return None


# Context manager for null context (when tracing disabled)
class nullcontext:
    """Null context manager."""
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        return False
