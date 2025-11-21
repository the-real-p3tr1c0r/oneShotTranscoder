"""FFmpeg command building and execution.

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

import queue
import re
import subprocess
import threading
import time
from pathlib import Path

from transcoder.constants import (
    AUDIO_CODEC,
    DEFAULT_AUDIO_BITRATE_KBPS,
    ENCODER_AMF,
    ENCODER_CPU,
    ENCODER_NVENC,
    ENCODER_QSV,
    ENCODER_VIDEOTOOLBOX,
    FFMPEG_GLOBAL_QUALITY_QSV,
    FFMPEG_LOGLEVEL,
    FFMPEG_PRESET_MEDIUM,
    FFMPEG_PRESET_P4,
    FFMPEG_QUALITY_BALANCED,
    FFMPEG_QUALITY_BEST,
    MAX_COVER_IMAGE_DIMENSION,
    MP4_SUBTITLE_CODEC,
    VIDEO_TAG_HVC1,
)
from transcoder.exceptions import FFmpegError
from transcoder.metadata import EpisodeMetadata, MovieMetadata, metadata_to_ffmpeg_args
from transcoder.subtitles import GeneratedSubtitle
from transcoder.utils import detect_gpu_encoder


def build_transcode_command(
    input_path: Path,
    output_path: Path,
    video_bitrate_kbps: float,
    subtitle_streams: list[tuple[int, str | None]],
    encoder: str | None = None,
    generated_subtitles: list[GeneratedSubtitle] | None = None,
    media_metadata: EpisodeMetadata | MovieMetadata | None = None,
    cover_image_path: Path | None = None,
) -> list[str]:
    """
    Build ffmpeg command for transcoding mode.
    
    Args:
        input_path: Input .mkv file path
        output_path: Output .mp4 file path
        video_bitrate_kbps: Target video bitrate in kbps
        subtitle_streams: List of tuples (stream_index, language_code) for text subtitles
        encoder: Video encoder to use (auto-detected if None)
        generated_subtitles: List of generated subtitle files from OCR
        media_metadata: Metadata for Apple TV tags (movie or TV)
        cover_image_path: Optional path to cover image to embed as thumbnail
    
    Returns:
        List of command arguments for ffmpeg
    """
    encoder = encoder or detect_gpu_encoder()
    generated_subtitles = generated_subtitles or []
    
    cmd = [
        "ffmpeg",
        "-i",
        str(input_path),
    ]
    
    # Add generated subtitle files as inputs
    for gen_sub in generated_subtitles:
        cmd.extend(["-i", str(gen_sub.path)])
    
    # Add cover image as input if provided
    image_input_index = len(generated_subtitles) + 1
    if cover_image_path:
        cmd.extend(["-i", str(cover_image_path)])
    
    # Map video and audio first
    cmd.extend([
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
    ])
    
    # Map cover image as attached picture if provided
    if cover_image_path:
        cmd.extend(["-map", f"{image_input_index}:v:0"])
    
    # Map text subtitle streams from source
    subtitle_count = 0
    if subtitle_streams:
        for sub_idx, sub_lang in subtitle_streams:
            cmd.extend(["-map", f"0:{sub_idx}"])
            subtitle_count += 1
    
    # Map generated subtitle files
    for idx, gen_sub in enumerate(generated_subtitles):
        cmd.extend(["-map", f"{idx + 1}:s:0"])
        subtitle_count += 1
    
    # Set codec for main video stream explicitly (use :0 to avoid affecting cover image)
    cmd.extend([
        "-c:v:0",
        encoder,
        "-b:v:0",
        f"{int(video_bitrate_kbps)}k",
    ])
    
    if encoder == ENCODER_NVENC:
        cmd.extend(["-preset", FFMPEG_PRESET_P4, "-rc", "vbr"])
    elif encoder == ENCODER_AMF:
        cmd.extend(["-quality", FFMPEG_QUALITY_BALANCED, "-rc", "vbr_peak"])
    elif encoder == ENCODER_QSV:
        cmd.extend(["-preset", FFMPEG_PRESET_MEDIUM, "-global_quality", FFMPEG_GLOBAL_QUALITY_QSV])
    elif encoder == ENCODER_VIDEOTOOLBOX:
        cmd.extend(["-quality", FFMPEG_QUALITY_BEST])  # 0=realtime, 1=best, 2=better
    else:
        cmd.extend(["-preset", FFMPEG_PRESET_MEDIUM])
    
    # Add HEVC tag for main video stream only (not cover image)
    if encoder in [ENCODER_NVENC, ENCODER_AMF, ENCODER_QSV, ENCODER_VIDEOTOOLBOX, ENCODER_CPU]:
        cmd.extend(["-tag:v:0", VIDEO_TAG_HVC1])
    
    # Set codec for cover image if provided
    if cover_image_path:
        cmd.extend(["-c:v:1", "mjpeg"])
        cmd.extend(["-disposition:v:1", "attached_pic"])
    
    cmd.extend([
        "-c:a",
        AUDIO_CODEC,
        "-b:a",
        f"{int(DEFAULT_AUDIO_BITRATE_KBPS)}k",
    ])
    
    # Set codec and language metadata for all subtitle streams
    if subtitle_count > 0:
        stream_idx = 0
        # Original text subtitles
        if subtitle_streams:
            for sub_idx, sub_lang in subtitle_streams:
                cmd.extend(["-c:s:{}".format(stream_idx), MP4_SUBTITLE_CODEC])
                if sub_lang:
                    cmd.extend(["-metadata:s:s:{}".format(stream_idx), f"language={sub_lang}"])
                stream_idx += 1
        # Generated OCR subtitles
        for gen_sub in generated_subtitles:
            cmd.extend(["-c:s:{}".format(stream_idx), MP4_SUBTITLE_CODEC])
            if gen_sub.language:
                cmd.extend(["-metadata:s:s:{}".format(stream_idx), f"language={gen_sub.language}"])
            stream_idx += 1
    else:
        cmd.append("-sn")
    
    # Add episode metadata if available
    if media_metadata:
        cmd.extend(metadata_to_ffmpeg_args(media_metadata))
    
    cmd.extend([
        "-f",
        "mp4",
        "-movflags",
        "+faststart",
        "-loglevel",
        "info",  # Show info messages (for faststart detection) but suppress stats
        "-nostats",  # Suppress default progress output
        "-progress",
        "pipe:1",  # Parse this for progress display
        "-y",
        str(output_path),
    ])
    
    return cmd


def build_rewrap_command(
    input_path: Path,
    output_path: Path,
    subtitle_streams: list[tuple[int, str | None]],
    probe_data: dict | None = None,
    generated_subtitles: list[GeneratedSubtitle] | None = None,
    media_metadata: EpisodeMetadata | MovieMetadata | None = None,
    cover_image_path: Path | None = None,
) -> list[str]:
    """
    Build ffmpeg command for rewrap mode (stream copy).
    
    Args:
        input_path: Input .mkv file path
        output_path: Output .mp4 file path
        subtitle_streams: List of tuples (stream_index, language_code) for text subtitles
        probe_data: Video probe data to detect codec (optional)
        generated_subtitles: List of generated subtitle files from OCR
        media_metadata: Metadata for Apple TV tags
        cover_image_path: Optional path to cover image to embed as thumbnail
    
    Returns:
        List of command arguments for ffmpeg
    """
    generated_subtitles = generated_subtitles or []
    
    # Build subtitle codec map from probe data (used for language metadata)
    subtitle_codec_map = {}
    if probe_data and "streams" in probe_data:
        for stream in probe_data["streams"]:
            if stream.get("codec_type") == "subtitle":
                stream_idx = stream.get("index")
                codec_name = stream.get("codec_name", "").lower()
                subtitle_codec_map[stream_idx] = codec_name
    
    cmd = [
        "ffmpeg",
        "-i",
        str(input_path),
    ]
    
    # Add generated subtitle files as inputs
    for gen_sub in generated_subtitles:
        cmd.extend(["-i", str(gen_sub.path)])
    
    # Add cover image as input if provided
    image_input_index = len(generated_subtitles) + 1
    if cover_image_path:
        cmd.extend(["-i", str(cover_image_path)])
    
    # Map video and audio first
    cmd.extend([
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
    ])
    
    # Map cover image as attached picture if provided
    if cover_image_path:
        cmd.extend(["-map", f"{image_input_index}:v:0"])
    
    # Map text subtitle streams from source
    subtitle_count = 0
    if subtitle_streams:
        for sub_idx, sub_lang in subtitle_streams:
            cmd.extend(["-map", f"0:{sub_idx}"])
            subtitle_count += 1
    
    # Map generated subtitle files
    for idx, gen_sub in enumerate(generated_subtitles):
        cmd.extend(["-map", f"{idx + 1}:s:0"])
        subtitle_count += 1
    
    # Set codecs: video copy, audio copy, image mjpeg
    # Set codecs for all streams after mapping
    if cover_image_path:
        cmd.extend([
            "-c:v:0", "copy",
            "-c:v:1", "mjpeg",
            "-disposition:v:1", "attached_pic",
        ])
    else:
        cmd.extend([
            "-c:v:0", "copy",
        ])
    
    cmd.extend([
        "-c:a", "copy",
    ])
    
    # Set subtitle codecs (MP4 only supports mov_text)
    subtitle_stream_idx = 0
    if subtitle_streams:
        for idx, (sub_idx, sub_lang) in enumerate(subtitle_streams):
            cmd.extend(["-c:s:{}".format(subtitle_stream_idx), MP4_SUBTITLE_CODEC])
            if sub_lang:
                cmd.extend(["-metadata:s:s:{}".format(subtitle_stream_idx), f"language={sub_lang}"])
            subtitle_stream_idx += 1
    
    # Set codecs for generated subtitle files
    for idx, gen_sub in enumerate(generated_subtitles):
        cmd.extend(["-c:s:{}".format(subtitle_stream_idx), MP4_SUBTITLE_CODEC])
        if gen_sub.language:
            cmd.extend(["-metadata:s:s:{}".format(subtitle_stream_idx), f"language={gen_sub.language}"])
        subtitle_stream_idx += 1
    
    # Check if video codec is HEVC and add tag for Apple TV compatibility
    if probe_data and "streams" in probe_data:
        for stream in probe_data["streams"]:
            if stream.get("codec_type") == "video":
                codec_name = stream.get("codec_name", "").lower()
                if codec_name in ["hevc", "h265"]:
                    cmd.extend(["-tag:v:0", VIDEO_TAG_HVC1])
                break

    if subtitle_count == 0 and len(generated_subtitles) == 0:
        cmd.append("-sn")
    
    # Add episode metadata if available
    if media_metadata:
        cmd.extend(metadata_to_ffmpeg_args(media_metadata))
    
    cmd.extend([
        "-f",
        "mp4",
        "-movflags",
        "+faststart",
        "-loglevel",
        FFMPEG_LOGLEVEL,  # Show info messages (for faststart detection) but suppress stats
        "-nostats",  # Suppress default progress output
        "-progress",
        "pipe:1",  # Parse this for progress display
        "-y",
        str(output_path),
    ])
    
    return cmd


def parse_ffmpeg_progress(line: str) -> dict[str, int | float | str] | None:
    """
    Parse ffmpeg progress line and extract key metrics.
    Supports both stderr format and progress pipe format.
    
    Args:
        line: Single line from ffmpeg stderr or progress output
    
    Returns:
        Dictionary with progress metrics or None if not a progress line
    """
    line = line.strip()
    if not line:
        return None
    
    # Progress pipe format: key=value pairs (one per line)
    if "=" in line and not line.startswith("frame="):
        # Parse progress pipe format - each line is a single key=value pair
        if "=" in line:
            key, value = line.split("=", 1)
            # Return None here - we'll accumulate these in the calling function
            return {"_raw": {key: value}}
    
    # Standard stderr format: frame=  123 fps= 25 q=28.0 size=    1024kB time=00:00:05.00 bitrate=1677.7kbits/s speed=1.0x
    progress_patterns = [
        # Standard format with q
        re.compile(
            r"frame=\s*(\d+)\s+fps=\s*([\d.]+)\s+q=([\d.-]+)\s+"
            r"size=\s*(\d+)kB\s+time=([\d:\.]+)\s+"
            r"bitrate=\s*([\d.]+)kbits/s\s+speed=\s*([\d.]+)x"
        ),
        # Format without q
        re.compile(
            r"frame=\s*(\d+)\s+fps=\s*([\d.]+)\s+"
            r"size=\s*(\d+)kB\s+time=([\d:\.]+)\s+"
            r"bitrate=\s*([\d.]+)kbits/s\s+speed=\s*([\d.]+)x"
        ),
    ]
    
    for pattern in progress_patterns:
        match = pattern.search(line)
        if match:
            groups = match.groups()
            if len(groups) == 7:
                return {
                    "frame": int(groups[0]),
                    "fps": float(groups[1]),
                    "q": float(groups[2]),
                    "size_kb": int(groups[3]),
                    "time": groups[4],
                    "bitrate": float(groups[5]),
                    "speed": float(groups[6]),
                }
            elif len(groups) == 6:
                return {
                    "frame": int(groups[0]),
                    "fps": float(groups[1]),
                    "q": 0.0,
                    "size_kb": int(groups[2]),
                    "time": groups[3],
                    "bitrate": float(groups[4]),
                    "speed": float(groups[5]),
                }
    return None


def run_ffmpeg_with_progress(
    cmd: list[str],
    total_duration: float | None = None,
    output_path: Path | None = None,
    input_size_bytes: int | None = None,
    total_frames: int | None = None,
    source_fps: float | None = None,
) -> tuple[int, str]:
    """
    Run ffmpeg command and display FFmpeg's default progress output.
    
    Args:
        cmd: ffmpeg command as list of arguments
        total_duration: Total video duration in seconds (for speed calculation in rewraps)
        output_path: Output file path (for size fallback)
        input_size_bytes: Input file size in bytes (for percentage calculation in rewraps)
        total_frames: Total frame count (for percentage calculation in transcodes)
        source_fps: Source video FPS (for calculating stream time position from frame count)
    
    Returns:
        Tuple of (returncode, error_output)
    """
    # Use progress pipe (stdout) only for faststart detection, stderr for default progress
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,  # Progress pipe (for faststart detection only)
        stderr=subprocess.PIPE,  # Default FFmpeg progress output
        text=True,
        bufsize=1,
    )
    
    error_lines = []
    faststart_message_shown = False
    stdout_queue = queue.Queue()  # Progress pipe
    stderr_queue = queue.Queue()  # Errors only
    
    progress_data = {}  # Accumulate progress pipe key=value pairs
    last_frame_count = 0
    last_frame_time = None
    speed_calculated = 1.0
    transcode_start_time = None
    rewrap_start_time = None
    
    def read_stdout():
        """Read stdout (progress pipe)."""
        for line in iter(process.stdout.readline, ''):
            if line:
                stdout_queue.put(line)
        process.stdout.close()
    
    def read_stderr():
        """Read stderr (errors only)."""
        for line in iter(process.stderr.readline, ''):
            if line:
                stderr_queue.put(line)
        process.stderr.close()
    
    # Start reading both streams in separate threads
    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    
    # Process lines as they come
    while True:
        process_done = process.poll() is not None
        stdout_empty = stdout_queue.empty()
        stderr_empty = stderr_queue.empty()
        
        # Exit if process is done and all queues are empty
        if process_done and stdout_empty and stderr_empty:
            break
        
        # Check stdout (progress pipe) - parse and display compactly
        try:
            line = stdout_queue.get(timeout=0.01)
            if line:
                line = line.strip()
                if line and "=" in line:
                    key, value = line.split("=", 1)
                    progress_data[key] = value
                    
                    # Display progress when we have frame data (for transcodes) or time data (for rewraps)
                    should_display = False
                    if total_frames and "frame" in progress_data:
                        # Transcode: display when we have frame data
                        should_display = True
                    elif input_size_bytes and ("out_time" in progress_data or "out_time_ms" in progress_data):
                        # Rewrap: display when we have time data
                        should_display = True
                    
                    # Calculate speed from frame progression if we have frame data (for transcodes)
                    if "frame" in progress_data and source_fps and source_fps > 0:
                        try:
                            current_frame = int(progress_data["frame"])
                            current_time = time.time()
                            
                            # Track start time for time remaining calculation
                            if transcode_start_time is None:
                                transcode_start_time = current_time
                            
                            if last_frame_time is not None and last_frame_count >= 0:
                                # Calculate speed: frames processed per second / source FPS
                                frames_delta = current_frame - last_frame_count
                                time_delta = current_time - last_frame_time
                                # Only update if we have meaningful progress (at least 0.1 seconds elapsed)
                                if time_delta > 0.1 and frames_delta > 0:
                                    frames_per_second = frames_delta / time_delta
                                    calculated_speed = frames_per_second / source_fps
                                    # Only update if we got a reasonable speed value
                                    if calculated_speed > 0.01:
                                        speed_calculated = calculated_speed
                            
                            last_frame_count = current_frame
                            last_frame_time = current_time
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
                    
                    # Calculate speed from percentage progress if we have size data (for rewraps)
                    if input_size_bytes and input_size_bytes > 0 and total_duration and total_duration > 0:
                        try:
                            # Get current size from progress data or file
                            current_size = 0
                            for size_field in ["out_size", "total_size", "size"]:
                                if size_field in progress_data:
                                    try:
                                        size_val = progress_data[size_field]
                                        if size_val and size_val != "N/A":
                                            current_size = int(size_val)
                                            if current_size > 0:
                                                break
                                    except (ValueError, TypeError):
                                        continue
                            
                            # Fallback: check output file size if available
                            if current_size == 0 and output_path and output_path.exists():
                                try:
                                    current_size = output_path.stat().st_size
                                except (OSError, AttributeError):
                                    pass
                            
                            if current_size > 0:
                                current_time = time.time()
                                
                                # Track start time for rewrap speed calculation
                                if rewrap_start_time is None:
                                    rewrap_start_time = current_time
                                
                                # Calculate percentage progress
                                percentage = min(100.0, (current_size / input_size_bytes) * 100.0)
                                
                                if percentage > 0.1 and rewrap_start_time is not None:
                                    elapsed_time = current_time - rewrap_start_time
                                    if elapsed_time > 0.1:
                                        # Speed = percentage progress / (elapsed_time / total_duration)
                                        # This gives us how fast we're processing relative to real-time
                                        expected_progress = (elapsed_time / total_duration) * 100.0
                                        if expected_progress > 0:
                                            calculated_speed = percentage / expected_progress
                                            # Only update if we got a reasonable speed value
                                            if calculated_speed > 0.01:
                                                speed_calculated = calculated_speed
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
                    
                    if not faststart_message_shown and should_display:
                        # Get time - prefer out_time, fallback to calculating from frame count using source FPS
                        time_str = progress_data.get("out_time", "")
                        if not time_str or time_str == "N/A":
                            # Calculate time from frame count and source FPS (not encoding FPS)
                            if total_frames and "frame" in progress_data and source_fps and source_fps > 0:
                                try:
                                    current_frame = int(progress_data["frame"])
                                    # Use source FPS to calculate stream position, not encoding FPS
                                    seconds = current_frame / source_fps
                                    hours = int(seconds // 3600)
                                    minutes = int((seconds % 3600) // 60)
                                    secs = seconds % 60
                                    time_str = f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
                                except (ValueError, TypeError, ZeroDivisionError):
                                    time_str = "00:00:00.000"
                            else:
                                time_str = "00:00:00.000"
                        
                        # Try to get size from progress data
                        size_bytes = 0
                        for size_field in ["out_size", "total_size", "size"]:
                            if size_field in progress_data:
                                try:
                                    size_val = progress_data[size_field]
                                    if size_val and size_val != "N/A":
                                        size_bytes = int(size_val)
                                        if size_bytes > 0:
                                            break
                                except (ValueError, TypeError):
                                    continue
                        
                        # Fallback: check output file size if available
                        if size_bytes == 0 and output_path and output_path.exists():
                            try:
                                size_bytes = output_path.stat().st_size
                            except (OSError, AttributeError):
                                pass
                        
                        size_mb = size_bytes / (1024 * 1024) if size_bytes > 0 else 0.0
                        
                        # Use calculated speed (already computed above if frame data available)
                        # Only use default 1.0 if we truly don't have a valid speed yet
                        speed = speed_calculated if speed_calculated > 0.01 else 1.0
                        
                        # Calculate percentage for rewraps (based on file size) or transcodes (based on frame count)
                        percentage_str = ""
                        time_remaining_str = ""
                        if input_size_bytes and input_size_bytes > 0 and size_bytes > 0:
                            # Rewrap: use file size
                            percentage = min(100.0, (size_bytes / input_size_bytes) * 100.0)
                            percentage_str = f"{percentage:5.1f}% | "
                        elif total_frames and total_frames > 0 and "frame" in progress_data:
                            # Transcode: use frame count
                            try:
                                current_frame = int(progress_data["frame"])
                                percentage = min(100.0, (current_frame / total_frames) * 100.0)
                                percentage_str = f"{percentage:5.1f}% | "
                                
                                # Calculate time remaining for transcodes
                                if transcode_start_time is not None and percentage > 0.1:
                                    elapsed_time = time.time() - transcode_start_time
                                    if elapsed_time > 0:
                                        # Estimated total time = elapsed_time / (percentage / 100)
                                        estimated_total_time = elapsed_time / (percentage / 100.0)
                                        remaining_time = estimated_total_time - elapsed_time
                                        
                                        if remaining_time > 0:
                                            hours_remaining = int(remaining_time // 3600)
                                            minutes_remaining = int((remaining_time % 3600) // 60)
                                            seconds_remaining = int(remaining_time % 60)
                                            
                                            if hours_remaining > 0:
                                                time_remaining_str = f" | ETA {hours_remaining:02d}:{minutes_remaining:02d}:{seconds_remaining:02d}"
                                            else:
                                                time_remaining_str = f" | ETA {minutes_remaining:02d}:{seconds_remaining:02d}"
                            except (ValueError, TypeError, ZeroDivisionError):
                                pass
                        
                        print(f"\r{percentage_str}time={time_str} size={size_mb:7.1f}MB speed={speed:5.2f}x{time_remaining_str}", end="", flush=True)
        except queue.Empty:
            pass
        
        # Check stderr (errors and faststart message only)
        try:
            line = stderr_queue.get(timeout=0.01)
            if line:
                line = line.strip()
                if line:
                    # Check for faststart message
                    if "Starting second pass: moving the moov atom to the beginning of the file" in line:
                        if not faststart_message_shown:
                            # Show 100% progress before faststart message
                            if "out_time" in progress_data or "out_time_ms" in progress_data:
                                time_str = progress_data.get("out_time", "00:00:00")
                                size_bytes = 0
                                for size_field in ["out_size", "total_size", "size"]:
                                    if size_field in progress_data:
                                        try:
                                            size_val = progress_data[size_field]
                                            if size_val and size_val != "N/A":
                                                size_bytes = int(size_val)
                                                if size_bytes > 0:
                                                    break
                                        except (ValueError, TypeError):
                                            continue
                                
                                if size_bytes == 0 and output_path and output_path.exists():
                                    try:
                                        size_bytes = output_path.stat().st_size
                                    except (OSError, AttributeError):
                                        pass
                                
                                size_mb = size_bytes / (1024 * 1024) if size_bytes > 0 else 0.0
                                speed_str = progress_data.get("speed", "1.0x").replace("x", "")
                                try:
                                    speed = float(speed_str)
                                except (ValueError, TypeError):
                                    speed = 1.0
                                
                                # Show 100% when faststart begins (main encoding/rewrapping is complete)
                                percentage_str = "100.0% | "
                                
                                print(f"\r{percentage_str}time={time_str} size={size_mb:7.1f}MB speed={speed:5.2f}x", end="", flush=True)
                                time.sleep(0.1)  # Brief pause to show 100%
                            
                            faststart_message_shown = True
                            print()  # New line
                            print("Optimizing stream for fast start...")
                        continue  # Don't print the FFmpeg message
                    
                    # Only show actual errors (not warnings or info messages)
                    # Filter out: stream info, metadata, configuration, warnings
                    if any(skip in line.lower() for skip in [
                        "ffmpeg version", "built with", "configuration:", "libav",
                        "input #", "output #", "stream #", "metadata:", "duration:",
                        "encoder", "bps", "number_of", "statistics", "stream mapping",
                        "press [q]", "frame=", "fps=", "size=", "time=", "bitrate=",
                        "speed=", "[mp4 @", "packet duration", "pts has no value",
                        "muxing overhead", "elapsed="
                    ]):
                        # Suppress these info/warning lines
                        if "error" in line.lower() and not any(warn in line.lower() for warn in ["warning", "info"]):
                            # Only show actual errors
                            print(line, flush=True)
                            error_lines.append(line)
                        continue
                    
                    # Show only fatal errors
                    if "error" in line.lower() and "fatal" in line.lower():
                        print(line, flush=True)
                        error_lines.append(line)
        except queue.Empty:
            pass
    
    # Ensure process has finished
    if process.poll() is None:
        process.wait()
    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    
    # Process any remaining stdout lines
    while not stdout_queue.empty():
        try:
            line = stdout_queue.get_nowait()
            if line:
                line = line.strip()
                if line and "=" in line:
                    key, value = line.split("=", 1)
                    progress_data[key] = value
                    # Don't display progress after faststart message
                    should_display = False
                    if total_frames and "frame" in progress_data:
                        # Transcode: display when we have frame data
                        should_display = True
                    elif input_size_bytes and ("out_time" in progress_data or "out_time_ms" in progress_data):
                        # Rewrap: display when we have time data
                        should_display = True
                    
                    if not faststart_message_shown and should_display:
                        # Get time - prefer out_time, fallback to calculating from frame count using source FPS
                        time_str = progress_data.get("out_time", "")
                        if not time_str or time_str == "N/A":
                            # Calculate time from frame count and source FPS (not encoding FPS)
                            if total_frames and "frame" in progress_data and source_fps and source_fps > 0:
                                try:
                                    current_frame = int(progress_data["frame"])
                                    # Use source FPS to calculate stream position, not encoding FPS
                                    seconds = current_frame / source_fps
                                    hours = int(seconds // 3600)
                                    minutes = int((seconds % 3600) // 60)
                                    secs = seconds % 60
                                    time_str = f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
                                except (ValueError, TypeError, ZeroDivisionError):
                                    time_str = "00:00:00.000"
                            else:
                                time_str = "00:00:00.000"
                        
                        # Try to get size from progress data
                        size_bytes = 0
                        for size_field in ["out_size", "total_size", "size"]:
                            if size_field in progress_data:
                                try:
                                    size_val = progress_data[size_field]
                                    if size_val and size_val != "N/A":
                                        size_bytes = int(size_val)
                                        if size_bytes > 0:
                                            break
                                except (ValueError, TypeError):
                                    continue
                        
                        # Fallback: check output file size if available
                        if size_bytes == 0 and output_path and output_path.exists():
                            try:
                                size_bytes = output_path.stat().st_size
                            except (OSError, AttributeError):
                                pass
                        
                        size_mb = size_bytes / (1024 * 1024) if size_bytes > 0 else 0.0
                        
                        # Use calculated speed (already computed above if frame data available)
                        # Only use default 1.0 if we truly don't have a valid speed yet
                        speed = speed_calculated if speed_calculated > 0.01 else 1.0
                        
                        # Calculate percentage for rewraps (based on file size) or transcodes (based on frame count)
                        percentage_str = ""
                        time_remaining_str = ""
                        if input_size_bytes and input_size_bytes > 0 and size_bytes > 0:
                            # Rewrap: use file size
                            percentage = min(100.0, (size_bytes / input_size_bytes) * 100.0)
                            percentage_str = f"{percentage:5.1f}% | "
                        elif total_frames and total_frames > 0 and "frame" in progress_data:
                            # Transcode: use frame count
                            try:
                                current_frame = int(progress_data["frame"])
                                percentage = min(100.0, (current_frame / total_frames) * 100.0)
                                percentage_str = f"{percentage:5.1f}% | "
                                
                                # Calculate time remaining for transcodes
                                if transcode_start_time is not None and percentage > 0.1:
                                    elapsed_time = time.time() - transcode_start_time
                                    if elapsed_time > 0:
                                        # Estimated total time = elapsed_time / (percentage / 100)
                                        estimated_total_time = elapsed_time / (percentage / 100.0)
                                        remaining_time = estimated_total_time - elapsed_time
                                        
                                        if remaining_time > 0:
                                            hours_remaining = int(remaining_time // 3600)
                                            minutes_remaining = int((remaining_time % 3600) // 60)
                                            seconds_remaining = int(remaining_time % 60)
                                            
                                            if hours_remaining > 0:
                                                time_remaining_str = f" | ETA {hours_remaining:02d}:{minutes_remaining:02d}:{seconds_remaining:02d}"
                                            else:
                                                time_remaining_str = f" | ETA {minutes_remaining:02d}:{seconds_remaining:02d}"
                            except (ValueError, TypeError, ZeroDivisionError):
                                pass
                        
                        print(f"\r{percentage_str}time={time_str} size={size_mb:7.1f}MB speed={speed:5.2f}x{time_remaining_str}", end="", flush=True)
        except queue.Empty:
            break
    
    # Process any remaining stderr lines
    while not stderr_queue.empty():
        try:
            line = stderr_queue.get_nowait()
            if line:
                line = line.strip()
                if line:
                    # Only show actual errors, filter out info/warnings
                    if any(skip in line.lower() for skip in [
                        "ffmpeg version", "built with", "configuration:", "libav",
                        "input #", "output #", "stream #", "metadata:", "duration:",
                        "encoder", "bps", "number_of", "statistics", "stream mapping",
                        "press [q]", "frame=", "fps=", "size=", "time=", "bitrate=",
                        "speed=", "[mp4 @", "packet duration", "pts has no value",
                        "muxing overhead", "elapsed="
                    ]):
                        if "error" in line.lower() and "fatal" in line.lower():
                            print(line, flush=True)
                            error_lines.append(line)
                        continue
                    
                    if "error" in line.lower() and "fatal" in line.lower():
                        print(line, flush=True)
                        error_lines.append(line)
        except queue.Empty:
            break
    
    # Print newline after progress line
    if not faststart_message_shown:
        print()
    
    return process.returncode, "\n".join(error_lines)

