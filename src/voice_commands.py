"""
Voice command recognition for bot control.

Provides:
- Speech-to-text (STT) conversion using various backends
- Command keyword detection and intent classification
- Command parsing with parameter extraction
- Support for commands: new conversation, clear history, change language
"""
import os
import logging
import re
import time
from typing import Optional, Dict, Any
from enum import Enum

try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    SPEECH_RECOGNITION_AVAILABLE = False
    sr = None

logger = logging.getLogger(__name__)

# Lazy import for cost tracking to avoid circular imports
_cost_tracker = None

def _get_cost_tracker():
    """Get cost tracker instance (lazy initialization)."""
    global _cost_tracker
    if _cost_tracker is None:
        try:
            from cost_tracking import CostTracker, ServiceType
            _cost_tracker = CostTracker()
        except Exception as e:
            logger.warning(f"Cost tracking not available: {e}")
            _cost_tracker = False  # Use False to indicate unavailable
    return _cost_tracker if _cost_tracker is not False else None


class CommandType(Enum):
    """Types of voice commands."""
    NEW_CONVERSATION = "new_conversation"
    CLEAR_HISTORY = "clear_history"
    CHANGE_LANGUAGE = "change_language"
    UNKNOWN = "unknown"


class VoiceCommand:
    """Represents a recognized voice command."""
    
    def __init__(
        self,
        command_type: CommandType,
        text: str,
        confidence: float = 1.0,
        parameters: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize voice command.
        
        Args:
            command_type: Type of command recognized
            text: Original transcribed text
            confidence: Confidence score (0.0 to 1.0)
            parameters: Additional parameters extracted from command
        """
        self.command_type = command_type
        self.text = text
        self.confidence = confidence
        self.parameters = parameters or {}


class VoiceCommandError(Exception):
    """Exception raised for voice command recognition errors."""
    pass


class VoiceCommandRecognizer:
    """Recognizes voice commands from audio input."""
    
    def __init__(self, stt_engine: str = "google"):
        """
        Initialize voice command recognizer.
        
        Args:
            stt_engine: Speech-to-text engine to use ('google', 'sphinx', etc.)
        """
        self.stt_engine = stt_engine
        
        if not SPEECH_RECOGNITION_AVAILABLE:
            logger.warning(
                "speech_recognition not installed. Voice command recognition will be disabled."
            )
            self.recognizer = None
        else:
            self.recognizer = sr.Recognizer()
            logger.info(f"Voice command recognizer initialized with engine: {stt_engine}")
        
        # Command keywords for detection
        self.command_keywords = {
            CommandType.NEW_CONVERSATION: [
                "new conversation", "start new", "begin new", "new chat",
                "start conversation", "begin conversation"
            ],
            CommandType.CLEAR_HISTORY: [
                "clear history", "delete history", "erase history",
                "clear chat", "delete chat", "clear conversation"
            ],
            CommandType.CHANGE_LANGUAGE: [
                "change language", "switch language", "set language",
                "switch to", "change to", "set to", "language"
            ]
        }
    
    def recognize_command(self, audio_path: str, user_id: Optional[str] = None, 
                         conversation_id: Optional[int] = None) -> VoiceCommand:
        """
        Recognize command from audio file.
        
        Args:
            audio_path: Path to audio file (WAV, FLAC, etc.)
            user_id: Optional user ID for cost tracking
            conversation_id: Optional conversation ID for cost tracking
            
        Returns:
            VoiceCommand object with recognized command
            
        Raises:
            VoiceCommandError: If recognition fails or file not found
        """
        if not self.recognizer:
            raise VoiceCommandError(
                "Speech recognition not available. Install speech_recognition package."
            )
        
        if not os.path.exists(audio_path):
            raise VoiceCommandError(f"Audio file not found: {audio_path}")
        
        # Get audio duration for cost tracking
        duration_seconds = None
        try:
            from audio_converter import AudioConverter
            converter = AudioConverter()
            duration_seconds = converter.get_audio_duration(audio_path)
        except Exception as e:
            logger.debug(f"Could not get audio duration: {e}")
        
        start_time = time.time()
        
        try:
            # Load audio file
            with sr.AudioFile(audio_path) as source:
                audio = self.recognizer.record(source)
            
            # Perform speech-to-text
            try:
                if self.stt_engine == "google":
                    text = self.recognizer.recognize_google(audio)
                elif self.stt_engine == "sphinx":
                    text = self.recognizer.recognize_sphinx(audio)
                else:
                    text = self.recognizer.recognize_google(audio)
                
                logger.debug(f"Transcribed text: {text}")
                
            except sr.UnknownValueError:
                raise VoiceCommandError(
                    "Could not understand audio. Please speak clearly."
                )
            except sr.RequestError as e:
                raise VoiceCommandError(
                    f"Speech recognition service error: {str(e)}"
                )
            
            # Track cost if user_id is provided
            if user_id and duration_seconds:
                try:
                    cost_tracker = _get_cost_tracker()
                    if cost_tracker:
                        from cost_tracking import ServiceType
                        cost_tracker.record_cost(
                            service_type=ServiceType.STT,
                            user_id=user_id,
                            conversation_id=conversation_id,
                            duration_seconds=duration_seconds,
                            metadata={
                                "model": self.stt_engine,
                                "audio_path": audio_path,
                                "recognition_time": time.time() - start_time
                            }
                        )
                except Exception as e:
                    # Don't fail the request if cost tracking fails
                    logger.warning(f"Failed to track STT cost: {e}")
            
            # Parse command from text
            command = self._parse_command(text)
            return command
            
        except VoiceCommandError:
            raise
        except Exception as e:
            logger.error(f"Error recognizing voice command: {str(e)}", exc_info=True)
            raise VoiceCommandError(f"Failed to recognize command: {str(e)}")
    
    def _parse_command(self, text: str) -> VoiceCommand:
        """
        Parse command from transcribed text.
        
        Args:
            text: Transcribed text from STT
            
        Returns:
            VoiceCommand object
        """
        text_lower = text.lower().strip()
        
        # Try to match each command type
        for command_type, keywords in self.command_keywords.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    # Extract parameters if needed
                    parameters = {}
                    
                    if command_type == CommandType.CHANGE_LANGUAGE:
                        # Try to extract language name
                        language = self._extract_language(text_lower)
                        if language:
                            parameters["language"] = language
                    
                    return VoiceCommand(
                        command_type=command_type,
                        text=text,
                        confidence=0.8,  # Default confidence
                        parameters=parameters
                    )
        
        # No command matched
        return VoiceCommand(
            command_type=CommandType.UNKNOWN,
            text=text,
            confidence=0.0
        )
    
    def _extract_language(self, text: str) -> Optional[str]:
        """
        Extract language name from text.
        
        Args:
            text: Lowercase text
            
        Returns:
            Language name if found, None otherwise
        """
        # Common language names
        languages = [
            "english", "spanish", "french", "german", "italian",
            "portuguese", "chinese", "japanese", "korean", "russian",
            "arabic", "hindi", "dutch", "swedish", "norwegian",
            "danish", "finnish", "polish", "turkish", "greek"
        ]
        
        for language in languages:
            if language in text:
                return language.capitalize()
        
        # Try to extract after common phrases
        patterns = [
            r"(?:to|as)\s+([a-z]+)",
            r"language\s+(?:to|as|is)\s+([a-z]+)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                potential_language = match.group(1)
                if potential_language in languages:
                    return potential_language.capitalize()
        
        return None
    
    def recognize_command_from_bytes(self, audio_bytes: bytes, format: str = "wav",
                                    user_id: Optional[str] = None,
                                    conversation_id: Optional[int] = None) -> VoiceCommand:
        """
        Recognize command from audio bytes.
        
        Args:
            audio_bytes: Audio data as bytes
            format: Audio format ('wav', 'flac', etc.)
            user_id: Optional user ID for cost tracking
            conversation_id: Optional conversation ID for cost tracking
            
        Returns:
            VoiceCommand object
            
        Raises:
            VoiceCommandError: If recognition fails
        """
        if not self.recognizer:
            raise VoiceCommandError(
                "Speech recognition not available. Install speech_recognition package."
            )
        
        start_time = time.time()
        
        try:
            # Create AudioData from bytes
            import io
            audio_file = io.BytesIO(audio_bytes)
            audio_data = sr.AudioData(audio_bytes, 16000, 2)  # Default: 16kHz, 16-bit
            
            # Estimate duration (rough: assume 16kHz, 16-bit, mono = 2 bytes per sample)
            # Duration = len(bytes) / (sample_rate * bytes_per_sample)
            duration_seconds = len(audio_bytes) / (16000 * 2) if audio_bytes else None
            
            # Perform speech-to-text
            try:
                if self.stt_engine == "google":
                    text = self.recognizer.recognize_google(audio_data)
                elif self.stt_engine == "sphinx":
                    text = self.recognizer.recognize_sphinx(audio_data)
                else:
                    text = self.recognizer.recognize_google(audio_data)
                
                logger.debug(f"Transcribed text: {text}")
                
            except sr.UnknownValueError:
                raise VoiceCommandError(
                    "Could not understand audio. Please speak clearly."
                )
            except sr.RequestError as e:
                raise VoiceCommandError(
                    f"Speech recognition service error: {str(e)}"
                )
            
            # Track cost if user_id is provided
            if user_id and duration_seconds:
                try:
                    cost_tracker = _get_cost_tracker()
                    if cost_tracker:
                        from cost_tracking import ServiceType
                        cost_tracker.record_cost(
                            service_type=ServiceType.STT,
                            user_id=user_id,
                            conversation_id=conversation_id,
                            duration_seconds=duration_seconds,
                            metadata={
                                "model": self.stt_engine,
                                "format": format,
                                "recognition_time": time.time() - start_time,
                                "audio_bytes": len(audio_bytes)
                            }
                        )
                except Exception as e:
                    # Don't fail the request if cost tracking fails
                    logger.warning(f"Failed to track STT cost: {e}")
            
            # Parse command from text
            command = self._parse_command(text)
            return command
            
        except VoiceCommandError:
            raise
        except Exception as e:
            logger.error(f"Error recognizing voice command from bytes: {str(e)}", exc_info=True)
            raise VoiceCommandError(f"Failed to recognize command: {str(e)}")
