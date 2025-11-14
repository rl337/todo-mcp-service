"""Prompt template management operations."""

import json
import logging
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class PromptTemplateManager:
    """Manages prompt template CRUD operations."""
    
    def __init__(self, adapter, normalize_sql_func):
        self.adapter = adapter
        self._normalize_sql = normalize_sql_func
    
    def _get_connection(self):
        return self.adapter.connect()
    
    def validate_prompt_template(self, template_content: str) -> Tuple[bool, Optional[str]]:
        """Validate prompt template syntax."""
        try:
            brace_count = 0
            in_brace = False
            i = 0
            
            while i < len(template_content):
                if template_content[i] == '{':
                    if in_brace:
                        return False, "Nested braces are not allowed"
                    in_brace = True
                    brace_count += 1
                elif template_content[i] == '}':
                    if not in_brace:
                        return False, "Unmatched closing brace"
                    in_brace = False
                    if i > 0 and template_content[i-1] == '{':
                        return False, "Empty variable name not allowed"
                i += 1
            
            if in_brace:
                return False, "Unclosed brace in template"
            
            return True, None
        except Exception as e:
            return False, f"Template validation error: {str(e)}"
    
    def create_prompt_template(
        self,
        user_id: str,
        template_name: str,
        template_content: str,
        template_type: str = "summarization",
        conversation_id: Optional[int] = None,
        validate_func: Optional[callable] = None,
        get_conversation_func: Optional[callable] = None
    ) -> int:
        """Create a new prompt template."""
        # Validate template syntax
        if validate_func:
            is_valid, error = validate_func(template_content)
        else:
            is_valid, error = self.validate_prompt_template(template_content)
        if not is_valid:
            raise ValueError(f"Invalid template syntax: {error}")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # If conversation_id is provided, verify it exists and belongs to user
            if conversation_id and get_conversation_func:
                # Would need to check conversation exists - simplified for now
                pass
            
            query = self._normalize_sql("""
                INSERT INTO prompt_templates 
                (user_id, conversation_id, template_name, template_content, template_type)
                VALUES (?, ?, ?, ?, ?)
            """)
            cursor.execute(query, (user_id, conversation_id, template_name, template_content, template_type))
            template_id = self.adapter.get_last_insert_id(cursor)
            conn.commit()
            
            logger.info(f"Created prompt template {template_id} for user {user_id}")
            return template_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create prompt template: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_prompt_template(self, template_id: int) -> Optional[Dict[str, Any]]:
        """Get a prompt template by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                SELECT id, user_id, conversation_id, template_name, template_content, 
                       template_type, created_at, updated_at
                FROM prompt_templates 
                WHERE id = ?
            """)
            cursor.execute(query, (template_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': row[0],
                    'user_id': row[1],
                    'conversation_id': row[2],
                    'template_name': row[3],
                    'template_content': row[4],
                    'template_type': row[5],
                    'created_at': row[6],
                    'updated_at': row[7]
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get prompt template: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_prompt_template_for_user(
        self,
        user_id: str,
        template_type: str = "summarization"
    ) -> Optional[Dict[str, Any]]:
        """Get prompt template for a user (per-user templates, not conversation-specific)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                SELECT id, user_id, conversation_id, template_name, template_content, 
                       template_type, created_at, updated_at
                FROM prompt_templates 
                WHERE user_id = ? AND template_type = ? AND conversation_id IS NULL
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            cursor.execute(query, (user_id, template_type))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': row[0],
                    'user_id': row[1],
                    'conversation_id': row[2],
                    'template_name': row[3],
                    'template_content': row[4],
                    'template_type': row[5],
                    'created_at': row[6],
                    'updated_at': row[7]
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get prompt template for user: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_prompt_template_for_conversation(
        self,
        user_id: str,
        chat_id: str,
        template_type: str = "summarization",
        get_conversation_func: Optional[callable] = None
    ) -> Optional[Dict[str, Any]]:
        """Get prompt template for a conversation. Prefers conversation-specific, falls back to user."""
        # First try to get conversation-specific template
        if get_conversation_func:
            conversation = get_conversation_func(user_id, chat_id)
            if conversation:
                conv_id = conversation['id']
                conn = self._get_connection()
                try:
                    cursor = conn.cursor()
                    query = self._normalize_sql("""
                        SELECT id, user_id, conversation_id, template_name, template_content, 
                               template_type, created_at, updated_at
                        FROM prompt_templates 
                        WHERE conversation_id = ? AND template_type = ?
                        ORDER BY updated_at DESC
                        LIMIT 1
                    """)
                    cursor.execute(query, (conv_id, template_type))
                    row = cursor.fetchone()
                    
                    if row:
                        return {
                            'id': row[0],
                            'user_id': row[1],
                            'conversation_id': row[2],
                            'template_name': row[3],
                            'template_content': row[4],
                            'template_type': row[5],
                            'created_at': row[6],
                            'updated_at': row[7]
                        }
                except Exception as e:
                    logger.error(f"Failed to get conversation prompt template: {e}", exc_info=True)
                finally:
                    self.adapter.close(conn)
        
        # Fall back to user template
        return self.get_prompt_template_for_user(user_id, template_type)
    
    def list_prompt_templates(
        self,
        user_id: Optional[str] = None,
        template_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List prompt templates."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            conditions = []
            params = []
            
            if user_id:
                conditions.append("user_id = ?")
                params.append(user_id)
            
            if template_type:
                conditions.append("template_type = ?")
                params.append(template_type)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            query = self._normalize_sql(f"""
                SELECT id, user_id, conversation_id, template_name, template_content, 
                       template_type, created_at, updated_at
                FROM prompt_templates 
                WHERE {where_clause}
                ORDER BY updated_at DESC
            """)
            cursor.execute(query, params)
            
            templates = []
            for row in cursor.fetchall():
                templates.append({
                    'id': row[0],
                    'user_id': row[1],
                    'conversation_id': row[2],
                    'template_name': row[3],
                    'template_content': row[4],
                    'template_type': row[5],
                    'created_at': row[6],
                    'updated_at': row[7]
                })
            
            return templates
        except Exception as e:
            logger.error(f"Failed to list prompt templates: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def update_prompt_template(
        self,
        template_id: int,
        template_name: Optional[str] = None,
        template_content: Optional[str] = None,
        validate_func: Optional[callable] = None
    ) -> bool:
        """Update a prompt template."""
        # Validate template content if provided
        if template_content:
            if validate_func:
                is_valid, error = validate_func(template_content)
            else:
                is_valid, error = self.validate_prompt_template(template_content)
            if not is_valid:
                raise ValueError(f"Invalid template syntax: {error}")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if template_name:
                updates.append("template_name = ?")
                params.append(template_name)
            
            if template_content:
                updates.append("template_content = ?")
                params.append(template_content)
            
            if not updates:
                return False
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(template_id)
            
            query = self._normalize_sql(f"""
                UPDATE prompt_templates 
                SET {', '.join(updates)}
                WHERE id = ?
            """)
            cursor.execute(query, params)
            conn.commit()
            
            updated = cursor.rowcount > 0
            if updated:
                logger.info(f"Updated prompt template {template_id}")
            return updated
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update prompt template: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def delete_prompt_template(self, template_id: int) -> bool:
        """Delete a prompt template."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                DELETE FROM prompt_templates 
                WHERE id = ?
            """)
            cursor.execute(query, (template_id,))
            conn.commit()
            
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted prompt template {template_id}")
            return deleted
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete prompt template: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
