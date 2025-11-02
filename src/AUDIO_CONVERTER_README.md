# Audio Converter Utility

Audio format conversion utility for Telegram voice messages.

## Features

- Converts PCM/WAV audio files to OGG/OPUS format (Telegram's preferred format)
- Handles Telegram's ~1 minute duration limit (automatically truncates longer audio)
- Optimizes audio quality and file size
- Supports compression for smaller file sizes
- Converts raw PCM audio data

## Requirements

**System Dependency:**
- `ffmpeg` must be installed on the system

### Installation

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
Download from https://ffmpeg.org/download.html

## Usage

### Basic Usage

```python
from audio_converter import TelegramAudioConverter

converter = TelegramAudioConverter()

# Convert WAV to OGG/OPUS for Telegram
converter.convert_for_telegram(
    input_path="input.wav",
    output_path="output.ogg"
)
```

### With Compression

```python
# Enable compression for smaller file size
converter.convert_for_telegram(
    input_path="input.wav",
    output_path="output.ogg",
    compress=True
)
```

### Convert Raw PCM

```python
# Convert raw PCM audio to OGG/OPUS
converter.convert_pcm_to_ogg(
    pcm_path="input.pcm",
    output_path="output.ogg",
    sample_rate=16000,
    channels=1,
    sample_width=2  # 16-bit
)
```

### Get Audio Duration

```python
duration = converter.get_audio_duration("audio.wav")
print(f"Duration: {duration:.2f} seconds")
```

## Telegram Constraints

- **Maximum Duration:** ~60 seconds (automatically enforced)
- **Recommended Bitrate:** 64 kbps
- **Maximum File Size:** 20 MB
- **Format:** OGG/OPUS
- **Sample Rate:** 48000 Hz (automatically set)
- **Channels:** Mono (automatically set)

## Error Handling

The converter raises `AudioConversionError` for:
- Missing input files
- ffmpeg not installed or unavailable
- Conversion failures
- Invalid audio formats

## Testing

Run tests with:
```bash
python3 -m pytest tests/test_audio_conversion.py -v
```

**Note:** Tests require ffmpeg to be installed.
