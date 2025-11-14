"""Schema initialization for conversation storage."""

import logging

logger = logging.getLogger(__name__)


class ConversationSchemaManager:
    """Manages conversation storage schema initialization."""
    
    def __init__(self, adapter, normalize_sql_func):
        """
        Initialize schema manager.
        
        Args:
            adapter: Database adapter instance
            normalize_sql_func: Function to normalize SQL queries
        """
        self.adapter = adapter
        self._normalize_sql = normalize_sql_func
    
    def _get_connection(self):
        """Get database connection using adapter."""
        return self.adapter.connect()
    
    def initialize_schema(self):
        """Initialize conversation storage schema."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Create all tables
            self._create_conversations_schema(cursor)
            self._create_messages_schema(cursor)
            self._create_shares_schema(cursor)
            self._create_templates_schema(cursor)
            self._create_prompt_templates_schema(cursor)
            self._create_ab_tests_schema(cursor)
            
            # Create all indexes
            self._create_indexes(cursor)
            
            conn.commit()
            logger.info("Conversation storage schema initialized")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to initialize conversation schema: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
    
    def _create_conversations_schema(self, cursor):
        """Create conversations table schema."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_message_at TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                metadata TEXT,
                UNIQUE(user_id, chat_id)
            )
        """)
        cursor.execute(query)
    
    def _create_messages_schema(self, cursor):
        """Create conversation_messages table schema."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                tokens INTEGER,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        cursor.execute(query)
    
    def _create_shares_schema(self, cursor):
        """Create conversation_shares table schema."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS conversation_shares (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                owner_user_id TEXT NOT NULL,
                shared_with_user_id TEXT,
                share_token TEXT NOT NULL UNIQUE,
                permission TEXT NOT NULL CHECK(permission IN ('read_only', 'editable')),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        cursor.execute(query)
    
    def _create_templates_schema(self, cursor):
        """Create conversation_templates and quick_replies table schemas."""
        # Conversation templates table
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS conversation_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                initial_messages TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(query)
        
        # Quick replies table
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS quick_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                action TEXT NOT NULL,
                order_index INTEGER DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (template_id) REFERENCES conversation_templates(id) ON DELETE CASCADE
            )
        """)
        cursor.execute(query)
    
    def _create_prompt_templates_schema(self, cursor):
        """Create prompt_templates table schema."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS prompt_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                conversation_id INTEGER,
                template_name TEXT NOT NULL,
                template_content TEXT NOT NULL,
                template_type TEXT NOT NULL DEFAULT 'summarization',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        cursor.execute(query)
    
    def _create_ab_tests_schema(self, cursor):
        """Create AB testing tables schema."""
        # AB tests table
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS ab_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                control_config TEXT NOT NULL,
                variant_config TEXT NOT NULL,
                traffic_split REAL NOT NULL DEFAULT 0.5 CHECK(traffic_split >= 0 AND traffic_split <= 1),
                active BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(query)
        
        # AB test assignments table
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS ab_test_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                conversation_id INTEGER NOT NULL,
                variant TEXT NOT NULL CHECK(variant IN ('control', 'variant')),
                assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (test_id) REFERENCES ab_tests(id) ON DELETE CASCADE,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                UNIQUE(test_id, conversation_id)
            )
        """)
        cursor.execute(query)
        
        # AB test metrics table
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS ab_test_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                conversation_id INTEGER NOT NULL,
                variant TEXT NOT NULL CHECK(variant IN ('control', 'variant')),
                response_time_ms INTEGER,
                tokens_used INTEGER,
                user_satisfaction_score REAL,
                error_occurred BOOLEAN DEFAULT 0,
                metadata TEXT,
                recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (test_id) REFERENCES ab_tests(id) ON DELETE CASCADE,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        cursor.execute(query)
    
    def _create_indexes(self, cursor):
        """Create all indexes for efficient queries."""
        # Conversations indexes
        cursor.execute(self._normalize_sql(
            "CREATE INDEX IF NOT EXISTS idx_conversations_user_chat "
            "ON conversations(user_id, chat_id)"
        ))
        cursor.execute(self._normalize_sql(
            "CREATE INDEX IF NOT EXISTS idx_conversations_updated "
            "ON conversations(updated_at)"
        ))
        
        # Messages indexes
        cursor.execute(self._normalize_sql(
            "CREATE INDEX IF NOT EXISTS idx_messages_conversation "
            "ON conversation_messages(conversation_id, created_at)"
        ))
        
        # Shares indexes
        cursor.execute(self._normalize_sql(
            "CREATE INDEX IF NOT EXISTS idx_shares_conversation "
            "ON conversation_shares(conversation_id)"
        ))
        cursor.execute(self._normalize_sql(
            "CREATE INDEX IF NOT EXISTS idx_shares_token "
            "ON conversation_shares(share_token)"
        ))
        cursor.execute(self._normalize_sql(
            "CREATE INDEX IF NOT EXISTS idx_shares_shared_with "
            "ON conversation_shares(shared_with_user_id)"
        ))
        cursor.execute(self._normalize_sql(
            "CREATE INDEX IF NOT EXISTS idx_shares_owner "
            "ON conversation_shares(owner_user_id)"
        ))
        
        # Templates indexes
        cursor.execute(self._normalize_sql(
            "CREATE INDEX IF NOT EXISTS idx_templates_user "
            "ON conversation_templates(user_id)"
        ))
        cursor.execute(self._normalize_sql(
            "CREATE INDEX IF NOT EXISTS idx_quick_replies_template "
            "ON quick_replies(template_id)"
        ))
        
        # Prompt templates indexes
        cursor.execute(self._normalize_sql(
            "CREATE INDEX IF NOT EXISTS idx_prompt_templates_user "
            "ON prompt_templates(user_id, template_type)"
        ))
        cursor.execute(self._normalize_sql(
            "CREATE INDEX IF NOT EXISTS idx_prompt_templates_conversation "
            "ON prompt_templates(conversation_id, template_type)"
        ))
        
        # AB testing indexes
        cursor.execute(self._normalize_sql(
            "CREATE INDEX IF NOT EXISTS idx_ab_tests_active "
            "ON ab_tests(active)"
        ))
        cursor.execute(self._normalize_sql(
            "CREATE INDEX IF NOT EXISTS idx_ab_assignments_test_conversation "
            "ON ab_test_assignments(test_id, conversation_id)"
        ))
        cursor.execute(self._normalize_sql(
            "CREATE INDEX IF NOT EXISTS idx_ab_metrics_test_variant "
            "ON ab_test_metrics(test_id, variant, recorded_at)"
        ))
