"""Apple TV compatibility checking.

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

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class CompatibilityStatus(Enum):
    """Compatibility check result status."""
    COMPATIBLE = "compatible"
    NEEDS_REMUX = "needs_remux"
    NEEDS_TRANSCODE = "needs_transcode"


@dataclass
class CompatibilityCheck:
    """Result of a single compatibility check."""
    name: str
    compatible: bool
    current_value: str
    required_value: str | None = None
    action_needed: str | None = None


@dataclass
class AppleTVCompatibility:
    """Full Apple TV compatibility analysis result."""
    overall_status: CompatibilityStatus
    checks: list[CompatibilityCheck] = field(default_factory=list)
    video_action: str = "copy"  # "copy" or "transcode"
    audio_action: str = "copy"  # "copy" or "transcode"
    container_action: str = "none"  # "none" or "remux"
    estimated_time: str = "unknown"
    
    def add_check(self, check: CompatibilityCheck) -> None:
        """Add a compatibility check result."""
        self.checks.append(check)
    
    def get_summary(self) -> str:
        """Get a summary of required actions."""
        actions = []
        if self.container_action == "remux":
            actions.append("remux to MP4")
        if self.video_action == "transcode":
            actions.append("transcode video")
        if self.audio_action == "transcode":
            actions.append("transcode audio")
        
        if not actions:
            return "No changes needed (already compatible)"
        return ", ".join(actions).capitalize()


# Apple TV supported specifications
APPLE_TV_SUPPORTED_VIDEO_CODECS = {"h264", "avc1", "hevc", "h265", "hvc1", "hev1"}
APPLE_TV_SUPPORTED_AUDIO_CODECS = {"aac", "ac3", "eac3", "ec-3", "alac", "mp3"}
APPLE_TV_SUPPORTED_CONTAINERS = {".mp4", ".m4v", ".mov"}

# H.264 profile/level limits
H264_MAX_LEVEL_1080P = 4.2
H264_MAX_LEVEL_4K = 5.2

# HEVC profile limits
HEVC_SUPPORTED_PROFILES = {"main", "main 10", "main10"}

# Resolution limits
MAX_WIDTH_4K = 3840
MAX_HEIGHT_4K = 2160
MAX_FPS = 60


def _parse_h264_level(level_str: str | int | float | None) -> float:
    """Parse H.264 level from various formats."""
    if level_str is None:
        return 0.0
    
    if isinstance(level_str, (int, float)):
        # FFprobe returns level as integer (42 = 4.2)
        if level_str > 10:
            return level_str / 10.0
        return float(level_str)
    
    try:
        level = float(level_str)
        if level > 10:
            return level / 10.0
        return level
    except (ValueError, TypeError):
        return 0.0


def _get_video_stream(probe_data: dict[str, Any]) -> dict[str, Any] | None:
    """Get the first video stream from probe data."""
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    return None


def _get_audio_streams(probe_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Get all audio streams from probe data."""
    return [s for s in probe_data.get("streams", []) if s.get("codec_type") == "audio"]


def check_apple_tv_compatibility(
    probe_data: dict[str, Any],
    input_path: Path,
) -> AppleTVCompatibility:
    """
    Check if a video file is Apple TV compatible.
    
    Args:
        probe_data: FFprobe data for the video file
        input_path: Path to the input file
    
    Returns:
        AppleTVCompatibility object with detailed check results
    """
    result = AppleTVCompatibility(overall_status=CompatibilityStatus.COMPATIBLE)
    
    video_stream = _get_video_stream(probe_data)
    audio_streams = _get_audio_streams(probe_data)
    
    # Check container format
    container_ext = input_path.suffix.lower()
    container_compatible = container_ext in APPLE_TV_SUPPORTED_CONTAINERS
    result.add_check(CompatibilityCheck(
        name="Container",
        compatible=container_compatible,
        current_value=container_ext.upper().lstrip("."),
        required_value="MP4/M4V/MOV",
        action_needed="Remux to MP4" if not container_compatible else None,
    ))
    if not container_compatible:
        result.container_action = "remux"
        if result.overall_status == CompatibilityStatus.COMPATIBLE:
            result.overall_status = CompatibilityStatus.NEEDS_REMUX
    
    # Check video codec
    if video_stream:
        video_codec = video_stream.get("codec_name", "").lower()
        video_compatible = video_codec in APPLE_TV_SUPPORTED_VIDEO_CODECS
        result.add_check(CompatibilityCheck(
            name="Video Codec",
            compatible=video_compatible,
            current_value=video_codec.upper(),
            required_value="H.264/HEVC",
            action_needed="Transcode video" if not video_compatible else None,
        ))
        if not video_compatible:
            result.video_action = "transcode"
            result.overall_status = CompatibilityStatus.NEEDS_TRANSCODE
        
        # Check H.264 profile/level
        if video_codec in {"h264", "avc1"}:
            profile = video_stream.get("profile", "").lower()
            level = _parse_h264_level(video_stream.get("level"))
            
            # Profile check (High and below are supported)
            profile_compatible = profile in {"baseline", "main", "high", "constrained baseline"}
            result.add_check(CompatibilityCheck(
                name="H.264 Profile",
                compatible=profile_compatible,
                current_value=profile.title() if profile else "Unknown",
                required_value="Baseline/Main/High",
                action_needed="Transcode video" if not profile_compatible else None,
            ))
            if not profile_compatible:
                result.video_action = "transcode"
                result.overall_status = CompatibilityStatus.NEEDS_TRANSCODE
            
            # Level check
            width = video_stream.get("width", 0)
            max_level = H264_MAX_LEVEL_4K if width > 1920 else H264_MAX_LEVEL_1080P
            level_compatible = level <= max_level if level > 0 else True
            result.add_check(CompatibilityCheck(
                name="H.264 Level",
                compatible=level_compatible,
                current_value=f"{level:.1f}" if level > 0 else "Unknown",
                required_value=f"≤{max_level}",
                action_needed="Transcode video" if not level_compatible else None,
            ))
            if not level_compatible:
                result.video_action = "transcode"
                result.overall_status = CompatibilityStatus.NEEDS_TRANSCODE
        
        # Check HEVC profile
        elif video_codec in {"hevc", "h265", "hvc1", "hev1"}:
            profile = video_stream.get("profile", "").lower()
            profile_compatible = profile in HEVC_SUPPORTED_PROFILES or not profile
            result.add_check(CompatibilityCheck(
                name="HEVC Profile",
                compatible=profile_compatible,
                current_value=profile.title() if profile else "Unknown",
                required_value="Main/Main 10",
                action_needed="Transcode video" if not profile_compatible else None,
            ))
            if not profile_compatible:
                result.video_action = "transcode"
                result.overall_status = CompatibilityStatus.NEEDS_TRANSCODE
        
        # Check resolution
        width = video_stream.get("width", 0)
        height = video_stream.get("height", 0)
        resolution_compatible = width <= MAX_WIDTH_4K and height <= MAX_HEIGHT_4K
        result.add_check(CompatibilityCheck(
            name="Resolution",
            compatible=resolution_compatible,
            current_value=f"{width}x{height}",
            required_value=f"≤{MAX_WIDTH_4K}x{MAX_HEIGHT_4K}",
            action_needed="Transcode video" if not resolution_compatible else None,
        ))
        if not resolution_compatible:
            result.video_action = "transcode"
            result.overall_status = CompatibilityStatus.NEEDS_TRANSCODE
        
        # Check frame rate
        fps_str = video_stream.get("r_frame_rate", "0/1")
        try:
            if "/" in fps_str:
                num, den = fps_str.split("/")
                fps = float(num) / float(den) if float(den) != 0 else 0
            else:
                fps = float(fps_str)
        except (ValueError, ZeroDivisionError):
            fps = 0
        
        fps_compatible = fps <= MAX_FPS if fps > 0 else True
        result.add_check(CompatibilityCheck(
            name="Frame Rate",
            compatible=fps_compatible,
            current_value=f"{fps:.3f} fps" if fps > 0 else "Unknown",
            required_value=f"≤{MAX_FPS} fps",
            action_needed="Transcode video" if not fps_compatible else None,
        ))
        if not fps_compatible:
            result.video_action = "transcode"
            result.overall_status = CompatibilityStatus.NEEDS_TRANSCODE
        
        # Check bit depth
        pix_fmt = video_stream.get("pix_fmt", "")
        bit_depth = "8-bit"
        if "10" in pix_fmt or "p10" in pix_fmt.lower():
            bit_depth = "10-bit"
        elif "12" in pix_fmt or "p12" in pix_fmt.lower():
            bit_depth = "12-bit"
        
        # 10-bit only supported with HEVC
        bit_depth_compatible = True
        if bit_depth != "8-bit" and video_codec not in {"hevc", "h265", "hvc1", "hev1"}:
            bit_depth_compatible = False
        if bit_depth == "12-bit":
            bit_depth_compatible = False
        
        result.add_check(CompatibilityCheck(
            name="Bit Depth",
            compatible=bit_depth_compatible,
            current_value=bit_depth,
            required_value="8-bit (H.264) or 8/10-bit (HEVC)",
            action_needed="Transcode video" if not bit_depth_compatible else None,
        ))
        if not bit_depth_compatible:
            result.video_action = "transcode"
            result.overall_status = CompatibilityStatus.NEEDS_TRANSCODE
    
    # Check audio codec (first audio stream)
    if audio_streams:
        audio_stream = audio_streams[0]
        audio_codec = audio_stream.get("codec_name", "").lower()
        audio_compatible = audio_codec in APPLE_TV_SUPPORTED_AUDIO_CODECS
        
        # Get channel info
        channels = audio_stream.get("channels", 0)
        channel_layout = audio_stream.get("channel_layout", "")
        channel_info = channel_layout if channel_layout else f"{channels}ch"
        
        result.add_check(CompatibilityCheck(
            name="Audio Codec",
            compatible=audio_compatible,
            current_value=f"{audio_codec.upper()} ({channel_info})",
            required_value="AAC/AC3/E-AC3/ALAC",
            action_needed="Transcode audio" if not audio_compatible else None,
        ))
        if not audio_compatible:
            result.audio_action = "transcode"
            # Audio-only transcode doesn't require full transcode
            if result.overall_status == CompatibilityStatus.COMPATIBLE:
                result.overall_status = CompatibilityStatus.NEEDS_REMUX
    
    # Estimate time based on required actions
    if result.video_action == "transcode":
        result.estimated_time = "Long (video re-encoding required)"
    elif result.audio_action == "transcode" or result.container_action == "remux":
        result.estimated_time = "Fast (remux/audio only)"
    else:
        result.estimated_time = "None (already compatible)"
    
    return result


def format_compatibility_report(
    compat: AppleTVCompatibility,
    input_path: Path,
) -> str:
    """
    Format a compatibility report for display.
    
    Args:
        compat: Compatibility analysis result
        input_path: Path to input file
    
    Returns:
        Formatted string report
    """
    lines = []
    lines.append("\nApple TV Compatibility:")
    lines.append("-" * 40)
    
    for check in compat.checks:
        status = "✓" if check.compatible else "✗"
        line = f"  {status} {check.name}: {check.current_value}"
        if not check.compatible and check.action_needed:
            line += f" → {check.action_needed}"
        lines.append(line)
    
    lines.append("-" * 40)
    
    # Overall result
    if compat.overall_status == CompatibilityStatus.COMPATIBLE:
        lines.append("Result: COMPATIBLE (no changes needed)")
    elif compat.overall_status == CompatibilityStatus.NEEDS_REMUX:
        lines.append(f"Result: REMUX REQUIRED ({compat.get_summary()})")
    else:
        lines.append(f"Result: TRANSCODE REQUIRED ({compat.get_summary()})")
    
    lines.append(f"Estimated time: {compat.estimated_time}")
    
    return "\n".join(lines)

