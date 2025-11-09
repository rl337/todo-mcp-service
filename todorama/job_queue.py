"""
Background job queue system for handling long-running tasks.

Uses Redis as the queue backend for reliability and scalability.
Supports job types: backup, webhook delivery, bulk operations, etc.
"""
import os
import json
import time
import uuid
import logging
from enum import Enum
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from todorama.tracing import trace_span, add_span_attribute

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Job status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(Enum):
    """Job type enumeration."""
    BACKUP = "backup"
    WEBHOOK = "webhook"
    BULK_IMPORT = "bulk_import"
    BULK_EXPORT = "bulk_export"
    CLEANUP = "cleanup"
    NOTIFICATION = "notification"


class JobPriority(Enum):
    """Job priority enumeration."""
    LOW = 3
    MEDIUM = 2
    HIGH = 1
    CRITICAL = 0  # Highest priority


class JobError(Exception):
    """Base exception for job errors."""
    pass


class RetryableJobError(JobError):
    """Error that can be retried."""
    pass


class NonRetryableJobError(JobError):
    """Error that should not be retried."""
    pass


class JobQueue:
    """
    Background job queue using Redis.
    
    Features:
    - Priority-based job processing
    - Job status tracking
    - Automatic retries on retryable errors
    - Job timeout handling
    - Result storage
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        redis_client: Optional[Any] = None,
        default_timeout: int = 3600,  # 1 hour
        max_retries: int = 3
    ):
        """
        Initialize job queue.
        
        Args:
            redis_url: Redis connection URL (e.g., 'redis://localhost:6379')
            redis_client: Optional Redis client instance
            default_timeout: Default job timeout in seconds
            max_retries: Maximum number of retries for failed jobs
        """
        if not REDIS_AVAILABLE:
            raise ImportError("redis package is required. Install with: pip install redis>=5.0.0")
        
        if redis_client:
            self.redis = redis_client
        elif redis_url:
            self.redis = redis.from_url(redis_url, decode_responses=False)
        else:
            # Default to localhost
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_db = int(os.getenv("REDIS_DB", "0"))
            self.redis = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=False
            )
        
        # Test connection
        try:
            self.redis.ping()
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
        
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        
        # Redis key prefixes
        self.queue_prefix = "job:queue:"
        self.status_prefix = "job:status:"
        self.result_prefix = "job:result:"
        self.priority_queue_key = "job:priority_queue"
        
    def submit_job(
        self,
        job_type: JobType,
        parameters: Dict[str, Any],
        priority: JobPriority = JobPriority.MEDIUM,
        timeout: Optional[int] = None,
        delay: int = 0
    ) -> str:
        """
        Submit a job to the queue.
        
        Args:
            job_type: Type of job to execute
            parameters: Job parameters
            priority: Job priority
            timeout: Job timeout in seconds (uses default if None)
            delay: Delay before processing (seconds)
            
        Returns:
            Job ID (unique identifier)
        """
        with trace_span("job_queue.submit_job", attributes={
            "job.type": job_type.value,
            "job.priority": priority.value
        }):
            job_id = str(uuid.uuid4())
            timeout_seconds = timeout or self.default_timeout
            
            # Create job data
            job_data = {
                "job_id": job_id,
                "job_type": job_type.value,
                "parameters": parameters,
                "priority": priority.value,
                "created_at": datetime.utcnow().isoformat(),
                "timeout": timeout_seconds,
                "delay": delay,
                "retry_count": 0
            }
            
            # Store job metadata
            status_key = f"{self.status_prefix}{job_id}"
            status_data = {
                "status": JobStatus.PENDING.value,
                "job_type": job_type.value,
                "priority": str(priority.value),
                "created_at": job_data["created_at"],
                "timeout": str(timeout_seconds),
                "retry_count": "0"
            }
            
            # Use Redis hash for status
            self.redis.hset(status_key, mapping={
                k.encode(): json.dumps(v).encode() if isinstance(v, (dict, list)) else str(v).encode()
                for k, v in status_data.items()
            })
            
            # Set expiration on status (7 days)
            self.redis.expire(status_key, 7 * 24 * 3600)
            
            # Add to priority queue (sorted set)
            # Score = priority * 1000000000 + timestamp (higher priority = lower score)
            score = priority.value * 1000000000 + time.time() + delay
            self.redis.zadd(
                self.priority_queue_key,
                {job_id.encode(): score}
            )
            
            # Also add to simple queue for compatibility
            queue_key = f"{self.queue_prefix}{job_type.value}"
            self.redis.lpush(queue_key, json.dumps(job_data).encode())
            
            logger.info(f"Job submitted: {job_id} (type={job_type.value}, priority={priority.value})")
            add_span_attribute("job.id", job_id)
            
            return job_id
    
    def get_next_job(self, job_type: Optional[JobType] = None) -> Optional[Dict[str, Any]]:
        """
        Get next job from queue (priority-based).
        
        Args:
            job_type: Optional job type filter
            
        Returns:
            Job data dictionary or None if no jobs available
        """
        with trace_span("job_queue.get_next_job"):
            # Get highest priority job (lowest score)
            jobs = self.redis.zrange(self.priority_queue_key, 0, 0, withscores=True)
            
            if not jobs:
                return None
            
            job_id_bytes, score = jobs[0]
            job_id = job_id_bytes.decode()
            
            # Check if job is ready (delay has passed)
            status_key = f"{self.status_prefix}{job_id}"
            status_data = self.redis.hgetall(status_key)
            
            if not status_data:
                # Status missing, remove from queue
                self.redis.zrem(self.priority_queue_key, job_id_bytes)
                return None
            
            # Decode status data
            status = {
                k.decode(): json.loads(v.decode()) if v.startswith(b'[') or v.startswith(b'{') else v.decode()
                for k, v in status_data.items()
            }
            
            # Check delay
            created_at_str = status.get("created_at", "")
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    delay_seconds = float(status.get("delay", "0"))
                    if time.time() < created_at.timestamp() + delay_seconds:
                        return None  # Not ready yet
                except (ValueError, TypeError):
                    pass
            
            # Check status
            if status.get("status") != JobStatus.PENDING.value:
                # Already processing or completed, remove from queue
                self.redis.zrem(self.priority_queue_key, job_id_bytes)
                return None
            
            # Get full job data from simple queue or reconstruct
            job_type_str = status.get("job_type", "")
            queue_key = f"{self.queue_prefix}{job_type_str}"
            
            # Try to pop from queue (may have been processed already)
            job_json = self.redis.rpop(queue_key)
            
            if job_json:
                job_data = json.loads(job_json.decode())
            else:
                # Reconstruct from status
                parameters_json = status.get("parameters", "{}")
                if isinstance(parameters_json, str):
                    try:
                        parameters = json.loads(parameters_json)
                    except json.JSONDecodeError:
                        parameters = {}
                else:
                    parameters = parameters_json
                
                job_data = {
                    "job_id": job_id,
                    "job_type": job_type_str,
                    "parameters": parameters,
                    "priority": int(status.get("priority", JobPriority.MEDIUM.value)),
                    "created_at": created_at_str,
                    "timeout": int(status.get("timeout", self.default_timeout)),
                    "retry_count": int(status.get("retry_count", "0"))
                }
            
            # Filter by job type if specified
            if job_type and job_data.get("job_type") != job_type.value:
                return None
            
            # Remove from priority queue (will be re-added if processing fails)
            self.redis.zrem(self.priority_queue_key, job_id_bytes)
            
            add_span_attribute("job.id", job_id)
            return job_data
    
    def start_job_processing(self, job_id: str) -> None:
        """Mark job as processing."""
        status_key = f"{self.status_prefix}{job_id}"
        self.redis.hset(status_key, "status", JobStatus.PROCESSING.value)
        self.redis.hset(status_key, "started_at", datetime.utcnow().isoformat())
        logger.debug(f"Job processing started: {job_id}")
    
    def complete_job(self, job_id: str, result: Dict[str, Any]) -> None:
        """
        Mark job as complete with result.
        
        Args:
            job_id: Job identifier
            result: Job result data
        """
        with trace_span("job_queue.complete_job", attributes={"job.id": job_id}):
            status_key = f"{self.status_prefix}{job_id}"
            result_key = f"{self.result_prefix}{job_id}"
            
            # Update status
            self.redis.hset(status_key, "status", JobStatus.COMPLETE.value)
            self.redis.hset(status_key, "completed_at", datetime.utcnow().isoformat())
            
            # Store result
            self.redis.setex(
                result_key,
                7 * 24 * 3600,  # 7 days
                json.dumps(result).encode()
            )
            
            logger.info(f"Job completed: {job_id}")
    
    def record_job_error(
        self,
        job_id: str,
        error: Exception,
        retry: bool = True
    ) -> None:
        """
        Record job error and handle retry logic.
        
        Args:
            job_id: Job identifier
            error: Exception that occurred
            retry: Whether to retry the job
        """
        with trace_span("job_queue.record_job_error", attributes={"job.id": job_id}):
            status_key = f"{self.status_prefix}{job_id}"
            
            # Get current retry count
            retry_count = int(self.redis.hget(status_key, "retry_count") or b"0")
            
            is_retryable = isinstance(error, RetryableJobError) or (
                isinstance(error, Exception) and retry
            )
            
            if is_retryable and retry_count < self.max_retries:
                # Retry the job
                retry_count += 1
                self.redis.hset(status_key, "retry_count", str(retry_count))
                self.redis.hset(status_key, "status", JobStatus.PENDING.value)
                self.redis.hset(status_key, "last_error", str(error))
                self.redis.hset(status_key, "last_error_at", datetime.utcnow().isoformat())
                
                # Re-add to priority queue with lower priority (higher score)
                status_data = self.redis.hgetall(status_key)
                priority = int(status_data.get(b"priority", str(JobPriority.LOW.value).encode()))
                
                # Lower priority for retries (add 1 to priority value = higher score)
                retry_priority = min(priority + 1, JobPriority.LOW.value)
                score = retry_priority * 1000000000 + time.time()
                self.redis.zadd(self.priority_queue_key, {job_id.encode(): score})
                
                logger.warning(f"Job error (will retry {retry_count}/{self.max_retries}): {job_id} - {error}")
            else:
                # Mark as failed
                self.redis.hset(status_key, "status", JobStatus.FAILED.value)
                self.redis.hset(status_key, "error", str(error))
                self.redis.hset(status_key, "failed_at", datetime.utcnow().isoformat())
                
                logger.error(f"Job failed permanently: {job_id} - {error}")
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job status and metadata.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Status dictionary or None if job not found
        """
        status_key = f"{self.status_prefix}{job_id}"
        status_data = self.redis.hgetall(status_key)
        
        if not status_data:
            return None
        
        # Decode status data
        status = {}
        for k, v in status_data.items():
            key = k.decode() if isinstance(k, bytes) else k
            if isinstance(v, bytes):
                value = v.decode()
                # Try to parse JSON if it looks like JSON
                if value.startswith('[') or value.startswith('{'):
                    try:
                        status[key] = json.loads(value)
                    except json.JSONDecodeError:
                        status[key] = value
                else:
                    status[key] = value
            else:
                status[key] = v
        
        # Get result if job is complete
        if status.get("status") == JobStatus.COMPLETE.value:
            result_key = f"{self.result_prefix}{job_id}"
            result_json = self.redis.get(result_key)
            if result_json:
                try:
                    status["result"] = json.loads(result_json.decode())
                except json.JSONDecodeError:
                    pass
        
        return status
    
    def check_job_timeout(self, job_id: str, timeout_seconds: Optional[int] = None) -> bool:
        """
        Check if job has timed out.
        
        Args:
            job_id: Job identifier
            timeout_seconds: Optional timeout override
            
        Returns:
            True if job has timed out
        """
        status = self.get_job_status(job_id)
        if not status or status.get("status") != JobStatus.PROCESSING.value:
            return False
        
        started_at_str = status.get("started_at")
        if not started_at_str:
            return False
        
        try:
            started_at = datetime.fromisoformat(started_at_str.replace('Z', '+00:00'))
            timeout = timeout_seconds or int(status.get("timeout", self.default_timeout))
            elapsed = (datetime.utcnow() - started_at.replace(tzinfo=None)).total_seconds()
            
            return elapsed > timeout
        except (ValueError, TypeError):
            return False
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a pending or processing job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if job was cancelled, False if not found or already complete
        """
        status = self.get_job_status(job_id)
        if not status:
            return False
        
        current_status = status.get("status")
        if current_status in (JobStatus.COMPLETE.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value):
            return False
        
        status_key = f"{self.status_prefix}{job_id}"
        self.redis.hset(status_key, "status", JobStatus.CANCELLED.value)
        self.redis.hset(status_key, "cancelled_at", datetime.utcnow().isoformat())
        
        # Remove from priority queue
        self.redis.zrem(self.priority_queue_key, job_id.encode())
        
        logger.info(f"Job cancelled: {job_id}")
        return True


class JobProcessor:
    """Base class for job processors."""
    
    def __init__(self, job_queue: JobQueue):
        self.job_queue = job_queue
    
    def process(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a job.
        
        Args:
            job_data: Job data dictionary
            
        Returns:
            Result dictionary
            
        Raises:
            JobError: If job processing fails
        """
        raise NotImplementedError("Subclasses must implement process()")


class BackupJobProcessor(JobProcessor):
    """Processor for backup jobs."""
    
    def __init__(self, job_queue: JobQueue, backup_manager=None):
        super().__init__(job_queue)
        if backup_manager is None:
            from backup import BackupManager
            db_path = os.getenv("TODO_DB_PATH", "/app/data/todos.db")
            backups_dir = os.getenv("TODO_BACKUPS_DIR", "/app/backups")
            self.backup_manager = BackupManager(db_path, backups_dir)
        else:
            self.backup_manager = backup_manager
    
    def process(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process backup job."""
        job_id = job_data["job_id"]
        parameters = job_data.get("parameters", {})
        project_id = parameters.get("project_id")
        
        try:
            backup_file = self.backup_manager.create_backup()
            logger.info(f"Backup job completed: {job_id} -> {backup_file}")
            return {
                "backup_file": backup_file,
                "project_id": project_id
            }
        except Exception as e:
            logger.error(f"Backup job failed: {job_id} - {e}", exc_info=True)
            raise RetryableJobError(f"Backup failed: {e}") from e


class WebhookJobProcessor(JobProcessor):
    """Processor for webhook delivery jobs."""
    
    def process(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process webhook delivery job."""
        import httpx
        
        job_id = job_data["job_id"]
        parameters = job_data.get("parameters", {})
        
        url = parameters.get("url")
        payload = parameters.get("payload", {})
        secret = parameters.get("secret")
        timeout = parameters.get("timeout_seconds", 10)
        retry_count = parameters.get("retry_count", 0)
        
        if not url:
            raise NonRetryableJobError("Webhook URL is required")
        
        # Add HMAC signature if secret provided
        headers = {"Content-Type": "application/json"}
        if secret:
            import hmac
            import hashlib
            payload_bytes = json.dumps(payload).encode()
            signature = hmac.new(
                secret.encode(),
                payload_bytes,
                hashlib.sha256
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"
        
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                
                logger.info(f"Webhook delivered: {job_id} -> {url} ({response.status_code})")
                return {
                    "status_code": response.status_code,
                    "url": url,
                    "delivered_at": datetime.utcnow().isoformat()
                }
        except httpx.HTTPStatusError as e:
            # 4xx errors are non-retryable, 5xx are retryable
            if 400 <= e.response.status_code < 500:
                raise NonRetryableJobError(f"Webhook delivery failed: {e.response.status_code}")
            else:
                raise RetryableJobError(f"Webhook delivery failed: {e.response.status_code}")
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            raise RetryableJobError(f"Webhook delivery network error: {e}")
        except Exception as e:
            logger.error(f"Webhook job failed: {job_id} - {e}", exc_info=True)
            raise RetryableJobError(f"Webhook delivery error: {e}") from e
