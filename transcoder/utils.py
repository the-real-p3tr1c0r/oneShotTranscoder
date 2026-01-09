"""Utility functions for video transcoding.

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

import os
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

from transcoder.constants import (
    AUDIO_CODEC,
    DEFAULT_AUDIO_BITRATE_KBPS,
    IMAGE_BASED_SUBTITLE_CODECS,
    SUPPORTED_VIDEO_FORMATS,
    TEXT_SUBTITLE_CODECS,
)
from transcoder.exceptions import FFmpegError
from transcoder.language import normalize_language_tag

# Global cache for bundled binary paths
_BUNDLED_FFMPEG_PATH: str | None = None
_BUNDLED_FFPROBE_PATH: str | None = None
_BUNDLED_TEMP_DIR: Path | None = None


def _get_bundled_binary_path(binary_name: str) -> str | None:
    """
    Get path to bundled ffmpeg binary if running from PyInstaller executable.
    
    PyInstaller extracts bundled files to a temp directory. This function
    locates and extracts bundled binaries if needed.
    
    Args:
        binary_name: Name of binary ('ffmpeg' or 'ffprobe', with .exe on Windows)
    
    Returns:
        Path to bundled binary or None if not found
    """
    global _BUNDLED_FFMPEG_PATH, _BUNDLED_FFPROBE_PATH, _BUNDLED_TEMP_DIR
    
    # Check if we're running from PyInstaller
    if not getattr(sys, 'frozen', False):
        return None
    
    # Check cache first
    if binary_name == "ffmpeg" and _BUNDLED_FFMPEG_PATH:
        return _BUNDLED_FFMPEG_PATH
    if binary_name == "ffprobe" and _BUNDLED_FFPROBE_PATH:
        return _BUNDLED_FFPROBE_PATH
    
    # Determine binary name with extension
    if sys.platform == "win32":
        binary_name_with_ext = f"{binary_name}.exe"
    else:
        binary_name_with_ext = binary_name
    
    # Get PyInstaller temp directory
    if sys.platform == "win32":
        # On Windows, PyInstaller uses _MEIPASS
        base_path = getattr(sys, '_MEIPASS', None)
    else:
        # On macOS/Linux, PyInstaller uses _MEIPASS
        base_path = getattr(sys, '_MEIPASS', None)
    
    if not base_path:
        return None
    
    # Look for binary in PyInstaller temp directory
    bundled_path = Path(base_path) / "ffmpeg" / binary_name_with_ext
    
    if bundled_path.exists() and bundled_path.is_file():
        # On macOS, when installed under /Applications, the app bundle contents are
        # typically owned by root. Attempting to chmod can raise PermissionError.
        # To stay user-serviceable (and avoid Gatekeeper quirks), we copy binaries to
        # a user-writable temp dir and execute from there when needed.
        if sys.platform == "darwin":
            global _BUNDLED_TEMP_DIR
            if _BUNDLED_TEMP_DIR is None:
                _BUNDLED_TEMP_DIR = Path(
                    tempfile.mkdtemp(prefix="transcoder-bundled-ffmpeg-")
                )

            local_bin = _BUNDLED_TEMP_DIR / binary_name_with_ext
            if not local_bin.exists():
                shutil.copy2(bundled_path, local_bin)
                try:
                    os.chmod(local_bin, 0o755)
                except Exception:
                    pass
                # Best-effort: remove quarantine attribute so execution isn't blocked
                try:
                    subprocess.run(
                        ["/usr/bin/xattr", "-d", "com.apple.quarantine", str(local_bin)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                except Exception:
                    pass

            resolved_path = str(local_bin)
        else:
            # Make executable on Unix systems (best-effort)
            if sys.platform != "win32":
                try:
                    if not os.access(bundled_path, os.X_OK):
                        os.chmod(bundled_path, 0o755)
                except Exception:
                    pass
            resolved_path = str(bundled_path)
        
        # Cache the path
        if binary_name == "ffmpeg":
            _BUNDLED_FFMPEG_PATH = resolved_path
        else:
            _BUNDLED_FFPROBE_PATH = resolved_path
        
        return resolved_path
    
    return None


def get_ffmpeg_path() -> str:
    """
    Get path to ffmpeg binary, preferring bundled version if available.
    
    Returns:
        Path to ffmpeg binary
    
    Raises:
        FFmpegError: If ffmpeg is not found
    """
    # Try bundled binary first
    bundled_path = _get_bundled_binary_path("ffmpeg")
    if bundled_path:
        return bundled_path
    
    # Fall back to system binary
    system_path = shutil.which("ffmpeg")
    if system_path:
        return system_path
    
    raise FFmpegError("ffmpeg not found. Please install ffmpeg or use the bundled executable.")


def get_ffprobe_path() -> str:
    """
    Get path to ffprobe binary, preferring bundled version if available.
    
    Returns:
        Path to ffprobe binary
    
    Raises:
        FFmpegError: If ffprobe is not found
    """
    # Try bundled binary first
    bundled_path = _get_bundled_binary_path("ffprobe")
    if bundled_path:
        return bundled_path
    
    # Fall back to system binary
    system_path = shutil.which("ffprobe")
    if system_path:
        return system_path
    
    raise FFmpegError("ffprobe not found. Please install ffmpeg or use the bundled executable.")


def check_ffmpeg_available() -> bool:
    """Check if ffmpeg and ffprobe are available."""
    try:
        get_ffmpeg_path()
        get_ffprobe_path()
        return True
    except FFmpegError:
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
    
    ffmpeg_path = get_ffmpeg_path()
    
    for encoder, vendor in encoders:
        try:
            result = subprocess.run(
                [ffmpeg_path, "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                check=True,
            )
            if encoder in result.stdout:
                return encoder
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    
    return "libx265"


def probe_video_file(file_path: Path) -> dict:
    """
    Probe video file using ffprobe and return stream information.
    
    Uses subprocess to call ffprobe directly for reliable results.
    """
    import json as json_module
    import subprocess
    
    # ffmpeg-python's probe() doesn't handle multiple show_entries well,
    # so we use subprocess directly for this specific use case
    try:
        ffprobe_path = get_ffprobe_path()
        cmd = [
            ffprobe_path,
            "-v", "error",
            "-show_entries", "stream=index,codec_name,codec_type,codec_long_name,duration,r_frame_rate,avg_frame_rate",
            "-show_entries", "format=duration",
            "-of", "json",
            str(file_path),
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        )
        return json_module.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        raise FFmpegError(f"Failed to probe video file: {e}") from e
    except json_module.JSONDecodeError as e:
        raise FFmpegError(f"Failed to parse probe output: {e}") from e


def get_video_duration(probe_data: dict) -> float:
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


def parse_fps(fps_str: str) -> float:
    """Parse FPS string (e.g., '30/1' or '29.97') to float."""
    try:
        return float(Fraction(fps_str))
    except (ValueError, ZeroDivisionError):
        return 0.0


def get_video_fps(probe_data: dict) -> float:
    """Extract video FPS from probe data."""
    if "streams" in probe_data:
        for stream in probe_data["streams"]:
            if stream.get("codec_type") == "video":
                # Try avg_frame_rate first (more accurate), then r_frame_rate
                fps_str = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
                if fps_str:
                    fps = parse_fps(fps_str)
                    if fps > 0:
                        return fps
    
    raise ValueError("Could not determine video FPS")


def get_total_frames(probe_data: dict) -> int:
    """Calculate total frame count from duration and FPS."""
    duration = get_video_duration(probe_data)
    fps = get_video_fps(probe_data)
    return int(duration * fps)


def get_text_subtitle_streams(probe_data: dict) -> list[tuple[int, str | None]]:
    """
    Identify text-based subtitle stream indices with language information.
    
    Returns:
        List of tuples (stream_index, language_code) where language_code is ISO 639-2
    """
    text_streams: list[tuple[int, str | None]] = []
    
    if "streams" not in probe_data:
        return text_streams
    
    for stream in probe_data["streams"]:
        if stream.get("codec_type") != "subtitle":
            continue
        
        codec_name = stream.get("codec_name", "").lower()
        is_text_subtitle = False
        
        if codec_name in TEXT_SUBTITLE_CODECS:
            is_text_subtitle = True
        elif codec_name not in IMAGE_BASED_SUBTITLE_CODECS:
            codec_long_name = stream.get("codec_long_name", "").lower()
            if any(
                text_codec in codec_long_name
                for text_codec in TEXT_SUBTITLE_CODECS
            ):
                is_text_subtitle = True
        
        if is_text_subtitle:
            stream_index = stream.get("index")
            tags = stream.get("tags") or {}
            language = normalize_language_tag(tags.get("language"))
            text_streams.append((stream_index, language))
    
    return text_streams


def get_bitmap_subtitle_streams(probe_data: dict) -> list[int]:
    """Identify image-based subtitle stream indices."""
    bitmap_streams: list[int] = []
    
    if "streams" not in probe_data:
        return bitmap_streams
    
    for stream in probe_data["streams"]:
        if stream.get("codec_type") != "subtitle":
            continue
        
        codec_name = stream.get("codec_name", "").lower()
        
        if codec_name in IMAGE_BASED_SUBTITLE_CODECS:
            bitmap_streams.append(stream.get("index", len(bitmap_streams)))
    
    return bitmap_streams


def calculate_target_bitrate(
    duration_seconds: float,
    target_size_mb_per_hour: float,
    audio_bitrate_kbps: float = DEFAULT_AUDIO_BITRATE_KBPS,
) -> tuple[float, float]:
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


def find_video_files(directory: Path) -> list[Path]:
    """Find all supported video files in the given directory."""
    video_files = []
    for ext in SUPPORTED_VIDEO_FORMATS:
        video_files.extend(directory.glob(f"*{ext}"))
    return sorted(video_files)


def expand_path_pattern(pattern: str) -> list[Path]:
    """
    Expand a path pattern with wildcards to matching video files.
    
    Supports wildcards (* and ?) in the filename. Examples:
    - "*est.mkv" matches all files ending with "est.mkv"
    - "test*.mp4" matches all files starting with "test" and ending with ".mp4"
    - "test?.mkv" matches files like "test1.mkv", "test2.mkv", etc.
    
    Args:
        pattern: Path pattern with optional wildcards (can be absolute or relative)
    
    Returns:
        List of matching video file paths, sorted
    
    Raises:
        ValueError: If no files match the pattern or no supported video files found
    """
    path = Path(pattern)
    
    # Determine the directory to search in
    if path.is_absolute():
        search_dir = path.parent
        file_pattern = path.name
    else:
        # Relative path - resolve relative to current directory
        search_dir = Path.cwd() / path.parent
        file_pattern = path.name
    
    # Expand the glob pattern
    matching_files = list(search_dir.glob(file_pattern))
    if not matching_files:
        raise ValueError(f"No files found matching pattern: {pattern}")
    
    # Filter to only supported video formats
    video_files = [Path(f) for f in matching_files if Path(f).suffix.lower() in SUPPORTED_VIDEO_FORMATS]
    if not video_files:
        raise ValueError(f"No supported video files found matching pattern: {pattern}")
    
    return sorted(video_files)


def get_output_path(input_path: Path, target_dir: Path | None = None, overwrite: bool = False) -> Path:
    """
    Generate output .mp4 path from input video file path.
    
    Args:
        input_path: Path to input video file
        target_dir: Optional target directory for output. If None, output is in same directory as input.
        overwrite: If True, allow overwriting existing files. If False, add incremental suffix to avoid overwriting.
    
    Returns:
        Path to output .mp4 file
    """
    if target_dir:
        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)
        # Use same filename but with .mp4 extension
        base_path = target_dir / input_path.with_suffix(".mp4").name
    else:
        base_path = input_path.with_suffix(".mp4")
    
    # If overwrite is enabled, return the path as-is
    if overwrite:
        return base_path
    
    # If file doesn't exist, return the path as-is
    if not base_path.exists():
        return base_path
    
    # File exists, need to find a non-existing name by incrementing suffix
    stem = base_path.stem
    suffix = base_path.suffix
    parent = base_path.parent
    counter = 1
    
    while True:
        new_name = f"{stem}_{counter}{suffix}"
        new_path = parent / new_name
        if not new_path.exists():
            return new_path
        counter += 1


def find_cover_image(source_dir: Path) -> Path | None:
    """
    Find cover image in source directory with priority: cover.* > front.* > alphabetical.
    
    Args:
        source_dir: Directory to search for images
    
    Returns:
        Path to cover image or None if not found
    """
    # Supported image formats
    image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    
    # Find all image files in one pass using pathlib
    all_images = [
        p for p in source_dir.iterdir()
        if p.is_file() and p.suffix.lower() in image_extensions
    ]
    
    if not all_images:
        return None
    
    # Priority 1: "cover.*" using next() with generator
    cover = next((img for img in all_images if img.stem.lower() == "cover"), None)
    if cover:
        return cover
    
    # Priority 2: "front.*"
    front = next((img for img in all_images if img.stem.lower() == "front"), None)
    if front:
        return front
    
    # Priority 3: Alphabetical order (first image)
    return sorted(all_images)[0]


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
    ffmpeg_path = get_ffmpeg_path()
    cmd = [
        ffmpeg_path,
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
        error_msg = e.stderr.decode() if e.stderr else str(e)
        raise FFmpegError(f"Failed to convert image: {error_msg}") from e

