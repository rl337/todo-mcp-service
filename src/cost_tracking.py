"""
Cost tracking for STT, TTS, and LLM usage.

Tracks costs per user and conversation, calculates costs in real-time,
and generates billing reports.
"""
import os
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum

from db_adapter import get_database_adapter

logger = logging.getLogger(__name__)


class ServiceType(Enum):
    """Service type enumeration for cost tracking."""
    STT = "stt"  # Speech-to-text
    TTS = "tts"  # Text-to-speech
    LLM = "llm"  # Large language model


class CostTracker:
    """Track costs for STT, TTS, and LLM usage."""
    
    # Pricing configuration (per provider/model)
    # These can be overridden via environment variables or config
    PRICING = {
        "llm": {
            "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},  # per 1K tokens
            "gpt-4": {"input": 0.03, "output": 0.06},  # per 1K tokens
            "gpt-4-turbo": {"input": 0.01, "output": 0.03},  # per 1K tokens
            "claude-3-opus": {"input": 0.015, "output": 0.075},  # per 1K tokens
            "claude-3-sonnet": {"input": 0.003, "output": 0.015},  # per 1K tokens
            "default": {"input": 0.002, "output": 0.002},  # fallback
        },
        "stt": {
            "google": 0.006,  # per minute
            "openai": 0.006,  # per minute
            "whisper": 0.006,  # per minute
            "default": 0.006,  # fallback
        },
        "tts": {
            "openai": 0.015,  # per 1000 characters
            "google": 0.016,  # per 1000 characters
            "elevenlabs": 0.018,  # per 1000 characters
            "default": 0.015,  # fallback
        }
    }
    
    def __init__(self, db_path: str = None):
        """
        Initialize cost tracker.
        
        Args:
            db_path: Database connection string. If None, uses environment variables.
        """
        # Use same database as conversation storage
        db_type = os.getenv("DB_TYPE", "postgresql").lower()
        
        if db_path is None:
            if db_type == "postgresql":
                db_host = os.getenv("DB_HOST", "localhost")
                db_port = os.getenv("DB_PORT", "5432")
                db_name = os.getenv("DB_NAME", "conversations")
                db_user = os.getenv("DB_USER", "postgres")
                db_password = os.getenv("DB_PASSWORD", "")
                
                if db_password:
                    self.db_path = f"host={db_host} port={db_port} dbname={db_name} user={db_user} password={db_password}"
                else:
                    self.db_path = f"host={db_host} port={db_port} dbname={db_name} user={db_user}"
            else:
                # SQLite fallback (shouldn't be used in production)
                self.db_path = os.getenv("COST_DB_PATH", "/app/data/costs.db")
        else:
            self.db_path = db_path
        
        self.db_type = db_type
        self.adapter = get_database_adapter(self.db_path)
        self._init_schema()
    
    def _get_connection(self):
        """Get database connection using adapter."""
        return self.adapter.connect()
    
    def _normalize_sql(self, query: str) -> str:
        """Normalize SQL query for the current database backend."""
        return self.adapter.normalize_query(query)
    
    def _init_schema(self):
        """Initialize cost tracking schema."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Cost entries table
            query = self._normalize_sql("""
                CREATE TABLE IF NOT EXISTS cost_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_type TEXT NOT NULL CHECK(service_type IN ('stt', 'tts', 'llm')),
                    user_id TEXT NOT NULL,
                    conversation_id INTEGER,
                    cost REAL NOT NULL,
                    tokens INTEGER,
                    duration_seconds REAL,
                    metadata TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
                )
            """)
            cursor.execute(query)
            
            # Create indexes for efficient queries
            cursor.execute(self._normalize_sql(
                "CREATE INDEX IF NOT EXISTS idx_cost_entries_user "
                "ON cost_entries(user_id, created_at)"
            ))
            cursor.execute(self._normalize_sql(
                "CREATE INDEX IF NOT EXISTS idx_cost_entries_conversation "
                "ON cost_entries(conversation_id, created_at)"
            ))
            cursor.execute(self._normalize_sql(
                "CREATE INDEX IF NOT EXISTS idx_cost_entries_service_type "
                "ON cost_entries(service_type, created_at)"
            ))
            
            conn.commit()
            logger.info("Cost tracking schema initialized")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to initialize cost tracking schema: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def record_cost(
        self,
        service_type: ServiceType,
        user_id: str,
        conversation_id: Optional[int] = None,
        cost: float = None,
        tokens: Optional[int] = None,
        duration_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Record a cost entry.
        
        Args:
            service_type: Type of service (STT, TTS, LLM)
            user_id: User identifier
            conversation_id: Optional conversation ID
            cost: Cost in USD (if None, will be calculated)
            tokens: Optional token count (for LLM/TTS)
            duration_seconds: Optional duration in seconds (for STT)
            metadata: Optional metadata dictionary
            
        Returns:
            Cost entry ID
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Calculate cost if not provided
            if cost is None:
                if service_type == ServiceType.LLM and tokens:
                    # Would need model info from metadata to calculate
                    cost = 0.002  # Default fallback
                elif service_type == ServiceType.STT and duration_seconds:
                    cost = self.calculate_stt_cost(
                        provider=metadata.get("model", "default") if metadata else "default",
                        duration_seconds=duration_seconds
                    )
                elif service_type == ServiceType.TTS and tokens:  # tokens = characters for TTS
                    cost = self.calculate_tts_cost(
                        provider=metadata.get("model", "default") if metadata else "default",
                        characters=tokens
                    )
                else:
                    cost = 0.0
            
            # Serialize metadata
            metadata_json = json.dumps(metadata) if metadata else None
            
            query = self._normalize_sql("""
                INSERT INTO cost_entries (
                    service_type, user_id, conversation_id, cost,
                    tokens, duration_seconds, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """)
            
            cursor.execute(query, (
                service_type.value,
                user_id,
                conversation_id,
                cost,
                tokens,
                duration_seconds,
                metadata_json
            ))
            
            cost_entry_id = self.adapter.get_last_insert_id(cursor)
            conn.commit()
            
            logger.debug(
                f"Recorded cost entry {cost_entry_id}: {service_type.value} "
                f"for user {user_id}, cost=${cost:.6f}"
            )
            
            return cost_entry_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to record cost: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_costs_for_user(
        self,
        user_id: str,
        service_type: Optional[ServiceType] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        Get cost entries for a user.
        
        Args:
            user_id: User identifier
            service_type: Optional service type filter
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            List of cost entry dictionaries
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            query = "SELECT * FROM cost_entries WHERE user_id = ?"
            params = [user_id]
            
            if service_type:
                query += " AND service_type = ?"
                params.append(service_type.value)
            
            if start_date:
                query += " AND created_at >= ?"
                params.append(start_date.isoformat())
            
            if end_date:
                query += " AND created_at <= ?"
                params.append(end_date.isoformat())
            
            query += " ORDER BY created_at DESC"
            
            cursor.execute(self._normalize_sql(query), tuple(params))
            
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            results = []
            for row in rows:
                entry = dict(zip(columns, row))
                # Parse metadata JSON
                if entry.get('metadata'):
                    try:
                        entry['metadata'] = json.loads(entry['metadata'])
                    except (json.JSONDecodeError, TypeError):
                        entry['metadata'] = {}
                results.append(entry)
            
            return results
        except Exception as e:
            logger.error(f"Failed to get costs for user: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_costs_for_conversation(
        self,
        conversation_id: int,
        service_type: Optional[ServiceType] = None
    ) -> List[Dict[str, Any]]:
        """
        Get cost entries for a conversation.
        
        Args:
            conversation_id: Conversation ID
            service_type: Optional service type filter
            
        Returns:
            List of cost entry dictionaries
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            query = "SELECT * FROM cost_entries WHERE conversation_id = ?"
            params = [conversation_id]
            
            if service_type:
                query += " AND service_type = ?"
                params.append(service_type.value)
            
            query += " ORDER BY created_at DESC"
            
            cursor.execute(self._normalize_sql(query), tuple(params))
            
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            results = []
            for row in rows:
                entry = dict(zip(columns, row))
                if entry.get('metadata'):
                    try:
                        entry['metadata'] = json.loads(entry['metadata'])
                    except (json.JSONDecodeError, TypeError):
                        entry['metadata'] = {}
                results.append(entry)
            
            return results
        except Exception as e:
            logger.error(f"Failed to get costs for conversation: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_total_cost_for_user(
        self,
        user_id: str,
        service_type: Optional[ServiceType] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> float:
        """
        Get total cost for a user.
        
        Args:
            user_id: User identifier
            service_type: Optional service type filter
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Total cost in USD
        """
        costs = self.get_costs_for_user(user_id, service_type, start_date, end_date)
        return sum(c['cost'] for c in costs)
    
    def get_costs_by_date_range(
        self,
        user_id: str,
        start_date: date,
        end_date: date,
        service_type: Optional[ServiceType] = None
    ) -> List[Dict[str, Any]]:
        """
        Get costs by date range.
        
        Args:
            user_id: User identifier
            start_date: Start date
            end_date: End date
            service_type: Optional service type filter
            
        Returns:
            List of cost entry dictionaries
        """
        return self.get_costs_for_user(user_id, service_type, start_date, end_date)
    
    def generate_billing_report(
        self,
        user_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Generate billing report for a user.
        
        Args:
            user_id: User identifier
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            Billing report dictionary
        """
        costs = self.get_costs_for_user(user_id, start_date=start_date, end_date=end_date)
        
        total_cost = sum(c['cost'] for c in costs)
        
        # Breakdown by service type
        service_breakdown = {}
        for cost in costs:
            service = cost['service_type']
            if service not in service_breakdown:
                service_breakdown[service] = {
                    'count': 0,
                    'total_cost': 0.0,
                    'total_tokens': 0,
                    'total_duration': 0.0
                }
            
            service_breakdown[service]['count'] += 1
            service_breakdown[service]['total_cost'] += cost['cost']
            if cost.get('tokens'):
                service_breakdown[service]['total_tokens'] += cost['tokens']
            if cost.get('duration_seconds'):
                service_breakdown[service]['total_duration'] += cost['duration_seconds']
        
        return {
            'user_id': user_id,
            'start_date': start_date.isoformat() if start_date else None,
            'end_date': end_date.isoformat() if end_date else None,
            'total_cost': total_cost,
            'total_entries': len(costs),
            'service_breakdown': service_breakdown,
            'generated_at': datetime.now().isoformat()
        }
    
    def calculate_llm_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """
        Calculate LLM cost from token usage.
        
        Args:
            model: Model name (e.g., 'gpt-3.5-turbo')
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            
        Returns:
            Cost in USD
        """
        pricing = self.PRICING["llm"].get(model, self.PRICING["llm"]["default"])
        
        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (output_tokens / 1000) * pricing["output"]
        
        return input_cost + output_cost
    
    def calculate_stt_cost(
        self,
        provider: str,
        duration_seconds: float
    ) -> float:
        """
        Calculate STT cost from duration.
        
        Args:
            provider: Provider name (e.g., 'google')
            duration_seconds: Duration in seconds
            
        Returns:
            Cost in USD
        """
        price_per_minute = self.PRICING["stt"].get(provider, self.PRICING["stt"]["default"])
        minutes = duration_seconds / 60.0
        return minutes * price_per_minute
    
    def calculate_tts_cost(
        self,
        provider: str,
        characters: int
    ) -> float:
        """
        Calculate TTS cost from character count.
        
        Args:
            provider: Provider name (e.g., 'openai')
            characters: Number of characters
            
        Returns:
            Cost in USD
        """
        price_per_1k = self.PRICING["tts"].get(provider, self.PRICING["tts"]["default"])
        return (characters / 1000.0) * price_per_1k