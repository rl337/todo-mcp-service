"""Conversation sharing management operations."""

import json
import secrets
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class SharingManager:
    """Manages conversation sharing operations."""
    
    def __init__(self, adapter, normalize_sql_func):
        self.adapter = adapter
        self._normalize_sql = normalize_sql_func
    
    def _get_connection(self):
        return self.adapter.connect()
    
    def create_share(
        self,
        user_id: str,
        chat_id: str,
        shared_with_user_id: Optional[str] = None,
        permission: str = "read_only",
        share_token: Optional[str] = None,
        get_or_create_conversation_func: callable = None
    ) -> int:
        """Create a share for a conversation."""
        if permission not in ('read_only', 'editable'):
            raise ValueError("Permission must be 'read_only' or 'editable'")
        
        # Get conversation ID
        if get_or_create_conversation_func:
            conversation_id = get_or_create_conversation_func(user_id, chat_id)
        else:
            raise ValueError("get_or_create_conversation_func is required")
        
        if not conversation_id:
            raise ValueError(f"Conversation not found for user {user_id}, chat {chat_id}")
        
        # Generate token if not provided
        if not share_token:
            share_token = secrets.token_urlsafe(32)
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Check if token already exists
            query = self._normalize_sql(
                "SELECT id FROM conversation_shares WHERE share_token = ?"
            )
            cursor.execute(query, (share_token,))
            if cursor.fetchone():
                raise ValueError("Share token already exists")
            
            # Insert share
            query = self._normalize_sql("""
                INSERT INTO conversation_shares (
                    conversation_id, owner_user_id, shared_with_user_id,
                    share_token, permission
                )
                VALUES (?, ?, ?, ?, ?)
            """)
            cursor.execute(query, (
                conversation_id,
                user_id,
                shared_with_user_id,
                share_token,
                permission
            ))
            share_id = self.adapter.get_last_insert_id(cursor)
            conn.commit()
            logger.info(f"Created share {share_id} for conversation {conversation_id}")
            return share_id
        except ValueError:
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create share: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_share(self, share_id: int) -> Optional[Dict[str, Any]]:
        """Get a share by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                SELECT id, conversation_id, owner_user_id, shared_with_user_id,
                       share_token, permission, created_at
                FROM conversation_shares
                WHERE id = ?
            """)
            cursor.execute(query, (share_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return {
                'id': row[0],
                'conversation_id': row[1],
                'owner_user_id': row[2],
                'shared_with_user_id': row[3],
                'share_token': row[4],
                'permission': row[5],
                'created_at': row[6]
            }
        except Exception as e:
            logger.error(f"Failed to get share: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_share_by_token(self, share_token: str) -> Optional[Dict[str, Any]]:
        """Get a share by its token."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                SELECT id, conversation_id, owner_user_id, shared_with_user_id,
                       share_token, permission, created_at
                FROM conversation_shares
                WHERE share_token = ?
            """)
            cursor.execute(query, (share_token,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return {
                'id': row[0],
                'conversation_id': row[1],
                'owner_user_id': row[2],
                'shared_with_user_id': row[3],
                'share_token': row[4],
                'permission': row[5],
                'created_at': row[6]
            }
        except Exception as e:
            logger.error(f"Failed to get share by token: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def list_shares_for_conversation(
        self,
        user_id: str,
        chat_id: str,
        get_or_create_conversation_func: callable = None
    ) -> List[Dict[str, Any]]:
        """List all shares for a conversation."""
        if get_or_create_conversation_func:
            conversation_id = get_or_create_conversation_func(user_id, chat_id)
        else:
            return []
        
        if not conversation_id:
            return []
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                SELECT id, conversation_id, owner_user_id, shared_with_user_id,
                       share_token, permission, created_at
                FROM conversation_shares
                WHERE conversation_id = ?
                ORDER BY created_at DESC
            """)
            cursor.execute(query, (conversation_id,))
            
            shares = []
            for row in cursor.fetchall():
                shares.append({
                    'id': row[0],
                    'conversation_id': row[1],
                    'owner_user_id': row[2],
                    'shared_with_user_id': row[3],
                    'share_token': row[4],
                    'permission': row[5],
                    'created_at': row[6]
                })
            return shares
        except Exception as e:
            logger.error(f"Failed to list shares: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def list_shares_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """List all shares where a user is the recipient."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                SELECT id, conversation_id, owner_user_id, shared_with_user_id,
                       share_token, permission, created_at
                FROM conversation_shares
                WHERE shared_with_user_id = ?
                ORDER BY created_at DESC
            """)
            cursor.execute(query, (user_id,))
            
            shares = []
            for row in cursor.fetchall():
                shares.append({
                    'id': row[0],
                    'conversation_id': row[1],
                    'owner_user_id': row[2],
                    'shared_with_user_id': row[3],
                    'share_token': row[4],
                    'permission': row[5],
                    'created_at': row[6]
                })
            return shares
        except Exception as e:
            logger.error(f"Failed to list shares for user: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def delete_share(self, share_id: int) -> bool:
        """Delete a share."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql(
                "DELETE FROM conversation_shares WHERE id = ?"
            )
            cursor.execute(query, (share_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted share {share_id}")
            return deleted
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete share: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def check_conversation_access(
        self,
        user_id: str,
        chat_id: str,
        accessed_by_user_id: str,
        get_or_create_conversation_func: callable = None
    ) -> Dict[str, Any]:
        """Check if a user has access to a conversation and what permissions."""
        # Owner has full access
        if accessed_by_user_id == user_id:
            return {
                'has_access': True,
                'can_read': True,
                'can_write': True,
                'permission': 'owner'
            }
        
        # Check for shares
        if get_or_create_conversation_func:
            conversation_id = get_or_create_conversation_func(user_id, chat_id)
        else:
            return {
                'has_access': False,
                'can_read': False,
                'can_write': False,
                'permission': None
            }
        
        if not conversation_id:
            return {
                'has_access': False,
                'can_read': False,
                'can_write': False,
                'permission': None
            }
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                SELECT permission
                FROM conversation_shares
                WHERE conversation_id = ? AND shared_with_user_id = ?
            """)
            cursor.execute(query, (conversation_id, accessed_by_user_id))
            row = cursor.fetchone()
            
            if not row:
                return {
                    'has_access': False,
                    'can_read': False,
                    'can_write': False,
                    'permission': None
                }
            
            permission = row[0]
            return {
                'has_access': True,
                'can_read': True,
                'can_write': permission == 'editable',
                'permission': permission
            }
        except Exception as e:
            logger.error(f"Failed to check access: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_conversation_by_share_token(
        self,
        share_token: str,
        limit: Optional[int] = None,
        max_tokens: Optional[int] = None,
        get_share_by_token_func: callable = None
    ) -> Optional[Dict[str, Any]]:
        """Get a conversation using a share token."""
        if get_share_by_token_func:
            share = get_share_by_token_func(share_token)
        else:
            share = self.get_share_by_token(share_token)
        
        if not share:
            return None
        
        # Get conversation via conversation_id
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                SELECT id, user_id, chat_id, created_at, updated_at,
                       last_message_at, message_count, total_tokens, metadata
                FROM conversations
                WHERE id = ?
            """)
            cursor.execute(query, (share['conversation_id'],))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            conversation = {
                'id': row[0],
                'user_id': row[1],
                'chat_id': row[2],
                'created_at': row[3],
                'updated_at': row[4],
                'last_message_at': row[5],
                'message_count': row[6],
                'total_tokens': row[7],
                'metadata': json.loads(row[8]) if row[8] else {}
            }
            
            # Get messages
            query = self._normalize_sql("""
                SELECT id, role, content, tokens, created_at
                FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
            """)
            
            if max_tokens:
                cursor.execute(query, (share['conversation_id'],))
                all_messages = []
                total_tokens = 0
                
                for msg_row in cursor.fetchall():
                    all_messages.append({
                        'id': msg_row[0],
                        'role': msg_row[1],
                        'content': msg_row[2],
                        'tokens': msg_row[3],
                        'created_at': msg_row[4]
                    })
                    total_tokens += msg_row[3] or 0
                
                # Prune oldest messages if over token limit
                while total_tokens > max_tokens and len(all_messages) > 5:
                    removed = all_messages.pop(0)
                    total_tokens -= removed['tokens'] or 0
                
                conversation['messages'] = all_messages
            elif limit:
                query += f" LIMIT {limit}"
                cursor.execute(query, (share['conversation_id'],))
                conversation['messages'] = [
                    {
                        'id': row[0],
                        'role': row[1],
                        'content': row[2],
                        'tokens': row[3],
                        'created_at': row[4]
                    }
                    for row in cursor.fetchall()
                ]
            else:
                cursor.execute(query, (share['conversation_id'],))
                conversation['messages'] = [
                    {
                        'id': row[0],
                        'role': row[1],
                        'content': row[2],
                        'tokens': row[3],
                        'created_at': row[4]
                    }
                    for row in cursor.fetchall()
                ]
            
            return conversation
        except Exception as e:
            logger.error(f"Failed to get conversation by share token: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
