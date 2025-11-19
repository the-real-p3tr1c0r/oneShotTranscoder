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


def get_text_subtitle_streams(probe_data: Dict) -> List[Tuple[int, Optional[str]]]:
    """
    Identify text-based subtitle stream indices with language information.
    
    Returns:
        List of tuples (stream_index, language_code) where language_code is ISO 639-2
    """
    from babelfish import Language as BabelLanguage
    
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
    
    def normalize_language_tag(code: Optional[str]) -> Optional[str]:
        """Normalize language code to ISO 639-2."""
        if not code:
            return None
        
        code_lower = code.lower().strip()
        
        # If already 3-letter, check if it's ISO 639-2
        if len(code_lower) == 3 and code_lower.isalpha():
            # Map common variations to ISO 639-2
            iso6392_map = {
                "fre": "fra",  # French bibliographic -> terminological
                "chi": "zho",  # Chinese bibliographic -> terminological
                "cze": "ces",  # Czech bibliographic -> terminological
                "dut": "nld",  # Dutch bibliographic -> terminological
                "ger": "deu",  # German bibliographic -> terminological
                "gre": "ell",  # Greek bibliographic -> terminological
                "ice": "isl",  # Icelandic bibliographic -> terminological
                "mac": "mkd",  # Macedonian bibliographic -> terminological
                "rum": "ron",  # Romanian bibliographic -> terminological
                "slo": "slk",  # Slovak bibliographic -> terminological
            }
            if code_lower in iso6392_map:
                return iso6392_map[code_lower]
            # Try to validate with babelfish
            try:
                lang = BabelLanguage(code_lower)
                iso6392 = getattr(lang, 'alpha3', None)
                if iso6392 and len(iso6392) == 3:
                    return iso6392.lower()
                return code_lower
            except Exception:
                return code_lower
        
        # Try to resolve using babelfish
        for resolver in (BabelLanguage.fromietf, BabelLanguage):
            try:
                lang = resolver(code)
                iso6392 = getattr(lang, 'alpha3', None)
                if iso6392 and len(iso6392) == 3:
                    return iso6392.lower()
            except Exception:
                continue
        
        return code_lower
    
    text_streams = []
    
    if "streams" not in probe_data:
        return text_streams
    
    for stream in probe_data["streams"]:
        if stream.get("codec_type") != "subtitle":
            continue
        
        codec_name = stream.get("codec_name", "").lower()
        is_text_subtitle = False
        
        if codec_name in text_subtitle_codecs:
            is_text_subtitle = True
        elif codec_name not in image_subtitle_codecs:
            codec_long_name = stream.get("codec_long_name", "").lower()
            if any(
                text_codec in codec_long_name
                for text_codec in text_subtitle_codecs
            ):
                is_text_subtitle = True
        
        if is_text_subtitle:
            stream_index = stream.get("index")
            tags = stream.get("tags") or {}
            language = normalize_language_tag(tags.get("language"))
            text_streams.append((stream_index, language))
    
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


def get_output_path(input_path: Path, target_dir: Optional[Path] = None) -> Path:
    """
    Generate output .mp4 path from input .mkv path.
    
    Args:
        input_path: Path to input .mkv file
        target_dir: Optional target directory for output. If None, output is in same directory as input.
    
    Returns:
        Path to output .mp4 file
    """
    if target_dir:
        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)
        # Use same filename but with .mp4 extension
        return target_dir / input_path.with_suffix(".mp4").name
    return input_path.with_suffix(".mp4")

