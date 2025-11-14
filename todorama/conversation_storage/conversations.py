"""Conversation management operations."""

import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversation CRUD operations."""
    
    def __init__(self, adapter, normalize_sql_func):
        """
        Initialize conversation manager.
        
        Args:
            adapter: Database adapter instance
            normalize_sql_func: Function to normalize SQL queries
        """
        self.adapter = adapter
        self._normalize_sql = normalize_sql_func
    
    def _get_connection(self):
        """Get database connection using adapter."""
        return self.adapter.connect()
    
    def get_or_create_conversation(self, user_id: str, chat_id: str) -> int:
        """
        Get existing conversation or create a new one.
        
        Args:
            user_id: User identifier
            chat_id: Chat/conversation identifier
            
        Returns:
            Conversation ID
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Try to get existing conversation
            query = self._normalize_sql("""
                SELECT id FROM conversations 
                WHERE user_id = ? AND chat_id = ?
            """)
            cursor.execute(query, (user_id, chat_id))
            row = cursor.fetchone()
            
            if row:
                conversation_id = row[0]
                logger.debug(f"Found existing conversation {conversation_id} for user {user_id}, chat {chat_id}")
                return conversation_id
            
            # Create new conversation
            query = self._normalize_sql("""
                INSERT INTO conversations (user_id, chat_id, last_message_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """)
            cursor.execute(query, (user_id, chat_id))
            conversation_id = self.adapter.get_last_insert_id(cursor)
            conn.commit()
            logger.info(f"Created new conversation {conversation_id} for user {user_id}, chat {chat_id}")
            return conversation_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to get/create conversation: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def get_conversation(
        self,
        user_id: str,
        chat_id: str,
        limit: Optional[int] = None,
        max_tokens: Optional[int] = None,
        accessed_by_user_id: Optional[str] = None,
        check_access_func: Optional[callable] = None,
        get_all_messages_func: Optional[callable] = None,
        summarize_old_messages_func: Optional[callable] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get conversation history for a user/chat.
        
        Args:
            user_id: User identifier (owner)
            chat_id: Chat identifier
            limit: Maximum number of messages to return (None for all)
            max_tokens: Maximum tokens (None for all, oldest messages pruned first)
            accessed_by_user_id: User ID requesting access (for access control)
            check_access_func: Optional function to check conversation access
            get_all_messages_func: Optional function to get all messages
            summarize_old_messages_func: Optional function to summarize old messages
            
        Returns:
            Conversation dictionary with messages, or None if not found or no access
        """
        # Check access if accessed_by_user_id is provided and different from owner
        if accessed_by_user_id and accessed_by_user_id != user_id and check_access_func:
            access = check_access_func(user_id, chat_id, accessed_by_user_id)
            if not access['has_access']:
                return None
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get conversation
            query = self._normalize_sql("""
                SELECT id, user_id, chat_id, created_at, updated_at, 
                       last_message_at, message_count, total_tokens, metadata
                FROM conversations
                WHERE user_id = ? AND chat_id = ?
            """)
            cursor.execute(query, (user_id, chat_id))
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
                # Get messages in reverse order and limit by tokens
                query = self._normalize_sql("""
                    SELECT id, role, content, tokens, created_at
                    FROM conversation_messages
                    WHERE conversation_id = ?
                    ORDER BY created_at DESC
                """)
                cursor.execute(query, (conversation['id'],))
                messages = []
                total_tokens = 0
                
                for msg_row in cursor.fetchall():
                    msg_tokens = msg_row[3] or 0
                    if total_tokens + msg_tokens > max_tokens:
                        break
                    messages.append({
                        'id': msg_row[0],
                        'role': msg_row[1],
                        'content': msg_row[2],
                        'tokens': msg_row[3],
                        'created_at': msg_row[4]
                    })
                    total_tokens += msg_tokens
                
                # Reverse to get chronological order
                messages.reverse()
                
                if limit:
                    messages = messages[-limit:]
            else:
                cursor.execute(query, (conversation['id'],))
                messages = []
                for msg_row in cursor.fetchall():
                    messages.append({
                        'id': msg_row[0],
                        'role': msg_row[1],
                        'content': msg_row[2],
                        'tokens': msg_row[3],
                        'created_at': msg_row[4]
                    })
                
                if limit:
                    messages = messages[-limit:]
            
            conversation['messages'] = messages
            
            # Check if summarization should be triggered
            # Only trigger if max_tokens is provided (indicating we care about token limits)
            if max_tokens and summarize_old_messages_func and get_all_messages_func:
                # Get all messages to check if summarization is needed
                all_messages = get_all_messages_func(conversation['id'])
                all_tokens = sum(msg.get('tokens', 0) for msg in all_messages)
                
                # If total tokens exceed threshold (e.g., 80% of max), consider summarization
                threshold = max_tokens * 0.8
                if all_tokens > threshold and len(all_messages) > 6:  # Need enough messages to summarize
                    logger.info(f"Context window is long ({all_tokens} tokens), considering summarization")
                    # Try to summarize old messages
                    try:
                        summarize_old_messages_func(user_id, chat_id, max_tokens, keep_recent=5)
                        # After summarization, re-fetch messages to get updated state
                        if get_all_messages_func:
                            updated_messages = get_all_messages_func(conversation['id'])
                            # Re-apply token/limit filtering
                            if max_tokens:
                                total_tokens = 0
                                filtered_messages = []
                                for msg in reversed(updated_messages):
                                    msg_tokens = msg.get('tokens', 0)
                                    if total_tokens + msg_tokens > max_tokens:
                                        break
                                    filtered_messages.insert(0, msg)
                                    total_tokens += msg_tokens
                                messages = filtered_messages
                                if limit:
                                    messages = messages[-limit:]
                            else:
                                messages = updated_messages
                                if limit:
                                    messages = messages[-limit:]
                            conversation['messages'] = messages
                    except Exception as e:
                        logger.warning(f"Failed to summarize conversation: {e}", exc_info=True)
                        # Continue with original conversation if summarization fails
            
            return conversation
        finally:
            self.adapter.close(conn)
    
    def reset_conversation(self, user_id: str, chat_id: str, get_conversation_func: callable) -> bool:
        """
        Reset a conversation by clearing all messages but keeping the conversation record.
        
        Args:
            user_id: User identifier
            chat_id: Chat identifier
            get_conversation_func: Function to get conversation
            
        Returns:
            True if reset, False if conversation not found
        """
        conversation = get_conversation_func(user_id, chat_id)
        if not conversation:
            return False
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Delete all messages
            query = self._normalize_sql("""
                DELETE FROM conversation_messages
                WHERE conversation_id = ?
            """)
            cursor.execute(query, (conversation['id'],))
            
            # Reset conversation stats
            query = self._normalize_sql("""
                UPDATE conversations
                SET message_count = 0,
                    total_tokens = 0,
                    last_message_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """)
            cursor.execute(query, (conversation['id'],))
            
            conn.commit()
            logger.info(f"Reset conversation {conversation['id']} for user {user_id}, chat {chat_id}")
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to reset conversation: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def clear_conversation(self, user_id: str, chat_id: str) -> bool:
        """
        Clear all messages from a conversation but keep the conversation record.
        
        Args:
            user_id: User identifier
            chat_id: Chat identifier
            
        Returns:
            True if cleared, False if conversation not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Get conversation ID
            query = self._normalize_sql("""
                SELECT id FROM conversations
                WHERE user_id = ? AND chat_id = ?
            """)
            cursor.execute(query, (user_id, chat_id))
            row = cursor.fetchone()
            
            if not row:
                return False
            
            conversation_id = row[0]
            
            # Delete all messages
            query = self._normalize_sql("""
                DELETE FROM conversation_messages
                WHERE conversation_id = ?
            """)
            cursor.execute(query, (conversation_id,))
            
            # Reset conversation stats
            query = self._normalize_sql("""
                UPDATE conversations
                SET message_count = 0,
                    total_tokens = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """)
            cursor.execute(query, (conversation_id,))
            
            conn.commit()
            logger.info(f"Cleared conversation for user {user_id}, chat {chat_id}")
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to clear conversation: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def delete_conversation(self, user_id: str, chat_id: str) -> bool:
        """
        Delete a conversation and all its messages.
        
        Args:
            user_id: User identifier
            chat_id: Chat identifier
            
        Returns:
            True if deleted, False if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                DELETE FROM conversations
                WHERE user_id = ? AND chat_id = ?
            """)
            cursor.execute(query, (user_id, chat_id))
            deleted = cursor.rowcount > 0
            conn.commit()
            if deleted:
                logger.info(f"Deleted conversation for user {user_id}, chat {chat_id}")
            return deleted
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete conversation: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def list_conversations(
        self,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List conversations, optionally filtered by user.
        
        Args:
            user_id: Optional user ID to filter by
            limit: Maximum number of conversations to return
            
        Returns:
            List of conversation dictionaries
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            if user_id:
                query = self._normalize_sql("""
                    SELECT id, user_id, chat_id, created_at, updated_at,
                           last_message_at, message_count, total_tokens
                    FROM conversations
                    WHERE user_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                """)
                cursor.execute(query, (user_id, limit))
            else:
                query = self._normalize_sql("""
                    SELECT id, user_id, chat_id, created_at, updated_at,
                           last_message_at, message_count, total_tokens
                    FROM conversations
                    ORDER BY updated_at DESC
                    LIMIT ?
                """)
                cursor.execute(query, (limit,))
            
            conversations = []
            for row in cursor.fetchall():
                conversations.append({
                    'id': row[0],
                    'user_id': row[1],
                    'chat_id': row[2],
                    'created_at': row[3],
                    'updated_at': row[4],
                    'last_message_at': row[5],
                    'message_count': row[6],
                    'total_tokens': row[7]
                })
            
            return conversations
        finally:
            self.adapter.close(conn)
    
    def prune_old_contexts(
        self,
        user_id: str,
        chat_id: str,
        max_tokens: int,
        keep_recent: int = 5,
        get_conversation_func: Optional[callable] = None
    ) -> int:
        """
        Prune old messages from conversation to stay within token limit.
        Keeps the most recent messages.
        
        Args:
            user_id: User identifier
            chat_id: Chat identifier
            max_tokens: Maximum tokens to keep
            keep_recent: Minimum number of recent messages to always keep
            get_conversation_func: Optional function to get conversation
            
        Returns:
            Number of messages pruned
        """
        if get_conversation_func:
            conversation = get_conversation_func(user_id, chat_id)
        else:
            # Fallback: get conversation directly
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                query = self._normalize_sql("""
                    SELECT id FROM conversations
                    WHERE user_id = ? AND chat_id = ?
                """)
                cursor.execute(query, (user_id, chat_id))
                row = cursor.fetchone()
                if not row:
                    return 0
                conversation = {'id': row[0]}
            finally:
                self.adapter.close(conn)
        
        if not conversation:
            return 0
        
        # Get all messages
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = self._normalize_sql("""
                SELECT id, role, content, tokens, created_at
                FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
            """)
            cursor.execute(query, (conversation['id'],))
            messages = []
            for msg_row in cursor.fetchall():
                messages.append({
                    'id': msg_row[0],
                    'role': msg_row[1],
                    'content': msg_row[2],
                    'tokens': msg_row[3],
                    'created_at': msg_row[4]
                })
        finally:
            self.adapter.close(conn)
        
        if not messages:
            return 0
        
        # Calculate tokens from oldest to newest
        total_tokens = 0
        keep_messages = []
        
        # Always keep the most recent messages
        recent_messages = messages[-keep_recent:] if len(messages) > keep_recent else messages
        recent_tokens = sum(msg.get('tokens', 0) for msg in recent_messages)
        
        if recent_tokens > max_tokens:
            # Even recent messages exceed limit, keep only what fits
            for msg in reversed(recent_messages):
                msg_tokens = msg.get('tokens', 0)
                if total_tokens + msg_tokens <= max_tokens:
                    keep_messages.insert(0, msg)
                    total_tokens += msg_tokens
                else:
                    break
        else:
            # Keep recent messages, add older ones up to limit
            keep_messages = recent_messages.copy()
            total_tokens = recent_tokens
            
            # Add older messages from back to front
            older_messages = messages[:-keep_recent] if len(messages) > keep_recent else []
            for msg in reversed(older_messages):
                msg_tokens = msg.get('tokens', 0)
                if total_tokens + msg_tokens <= max_tokens:
                    keep_messages.insert(0, msg)
                    total_tokens += msg_tokens
                else:
                    break
        
        # Delete messages not in keep list
        keep_ids = {msg['id'] for msg in keep_messages}
        prune_count = len(messages) - len(keep_messages)
        
        if prune_count > 0:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                placeholders = ','.join(['?' for _ in keep_ids])
                query = self._normalize_sql(f"""
                    DELETE FROM conversation_messages
                    WHERE conversation_id = ? AND id NOT IN ({placeholders})
                """)
                cursor.execute(query, (conversation['id'],) + tuple(keep_ids))
                
                # Update conversation stats
                cursor.execute(self._normalize_sql("""
                    UPDATE conversations
                    SET message_count = ?,
                        total_tokens = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """), (len(keep_messages), total_tokens, conversation['id']))
                
                conn.commit()
                logger.info(f"Pruned {prune_count} messages from conversation {conversation['id']}")
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to prune messages: {e}", exc_info=True)
                raise
            finally:
                self.adapter.close(conn)
        
        return prune_count
    
    def export_conversation(
        self,
        user_id: str,
        chat_id: str,
        format: str = "json",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        get_conversation_func: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Export conversation to JSON format.
        
        Args:
            user_id: User identifier
            chat_id: Chat identifier
            format: Export format ('json', 'txt', or 'pdf')
            start_date: Optional start date for filtering messages (inclusive)
            end_date: Optional end date for filtering messages (inclusive)
            get_conversation_func: Optional function to get conversation
            
        Returns:
            Dictionary for JSON format (txt/pdf handled separately)
        """
        if get_conversation_func:
            conversation = get_conversation_func(user_id, chat_id)
        else:
            return None
        
        if not conversation:
            raise ValueError(f"Conversation not found for user {user_id}, chat {chat_id}")
        
        # Filter messages by date range if provided
        messages = conversation.get('messages', [])
        if start_date or end_date:
            filtered_messages = []
            for msg in messages:
                msg_date = msg.get('created_at')
                if msg_date:
                    if isinstance(msg_date, str):
                        try:
                            msg_date = datetime.fromisoformat(msg_date.replace('Z', '+00:00'))
                        except:
                            # If parsing fails, include the message
                            filtered_messages.append(msg)
                            continue
                    
                    # Check date range
                    if start_date and msg_date < start_date:
                        continue
                    if end_date and msg_date > end_date:
                        continue
                    filtered_messages.append(msg)
                else:
                    # If no date, include the message (for backwards compatibility)
                    filtered_messages.append(msg)
            messages = filtered_messages
        
        # Format conversation data
        conv_data = {
            'user_id': conversation['user_id'],
            'chat_id': conversation['chat_id'],
            'created_at': conversation['created_at'].isoformat() if isinstance(conversation['created_at'], datetime) else str(conversation['created_at']),
            'updated_at': conversation['updated_at'].isoformat() if isinstance(conversation['updated_at'], datetime) else str(conversation['updated_at']),
            'last_message_at': conversation['last_message_at'].isoformat() if conversation['last_message_at'] and isinstance(conversation['last_message_at'], datetime) else (str(conversation['last_message_at']) if conversation['last_message_at'] else None),
            'message_count': len(messages),
            'total_tokens': sum(msg.get('tokens', 0) for msg in messages),
            'metadata': conversation.get('metadata', {}),
            'messages': [
                {
                    'role': msg['role'],
                    'content': msg['content'],
                    'tokens': msg.get('tokens'),
                    'created_at': msg['created_at'].isoformat() if isinstance(msg['created_at'], datetime) else str(msg['created_at'])
                }
                for msg in messages
            ]
        }
        
        return conv_data
    
    def _export_to_txt(self, conv_data: Dict[str, Any]) -> str:
        """Export conversation data to plain text format."""
        lines = []
        lines.append("=" * 80)
        lines.append(f"Conversation Export")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"User ID: {conv_data['user_id']}")
        lines.append(f"Chat ID: {conv_data['chat_id']}")
        lines.append(f"Created At: {conv_data['created_at']}")
        lines.append(f"Updated At: {conv_data['updated_at']}")
        if conv_data.get('last_message_at'):
            lines.append(f"Last Message At: {conv_data['last_message_at']}")
        lines.append(f"Message Count: {conv_data['message_count']}")
        lines.append(f"Total Tokens: {conv_data['total_tokens']}")
        if conv_data.get('metadata'):
            lines.append(f"Metadata: {json.dumps(conv_data['metadata'], indent=2)}")
        lines.append("")
        lines.append("-" * 80)
        lines.append("Messages")
        lines.append("-" * 80)
        lines.append("")
        
        for msg in conv_data['messages']:
            role = msg['role'].upper()
            content = msg['content']
            timestamp = msg.get('created_at', '')
            tokens = msg.get('tokens', '')
            
            lines.append(f"[{role}] {timestamp}")
            if tokens:
                lines.append(f"Tokens: {tokens}")
            lines.append("")
            lines.append(content)
            lines.append("")
            lines.append("-" * 80)
            lines.append("")
        
        return "\n".join(lines)
    
    def _export_to_pdf(self, conv_data: Dict[str, Any]) -> bytes:
        """Export conversation data to PDF format."""
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
            from reportlab.lib.enums import TA_LEFT
            from io import BytesIO
            
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            story = []
            
            # Define styles
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                textColor='#000000',
                spaceAfter=12,
                alignment=TA_LEFT
            )
            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=12,
                textColor='#333333',
                spaceAfter=6,
                alignment=TA_LEFT
            )
            normal_style = styles['Normal']
            meta_style = ParagraphStyle(
                'Meta',
                parent=styles['Normal'],
                fontSize=9,
                textColor='#666666',
                spaceAfter=12
            )
            
            # Title
            story.append(Paragraph("Conversation Export", title_style))
            story.append(Spacer(1, 0.2 * inch))
            
            # Metadata
            story.append(Paragraph("<b>Conversation Information</b>", heading_style))
            story.append(Paragraph(f"User ID: {conv_data['user_id']}", meta_style))
            story.append(Paragraph(f"Chat ID: {conv_data['chat_id']}", meta_style))
            story.append(Paragraph(f"Created At: {conv_data['created_at']}", meta_style))
            story.append(Paragraph(f"Updated At: {conv_data['updated_at']}", meta_style))
            if conv_data.get('last_message_at'):
                story.append(Paragraph(f"Last Message At: {conv_data['last_message_at']}", meta_style))
            story.append(Paragraph(f"Message Count: {conv_data['message_count']}", meta_style))
            story.append(Paragraph(f"Total Tokens: {conv_data['total_tokens']}", meta_style))
            if conv_data.get('metadata'):
                story.append(Paragraph(f"Metadata: {json.dumps(conv_data['metadata'])}", meta_style))
            
            story.append(Spacer(1, 0.3 * inch))
            story.append(Paragraph("<b>Messages</b>", heading_style))
            story.append(Spacer(1, 0.2 * inch))
            
            # Messages
            for msg in conv_data['messages']:
                role = msg['role'].upper()
                content = msg['content']
                timestamp = msg.get('created_at', '')
                tokens = msg.get('tokens', '')
                
                # Role header
                role_text = f"<b>[{role}]</b>"
                if timestamp:
                    role_text += f" <i>{timestamp}</i>"
                if tokens:
                    role_text += f" (Tokens: {tokens})"
                
                story.append(Paragraph(role_text, heading_style))
                
                # Content (escape HTML special characters)
                content_escaped = content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                # Replace newlines with <br/>
                content_escaped = content_escaped.replace('\n', '<br/>')
                story.append(Paragraph(content_escaped, normal_style))
                story.append(Spacer(1, 0.2 * inch))
            
            # Build PDF
            doc.build(story)
            buffer.seek(0)
            return buffer.getvalue()
            
        except ImportError:
            logger.error("reportlab is not installed. Install it with: pip install reportlab")
            raise ValueError("PDF export requires reportlab library. Install with: pip install reportlab")
        except Exception as e:
            logger.error(f"Error generating PDF: {e}", exc_info=True)
            raise
    
    def import_conversation(
        self,
        data: Dict[str, Any],
        get_or_create_conversation_func: callable,
        add_message_func: callable
    ) -> int:
        """
        Import conversation from JSON format.
        
        Args:
            data: Dictionary with conversation data (from export_conversation)
            get_or_create_conversation_func: Function to get or create conversation
            add_message_func: Function to add message
            
        Returns:
            Conversation ID
        """
        user_id = data['user_id']
        chat_id = data['chat_id']
        
        # Create or get conversation
        conversation_id = get_or_create_conversation_func(user_id, chat_id)
        
        # Import messages
        for msg_data in data.get('messages', []):
            add_message_func(
                conversation_id=conversation_id,
                role=msg_data['role'],
                content=msg_data['content'],
                tokens=msg_data.get('tokens')
            )
        
        # Update metadata if provided
        if 'metadata' in data and data['metadata']:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                query = self._normalize_sql("""
                    UPDATE conversations
                    SET metadata = ?
                    WHERE id = ?
                """)
                cursor.execute(query, (json.dumps(data['metadata']), conversation_id))
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to update metadata: {e}", exc_info=True)
                raise
            finally:
                self.adapter.close(conn)
        
        logger.info(f"Imported conversation {conversation_id} with {len(data.get('messages', []))} messages")
        return conversation_id
