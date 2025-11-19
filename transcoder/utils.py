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
    Detect available GPU encoder in priority order: NVIDIA → AMD → Intel → Apple VideoToolbox → CPU.
    
    Returns:
        Encoder name (hevc_nvenc, hevc_amf, hevc_qsv, hevc_videotoolbox, or libx265)
    """
    encoders = [
        ("hevc_nvenc", "NVIDIA"),
        ("hevc_amf", "AMD"),
        ("hevc_qsv", "Intel"),
        ("hevc_videotoolbox", "Apple"),
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


def find_cover_image(source_dir: Path) -> Optional[Path]:
    """
    Find cover image in source directory with priority: cover.* > front.* > alphabetical.
    
    Args:
        source_dir: Directory to search for images
    
    Returns:
        Path to cover image or None if not found
    """
    # Supported image formats
    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    
    # Find all image files
    image_files = []
    for ext in image_extensions:
        image_files.extend(source_dir.glob(f"*{ext}"))
        image_files.extend(source_dir.glob(f"*{ext.upper()}"))
    
    if not image_files:
        return None
    
    # Priority 1: "cover.*"
    for img in image_files:
        if img.stem.lower() == "cover":
            return img
    
    # Priority 2: "front.*"
    for img in image_files:
        if img.stem.lower() == "front":
            return img
    
    # Priority 3: Alphabetical order (first image)
    return sorted(image_files)[0]


def convert_image_for_apple_tv(image_path: Path, temp_dir: Path) -> Path:
    """
    Convert image to JPEG format and resize for Apple TV compatibility.
    
    Args:
        image_path: Path to source image
        temp_dir: Temporary directory for converted image
    
    Returns:
        Path to converted JPEG image
    
    Raises:
        RuntimeError: If conversion fails
    """
    # Ensure temp directory exists
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Output path for converted image
    output_path = temp_dir / f"{image_path.stem}_cover.jpg"
    
    # Use ffmpeg to convert and resize
    # -vf scale: preserve aspect ratio, max dimension 2000px
    # -q:v 2: high quality JPEG
    # Use double quotes for Windows compatibility
    scale_filter = "scale='min(2000,iw)':'min(2000,ih)':force_original_aspect_ratio=decrease"
    cmd = [
        "ffmpeg",
        "-i", str(image_path),
        "-vf", scale_filter,
        "-q:v", "2",
        "-y",
        str(output_path),
    ]
    
    try:
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to convert image: {e.stderr.decode() if e.stderr else str(e)}") from e

