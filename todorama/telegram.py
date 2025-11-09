"""
Telegram integration for sending voice messages and user feedback.

Provides:
- Voice message sending to Telegram users
- LLM response streaming to Telegram (character-by-character updates)
- Telegram API rate limit handling with exponential backoff
- Retry logic for failed sends
- User feedback (typing indicators, status messages)
- Automatic audio conversion to Telegram format (OGG/OPUS)
- Graceful handling of message interruptions during streaming
"""
import os
import logging
import asyncio
import time
from typing import Optional, Dict, Any
from pathlib import Path

try:
    from telegram import Bot
    from telegram.error import TelegramError, RetryAfter, NetworkError
    TELEGRAM_SDK_AVAILABLE = True
except ImportError:
    TELEGRAM_SDK_AVAILABLE = False
    Bot = None
    TelegramError = Exception
    RetryAfter = Exception
    NetworkError = Exception

from src.audio_converter import TelegramAudioConverter, AudioConversionError

logger = logging.getLogger(__name__)


class TelegramRateLimitError(Exception):
    """Exception raised when Telegram API rate limit is exceeded."""
    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class TelegramBot:
    """Handles sending voice messages and user feedback via Telegram."""
    
    def __init__(self, bot_token: Optional[str] = None):
        """
        Initialize Telegram bot.
        
        Args:
            bot_token: Telegram bot token (optional, can be set via TELEGRAM_BOT_TOKEN env var)
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.bot = None
        
        if TELEGRAM_SDK_AVAILABLE and self.bot_token:
            try:
                self.bot = Bot(token=self.bot_token)
                logger.info("Telegram bot initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Telegram bot: {str(e)}")
        else:
            if not TELEGRAM_SDK_AVAILABLE:
                logger.warning("python-telegram-bot not installed. Telegram functionality will be disabled.")
            if not self.bot_token:
                logger.warning("TELEGRAM_BOT_TOKEN not set. Telegram functionality will be disabled.")
        
        self.audio_converter = TelegramAudioConverter()
    
    async def send_typing_indicator(self, chat_id: int) -> bool:
        """
        Send typing indicator to show bot is processing.
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.bot:
            logger.debug("Telegram bot not available, skipping typing indicator")
            return False
        
        try:
            await self.bot.send_chat_action(chat_id=chat_id, action="typing")
            return True
        except TelegramError as e:
            logger.error(f"Failed to send typing indicator: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending typing indicator: {str(e)}", exc_info=True)
            return False
    
    async def send_status_message(self, chat_id: int, message: str) -> bool:
        """
        Send a status message to the user.
        
        Args:
            chat_id: Telegram chat ID
            message: Status message text
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.bot:
            logger.debug("Telegram bot not available, skipping status message")
            return False
        
        try:
            await self.bot.send_message(chat_id=chat_id, text=message)
            logger.info(f"Status message sent to chat {chat_id}: {message[:50]}")
            return True
        except TelegramError as e:
            logger.error(f"Failed to send status message: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending status message: {str(e)}", exc_info=True)
            return False
    
    async def stream_text_message(
        self,
        chat_id: int,
        text_generator,
        initial_text: str = "...",
        update_interval: float = 0.1,
        min_update_length: int = 5
    ) -> Optional[int]:
        """
        Stream a text message character-by-character to Telegram.
        
        Sends an initial message, then updates it as text is generated.
        Improves perceived response time by showing partial responses immediately.
        
        Args:
            chat_id: Telegram chat ID
            text_generator: Async generator or iterable that yields text chunks
            initial_text: Initial text to show while waiting for first chunk
            update_interval: Minimum time (seconds) between message updates
            min_update_length: Minimum characters to accumulate before updating
            
        Returns:
            Message ID if successful, None otherwise
            
        Raises:
            Exception: If message streaming fails
        """
        if not self.bot:
            logger.debug("Telegram bot not available, skipping text streaming")
            return None
        
        message_id = None
        accumulated_text = ""
        last_update_time = 0
        
        try:
            # Send initial message
            sent_message = await self.bot.send_message(chat_id=chat_id, text=initial_text)
            message_id = sent_message.message_id
            logger.debug(f"Initial message sent to chat {chat_id} with message_id {message_id}")
            
            # Handle interruptions gracefully
            interrupted = False
            
            # Stream text chunks
            async for chunk in text_generator:
                if chunk is None:
                    break
                    
                accumulated_text += chunk
                current_time = time.time()
                
                # Update message if we have enough text and enough time has passed
                if (len(accumulated_text) >= min_update_length and 
                    (current_time - last_update_time) >= update_interval):
                    try:
                        # Telegram has a 4096 character limit per message
                        # Truncate if needed, but try to keep recent context
                        display_text = accumulated_text
                        if len(display_text) > 4096:
                            # Keep last ~4000 characters to show recent content
                            display_text = "..." + display_text[-4000:]
                        
                        await self.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=display_text
                        )
                        last_update_time = current_time
                        logger.debug(f"Updated message {message_id} with {len(display_text)} characters")
                    except TelegramError as e:
                        # Handle common errors gracefully
                        error_str = str(e).lower()
                        if "message is not modified" in error_str:
                            # Message content unchanged - not an error, just skip update
                            logger.debug(f"Message {message_id} unchanged, skipping update")
                            continue
                        elif "message to edit not found" in error_str:
                            # Message was deleted - can't continue streaming
                            logger.warning(f"Message {message_id} was deleted, stopping stream")
                            interrupted = True
                            break
                        else:
                            logger.warning(f"Failed to update message {message_id}: {str(e)}")
                            # Continue trying with next chunk
                            continue
            
            # Final update with complete text
            if accumulated_text and not interrupted:
                final_text = accumulated_text
                if len(final_text) > 4096:
                    # Telegram limit - send as multiple messages or truncate
                    final_text = accumulated_text[:4093] + "..."
                
                try:
                    await self.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=final_text
                    )
                    logger.info(f"Final message update sent to chat {chat_id} ({len(final_text)} characters)")
                except TelegramError as e:
                    error_str = str(e).lower()
                    if "message is not modified" not in error_str:
                        logger.warning(f"Failed to send final message update: {str(e)}")
            
            return message_id
            
        except TelegramError as e:
            logger.error(f"Telegram error during text streaming: {str(e)}", exc_info=True)
            # Try to send error message if we have a message_id
            if message_id:
                try:
                    await self.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=f"{accumulated_text}\n\n?? Error: Message delivery interrupted."
                    )
                except:
                    pass
            return None
        except Exception as e:
            logger.error(f"Unexpected error during text streaming: {str(e)}", exc_info=True)
            # Try to send error message if we have a message_id
            if message_id:
                try:
                    await self.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=f"{accumulated_text}\n\n?? Error: Unexpected error occurred."
                    )
                except:
                    pass
            return None
    
    def _convert_audio_if_needed(self, audio_path: str) -> str:
        """
        Convert audio to Telegram format (OGG/OPUS) if needed.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Path to converted audio file (same as input if already in correct format)
            
        Raises:
            AudioConversionError: If conversion fails
        """
        audio_path_obj = Path(audio_path)
        
        # Check if file is already in OGG format
        if audio_path_obj.suffix.lower() in ('.ogg', '.opus'):
            logger.debug(f"Audio file {audio_path} is already in OGG format")
            return audio_path
        
        # Convert to OGG
        output_path = audio_path_obj.with_suffix('.ogg')
        
        try:
            logger.info(f"Converting {audio_path} to Telegram format (OGG/OPUS)")
            success = self.audio_converter.convert_for_telegram(
                input_path=audio_path,
                output_path=str(output_path)
            )
            
            if not success:
                raise AudioConversionError("Audio conversion returned False")
            
            logger.info(f"Audio conversion successful: {output_path}")
            return str(output_path)
            
        except AudioConversionError:
            raise
        except Exception as e:
            raise AudioConversionError(f"Audio conversion failed: {str(e)}")
    
    async def send_voice_message(
        self,
        chat_id: int,
        audio_path: str,
        caption: Optional[str] = None,
        show_typing: bool = True,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> bool:
        """
        Send a voice message to a Telegram chat.
        
        Handles:
        - Audio format conversion (to OGG/OPUS if needed)
        - Telegram API rate limits with exponential backoff
        - Retry logic for failed sends
        - User feedback (typing indicators)
        
        Args:
            chat_id: Telegram chat ID
            audio_path: Path to audio file (will be converted to OGG/OPUS if needed)
            caption: Optional caption for the voice message
            show_typing: Whether to show typing indicator before sending
            max_retries: Maximum number of retry attempts
            retry_delay: Initial retry delay in seconds (exponentially increases)
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.bot:
            logger.debug("Telegram bot not available, skipping voice message")
            return False
        
        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            return False
        
        # Send typing indicator if requested
        if show_typing:
            await self.send_typing_indicator(chat_id)
        
        # Convert audio to Telegram format if needed
        converted_audio_path = None
        try:
            converted_audio_path = self._convert_audio_if_needed(audio_path)
        except AudioConversionError as e:
            logger.error(f"Audio conversion failed: {str(e)}")
            await self.send_status_message(
                chat_id,
                "? Failed to process audio. Please try again."
            )
            return False
        
        # Track if we created a converted file (for cleanup)
        file_was_converted = (converted_audio_path != audio_path)
        
        # Retry logic with exponential backoff
        last_error = None
        current_delay = retry_delay
        
        for attempt in range(1, max_retries + 1):
            # Open file for each attempt to ensure clean state
            try:
                with open(converted_audio_path, 'rb') as audio_file:
                    # Prepare voice message parameters
                    voice_params = {
                        "chat_id": chat_id,
                        "voice": audio_file
                    }
                    
                    if caption:
                        voice_params["caption"] = caption
                    
                    # Send voice message
                    await self.bot.send_voice(**voice_params)
                    
                    logger.info(
                        f"Voice message sent successfully to chat {chat_id} "
                        f"(attempt {attempt}/{max_retries})"
                    )
                    
                    # Clean up converted file if we created it
                    if file_was_converted and os.path.exists(converted_audio_path):
                        try:
                            os.remove(converted_audio_path)
                            logger.debug(f"Cleaned up converted audio file: {converted_audio_path}")
                        except Exception as e:
                            logger.warning(f"Failed to clean up converted audio file: {str(e)}")
                    
                    return True
                    
            except RetryAfter as e:
                # Rate limit exceeded - wait for retry_after seconds
                retry_after = getattr(e, 'retry_after', current_delay * 2)
                logger.warning(
                    f"Telegram rate limit exceeded for chat {chat_id}. "
                    f"Retrying after {retry_after} seconds (attempt {attempt}/{max_retries})"
                )
                
                # Send status message to user about delay
                if attempt == 1:
                    await self.send_status_message(
                        chat_id,
                        f"? Processing your request... (may take a moment)"
                    )
                
                await asyncio.sleep(retry_after)
                current_delay = retry_after
                last_error = e
                
            except (NetworkError, TelegramError) as e:
                # Network or Telegram API error - retry with exponential backoff
                logger.warning(
                    f"Telegram API error for chat {chat_id} (attempt {attempt}/{max_retries}): {str(e)}"
                )
                
                if attempt < max_retries:
                    await asyncio.sleep(current_delay)
                    current_delay *= 2  # Exponential backoff
                else:
                    last_error = e
                    
            except Exception as e:
                # Unexpected error - log and fail
                logger.error(
                    f"Unexpected error sending voice message to chat {chat_id}: {str(e)}",
                    exc_info=True
                )
                last_error = e
                break
        
        # All retries failed
        logger.error(
            f"Failed to send voice message to chat {chat_id} after {max_retries} attempts. "
            f"Last error: {str(last_error)}"
        )
        
        # Send error message to user
        await self.send_status_message(
            chat_id,
            "? Failed to send voice message. Please try again later."
        )
        
        # Clean up converted file if we created it
        if file_was_converted and converted_audio_path and os.path.exists(converted_audio_path):
            try:
                os.remove(converted_audio_path)
            except Exception:
                pass
        
        return False
    
    def send_voice_message_sync(
        self,
        chat_id: int,
        audio_path: str,
        caption: Optional[str] = None,
        show_typing: bool = True,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> bool:
        """
        Synchronous wrapper for send_voice_message.
        
        Args:
            chat_id: Telegram chat ID
            audio_path: Path to audio file
            caption: Optional caption for the voice message
            show_typing: Whether to show typing indicator
            max_retries: Maximum number of retry attempts
            retry_delay: Initial retry delay in seconds
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(
            self.send_voice_message(
                chat_id=chat_id,
                audio_path=audio_path,
                caption=caption,
                show_typing=show_typing,
                max_retries=max_retries,
                retry_delay=retry_delay
            )
        )


# Global Telegram bot instance
_telegram_bot: Optional[TelegramBot] = None


def get_telegram_bot() -> Optional[TelegramBot]:
    """Get or create global Telegram bot instance."""
    global _telegram_bot
    if _telegram_bot is None:
        _telegram_bot = TelegramBot()
    return _telegram_bot


def send_voice_message(
    chat_id: int,
    audio_path: str,
    caption: Optional[str] = None,
    show_typing: bool = True,
    max_retries: int = 3
) -> bool:
    """
    Send a voice message to Telegram (convenience function).
    
    Args:
        chat_id: Telegram chat ID
        audio_path: Path to audio file
        caption: Optional caption for the voice message
        show_typing: Whether to show typing indicator
        max_retries: Maximum number of retry attempts
        
    Returns:
        True if sent successfully, False otherwise
    """
    bot = get_telegram_bot()
    if bot:
        return bot.send_voice_message_sync(
            chat_id=chat_id,
            audio_path=audio_path,
            caption=caption,
            show_typing=show_typing,
            max_retries=max_retries
        )
    return False


async def stream_llm_response_to_telegram(
    chat_id: int,
    llm_stream_generator,
    initial_text: str = "Thinking...",
    update_interval: float = 0.1,
    min_update_length: int = 5
) -> Optional[int]:
    """
    Stream LLM response to Telegram (convenience function).
    
    Connects an async LLM stream generator to Telegram message streaming.
    This function provides a simple way to stream LLM responses character-by-character
    to Telegram users, improving perceived response time.
    
    Args:
        chat_id: Telegram chat ID
        llm_stream_generator: Async generator that yields text chunks from LLM
        initial_text: Initial text to show while waiting for first chunk
        update_interval: Minimum time (seconds) between message updates
        min_update_length: Minimum characters to accumulate before updating
        
    Returns:
        Message ID if successful, None otherwise
        
    Example:
        from src.conversation_storage import ConversationStorage
        from src.telegram import stream_llm_response_to_telegram
        
        storage = ConversationStorage()
        messages = [{"role": "user", "content": "Hello!"}]
        stream = storage.stream_llm_response(messages, user_id="user123", chat_id="chat456")
        
        message_id = await stream_llm_response_to_telegram(
            chat_id=123456,
            llm_stream_generator=stream,
            initial_text="Generating response..."
        )
    """
    bot = get_telegram_bot()
    if not bot:
        logger.debug("Telegram bot not available, cannot stream LLM response")
        return None
    
    return await bot.stream_text_message(
        chat_id=chat_id,
        text_generator=llm_stream_generator,
        initial_text=initial_text,
        update_interval=update_interval,
        min_update_length=min_update_length
    )
