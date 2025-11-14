"""Message management operations."""

import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class MessageManager:
    """Manages message storage and retrieval."""
    
    def __init__(self, adapter, normalize_sql_func):
        self.adapter = adapter
        self._normalize_sql = normalize_sql_func
    
    def _get_connection(self):
        return self.adapter.connect()
    
    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        tokens: Optional[int] = None
    ) -> int:
        """Add a message to a conversation."""
        if role not in ['user', 'assistant', 'system']:
            raise ValueError(f"Invalid role: {role}")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                INSERT INTO conversation_messages (conversation_id, role, content, tokens)
                VALUES (?, ?, ?, ?)
            """)
            cursor.execute(query, (conversation_id, role, content, tokens))
            message_id = self.adapter.get_last_insert_id(cursor)
            
            query = self._normalize_sql("""
                UPDATE conversations 
                SET message_count = message_count + 1,
                    total_tokens = COALESCE(total_tokens, 0) + COALESCE(?, 0),
                    last_message_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """)
            cursor.execute(query, (tokens or 0, conversation_id))
            
            conn.commit()
            logger.debug(f"Added message {message_id} to conversation {conversation_id}")
            return message_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to add message: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_all_messages(self, conversation_id: int) -> List[Dict[str, Any]]:
        """Get all messages for a conversation."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                SELECT id, role, content, tokens, created_at
                FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
            """)
            cursor.execute(query, (conversation_id,))
            messages = []
            for msg_row in cursor.fetchall():
                messages.append({
                    'id': msg_row[0],
                    'role': msg_row[1],
                    'content': msg_row[2],
                    'tokens': msg_row[3],
                    'created_at': msg_row[4]
                })
            return messages
        finally:
            self.adapter.close(conn)
