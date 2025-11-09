"""
Audio format conversion utility for Telegram voice messages.

Converts PCM/WAV audio to OGG/OPUS format (Telegram's preferred format),
with support for duration limits, quality optimization, and compression.
"""
import os
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Telegram voice message constraints
TELEGRAM_MAX_DURATION_SECONDS = 60  # ~1 minute maximum
TELEGRAM_RECOMMENDED_BITRATE = 64000  # 64 kbps
TELEGRAM_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB (general Telegram limit)


class AudioConversionError(Exception):
    """Exception raised for audio conversion errors."""
    pass


class AudioConverter:
    """Base audio converter class."""
    
    def __init__(self):
        """Initialize the audio converter."""
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check if required dependencies (ffmpeg) are available."""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                raise AudioConversionError("ffmpeg is not available or not working properly")
        except FileNotFoundError:
            raise AudioConversionError(
                "ffmpeg is not installed. Please install ffmpeg:\n"
                "  Ubuntu/Debian: sudo apt-get install ffmpeg\n"
                "  macOS: brew install ffmpeg\n"
                "  Windows: Download from https://ffmpeg.org/download.html"
            )
        except subprocess.TimeoutExpired:
            raise AudioConversionError("ffmpeg check timed out")
    
    def get_audio_duration(self, audio_path: str) -> float:
        """
        Get the duration of an audio file in seconds.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Duration in seconds
            
        Raises:
            AudioConversionError: If duration cannot be determined
        """
        if not os.path.exists(audio_path):
            raise AudioConversionError(f"Audio file not found: {audio_path}")
        
        try:
            result = subprocess.run(
                [
                    'ffprobe',
                    '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    audio_path
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                raise AudioConversionError(f"Failed to get duration: {result.stderr}")
            
            duration = float(result.stdout.strip())
            return duration
        except FileNotFoundError:
            raise AudioConversionError("ffprobe is not installed (part of ffmpeg)")
        except (ValueError, subprocess.TimeoutExpired) as e:
            raise AudioConversionError(f"Failed to get audio duration: {str(e)}")
    
    def convert_to_opus(self, input_path: str, output_path: str, 
                       bitrate: int = 64000, 
                       sample_rate: int = 48000) -> bool:
        """
        Convert audio file to OPUS format.
        
        Args:
            input_path: Path to input audio file
            output_path: Path to output OPUS file
            bitrate: Audio bitrate in bits per second (default: 64000)
            sample_rate: Sample rate in Hz (default: 48000)
            
        Returns:
            True if conversion successful
            
        Raises:
            AudioConversionError: If conversion fails
        """
        if not os.path.exists(input_path):
            raise AudioConversionError(f"Input file not found: {input_path}")
        
        try:
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
            
            # Use ffmpeg to convert to OPUS
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-c:a', 'libopus',
                '-b:a', str(bitrate),
                '-ar', str(sample_rate),
                '-y',  # Overwrite output file
                output_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.error(f"ffmpeg error: {result.stderr}")
                raise AudioConversionError(
                    f"Conversion failed: {result.stderr[:200]}"
                )
            
            if not os.path.exists(output_path):
                raise AudioConversionError("Output file was not created")
            
            logger.info(f"Successfully converted {input_path} to {output_path}")
            return True
            
        except subprocess.TimeoutExpired:
            raise AudioConversionError("Audio conversion timed out")
        except Exception as e:
            raise AudioConversionError(f"Audio conversion failed: {str(e)}")
    
    def convert_to_ogg_opus(self, input_path: str, output_path: str,
                           bitrate: int = 64000,
                           sample_rate: int = 48000) -> bool:
        """
        Convert audio file to OGG/OPUS format.
        
        Args:
            input_path: Path to input audio file
            output_path: Path to output OGG file
            bitrate: Audio bitrate in bits per second (default: 64000)
            sample_rate: Sample rate in Hz (default: 48000)
            
        Returns:
            True if conversion successful
            
        Raises:
            AudioConversionError: If conversion fails
        """
        # Ensure output has .ogg extension
        if not output_path.endswith(('.ogg', '.opus')):
            output_path = output_path.rsplit('.', 1)[0] + '.ogg'
        
        return self.convert_to_opus(input_path, output_path, bitrate, sample_rate)


class TelegramAudioConverter(AudioConverter):
    """Audio converter optimized for Telegram voice messages."""
    
    def convert_for_telegram(self, input_path: str, output_path: str,
                            bitrate: int = TELEGRAM_RECOMMENDED_BITRATE,
                            compress: bool = False,
                            max_duration: int = TELEGRAM_MAX_DURATION_SECONDS) -> bool:
        """
        Convert audio for Telegram voice messages.
        
        Handles:
        - Format conversion to OGG/OPUS
        - Duration limit enforcement (~1 minute)
        - Quality optimization
        - Optional compression
        
        Args:
            input_path: Path to input audio file (PCM/WAV)
            output_path: Path to output OGG file
            bitrate: Audio bitrate in bits per second
            compress: Whether to apply additional compression
            max_duration: Maximum duration in seconds (default: 60)
            
        Returns:
            True if conversion successful
            
        Raises:
            AudioConversionError: If conversion fails
        """
        if not os.path.exists(input_path):
            raise AudioConversionError(f"Input file not found: {input_path}")
        
        try:
            # Check input duration
            duration = self.get_audio_duration(input_path)
            logger.info(f"Input audio duration: {duration:.2f} seconds")
            
            # Adjust bitrate for compression
            if compress:
                bitrate = max(32000, bitrate // 2)  # Reduce bitrate for compression
                logger.info(f"Compression enabled, using bitrate: {bitrate}")
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
            
            # Build ffmpeg command
            cmd = [
                'ffmpeg',
                '-i', input_path,
            ]
            
            # Truncate if duration exceeds limit
            if duration > max_duration:
                logger.warning(
                    f"Audio duration ({duration:.2f}s) exceeds Telegram limit "
                    f"({max_duration}s). Truncating to {max_duration} seconds."
                )
                cmd.extend(['-t', str(max_duration)])
            
            # Add audio encoding options
            cmd.extend([
                '-c:a', 'libopus',
                '-b:a', str(bitrate),
                '-ar', '48000',  # Telegram recommended sample rate
                '-ac', '1',  # Mono (voice messages are typically mono)
                '-application', 'voip',  # Optimize for voice
                '-y',  # Overwrite output
                output_path
            ])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120  # Allow more time for long files
            )
            
            if result.returncode != 0:
                logger.error(f"ffmpeg error: {result.stderr}")
                raise AudioConversionError(
                    f"Telegram audio conversion failed: {result.stderr[:200]}"
                )
            
            if not os.path.exists(output_path):
                raise AudioConversionError("Output file was not created")
            
            # Verify output duration
            output_duration = self.get_audio_duration(output_path)
            if output_duration > max_duration:
                logger.warning(
                    f"Output duration ({output_duration:.2f}s) still exceeds limit. "
                    "File may need additional processing."
                )
            
            # Check file size
            file_size = os.path.getsize(output_path)
            if file_size > TELEGRAM_MAX_FILE_SIZE:
                logger.warning(
                    f"Output file size ({file_size} bytes) exceeds Telegram limit "
                    f"({TELEGRAM_MAX_FILE_SIZE} bytes)"
                )
            
            logger.info(
                f"Successfully converted {input_path} to Telegram format "
                f"({output_duration:.2f}s, {file_size} bytes)"
            )
            return True
            
        except subprocess.TimeoutExpired:
            raise AudioConversionError("Audio conversion timed out")
        except AudioConversionError:
            raise
        except Exception as e:
            raise AudioConversionError(f"Telegram audio conversion failed: {str(e)}")
    
    def convert_pcm_to_ogg(self, pcm_path: str, output_path: str,
                          sample_rate: int = 16000,
                          channels: int = 1,
                          sample_width: int = 2) -> bool:
        """
        Convert raw PCM audio to OGG/OPUS format.
        
        Args:
            pcm_path: Path to raw PCM file
            output_path: Path to output OGG file
            sample_rate: Sample rate in Hz (default: 16000)
            channels: Number of channels (1=mono, 2=stereo, default: 1)
            sample_width: Sample width in bytes (1=8-bit, 2=16-bit, default: 2)
            
        Returns:
            True if conversion successful
            
        Raises:
            AudioConversionError: If conversion fails
        """
        if not os.path.exists(pcm_path):
            raise AudioConversionError(f"PCM file not found: {pcm_path}")
        
        try:
            # Determine PCM format for ffmpeg
            if sample_width == 1:
                pcm_format = 'u8'  # Unsigned 8-bit
            elif sample_width == 2:
                pcm_format = 's16le'  # Signed 16-bit little-endian
            elif sample_width == 4:
                pcm_format = 's32le'  # Signed 32-bit little-endian
            else:
                raise AudioConversionError(f"Unsupported sample width: {sample_width}")
            
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
            
            # Use ffmpeg to convert PCM to OGG/OPUS
            cmd = [
                'ffmpeg',
                '-f', f's{pcm_format}',
                '-ar', str(sample_rate),
                '-ac', str(channels),
                '-i', pcm_path,
                '-c:a', 'libopus',
                '-b:a', str(TELEGRAM_RECOMMENDED_BITRATE),
                '-ar', '48000',
                '-ac', '1',
                '-application', 'voip',
                '-y',
                output_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                logger.error(f"ffmpeg error: {result.stderr}")
                raise AudioConversionError(
                    f"PCM to OGG conversion failed: {result.stderr[:200]}"
                )
            
            if not os.path.exists(output_path):
                raise AudioConversionError("Output file was not created")
            
            logger.info(f"Successfully converted PCM {pcm_path} to {output_path}")
            return True
            
        except subprocess.TimeoutExpired:
            raise AudioConversionError("PCM conversion timed out")
        except AudioConversionError:
            raise
        except Exception as e:
            raise AudioConversionError(f"PCM to OGG conversion failed: {str(e)}")
