"""Template management operations."""

import json
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class TemplateManager:
    """Manages conversation template CRUD operations."""
    
    def __init__(self, adapter, normalize_sql_func):
        """
        Initialize template manager.
        
        Args:
            adapter: Database adapter instance
            normalize_sql_func: Function to normalize SQL queries
        """
        self.adapter = adapter
        self._normalize_sql = normalize_sql_func
    
    def _get_connection(self):
        """Get database connection using adapter."""
        return self.adapter.connect()
    
    def create_template(
        self,
        user_id: str,
        name: str,
        description: str = "",
        initial_messages: List[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Create a conversation template."""
        if initial_messages is None:
            initial_messages = []
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                INSERT INTO conversation_templates (user_id, name, description, initial_messages, metadata)
                VALUES (?, ?, ?, ?, ?)
            """)
            cursor.execute(query, (
                user_id,
                name,
                description,
                json.dumps(initial_messages),
                json.dumps(metadata) if metadata else None
            ))
            template_id = self.adapter.get_last_insert_id(cursor)
            conn.commit()
            logger.info(f"Created template {template_id} for user {user_id}")
            return template_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create template: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_template(self, template_id: int) -> Optional[Dict[str, Any]]:
        """Get a template by ID, including its quick replies."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                SELECT id, user_id, name, description, initial_messages, metadata,
                       created_at, updated_at
                FROM conversation_templates
                WHERE id = ?
            """)
            cursor.execute(query, (template_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            template = {
                'id': row[0],
                'user_id': row[1],
                'name': row[2],
                'description': row[3],
                'initial_messages': json.loads(row[4]) if row[4] else [],
                'metadata': json.loads(row[5]) if row[5] else {},
                'created_at': row[6],
                'updated_at': row[7]
            }
            
            # Get quick replies
            query = self._normalize_sql("""
                SELECT id, label, action, order_index, created_at
                FROM quick_replies
                WHERE template_id = ?
                ORDER BY order_index ASC, id ASC
            """)
            cursor.execute(query, (template_id,))
            quick_replies = []
            for reply_row in cursor.fetchall():
                quick_replies.append({
                    'id': reply_row[0],
                    'label': reply_row[1],
                    'action': reply_row[2],
                    'order_index': reply_row[3],
                    'created_at': reply_row[4]
                })
            
            template['quick_replies'] = quick_replies
            return template
        finally:
            self.adapter.close(conn)
    
    def list_templates(self, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """List conversation templates, optionally filtered by user."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            if user_id:
                query = self._normalize_sql("""
                    SELECT id, user_id, name, description, initial_messages, metadata,
                           created_at, updated_at
                    FROM conversation_templates
                    WHERE user_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                """)
                cursor.execute(query, (user_id, limit))
            else:
                query = self._normalize_sql("""
                    SELECT id, user_id, name, description, initial_messages, metadata,
                           created_at, updated_at
                    FROM conversation_templates
                    ORDER BY updated_at DESC
                    LIMIT ?
                """)
                cursor.execute(query, (limit,))
            
            templates = []
            for row in cursor.fetchall():
                templates.append({
                    'id': row[0],
                    'user_id': row[1],
                    'name': row[2],
                    'description': row[3],
                    'initial_messages': json.loads(row[4]) if row[4] else [],
                    'metadata': json.loads(row[5]) if row[5] else {},
                    'created_at': row[6],
                    'updated_at': row[7]
                })
            
            return templates
        finally:
            self.adapter.close(conn)
    
    def update_template(
        self,
        template_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        initial_messages: Optional[List[Dict[str, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update a conversation template."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if initial_messages is not None:
                updates.append("initial_messages = ?")
                params.append(json.dumps(initial_messages))
            if metadata is not None:
                updates.append("metadata = ?")
                params.append(json.dumps(metadata))
            
            if not updates:
                return False
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(template_id)
            
            query = self._normalize_sql(f"""
                UPDATE conversation_templates
                SET {', '.join(updates)}
                WHERE id = ?
            """)
            cursor.execute(query, tuple(params))
            
            updated = cursor.rowcount > 0
            conn.commit()
            
            if updated:
                logger.info(f"Updated template {template_id}")
            return updated
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update template: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def delete_template(self, template_id: int) -> bool:
        """Delete a conversation template (and its quick replies via CASCADE)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                DELETE FROM conversation_templates
                WHERE id = ?
            """)
            cursor.execute(query, (template_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            if deleted:
                logger.info(f"Deleted template {template_id}")
            return deleted
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete template: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def add_quick_reply(
        self,
        template_id: int,
        label: str,
        action: str,
        order_index: int = 0
    ) -> int:
        """Add a quick reply button to a template."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                INSERT INTO quick_replies (template_id, label, action, order_index)
                VALUES (?, ?, ?, ?)
            """)
            cursor.execute(query, (template_id, label, action, order_index))
            reply_id = self.adapter.get_last_insert_id(cursor)
            conn.commit()
            logger.debug(f"Added quick reply {reply_id} to template {template_id}")
            return reply_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to add quick reply: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def update_quick_reply(
        self,
        reply_id: int,
        label: Optional[str] = None,
        action: Optional[str] = None,
        order_index: Optional[int] = None
    ) -> bool:
        """Update a quick reply."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if label is not None:
                updates.append("label = ?")
                params.append(label)
            if action is not None:
                updates.append("action = ?")
                params.append(action)
            if order_index is not None:
                updates.append("order_index = ?")
                params.append(order_index)
            
            if not updates:
                return False
            
            params.append(reply_id)
            
            query = self._normalize_sql(f"""
                UPDATE quick_replies
                SET {', '.join(updates)}
                WHERE id = ?
            """)
            cursor.execute(query, tuple(params))
            updated = cursor.rowcount > 0
            conn.commit()
            return updated
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update quick reply: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def delete_quick_reply(self, reply_id: int) -> bool:
        """Delete a quick reply."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                DELETE FROM quick_replies
                WHERE id = ?
            """)
            cursor.execute(query, (reply_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete quick reply: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def apply_template(
        self,
        user_id: str,
        chat_id: str,
        template_id: int,
        get_template_func: callable,
        get_conversation_func: callable,
        reset_conversation_func: callable,
        get_or_create_conversation_func: callable,
        add_message_func: callable
    ) -> int:
        """
        Apply a template to start a conversation.
        Creates or resets the conversation and adds initial messages from template.
        """
        template = get_template_func(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found")
        
        # Get or create conversation (reset if exists to apply template fresh)
        existing = get_conversation_func(user_id, chat_id)
        if existing:
            reset_conversation_func(user_id, chat_id)
        
        conversation_id = get_or_create_conversation_func(user_id, chat_id)
        
        # Add initial messages from template
        for msg in template['initial_messages']:
            role = msg.get('role', 'assistant')
            content = msg.get('content', '')
            tokens = msg.get('tokens')
            add_message_func(conversation_id, role, content, tokens=tokens)
        
        logger.info(f"Applied template {template_id} to conversation {conversation_id}")
        return conversation_id
