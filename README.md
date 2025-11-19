# oneShotTranscoder

A Python-based transcoding tool that converts MKV video files to Apple TV-compatible MP4 format with automatic hardware acceleration, subtitle conversion, and metadata extraction.

## Features

- **Hardware-Accelerated Encoding**: Automatically detects and uses the fastest available GPU encoder:
  - NVIDIA NVENC (RTX/GTX series)
  - AMD AMF (Radeon series)
  - Intel Quick Sync Video
  - Apple VideoToolbox (macOS M1/M2/M3)
  - Falls back to CPU encoding (libx265) if no GPU is available

- **Smart Subtitle Handling**:
  - Preserves text-based subtitles (SRT, ASS, VTT, etc.)
  - Converts bitmap subtitles (PGS/SUP) to text using OCR (EasyOCR)
  - Supports multiple languages with automatic language detection
  - Embeds subtitle language metadata (ISO 639-2)

- **Metadata Extraction**:
  - Parses episode metadata from filenames (series name, episode title, season/episode numbers, year)
  - Embeds metadata in Apple TV-compatible format
  - Configurable filename pattern matching

- **Cover Image Support**:
  - Automatically finds and embeds cover images from the source directory
  - Converts and resizes images to Apple TV-compatible format (JPEG, max 2000px)
  - Priority: `cover.*` > `front.*` > alphabetical first image

- **Flexible Output Options**:
  - Default: Transcode to H.265/HEVC with configurable target file size (default: 900MB/hour)
  - Rewrap mode: Copy existing video streams without transcoding (faster, preserves quality)
  - Custom output directory support
  - Batch processing of multiple files

- **Real-Time Progress**:
  - Live encoding progress with percentage, time, file size, and speed
  - Compact subtitle conversion feedback

## Installation

### Prerequisites

- Python 3.9 or higher
- ffmpeg (installed via conda or system package manager)
- Conda (for environment management)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/the-real-p3tr1c0r/oneShotTranscoder.git
cd oneShotTranscoder
```

2. Create and activate the conda environment:
```bash
conda env create -f environment.yml
conda activate pcp
```

3. Install the package:
```bash
pip install -e .
```

## Usage

### Basic Usage

Transcode all MKV files in the current directory:
```bash
transcode
```

Transcode a specific file:
```bash
transcode --source "Prison Break (2005) - S01E01 - Pilot.mkv"
```

Transcode all files in a directory:
```bash
transcode --source /path/to/videos
```

### Advanced Options

Rewrap mode (copy streams without transcoding):
```bash
transcode --rewrap --source "video.mkv"
```

Custom target file size:
```bash
transcode --targetSizePerHour 1200 --source "video.mkv"
```

Custom output directory:
```bash
transcode --targetDir /path/to/output --source "video.mkv"
```

Disable bitmap subtitle conversion:
```bash
transcode --no-convert-subs --source "video.mkv"
```

### Help

View all available options:
```bash
transcode --help
```

## Filename Pattern

The tool automatically extracts metadata from filenames using a configurable pattern. Default pattern:

```
<Series Name> (<Year>) - S<season:2 digits>E<episode:2 digits> - <Episode Name> (<video specs>).mkv
```

Example: `Prison Break (2005) - S01E01 - Pilot (1080p BluRay x265 Silence).mkv`

This extracts:
- Series Name: "Prison Break"
- Year: 2005
- Season: 1
- Episode: 1
- Episode Title: "Pilot"

## Output Format

- **Container**: MP4
- **Video Codec**: H.265/HEVC (hvc1 tag for Apple TV compatibility)
- **Audio Codec**: AAC (192kbps)
- **Subtitles**: mov_text format
- **Metadata**: Apple TV-compatible tags (title, show, date, season_number, episode_sort)

## Requirements

- Python 3.9+
- ffmpeg (with hardware encoder support for your GPU)
- EasyOCR (for subtitle OCR)
- OpenCV (for image processing)
- babelfish (for language code normalization)
- pgsrip (for SUP subtitle parsing)

All dependencies are automatically installed via `environment.yml` and `setup.py`.

## Platform Support

- **Windows**: Full support with NVIDIA/AMD/Intel GPU acceleration
- **macOS**: Full support with Apple VideoToolbox hardware acceleration (M1/M2/M3)
- **Linux**: Full support with NVIDIA/AMD/Intel GPU acceleration

## License

See LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
