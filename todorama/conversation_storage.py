"""
Conversation context persistence module.

Stores conversation history in PostgreSQL instead of memory, with support for:
- Conversation retrieval by user/chat ID
- Context pruning for old conversations
- Conversation summarization for long contexts
- Conversation export/import
- Conversation analytics and reporting
"""
import os
from typing import Optional, List, Dict, Any, Tuple, Union
from datetime import datetime
import logging

from todorama.db_adapter import get_database_adapter

# Import managers
from todorama.conversation_storage.schema import ConversationSchemaManager
from todorama.conversation_storage.conversations import ConversationManager
from todorama.conversation_storage.messages import MessageManager
from todorama.conversation_storage.templates import TemplateManager
from todorama.conversation_storage.prompt_templates import PromptTemplateManager
from todorama.conversation_storage.ab_testing import ABTestingManager
from todorama.conversation_storage.sharing import SharingManager
from todorama.conversation_storage.summarization import SummarizationManager
from todorama.conversation_storage.analytics import ConversationAnalytics
from todorama.conversation_storage.llm_streaming import LLMStreamingManager

logger = logging.getLogger(__name__)


class ConversationStorage:
    """Manage conversation history persistence in PostgreSQL - Facade that delegates to specialized managers."""
    
    def __init__(self, db_path: str = None):
        """
        Initialize conversation storage.
        
        Args:
            db_path: Database connection string (for PostgreSQL) or None to use environment variables.
        """
        # Determine database type - conversation storage requires PostgreSQL
        db_type = os.getenv("DB_TYPE", "postgresql").lower()
        
        if db_path is None:
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
            self.db_path = db_path
        
        self.db_type = db_type
        self.adapter = get_database_adapter(self.db_path)
        
        # LLM configuration for summarization
        self.llm_api_url = os.getenv("LLM_API_URL", "")
        self.llm_api_key = os.getenv("LLM_API_KEY", "")
        self.llm_model = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
        self.llm_enabled = bool(self.llm_api_url and self.llm_api_key)
        
        # Initialize managers
        self.schema_manager = ConversationSchemaManager(self.adapter, self._normalize_sql)
        self.conversation_manager = ConversationManager(self.adapter, self._normalize_sql)
        self.message_manager = MessageManager(self.adapter, self._normalize_sql)
        self.template_manager = TemplateManager(self.adapter, self._normalize_sql)
        self.prompt_template_manager = PromptTemplateManager(self.adapter, self._normalize_sql)
        self.ab_testing_manager = ABTestingManager(self.adapter, self._normalize_sql)
        self.sharing_manager = SharingManager(self.adapter, self._normalize_sql)
        self.summarization_manager = SummarizationManager(
            self.adapter, self._normalize_sql,
            self.llm_api_url, self.llm_api_key, self.llm_model
        )
        self.analytics_manager = ConversationAnalytics(self.adapter, self._normalize_sql)
        
        # Initialize schema
        self.schema_manager.initialize_schema()
        
        # Initialize LLM streaming manager after other managers are set up
        # (needs access to methods that are defined later)
        self.llm_streaming_manager = None
    
    def _get_connection(self):
        """Get database connection using adapter."""
        return self.adapter.connect()
    
    def _normalize_sql(self, query: str) -> str:
        """Normalize SQL query for the current database backend."""
        return self.adapter.normalize_query(query)
    
    # ==================== Conversation Methods ====================
    
    def get_or_create_conversation(self, user_id: str, chat_id: str) -> int:
        """Get existing conversation or create a new one."""
        return self.conversation_manager.get_or_create_conversation(user_id, chat_id)
    
    def get_conversation(
        self,
        user_id: str,
        chat_id: str,
        limit: Optional[int] = None,
        max_tokens: Optional[int] = None,
        accessed_by_user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get conversation history for a user/chat."""
        return self.conversation_manager.get_conversation(
            user_id=user_id,
            chat_id=chat_id,
            limit=limit,
            max_tokens=max_tokens,
            accessed_by_user_id=accessed_by_user_id,
            check_access_func=self.check_conversation_access,
            get_all_messages_func=self.message_manager.get_all_messages,
            summarize_old_messages_func=self.summarize_old_messages
        )
    
    def reset_conversation(self, user_id: str, chat_id: str) -> bool:
        """Reset a conversation by clearing all messages but keeping the conversation record."""
        return self.conversation_manager.reset_conversation(
            user_id, chat_id, self.get_conversation
        )
    
    def clear_conversation(self, user_id: str, chat_id: str) -> bool:
        """Clear all messages from a conversation but keep the conversation record."""
        return self.conversation_manager.clear_conversation(user_id, chat_id)
    
    def delete_conversation(self, user_id: str, chat_id: str) -> bool:
        """Delete a conversation and all its messages."""
        return self.conversation_manager.delete_conversation(user_id, chat_id)
    
    def list_conversations(
        self,
        user_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List conversations, optionally filtered by user."""
        return self.conversation_manager.list_conversations(user_id=user_id, limit=limit)
    
    def export_conversation(
        self,
        user_id: str,
        chat_id: str,
        format: str = "json",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Union[Dict[str, Any], str, bytes]:
        """Export conversation to JSON, TXT, or PDF format."""
        conv_data = self.conversation_manager.export_conversation(
            user_id=user_id,
            chat_id=chat_id,
            format=format,
            start_date=start_date,
            end_date=end_date,
            get_conversation_func=self.get_conversation
        )
        
        if format == "json":
            return conv_data
        elif format == "txt":
            return self.conversation_manager._export_to_txt(conv_data)
        elif format == "pdf":
            return self.conversation_manager._export_to_pdf(conv_data)
        else:
            raise ValueError(f"Unsupported export format: {format}. Supported formats: json, txt, pdf")
    
    def import_conversation(self, data: Dict[str, Any]) -> int:
        """Import conversation from JSON format."""
        return self.conversation_manager.import_conversation(
            data=data,
            get_or_create_conversation_func=self.get_or_create_conversation,
            add_message_func=self.add_message
        )
    
    def prune_old_contexts(
        self,
        user_id: str,
        chat_id: str,
        max_tokens: int,
        keep_recent: int = 5
    ) -> int:
        """Prune old messages from conversation to stay within token limit."""
        return self.conversation_manager.prune_old_contexts(
            user_id=user_id,
            chat_id=chat_id,
            max_tokens=max_tokens,
            keep_recent=keep_recent,
            get_conversation_func=self.get_conversation
        )
    
    # ==================== Message Methods ====================
    
    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        tokens: Optional[int] = None
    ) -> int:
        """Add a message to a conversation."""
        return self.message_manager.add_message(conversation_id, role, content, tokens)
    
    def _get_all_messages(self, conversation_id: int) -> List[Dict[str, Any]]:
        """Get all messages for a conversation (for internal use)."""
        return self.message_manager.get_all_messages(conversation_id)
    
    # ==================== Template Methods ====================
    
    def create_template(
        self,
        user_id: str,
        name: str,
        description: str = "",
        initial_messages: List[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Create a conversation template."""
        return self.template_manager.create_template(
            user_id=user_id,
            name=name,
            description=description,
            initial_messages=initial_messages,
            metadata=metadata
        )
    
    def get_template(self, template_id: int) -> Optional[Dict[str, Any]]:
        """Get a template by ID, including its quick replies."""
        return self.template_manager.get_template(template_id)
    
    def list_templates(self, user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """List conversation templates, optionally filtered by user."""
        return self.template_manager.list_templates(user_id=user_id, limit=limit)
    
    def update_template(
        self,
        template_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        initial_messages: Optional[List[Dict[str, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update a conversation template."""
        return self.template_manager.update_template(
            template_id=template_id,
            name=name,
            description=description,
            initial_messages=initial_messages,
            metadata=metadata
        )
    
    def delete_template(self, template_id: int) -> bool:
        """Delete a conversation template (and its quick replies via CASCADE)."""
        return self.template_manager.delete_template(template_id)
    
    def add_quick_reply(
        self,
        template_id: int,
        label: str,
        action: str,
        order_index: int = 0
    ) -> int:
        """Add a quick reply button to a template."""
        return self.template_manager.add_quick_reply(template_id, label, action, order_index)
    
    def update_quick_reply(
        self,
        reply_id: int,
        label: Optional[str] = None,
        action: Optional[str] = None,
        order_index: Optional[int] = None
    ) -> bool:
        """Update a quick reply."""
        return self.template_manager.update_quick_reply(reply_id, label, action, order_index)
    
    def delete_quick_reply(self, reply_id: int) -> bool:
        """Delete a quick reply."""
        return self.template_manager.delete_quick_reply(reply_id)
    
    def apply_template(
        self,
        user_id: str,
        chat_id: str,
        template_id: int
    ) -> int:
        """Apply a template to start a conversation."""
        return self.template_manager.apply_template(
            user_id=user_id,
            chat_id=chat_id,
            template_id=template_id,
            get_template_func=self.get_template,
            get_conversation_func=self.get_conversation,
            reset_conversation_func=self.reset_conversation,
            get_or_create_conversation_func=self.get_or_create_conversation,
            add_message_func=self.add_message
        )
    
    # ==================== Prompt Template Methods ====================
    
    def validate_prompt_template(self, template_content: str) -> Tuple[bool, Optional[str]]:
        """Validate prompt template syntax."""
        return self.prompt_template_manager.validate_prompt_template(template_content)
    
    def create_prompt_template(
        self,
        user_id: str,
        template_name: str,
        template_content: str,
        template_type: str = "summarization",
        conversation_id: Optional[int] = None
    ) -> int:
        """Create a new prompt template."""
        return self.prompt_template_manager.create_prompt_template(
            user_id=user_id,
            template_name=template_name,
            template_content=template_content,
            template_type=template_type,
            conversation_id=conversation_id,
            validate_func=self.validate_prompt_template,
            get_conversation_func=self.get_conversation
        )
    
    def get_prompt_template(self, template_id: int) -> Optional[Dict[str, Any]]:
        """Get a prompt template by ID."""
        return self.prompt_template_manager.get_prompt_template(template_id)
    
    def get_prompt_template_for_user(
        self,
        user_id: str,
        template_type: str = "summarization"
    ) -> Optional[Dict[str, Any]]:
        """Get prompt template for a user (per-user templates, not conversation-specific)."""
        return self.prompt_template_manager.get_prompt_template_for_user(user_id, template_type)
    
    def get_prompt_template_for_conversation(
        self,
        user_id: str,
        chat_id: str,
        template_type: str = "summarization"
    ) -> Optional[Dict[str, Any]]:
        """Get prompt template for a conversation. Prefers conversation-specific, falls back to user."""
        return self.prompt_template_manager.get_prompt_template_for_conversation(
            user_id=user_id,
            chat_id=chat_id,
            template_type=template_type,
            get_conversation_func=self.get_conversation
        )
    
    def list_prompt_templates(
        self,
        user_id: Optional[str] = None,
        template_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List prompt templates."""
        return self.prompt_template_manager.list_prompt_templates(user_id=user_id, template_type=template_type)
    
    def update_prompt_template(
        self,
        template_id: int,
        template_name: Optional[str] = None,
        template_content: Optional[str] = None
    ) -> bool:
        """Update a prompt template."""
        return self.prompt_template_manager.update_prompt_template(
            template_id=template_id,
            template_name=template_name,
            template_content=template_content,
            validate_func=self.validate_prompt_template
        )
    
    def delete_prompt_template(self, template_id: int) -> bool:
        """Delete a prompt template."""
        return self.prompt_template_manager.delete_prompt_template(template_id)
    
    # ==================== A/B Testing Methods ====================
    
    def create_ab_test(
        self,
        name: str,
        control: Dict[str, Any],
        variant: Dict[str, Any],
        description: Optional[str] = None,
        traffic_split: float = 0.5,
        active: bool = True
    ) -> int:
        """Create an A/B test configuration."""
        return self.ab_testing_manager.create_ab_test(
            name=name,
            control=control,
            variant=variant,
            description=description,
            traffic_split=traffic_split,
            active=active
        )
    
    def get_ab_test(self, test_id: int) -> Optional[Dict[str, Any]]:
        """Get an A/B test configuration."""
        return self.ab_testing_manager.get_ab_test(test_id)
    
    def list_ab_tests(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """List A/B tests."""
        return self.ab_testing_manager.list_ab_tests(active_only=active_only)
    
    def update_ab_test(
        self,
        test_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        control: Optional[Dict[str, Any]] = None,
        variant: Optional[Dict[str, Any]] = None,
        traffic_split: Optional[float] = None,
        active: Optional[bool] = None
    ) -> bool:
        """Update an A/B test configuration."""
        return self.ab_testing_manager.update_ab_test(
            test_id=test_id,
            name=name,
            description=description,
            control=control,
            variant=variant,
            traffic_split=traffic_split,
            active=active
        )
    
    def deactivate_ab_test(self, test_id: int) -> bool:
        """Deactivate an A/B test."""
        return self.ab_testing_manager.deactivate_ab_test(test_id)
    
    def assign_ab_variant(self, conversation_id: int, test_id: int) -> str:
        """Assign a variant (control or variant) to a conversation for an A/B test."""
        return self.ab_testing_manager.assign_ab_variant(
            conversation_id=conversation_id,
            test_id=test_id,
            get_ab_test_func=self.get_ab_test
        )
    
    def record_ab_metric(
        self,
        test_id: int,
        conversation_id: int,
        variant: str,
        response_time_ms: Optional[int] = None,
        tokens_used: Optional[int] = None,
        user_satisfaction_score: Optional[float] = None,
        error_occurred: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Record metrics for an A/B test response."""
        return self.ab_testing_manager.record_ab_metric(
            test_id=test_id,
            conversation_id=conversation_id,
            variant=variant,
            response_time_ms=response_time_ms,
            tokens_used=tokens_used,
            user_satisfaction_score=user_satisfaction_score,
            error_occurred=error_occurred,
            metadata=metadata
        )
    
    def get_ab_metrics(self, test_id: int, variant: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get metrics for an A/B test."""
        return self.ab_testing_manager.get_ab_metrics(test_id=test_id, variant=variant)
    
    def get_ab_statistics(self, test_id: int) -> Dict[str, Any]:
        """Get statistical analysis of A/B test results."""
        return self.ab_testing_manager.get_ab_statistics(
            test_id=test_id,
            get_ab_metrics_func=self.get_ab_metrics
        )
    
    # ==================== Sharing Methods ====================
    
    def create_share(
        self,
        user_id: str,
        chat_id: str,
        shared_with_user_id: Optional[str] = None,
        permission: str = "read_only",
        share_token: Optional[str] = None
    ) -> int:
        """Create a share for a conversation."""
        return self.sharing_manager.create_share(
            user_id=user_id,
            chat_id=chat_id,
            shared_with_user_id=shared_with_user_id,
            permission=permission,
            share_token=share_token,
            get_or_create_conversation_func=self.get_or_create_conversation
        )
    
    def get_share(self, share_id: int) -> Optional[Dict[str, Any]]:
        """Get a share by ID."""
        return self.sharing_manager.get_share(share_id)
    
    def get_share_by_token(self, share_token: str) -> Optional[Dict[str, Any]]:
        """Get a share by its token."""
        return self.sharing_manager.get_share_by_token(share_token)
    
    def list_shares_for_conversation(
        self,
        user_id: str,
        chat_id: str
    ) -> List[Dict[str, Any]]:
        """List all shares for a conversation."""
        return self.sharing_manager.list_shares_for_conversation(
            user_id=user_id,
            chat_id=chat_id,
            get_or_create_conversation_func=self.get_or_create_conversation
        )
    
    def list_shares_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """List all shares where a user is the recipient."""
        return self.sharing_manager.list_shares_for_user(user_id)
    
    def delete_share(self, share_id: int) -> bool:
        """Delete a share."""
        return self.sharing_manager.delete_share(share_id)
    
    def check_conversation_access(
        self,
        user_id: str,
        chat_id: str,
        accessed_by_user_id: str
    ) -> Dict[str, Any]:
        """Check if a user has access to a conversation and what permissions."""
        return self.sharing_manager.check_conversation_access(
            user_id=user_id,
            chat_id=chat_id,
            accessed_by_user_id=accessed_by_user_id,
            get_or_create_conversation_func=self.get_or_create_conversation
        )
    
    def get_conversation_by_share_token(
        self,
        share_token: str,
        limit: Optional[int] = None,
        max_tokens: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Get a conversation using a share token."""
        return self.sharing_manager.get_conversation_by_share_token(
            share_token=share_token,
            limit=limit,
            max_tokens=max_tokens,
            get_share_by_token_func=self.get_share_by_token
        )
    
    # ==================== Summarization Methods ====================
    
    def _summarize_messages(
        self,
        messages: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None
    ) -> str:
        """Summarize a list of conversation messages using LLM."""
        return self.summarization_manager.summarize_messages(
            messages=messages,
            user_id=user_id,
            chat_id=chat_id,
            get_prompt_template_for_conversation_func=self.get_prompt_template_for_conversation,
            get_or_create_conversation_func=self.get_or_create_conversation
        )
    
    def summarize_old_messages(
        self,
        user_id: str,
        chat_id: str,
        max_tokens: int,
        keep_recent: int = 5
    ) -> bool:
        """Summarize old messages when context window gets long."""
        return self.summarization_manager.summarize_old_messages(
            user_id=user_id,
            chat_id=chat_id,
            max_tokens=max_tokens,
            keep_recent=keep_recent,
            get_conversation_func=self.get_conversation,
            summarize_messages_func=self._summarize_messages,
            add_message_func=self.add_message
        )
    
    # ==================== Analytics Methods ====================
    
    def get_conversation_analytics(
        self,
        user_id: str,
        chat_id: str
    ) -> Dict[str, Any]:
        """Get analytics metrics for a specific conversation."""
        return self.analytics_manager.get_conversation_analytics(
            user_id=user_id,
            chat_id=chat_id,
            get_conversation_func=self.get_conversation
        )
    
    def get_dashboard_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get dashboard analytics aggregating data across conversations."""
        return self.analytics_manager.get_dashboard_analytics(
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            list_conversations_func=self.list_conversations,
            get_conversation_analytics_func=self.get_conversation_analytics
        )
    
    def generate_analytics_report(
        self,
        format: str = "json",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[str] = None
    ) -> Union[Dict[str, Any], str]:
        """Generate analytics report in specified format."""
        return self.analytics_manager.generate_analytics_report(
            format=format,
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            get_dashboard_analytics_func=self.get_dashboard_analytics,
            list_conversations_func=self.list_conversations,
            get_conversation_analytics_func=self.get_conversation_analytics
        )
    
    # ==================== LLM Streaming Method ====================
    
    def _init_llm_streaming_manager(self):
        """Initialize LLM streaming manager (lazy initialization)."""
        if self.llm_streaming_manager is None:
            self.llm_streaming_manager = LLMStreamingManager(
                llm_api_url=self.llm_api_url,
                llm_api_key=self.llm_api_key,
                llm_model=self.llm_model,
                llm_enabled=self.llm_enabled,
                get_or_create_conversation_func=self.get_or_create_conversation,
                assign_ab_variant_func=self.assign_ab_variant,
                get_ab_test_func=self.get_ab_test,
                get_prompt_template_for_conversation_func=self.get_prompt_template_for_conversation,
                record_ab_metric_func=self.record_ab_metric
            )
    
    async def stream_llm_response(
        self,
        messages: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        ab_test_id: Optional[int] = None
    ):
        """Stream LLM response character-by-character."""
        self._init_llm_streaming_manager()
        async for chunk in self.llm_streaming_manager.stream_response(
            messages=messages,
            user_id=user_id,
            chat_id=chat_id,
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt,
            ab_test_id=ab_test_id
        ):
            yield chunk
