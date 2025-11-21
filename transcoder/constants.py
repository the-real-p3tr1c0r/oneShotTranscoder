"""Constants used throughout the transcoder.

Copyright (C) 2025 oneShotTranscoder Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

# Audio settings
DEFAULT_AUDIO_BITRATE_KBPS = 192.0
AUDIO_CODEC = "aac"

# Video settings
VIDEO_CODEC_HEVC = "hevc"
VIDEO_TAG_HVC1 = "hvc1"

# Subtitle settings
MP4_SUBTITLE_CODEC = "mov_text"
IMAGE_BASED_SUBTITLE_CODECS = {
    "hdmv_pgs_subtitle",
    "dvd_subtitle",
    "xsub",
    "pgssub",
}

TEXT_SUBTITLE_CODECS = {
    "srt",
    "ass",
    "ssa",
    "vtt",
    "mov_text",
    "subrip",
    "text",
}

# Image settings
MAX_COVER_IMAGE_DIMENSION = 2000
COVER_IMAGE_QUALITY = 2  # JPEG quality (0-31, lower is better)

# FFmpeg settings
FFMPEG_LOGLEVEL = "info"
FFMPEG_PRESET_MEDIUM = "medium"
FFMPEG_PRESET_P4 = "p4"  # NVIDIA NVENC preset
FFMPEG_QUALITY_BALANCED = "balanced"  # AMD AMF quality
FFMPEG_QUALITY_BEST = "1"  # Apple VideoToolbox quality (0=realtime, 1=best, 2=better)
FFMPEG_GLOBAL_QUALITY_QSV = "23"  # Intel Quick Sync global quality

# Encoder names
ENCODER_NVENC = "hevc_nvenc"
ENCODER_AMF = "hevc_amf"
ENCODER_QSV = "hevc_qsv"
ENCODER_VIDEOTOOLBOX = "hevc_videotoolbox"
ENCODER_CPU = "libx265"

# Supported input video container formats
SUPPORTED_VIDEO_FORMATS = {
    ".mkv",   # Matroska
    ".mp4",   # MPEG-4
    ".m4v",   # MPEG-4 Video
    ".m4a",   # MPEG-4 Audio (can contain video)
    ".avi",   # Audio Video Interleave
    ".mov",   # QuickTime
    ".qt",    # QuickTime
    ".webm",  # WebM
    ".flv",   # Flash Video
    ".ts",    # MPEG Transport Stream
    ".mts",   # MPEG Transport Stream
    ".m2ts",  # Blu-ray Transport Stream
    ".ogv",   # Ogg Video
    ".ogg",   # Ogg (can contain video)
    ".3gp",   # 3GPP
    ".3g2",   # 3GPP2
    ".asf",   # Advanced Systems Format
    ".wmv",   # Windows Media Video
    ".vob",   # DVD Video Object
    ".mpg",   # MPEG-1/2
    ".mpeg",  # MPEG-1/2
    ".divx",  # DivX
    ".xvid",  # Xvid
}

# Default values
DEFAULT_TARGET_SIZE_MB_PER_HOUR = 900.0
DEFAULT_EASYOCR_LANGUAGE = "en"

# Progress display
PROGRESS_UPDATE_INTERVAL_SECONDS = 0.1
MIN_PROGRESS_PERCENTAGE_FOR_ETA = 0.1

