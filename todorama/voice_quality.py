"""
Voice message quality scoring and feedback.

Analyzes voice messages for:
- Volume level (too quiet or too loud)
- Background noise detection
- Speech clarity and intelligibility
- Overall quality assessment

Provides feedback and improvement suggestions to users.
"""
import os
import logging
import subprocess
import tempfile
import wave
import struct
from typing import Dict, List, Any, Optional

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None

logger = logging.getLogger(__name__)


class VoiceQualityError(Exception):
    """Exception raised for voice quality analysis errors."""
    pass


class VoiceQualityScorer:
    """Scores voice message quality and provides feedback."""
    
    def __init__(self):
        """Initialize the voice quality scorer."""
        if not NUMPY_AVAILABLE:
            logger.warning(
                "numpy not installed. Voice quality scoring will have limited functionality. "
                "Install numpy for full features: pip install numpy"
            )
    
    def score_voice_message(self, audio_path: str) -> Dict[str, Any]:
        """
        Score the quality of a voice message.
        
        Args:
            audio_path: Path to audio file (WAV, FLAC, OGG, etc.)
            
        Returns:
            Dictionary with:
                - overall_score: Overall quality score (0-100)
                - volume_score: Volume level score (0-100)
                - clarity_score: Speech clarity score (0-100)
                - noise_score: Noise level score (0-100, higher = less noise)
                - feedback: Textual feedback about quality
                - suggestions: List of improvement suggestions
                
        Raises:
            VoiceQualityError: If audio cannot be analyzed
        """
        if not os.path.exists(audio_path):
            raise VoiceQualityError(f"Audio file not found: {audio_path}")
        
        # Convert to WAV if needed for analysis
        wav_path = self._ensure_wav_format(audio_path)
        
        try:
            # Analyze audio using multiple methods
            if NUMPY_AVAILABLE:
                analysis = self._analyze_with_numpy(wav_path)
            else:
                # Fallback to ffprobe-based analysis
                analysis = self._analyze_with_ffprobe(wav_path)
            
            # Calculate scores
            volume_score = self._calculate_volume_score(analysis)
            clarity_score = self._calculate_clarity_score(analysis)
            noise_score = self._calculate_noise_score(analysis)
            overall_score = self._calculate_overall_score(
                volume_score, clarity_score, noise_score
            )
            
            # Generate feedback
            feedback = self._generate_feedback(
                overall_score, volume_score, clarity_score, noise_score, analysis
            )
            suggestions = self._generate_suggestions(
                volume_score, clarity_score, noise_score, analysis
            )
            
            result = {
                "overall_score": int(round(overall_score)),
                "volume_score": int(round(volume_score)),
                "clarity_score": int(round(clarity_score)),
                "noise_score": int(round(noise_score)),
                "feedback": feedback,
                "suggestions": suggestions
            }
            
            logger.debug(f"Voice quality scores for {audio_path}: {result}")
            return result
            
        finally:
            # Clean up temporary WAV file if created
            if wav_path != audio_path and os.path.exists(wav_path):
                try:
                    os.unlink(wav_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary WAV file: {e}")
    
    def _ensure_wav_format(self, audio_path: str) -> str:
        """
        Convert audio to WAV format if needed.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Path to WAV file (same if already WAV, temporary file if converted)
        """
        # If already WAV, return as-is
        if audio_path.lower().endswith('.wav'):
            return audio_path
        
        # Check if ffmpeg is available
        try:
            subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                timeout=5
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # If not WAV and no ffmpeg, raise error
            raise VoiceQualityError(
                f"Cannot analyze non-WAV file {audio_path} without ffmpeg. "
                "Please convert to WAV first or install ffmpeg."
            )
        
        # Convert to WAV using ffmpeg
        temp_dir = os.path.dirname(audio_path) or tempfile.gettempdir()
        temp_wav = tempfile.NamedTemporaryFile(
            suffix='.wav',
            dir=temp_dir,
            delete=False
        )
        temp_wav.close()
        
        try:
            result = subprocess.run(
                [
                    'ffmpeg',
                    '-i', audio_path,
                    '-ar', '16000',  # Resample to 16kHz
                    '-ac', '1',  # Mono
                    '-y',  # Overwrite
                    temp_wav.name
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                os.unlink(temp_wav.name)
                raise VoiceQualityError(
                    f"Failed to convert audio to WAV: {result.stderr[:200]}"
                )
            
            return temp_wav.name
            
        except subprocess.TimeoutExpired:
            if os.path.exists(temp_wav.name):
                os.unlink(temp_wav.name)
            raise VoiceQualityError("Audio conversion timed out")
        except Exception as e:
            if os.path.exists(temp_wav.name):
                os.unlink(temp_wav.name)
            raise VoiceQualityError(f"Failed to convert audio: {str(e)}")
    
    def _analyze_with_numpy(self, wav_path: str) -> Dict[str, Any]:
        """
        Analyze audio using numpy for detailed metrics.
        
        Args:
            wav_path: Path to WAV file
            
        Returns:
            Dictionary with analysis metrics
        """
        try:
            with wave.open(wav_path, 'r') as wav_file:
                sample_rate = wav_file.getframerate()
                num_channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                num_frames = wav_file.getnframes()
                
                # Read audio data
                audio_bytes = wav_file.readframes(num_frames)
                
                # Convert to numpy array
                if sample_width == 1:
                    # 8-bit unsigned
                    dtype = np.uint8
                    audio_data = np.frombuffer(audio_bytes, dtype=dtype).astype(np.float32)
                    audio_data = (audio_data - 128) / 128.0  # Normalize to [-1, 1]
                elif sample_width == 2:
                    # 16-bit signed
                    dtype = np.int16
                    audio_data = np.frombuffer(audio_bytes, dtype=dtype).astype(np.float32)
                    audio_data = audio_data / 32768.0  # Normalize to [-1, 1]
                elif sample_width == 4:
                    # 32-bit signed
                    dtype = np.int32
                    audio_data = np.frombuffer(audio_bytes, dtype=dtype).astype(np.float32)
                    audio_data = audio_data / 2147483648.0  # Normalize to [-1, 1]
                else:
                    raise VoiceQualityError(f"Unsupported sample width: {sample_width}")
                
                # Reshape for multi-channel
                if num_channels > 1:
                    audio_data = audio_data.reshape(-1, num_channels)
                    # Use first channel for mono analysis
                    audio_data = audio_data[:, 0]
                
                # Calculate metrics
                rms = np.sqrt(np.mean(audio_data ** 2))
                peak = np.max(np.abs(audio_data))
                
                # Estimate noise floor (using quiet parts)
                # Assume noise is in the lower amplitude regions
                abs_audio = np.abs(audio_data)
                noise_threshold = np.percentile(abs_audio, 10)  # Bottom 10% as noise estimate
                noise_level = np.mean(abs_audio[abs_audio < noise_threshold * 2])
                
                # Calculate signal-to-noise ratio approximation
                signal_level = np.mean(abs_audio[abs_audio > noise_threshold * 3])
                if noise_level > 0:
                    snr_estimate = 20 * np.log10(signal_level / noise_level) if signal_level > 0 else 0
                else:
                    snr_estimate = 60  # Assume good SNR if no noise detected
                
                # Frequency analysis for clarity
                # Use FFT to analyze frequency content
                fft_data = np.fft.rfft(audio_data)
                magnitude = np.abs(fft_data)
                frequencies = np.fft.rfftfreq(len(audio_data), 1.0 / sample_rate)
                
                # Speech frequencies are typically 85-3400 Hz
                speech_mask = (frequencies >= 85) & (frequencies <= 3400)
                speech_energy = np.sum(magnitude[speech_mask])
                total_energy = np.sum(magnitude)
                
                # Clarity metric: how much energy is in speech frequency range
                speech_ratio = speech_energy / total_energy if total_energy > 0 else 0
                
                # Detect clipping (distortion indicator)
                clipping_ratio = np.sum(np.abs(audio_data) >= 0.95) / len(audio_data)
                
                return {
                    "rms": float(rms),
                    "peak": float(peak),
                    "noise_level": float(noise_level),
                    "signal_level": float(signal_level),
                    "snr_estimate": float(snr_estimate),
                    "speech_ratio": float(speech_ratio),
                    "clipping_ratio": float(clipping_ratio),
                    "sample_rate": sample_rate,
                    "duration": len(audio_data) / sample_rate
                }
                
        except Exception as e:
            logger.error(f"Error analyzing audio with numpy: {e}", exc_info=True)
            raise VoiceQualityError(f"Failed to analyze audio: {str(e)}")
    
    def _analyze_with_ffprobe(self, wav_path: str) -> Dict[str, Any]:
        """
        Analyze audio using ffprobe as fallback when numpy is not available.
        
        Args:
            wav_path: Path to audio file
            
        Returns:
            Dictionary with basic analysis metrics
        """
        try:
            # Get basic audio info
            result = subprocess.run(
                [
                    'ffprobe',
                    '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    wav_path
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            duration = float(result.stdout.strip()) if result.returncode == 0 else 0.0
            
            # Basic analysis - limited without numpy
            return {
                "rms": 0.3,  # Default estimate
                "peak": 0.5,  # Default estimate
                "noise_level": 0.05,  # Default estimate
                "signal_level": 0.3,  # Default estimate
                "snr_estimate": 20.0,  # Default estimate
                "speech_ratio": 0.7,  # Default estimate
                "clipping_ratio": 0.0,  # Default estimate
                "sample_rate": 16000,  # Default
                "duration": duration
            }
            
        except Exception as e:
            logger.error(f"Error analyzing audio with ffprobe: {e}", exc_info=True)
            raise VoiceQualityError(f"Failed to analyze audio: {str(e)}")
    
    def _calculate_volume_score(self, analysis: Dict[str, Any]) -> float:
        """
        Calculate volume score (0-100).
        
        Optimal range: RMS around 0.1-0.5 (normalized)
        Too quiet: RMS < 0.05
        Too loud: RMS > 0.7
        """
        rms = analysis.get("rms", 0.0)
        
        # Optimal volume range
        optimal_min = 0.05
        optimal_max = 0.5
        
        if rms < optimal_min:
            # Too quiet - linear penalty
            score = 100 * (rms / optimal_min)
        elif rms > optimal_max:
            # Too loud - penalty for clipping risk
            if rms > 0.9:
                score = 20  # Very loud, high clipping risk
            else:
                score = 100 - 80 * ((rms - optimal_max) / (0.9 - optimal_max))
        else:
            # Optimal range
            score = 100
        
        return max(0, min(100, score))
    
    def _calculate_clarity_score(self, analysis: Dict[str, Any]) -> float:
        """
        Calculate clarity score (0-100).
        
        Based on:
        - Speech frequency ratio (higher = better)
        - Clipping ratio (lower = better)
        - SNR estimate (higher = better)
        """
        speech_ratio = analysis.get("speech_ratio", 0.5)
        clipping_ratio = analysis.get("clipping_ratio", 0.0)
        snr = analysis.get("snr_estimate", 20.0)
        
        # Speech ratio component (0-50 points)
        speech_score = 50 * min(1.0, speech_ratio / 0.7)
        
        # Clipping penalty (0-25 points)
        clipping_penalty = 25 * min(1.0, clipping_ratio * 10)
        
        # SNR component (0-25 points)
        # Good SNR is > 20 dB, excellent is > 30 dB
        snr_score = 25 * min(1.0, (snr - 10) / 20)
        
        score = speech_score + (25 - clipping_penalty) + snr_score
        
        return max(0, min(100, score))
    
    def _calculate_noise_score(self, analysis: Dict[str, Any]) -> float:
        """
        Calculate noise score (0-100, higher = less noise).
        
        Based on:
        - SNR estimate
        - Noise level relative to signal
        """
        snr = analysis.get("snr_estimate", 20.0)
        noise_level = analysis.get("noise_level", 0.05)
        signal_level = analysis.get("signal_level", 0.3)
        
        # Primary metric: SNR
        # Excellent: > 30 dB (90-100)
        # Good: 20-30 dB (70-90)
        # Fair: 10-20 dB (50-70)
        # Poor: < 10 dB (0-50)
        
        if snr >= 30:
            score = 90 + 10 * min(1.0, (snr - 30) / 20)
        elif snr >= 20:
            score = 70 + 20 * ((snr - 20) / 10)
        elif snr >= 10:
            score = 50 + 20 * ((snr - 10) / 10)
        else:
            score = 50 * (snr / 10)
        
        # Adjust based on relative noise level
        if signal_level > 0:
            noise_ratio = noise_level / signal_level
            if noise_ratio > 0.3:
                score *= 0.7  # Heavy noise penalty
            elif noise_ratio > 0.2:
                score *= 0.85  # Moderate noise penalty
        
        return max(0, min(100, score))
    
    def _calculate_overall_score(
        self,
        volume_score: float,
        clarity_score: float,
        noise_score: float
    ) -> float:
        """
        Calculate overall quality score.
        
        Weighted average:
        - Volume: 30%
        - Clarity: 40%
        - Noise: 30%
        """
        overall = (
            0.3 * volume_score +
            0.4 * clarity_score +
            0.3 * noise_score
        )
        return overall
    
    def _generate_feedback(
        self,
        overall_score: float,
        volume_score: float,
        clarity_score: float,
        noise_score: float,
        analysis: Dict[str, Any]
    ) -> str:
        """
        Generate textual feedback about voice quality.
        
        Args:
            overall_score: Overall quality score
            volume_score: Volume score
            clarity_score: Clarity score
            noise_score: Noise score
            analysis: Analysis metrics
            
        Returns:
            Feedback string
        """
        feedback_parts = []
        
        # Overall assessment
        if overall_score >= 80:
            feedback_parts.append("Excellent voice quality!")
        elif overall_score >= 60:
            feedback_parts.append("Good voice quality.")
        elif overall_score >= 40:
            feedback_parts.append("Fair voice quality.")
        else:
            feedback_parts.append("Voice quality needs improvement.")
        
        # Volume feedback
        if volume_score < 50:
            feedback_parts.append("Volume is too quiet.")
        elif volume_score > 90 and analysis.get("clipping_ratio", 0) > 0.01:
            feedback_parts.append("Volume is very loud (may be clipping).")
        
        # Clarity feedback
        if clarity_score < 50:
            feedback_parts.append("Speech clarity is low.")
        
        # Noise feedback
        if noise_score < 50:
            feedback_parts.append("Background noise is noticeable.")
        elif noise_score < 70:
            feedback_parts.append("Some background noise detected.")
        
        return " ".join(feedback_parts) if feedback_parts else "Voice quality is acceptable."
    
    def _generate_suggestions(
        self,
        volume_score: float,
        clarity_score: float,
        noise_score: float,
        analysis: Dict[str, Any]
    ) -> List[str]:
        """
        Generate improvement suggestions.
        
        Args:
            volume_score: Volume score
            clarity_score: Clarity score
            noise_score: Noise score
            analysis: Analysis metrics
            
        Returns:
            List of suggestion strings
        """
        suggestions = []
        
        # Volume suggestions
        if volume_score < 50:
            suggestions.append("Speak louder or move closer to the microphone.")
            suggestions.append("Check your microphone input level settings.")
        elif volume_score > 90 and analysis.get("clipping_ratio", 0) > 0.01:
            suggestions.append("Reduce volume or move further from the microphone to avoid clipping.")
        
        # Clarity suggestions
        if clarity_score < 50:
            suggestions.append("Speak more clearly and enunciate your words.")
            suggestions.append("Ensure you're speaking directly into the microphone.")
            if analysis.get("speech_ratio", 0.7) < 0.6:
                suggestions.append("Try speaking in a quieter environment to improve clarity.")
        
        # Noise suggestions
        if noise_score < 50:
            suggestions.append("Record in a quieter environment to reduce background noise.")
            suggestions.append("Use a directional microphone or noise-canceling headset.")
            suggestions.append("Close windows and doors to minimize ambient noise.")
        elif noise_score < 70:
            suggestions.append("Consider recording in a quieter location for better quality.")
        
        # General suggestions if all scores are low
        if volume_score < 60 and clarity_score < 60 and noise_score < 60:
            suggestions.append("For best results: Use a quality microphone, speak in a quiet room, and maintain consistent distance from the microphone.")
        
        # If no specific issues, provide positive feedback
        if not suggestions:
            suggestions.append("Your voice message quality is good! Keep up the great recording.")
        
        return suggestions
