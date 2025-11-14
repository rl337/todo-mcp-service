"""Conversation storage modules."""

# Re-export ConversationStorage from the main module file
# This allows imports like: from todorama.conversation_storage import ConversationStorage
import importlib.util
import os

# Import ConversationStorage directly from the .py file to avoid circular imports
module_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'conversation_storage.py')
spec = importlib.util.spec_from_file_location("todorama.conversation_storage_module", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

ConversationStorage = module.ConversationStorage

__all__ = ['ConversationStorage']
