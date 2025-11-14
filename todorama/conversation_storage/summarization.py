"""Conversation summarization operations."""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from todorama.adapters import HTTPClientAdapterFactory, HTTPError

logger = logging.getLogger(__name__)

# Try to import dateutil for flexible date parsing
try:
    from dateutil.parser import parse as parse_date
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False
    def parse_date(date_str):
        """Fallback date parser using datetime.fromisoformat."""
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            try:
                return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            except:
                return None


class SummarizationManager:
    """Manages conversation summarization operations."""
    
    def __init__(self, adapter, normalize_sql_func, llm_api_url: str = "", llm_api_key: str = "", llm_model: str = "gpt-3.5-turbo"):
        self.adapter = adapter
        self._normalize_sql = normalize_sql_func
        self.llm_api_url = llm_api_url
        self.llm_api_key = llm_api_key
        self.llm_model = llm_model
        self.llm_enabled = bool(llm_api_url and llm_api_key)
    
    def _get_connection(self):
        return self.adapter.connect()
    
    def summarize_messages(
        self,
        messages: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        get_prompt_template_for_conversation_func: Optional[callable] = None,
        get_or_create_conversation_func: Optional[callable] = None
    ) -> str:
        """Summarize a list of conversation messages using LLM."""
        if not self.llm_enabled:
            # Fallback: simple concatenation if LLM not available
            logger.warning("LLM not configured, using simple text concatenation for summary")
            summary_parts = []
            for msg in messages:
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                summary_parts.append(f"{role}: {content[:100]}...")
            return "Previous conversation: " + " | ".join(summary_parts)
        
        try:
            # Format messages for LLM API
            formatted_messages = [
                {"role": msg.get('role', 'user'), "content": msg.get('content', '')}
                for msg in messages
            ]
            
            # Get custom prompt template if user_id and chat_id are provided
            template_content = None
            if user_id and chat_id and get_prompt_template_for_conversation_func:
                template = get_prompt_template_for_conversation_func(user_id, chat_id, "summarization")
                if template:
                    template_content = template['template_content']
                    logger.debug(f"Using custom prompt template {template['id']} for summarization")
            
            # Use custom template or default system message
            if template_content:
                try:
                    if '{context}' in template_content:
                        system_content = template_content.format(context="conversation history")
                    else:
                        system_content = template_content
                except (KeyError, ValueError):
                    logger.warning("Failed to format template variables, using template as-is")
                    system_content = template_content
            else:
                system_content = "You are a helpful assistant that summarizes conversation history. Create a concise summary that preserves key information, important facts, user preferences, and context. Focus on what matters most for continuing the conversation."
            
            # Add system message for summarization task
            system_message = {
                "role": "system",
                "content": system_content
            }
            
            api_messages = [system_message] + formatted_messages
            
            # Call LLM API (OpenAI-compatible)
            headers = {
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.llm_model,
                "messages": api_messages,
                "max_tokens": 500,
                "temperature": 0.3
            }
            
            with HTTPClientAdapterFactory.create_client(timeout=30.0) as client:
                response = client.post(
                    f"{self.llm_api_url.rstrip('/')}/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                result = response.json()
                
                # Extract summary from response
                if "choices" in result and len(result["choices"]) > 0:
                    summary = result["choices"][0]["message"]["content"]
                    logger.info(f"Generated summary with {len(summary)} characters")
                    
                    # Track cost for summarization
                    if user_id and chat_id and get_or_create_conversation_func:
                        try:
                            from cost_tracking import CostTracker, ServiceType
                            cost_tracker = CostTracker()
                            conv_id = get_or_create_conversation_func(user_id, chat_id)
                            
                            usage = result.get("usage", {})
                            input_tokens = usage.get("prompt_tokens", 0)
                            output_tokens = usage.get("completion_tokens", 0)
                            total_tokens = usage.get("total_tokens", input_tokens + output_tokens)
                            
                            cost = cost_tracker.calculate_llm_cost(
                                model=self.llm_model,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens
                            )
                            
                            cost_tracker.record_cost(
                                service_type=ServiceType.LLM,
                                user_id=user_id,
                                conversation_id=conv_id,
                                cost=cost,
                                tokens=total_tokens,
                                metadata={
                                    "model": self.llm_model,
                                    "input_tokens": input_tokens,
                                    "output_tokens": output_tokens,
                                    "operation": "summarization"
                                }
                            )
                        except Exception as e:
                            logger.warning(f"Failed to track LLM cost for summarization: {e}", exc_info=True)
                    
                    return summary
                else:
                    raise ValueError("Invalid LLM API response format")
                    
        except HTTPError as e:
            logger.error(f"HTTP error calling LLM API: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Error summarizing messages: {e}", exc_info=True)
            raise
    
    def summarize_old_messages(
        self,
        user_id: str,
        chat_id: str,
        max_tokens: int,
        keep_recent: int = 5,
        get_conversation_func: callable = None,
        summarize_messages_func: callable = None,
        add_message_func: callable = None
    ) -> bool:
        """Summarize old messages when context window gets long."""
        if get_conversation_func:
            conversation = get_conversation_func(user_id, chat_id)
        else:
            return False
        
        if not conversation:
            return False
        
        messages = conversation.get('messages', [])
        if len(messages) <= keep_recent + 1:
            return False
        
        # Calculate tokens
        total_tokens = sum(msg.get('tokens', 0) for msg in messages)
        
        # Only summarize if we're approaching the limit
        threshold = max_tokens * 0.75
        if total_tokens < threshold:
            return False
        
        # Get messages to summarize
        recent_messages = messages[-keep_recent:] if len(messages) > keep_recent else []
        old_messages = messages[:-keep_recent] if len(messages) > keep_recent else []
        
        if not old_messages:
            return False
        
        # Check if there's already a summary message
        has_summary = any(
            msg.get('role') == 'system' and 'summary' in msg.get('content', '').lower()
            for msg in old_messages[-1:]
        )
        if has_summary and len(old_messages) <= 1:
            return False
        
        try:
            # Summarize old messages
            logger.info(f"Summarizing {len(old_messages)} old messages")
            if summarize_messages_func:
                summary_text = summarize_messages_func(old_messages, user_id=user_id, chat_id=chat_id)
            else:
                summary_text = self.summarize_messages(old_messages, user_id=user_id, chat_id=chat_id)
            
            # Estimate tokens for summary
            summary_tokens = len(summary_text) // 4
            
            # Calculate tokens in messages we're keeping
            kept_tokens = sum(msg.get('tokens', 0) for msg in recent_messages)
            old_tokens = sum(msg.get('tokens', 0) for msg in old_messages)
            
            # Replace old messages with summary
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                
                # Delete old messages
                old_message_ids = [msg['id'] for msg in old_messages]
                if old_message_ids:
                    placeholders = ','.join(['?' for _ in old_message_ids])
                    query = self._normalize_sql(f"""
                        DELETE FROM conversation_messages
                        WHERE conversation_id = ? AND id IN ({placeholders})
                    """)
                    cursor.execute(query, (conversation['id'],) + tuple(old_message_ids))
                
                # Add summary as a system message
                summary_content = f"[Summary of previous conversation ({len(old_messages)} messages)]: {summary_text}"
                if add_message_func:
                    add_message_func(conversation['id'], 'system', summary_content, summary_tokens)
                else:
                    query = self._normalize_sql("""
                        INSERT INTO conversation_messages (conversation_id, role, content, tokens)
                        VALUES (?, ?, ?, ?)
                    """)
                    cursor.execute(query, (conversation['id'], 'system', summary_content, summary_tokens))
                
                # Update conversation stats
                new_total_tokens = kept_tokens + summary_tokens
                new_message_count = len(recent_messages) + 1
                query = self._normalize_sql("""
                    UPDATE conversations
                    SET message_count = ?,
                        total_tokens = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """)
                cursor.execute(query, (new_message_count, new_total_tokens, conversation['id']))
                
                conn.commit()
                logger.info(f"Summarized {len(old_messages)} messages into summary, reduced tokens from {old_tokens} to {summary_tokens}")
                return True
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to replace messages with summary: {e}", exc_info=True)
                raise
            finally:
                self.adapter.close(conn)
                
        except Exception as e:
            logger.error(f"Failed to summarize old messages: {e}", exc_info=True)
            return False
