"""Utility functions for video transcoding."""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def check_ffmpeg_available() -> bool:
    """Check if ffmpeg and ffprobe are available."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        subprocess.run(
            ["ffprobe", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def detect_gpu_encoder() -> str:
    """
    Detect available GPU encoder in priority order: NVIDIA → AMD → Intel → CPU.
    
    Returns:
        Encoder name (hevc_nvenc, hevc_amf, hevc_qsv, or libx265)
    """
    encoders = [
        ("hevc_nvenc", "NVIDIA"),
        ("hevc_amf", "AMD"),
        ("hevc_qsv", "Intel"),
    ]
    
    for encoder, vendor in encoders:
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                check=True,
            )
            if encoder in result.stdout:
                return encoder
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    
    return "libx265"


def probe_video_file(file_path: Path) -> Dict:
    """Probe video file using ffprobe and return stream information."""
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_name,codec_type,codec_long_name,duration",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(file_path),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to probe video file: {e}") from e


def get_video_duration(probe_data: Dict) -> float:
    """Extract video duration in seconds from probe data."""
    duration = None
    
    if "format" in probe_data and "duration" in probe_data["format"]:
        duration = float(probe_data["format"]["duration"])
    elif "streams" in probe_data:
        for stream in probe_data["streams"]:
            if (
                stream.get("codec_type") == "video"
                and "duration" in stream
            ):
                duration = float(stream["duration"])
                break
    
    if duration is None:
        raise ValueError("Could not determine video duration")
    
    return duration


def get_text_subtitle_streams(probe_data: Dict) -> List[int]:
    """Identify text-based subtitle stream indices."""
    text_subtitle_codecs = {
        "srt",
        "ass",
        "ssa",
        "vtt",
        "mov_text",
        "subrip",
        "text",
    }
    
    image_subtitle_codecs = {
        "dvd_subtitle",
        "hdmv_pgs_subtitle",
        "pgssub",
        "dvb_subtitle",
        "xsub",
    }
    
    text_streams = []
    
    if "streams" not in probe_data:
        return text_streams
    
    for stream in probe_data["streams"]:
        if stream.get("codec_type") != "subtitle":
            continue
        
        codec_name = stream.get("codec_name", "").lower()
        
        if codec_name in text_subtitle_codecs:
            text_streams.append(stream.get("index", len(text_streams)))
        elif codec_name not in image_subtitle_codecs:
            codec_long_name = stream.get("codec_long_name", "").lower()
            if any(
                text_codec in codec_long_name
                for text_codec in text_subtitle_codecs
            ):
                text_streams.append(stream.get("index", len(text_streams)))
    
    return text_streams


def get_bitmap_subtitle_streams(probe_data: Dict) -> List[int]:
    """Identify image-based subtitle stream indices."""
    image_subtitle_codecs = {
        "dvd_subtitle",
        "hdmv_pgs_subtitle",
        "pgssub",
        "dvb_subtitle",
        "xsub",
    }
    
    bitmap_streams = []
    
    if "streams" not in probe_data:
        return bitmap_streams
    
    for stream in probe_data["streams"]:
        if stream.get("codec_type") != "subtitle":
            continue
        
        codec_name = stream.get("codec_name", "").lower()
        
        if codec_name in image_subtitle_codecs:
            bitmap_streams.append(stream.get("index", len(bitmap_streams)))
    
    return bitmap_streams


def calculate_target_bitrate(
    duration_seconds: float,
    target_size_mb_per_hour: float,
    audio_bitrate_kbps: float = 192.0,
) -> Tuple[float, float]:
    """
    Calculate target video bitrate based on duration and target size.
    
    Args:
        duration_seconds: Video duration in seconds
        target_size_mb_per_hour: Target file size in MB per hour
        audio_bitrate_kbps: Audio bitrate in kbps (default: 192)
    
    Returns:
        Tuple of (total_bitrate_kbps, video_bitrate_kbps)
    """
    duration_hours = duration_seconds / 3600.0
    target_size_mb = target_size_mb_per_hour * duration_hours
    
    total_bitrate_kbps = (target_size_mb * 8 * 1024) / duration_seconds
    video_bitrate_kbps = max(0, total_bitrate_kbps - audio_bitrate_kbps)
    
    return total_bitrate_kbps, video_bitrate_kbps


def find_mkv_files(directory: Path) -> List[Path]:
    """Find all .mkv files in the given directory."""
    return sorted(directory.glob("*.mkv"))


def get_output_path(input_path: Path) -> Path:
    """Generate output .mp4 path from input .mkv path."""
    return input_path.with_suffix(".mp4")

