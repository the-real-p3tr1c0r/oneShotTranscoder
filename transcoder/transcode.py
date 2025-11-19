"""Main transcoding logic for MKV to MP4 conversion."""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from transcoder.metadata import (
    DEFAULT_FILENAME_PATTERN,
    EpisodeMetadata,
    build_pattern_regex,
    metadata_to_ffmpeg_args,
    parse_episode_metadata,
)
from transcoder.subtitles import (
    GeneratedSubtitle,
    SubtitleStreamInfo,
    convert_bitmap_subtitles,
    probe_subtitle_streams,
)
from transcoder.utils import (
    calculate_target_bitrate,
    check_ffmpeg_available,
    convert_image_for_apple_tv,
    detect_gpu_encoder,
    find_cover_image,
    find_mkv_files,
    get_output_path,
    get_text_subtitle_streams,
    get_video_duration,
    probe_video_file,
)


def build_transcode_command(
    input_path: Path,
    output_path: Path,
    video_bitrate_kbps: float,
    subtitle_streams: List[Tuple[int, Optional[str]]],
    encoder: str = None,
    generated_subtitles: List[GeneratedSubtitle] = None,
    episode_metadata: EpisodeMetadata = None,
    cover_image_path: Optional[Path] = None,
) -> List[str]:
    """
    Build ffmpeg command for transcoding mode.
    
    Args:
        input_path: Input .mkv file path
        output_path: Output .mp4 file path
        video_bitrate_kbps: Target video bitrate in kbps
        subtitle_streams: List of tuples (stream_index, language_code) for text subtitles
        encoder: Video encoder to use (auto-detected if None)
        generated_subtitles: List of generated subtitle files from OCR
        episode_metadata: Episode metadata for Apple TV tags
        cover_image_path: Optional path to cover image to embed as thumbnail
    
    Returns:
        List of command arguments for ffmpeg
    """
    if encoder is None:
        encoder = detect_gpu_encoder()
    
    if generated_subtitles is None:
        generated_subtitles = []
    
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
    
    cmd.extend([
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
    ])
    
    # Map cover image as attached picture if provided (before setting codecs)
    if cover_image_path:
        cmd.extend(["-map", f"{image_input_index}:v:0"])
    
    # Set codec for main video stream explicitly (use :0 to avoid affecting cover image)
    cmd.extend([
        "-c:v:0",
        encoder,
        "-b:v:0",
        f"{int(video_bitrate_kbps)}k",
    ])
    
    if encoder == "hevc_nvenc":
        cmd.extend(["-preset", "p4", "-rc", "vbr"])
    elif encoder == "hevc_amf":
        cmd.extend(["-quality", "balanced", "-rc", "vbr_peak"])
    elif encoder == "hevc_qsv":
        cmd.extend(["-preset", "medium", "-global_quality", "23"])
    elif encoder == "hevc_videotoolbox":
        cmd.extend(["-quality", "1"])  # 0=realtime, 1=best, 2=better
    else:
        cmd.extend(["-preset", "medium"])
    
    # Add HEVC tag for main video stream only (not cover image)
    if encoder in ["hevc_nvenc", "hevc_amf", "hevc_qsv", "hevc_videotoolbox", "libx265"]:
        cmd.extend(["-tag:v:0", "hvc1"])
    
    # Set codec for cover image if provided
    if cover_image_path:
        cmd.extend(["-c:v:1", "mjpeg"])
        cmd.extend(["-disposition:v:1", "attached_pic"])
    
    cmd.extend([
        "-c:a",
        "aac",
        "-b:a",
        "192k",
    ])
    
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
    
    if subtitle_count > 0:
        # Set codec and language metadata for all subtitle streams
        stream_idx = 0
        # Original text subtitles
        if subtitle_streams:
            for sub_idx, sub_lang in subtitle_streams:
                cmd.extend(["-c:s:{}".format(stream_idx), "mov_text"])
                if sub_lang:
                    cmd.extend(["-metadata:s:s:{}".format(stream_idx), f"language={sub_lang}"])
                stream_idx += 1
        # Generated OCR subtitles
        for gen_sub in generated_subtitles:
            cmd.extend(["-c:s:{}".format(stream_idx), "mov_text"])
            if gen_sub.language:
                cmd.extend(["-metadata:s:s:{}".format(stream_idx), f"language={gen_sub.language}"])
            stream_idx += 1
    else:
        cmd.append("-sn")
    
    # Add episode metadata if available
    if episode_metadata:
        cmd.extend(metadata_to_ffmpeg_args(episode_metadata))
    
    cmd.extend([
        "-f",
        "mp4",
        "-movflags",
        "+faststart",
        "-hide_banner",
        "-progress",
        "pipe:1",
        "-stats_period",
        "0.5",
        "-y",
        str(output_path),
    ])
    
    return cmd


def build_rewrap_command(
    input_path: Path,
    output_path: Path,
    subtitle_streams: List[Tuple[int, Optional[str]]],
    probe_data: dict = None,
    generated_subtitles: List[GeneratedSubtitle] = None,
    episode_metadata: EpisodeMetadata = None,
    cover_image_path: Optional[Path] = None,
) -> List[str]:
    """
    Build ffmpeg command for rewrap mode (stream copy).
    
    Args:
        input_path: Input .mkv file path
        output_path: Output .mp4 file path
        subtitle_streams: List of tuples (stream_index, language_code) for text subtitles
        probe_data: Video probe data to detect codec (optional)
        generated_subtitles: List of generated subtitle files from OCR
        episode_metadata: Episode metadata for Apple TV tags
        cover_image_path: Optional path to cover image to embed as thumbnail
    
    Returns:
        List of command arguments for ffmpeg
    """
    if generated_subtitles is None:
        generated_subtitles = []
    
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
    
    # Set codecs: video copy, audio copy, image mjpeg
    cmd.extend([
        "-c:v:0",
        "copy",
        "-c:a",
        "copy",
    ])
    
    # Set codec for cover image if provided
    if cover_image_path:
        cmd.extend(["-c:v:1", "mjpeg"])
        cmd.extend(["-disposition:v:1", "attached_pic"])
    
    # Check if video codec is HEVC and add tag for Apple TV compatibility
    if probe_data and "streams" in probe_data:
        for stream in probe_data["streams"]:
            if stream.get("codec_type") == "video":
                codec_name = stream.get("codec_name", "").lower()
                if codec_name in ["hevc", "h265"]:
                    cmd.extend(["-tag:v:0", "hvc1"])
                break
    
    # Map text subtitle streams from source
    subtitle_count = 0
    if subtitle_streams:
        for idx, (sub_idx, sub_lang) in enumerate(subtitle_streams):
            cmd.extend(["-map", f"0:{sub_idx}"])
            cmd.extend(["-c:s:{}".format(idx), "copy"])
            if sub_lang:
                cmd.extend(["-metadata:s:s:{}".format(idx), f"language={sub_lang}"])
            subtitle_count += 1
    
    # Map generated subtitle files
    for idx, gen_sub in enumerate(generated_subtitles):
        output_sub_idx = subtitle_count + idx
        cmd.extend(["-map", f"{idx + 1}:s:0"])
        cmd.extend(["-c:s:{}".format(output_sub_idx), "mov_text"])
        if gen_sub.language:
            cmd.extend(["-metadata:s:s:{}".format(output_sub_idx), f"language={gen_sub.language}"])

    if subtitle_count == 0 and len(generated_subtitles) == 0:
        cmd.append("-sn")
    
    # Add episode metadata if available
    if episode_metadata:
        cmd.extend(metadata_to_ffmpeg_args(episode_metadata))
    
    cmd.extend([
        "-f",
        "mp4",
        "-movflags",
        "+faststart",
        "-hide_banner",
        "-progress",
        "pipe:1",
        "-stats_period",
        "0.5",
        "-y",
        str(output_path),
    ])
    
    return cmd


def parse_ffmpeg_progress(line: str) -> dict:
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


def run_ffmpeg_with_progress(cmd: List[str], total_duration: float = None) -> Tuple[int, str]:
    """
    Run ffmpeg command and display compact progress updates.
    
    Args:
        cmd: ffmpeg command as list of arguments
    
    Returns:
        Tuple of (returncode, error_output)
    """
    import threading
    import queue
    
    # Use progress pipe (stdout) for progress, stderr for errors
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    
    error_lines = []
    last_progress = None
    stdout_queue = queue.Queue()
    stderr_queue = queue.Queue()
    progress_data = {}  # Accumulate progress pipe key=value pairs
    
    def read_stdout():
        """Read stdout (progress pipe) in a separate thread."""
        for line in iter(process.stdout.readline, ''):
            if line:
                stdout_queue.put(line)
        process.stdout.close()
    
    def read_stderr():
        """Read stderr (errors) in a separate thread."""
        for line in iter(process.stderr.readline, ''):
            if line:
                stderr_queue.put(line)
        process.stderr.close()
    
    # Start reading both streams in separate threads
    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    
    def format_progress_from_data(data: dict) -> dict:
        """Convert progress pipe data to display format."""
        current_seconds = None
        
        if "out_time" in data:
            time_str = data["out_time"]
            # Parse time string to seconds for percentage calculation
            try:
                parts = time_str.split(":")
                if len(parts) == 3:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    secs = float(parts[2])
                    current_seconds = hours * 3600 + minutes * 60 + secs
            except (ValueError, TypeError):
                pass
        elif "out_time_ms" in data:
            # Convert microseconds to time string
            try:
                us = int(data["out_time_ms"])
                seconds = us / 1000000.0
                current_seconds = seconds
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                secs = seconds % 60
                time_str = f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
            except (ValueError, TypeError):
                time_str = "00:00:00.000"
        else:
            return None
        
        # Parse size - try multiple field names
        size_bytes = 0
        for field in ["out_size", "size", "total_size"]:
            if field in data:
                try:
                    size_bytes = int(data[field])
                    break
                except (ValueError, TypeError):
                    pass
        
        # If size not available, try to calculate from bitrate and time
        if size_bytes == 0 and current_seconds and "bitrate" in data:
            try:
                bitrate_bps = float(data["bitrate"]) * 1000  # Convert kbps to bps
                size_bytes = int((bitrate_bps * current_seconds) / 8)
            except (ValueError, TypeError):
                pass
        
        size_kb = size_bytes // 1024
        
        # Parse speed
        speed = 1.0
        if "speed" in data:
            try:
                speed_str = str(data["speed"]).replace("x", "").replace("N/A", "1.0")
                speed = float(speed_str)
            except (ValueError, TypeError):
                speed = 1.0
        
        # Calculate percentage if we have total duration
        percentage = None
        if total_duration and current_seconds:
            percentage = min(100.0, max(0.0, (current_seconds / total_duration) * 100.0))
        
        return {
            "time": time_str,
            "size_kb": size_kb,
            "speed": speed,
            "percentage": percentage,
        }
    
    # Process lines as they come
    while process.poll() is None or not stdout_queue.empty() or not stderr_queue.empty():
        # Check stdout for progress (progress pipe format)
        try:
            line = stdout_queue.get(timeout=0.1)
            if line:
                line = line.strip()
                if line and "=" in line:
                    # Progress pipe format: one key=value per line
                    key, value = line.split("=", 1)
                    progress_data[key] = value
                    
                    # Update display whenever we have time info (and ideally size/speed)
                    # Update more frequently for better feedback
                    if "out_time" in progress_data or "out_time_ms" in progress_data:
                        formatted = format_progress_from_data(progress_data)
                        if formatted:
                            last_progress = formatted
                            time_str = formatted["time"]
                            size_kb = formatted["size_kb"]
                            size_mb = size_kb / 1024
                            speed = formatted["speed"]
                            percentage = formatted.get("percentage")
                            
                            if percentage is not None:
                                print(
                                    f"\rProgress: {percentage:5.1f}% | {time_str} | {size_mb:.1f}MB | {speed:.2f}x speed",
                                    end="",
                                    flush=True,
                                )
                            else:
                                print(
                                    f"\rProgress: {time_str} | {size_mb:.1f}MB | {speed:.2f}x speed",
                                    end="",
                                    flush=True,
                                )
        except queue.Empty:
            pass
        
        # Check stderr for errors and also try to parse progress (fallback)
        try:
            line = stderr_queue.get(timeout=0.01)
            if line:
                line = line.strip()
                if line:
                    progress = parse_ffmpeg_progress(line)
                    if progress and "_raw" not in progress:
                        last_progress = progress
                        time_str = progress.get("time", "00:00:00.00")
                        size_kb = progress.get("size_kb", 0)
                        size_mb = size_kb / 1024 if size_kb > 0 else 0
                        speed = progress.get("speed", 0.0)
                        
                        # Calculate percentage from time if we have total duration
                        percentage = None
                        if total_duration:
                            try:
                                parts = time_str.split(":")
                                if len(parts) == 3:
                                    hours = int(parts[0])
                                    minutes = int(parts[1])
                                    secs = float(parts[2])
                                    current_seconds = hours * 3600 + minutes * 60 + secs
                                    percentage = min(100.0, max(0.0, (current_seconds / total_duration) * 100.0))
                            except (ValueError, TypeError):
                                pass
                        
                        if percentage is not None:
                            print(
                                f"\rProgress: {percentage:5.1f}% | {time_str} | {size_mb:.1f}MB | {speed:.2f}x speed",
                                end="",
                                flush=True,
                            )
                        else:
                            print(
                                f"\rProgress: {time_str} | {size_mb:.1f}MB | {speed:.2f}x speed",
                                end="",
                                flush=True,
                            )
                    elif "error" in line.lower() or "failed" in line.lower():
                        error_lines.append(line)
        except queue.Empty:
            continue
    
    process.wait()
    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    
    # Process any remaining lines
    while not stdout_queue.empty():
        try:
            line = stdout_queue.get_nowait()
            if line:
                line = line.strip()
                if line and "=" in line:
                    key, value = line.split("=", 1)
                    progress_data[key] = value
                    formatted = format_progress_from_data(progress_data)
                    if formatted:
                        last_progress = formatted
                        time_str = formatted["time"]
                        size_kb = formatted["size_kb"]
                        size_mb = size_kb / 1024
                        speed = formatted["speed"]
                        percentage = formatted.get("percentage")
                        
                        if percentage is not None:
                            print(
                                f"\rProgress: {percentage:5.1f}% | {time_str} | {size_mb:.1f}MB | {speed:.2f}x speed",
                                end="",
                                flush=True,
                            )
                        else:
                            print(
                                f"\rProgress: {time_str} | {size_mb:.1f}MB | {speed:.2f}x speed",
                                end="",
                                flush=True,
                            )
        except queue.Empty:
            break
    
    while not stderr_queue.empty():
        try:
            line = stderr_queue.get_nowait()
            if line:
                line = line.strip()
                if line:
                    progress = parse_ffmpeg_progress(line)
                    if progress and "_raw" not in progress:
                        last_progress = progress
                        time_str = progress.get("time", "00:00:00.00")
                        size_kb = progress.get("size_kb", 0)
                        size_mb = size_kb / 1024 if size_kb > 0 else 0
                        speed = progress.get("speed", 0.0)
                        
                        # Calculate percentage from time if we have total duration
                        percentage = None
                        if total_duration:
                            try:
                                parts = time_str.split(":")
                                if len(parts) == 3:
                                    hours = int(parts[0])
                                    minutes = int(parts[1])
                                    secs = float(parts[2])
                                    current_seconds = hours * 3600 + minutes * 60 + secs
                                    percentage = min(100.0, max(0.0, (current_seconds / total_duration) * 100.0))
                            except (ValueError, TypeError):
                                pass
                        
                        if percentage is not None:
                            print(
                                f"\rProgress: {percentage:5.1f}% | {time_str} | {size_mb:.1f}MB | {speed:.2f}x speed",
                                end="",
                                flush=True,
                            )
                        else:
                            print(
                                f"\rProgress: {time_str} | {size_mb:.1f}MB | {speed:.2f}x speed",
                                end="",
                                flush=True,
                            )
                    elif "error" in line.lower() or "failed" in line.lower():
                        error_lines.append(line)
        except queue.Empty:
            break
    
    if last_progress:
        print()
    
    return process.returncode, "\n".join(error_lines)


def transcode_file(
    input_path: Path,
    rewrap: bool = False,
    target_size_mb_per_hour: float = 900.0,
    filename_pattern: str = DEFAULT_FILENAME_PATTERN,
    convert_bitmap_subs: bool = True,
    target_dir: Optional[Path] = None,
) -> bool:
    """
    Transcode a single MKV file to MP4.
    
    Args:
        input_path: Path to input .mkv file
        rewrap: If True, copy streams without transcoding
        target_size_mb_per_hour: Target file size in MB per hour
        filename_pattern: Pattern for parsing metadata from filename
        convert_bitmap_subs: If True, convert bitmap subtitles to text using OCR
        target_dir: Optional target directory for output. If None, output is in same directory as input.
    
    Returns:
        True if successful, False otherwise
    """
    output_path = get_output_path(input_path, target_dir)
    
    print(f"Processing: {input_path.name}")
    
    temp_dirs = []
    generated_subtitles = []
    episode_metadata = None
    cover_image_path = None
    
    try:
        # Parse metadata from filename
        filename_regex = build_pattern_regex(filename_pattern)
        episode_metadata = parse_episode_metadata(input_path, filename_regex)
        if episode_metadata:
            print(f"Metadata: {episode_metadata.series_name} - {episode_metadata.episode_id} - {episode_metadata.episode_title}")
        
        probe_data = probe_video_file(input_path)
        text_subtitle_streams = get_text_subtitle_streams(probe_data)
        
        # Find and convert cover image if available
        cover_image = find_cover_image(input_path.parent)
        if cover_image:
            try:
                # Create temp directory for converted image
                import tempfile
                image_temp_dir = Path(tempfile.mkdtemp(prefix=f"{input_path.stem}_cover_"))
                temp_dirs.append(image_temp_dir)
                
                cover_image_path = convert_image_for_apple_tv(cover_image, image_temp_dir)
                print(f"Found cover image: {cover_image.name}")
            except Exception as e:
                print(f"Warning: Could not process cover image: {e}")
                cover_image_path = None
        
        # Convert bitmap subtitles if requested
        if convert_bitmap_subs:
            try:
                subtitle_streams_info = probe_subtitle_streams(input_path)
                bitmap_streams = [s for s in subtitle_streams_info if s.is_image_based]
                
                if bitmap_streams:
                    print(f"Found {len(bitmap_streams)} bitmap subtitle track(s), converting to text...")
                    generated_subtitles, temp_dir = convert_bitmap_subtitles(
                        input_path, bitmap_streams
                    )
                    if temp_dir:
                        temp_dirs.append(temp_dir)
                    if generated_subtitles:
                        print(f"Converted {len(generated_subtitles)} bitmap subtitle(s) to text")
            except Exception as e:
                print(f"Warning: Could not convert bitmap subtitles: {e}")
        
        if rewrap:
            cmd = build_rewrap_command(
                input_path, output_path, text_subtitle_streams, probe_data,
                generated_subtitles, episode_metadata, cover_image_path
            )
            print("Mode: Rewrap (stream copy)")
        else:
            duration = get_video_duration(probe_data)
            _, video_bitrate_kbps = calculate_target_bitrate(
                duration, target_size_mb_per_hour
            )
            encoder = detect_gpu_encoder()
            encoder_name = {
                "hevc_nvenc": "NVIDIA NVENC",
                "hevc_amf": "AMD AMF",
                "hevc_qsv": "Intel Quick Sync",
                "hevc_videotoolbox": "Apple VideoToolbox",
                "libx265": "CPU (libx265)",
            }.get(encoder, encoder)
            cmd = build_transcode_command(
                input_path, output_path, video_bitrate_kbps, text_subtitle_streams,
                encoder, generated_subtitles, episode_metadata, cover_image_path
            )
            print(f"Mode: Transcode (target: {target_size_mb_per_hour}MB/hour)")
            print(f"Encoder: {encoder_name}")
            print(f"Video bitrate: {int(video_bitrate_kbps)}k")
        
        total_subtitles = len(text_subtitle_streams) + len(generated_subtitles)
        if total_subtitles > 0:
            print(f"Found {len(text_subtitle_streams)} text subtitle track(s) + {len(generated_subtitles)} converted bitmap subtitle(s)")
        else:
            print("No text subtitles found")
        
        print(f"Output: {output_path.name}")
        
        # Get duration for percentage calculation (works for both transcode and rewrap)
        duration = get_video_duration(probe_data)
        
        returncode, error_output = run_ffmpeg_with_progress(cmd, duration)
        
        if returncode == 0:
            print(f"[OK] Successfully processed {input_path.name}\n")
            return True
        else:
            print(f"[ERROR] Error processing {input_path.name}:")
            print(error_output)
            return False
    
    except Exception as e:
        print(f"[ERROR] Error processing {input_path.name}: {e}\n")
        return False
    finally:
        # Clean up temporary directories
        for temp_dir in temp_dirs:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)


def transcode_all(
    source_path: Path,
    rewrap: bool = False,
    target_size_mb_per_hour: float = 900.0,
    filename_pattern: str = DEFAULT_FILENAME_PATTERN,
    convert_bitmap_subs: bool = True,
    target_dir: Optional[Path] = None,
) -> None:
    """
    Transcode MKV files from source path (file or directory).
    
    Args:
        source_path: Path to input .mkv file or directory containing .mkv files
        rewrap: If True, copy streams without transcoding
        target_size_mb_per_hour: Target file size in MB per hour
        filename_pattern: Pattern for parsing metadata from filename
        convert_bitmap_subs: If True, convert bitmap subtitles to text using OCR
        target_dir: Optional target directory for output. If None, output is in same directory as input.
    """
    # Check if source is a file or directory
    if source_path.is_file():
        # Process single file
        if source_path.suffix.lower() != ".mkv":
            print(f"Error: {source_path.name} is not an MKV file")
            return
        mkv_files = [source_path]
        print(f"Processing single file: {source_path.name}\n")
    elif source_path.is_dir():
        # Process all MKV files in directory
        mkv_files = find_mkv_files(source_path)
        if not mkv_files:
            print(f"No .mkv files found in {source_path}")
            return
        print(f"Found {len(mkv_files)} .mkv file(s) in {source_path}\n")
    else:
        print(f"Error: {source_path} does not exist or is not a valid file or directory")
        return
    
    success_count = 0
    for mkv_file in mkv_files:
        if transcode_file(mkv_file, rewrap, target_size_mb_per_hour, filename_pattern, convert_bitmap_subs, target_dir):
            success_count += 1
    
    print(f"\nCompleted: {success_count}/{len(mkv_files)} files processed successfully")


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert MKV files to Apple TV compatible MP4 files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Transcode all MKV files in current directory (default: 900MB/hour target size)
  transcode

  # Process a specific file
  transcode --source "video.mkv"

  # Process all MKV files in a specific directory
  transcode --source "C:\\Videos\\TV Shows"

  # Output to a specific directory
  transcode --targetDir "C:\\Output"

  # Process specific file and output to specific directory
  transcode --source "video.mkv" --targetDir "C:\\Output"

  # Rewrap/copy streams without transcoding (faster, preserves original quality)
  transcode --rewrap

  # Set custom target file size (e.g., 500MB per hour for smaller files)
  transcode --targetSizePerHour 500

  # Use custom filename pattern for metadata extraction
  transcode --filename-pattern "<Series Name> - S<season:1-2 digits>E<episode:1-2 digits> - <Episode Name>.mkv"

  # Skip bitmap subtitle conversion (faster, but no OCR subtitles)
  transcode --no-bitmap-subs

  # Combine options: rewrap with custom target size and output directory
  transcode --rewrap --targetSizePerHour 1200 --targetDir "C:\\Output"

Features:
  - Automatic GPU acceleration (NVIDIA > AMD > Intel > CPU fallback)
  - Converts bitmap subtitles (PGS) to text subtitles using OCR
  - Preserves text-based subtitles from source
  - Extracts episode metadata from filename (series name, episode title, season/episode numbers, year)
  - Apple TV compatible MP4 output with proper metadata tags
  - Real-time progress display during encoding

Default behavior:
  - Transcodes video to H.265 (HEVC) with target size of 900MB/hour
  - Converts all bitmap subtitle tracks to text using OCR
  - Preserves all text-based subtitle tracks
  - Outputs .mp4 files in the same directory as input files
        """
    )
    parser.add_argument(
        "--rewrap",
        action="store_true",
        help="Rewrap/copy streams without transcoding. Much faster but preserves "
             "original file size. Use when source video is already HEVC/H.265.",
    )
    parser.add_argument(
        "--targetSizePerHour",
        type=float,
        default=900.0,
        metavar="MB",
        help="Target file size in MB per hour of video. Lower values = smaller files "
             "but lower quality. Higher values = larger files but better quality. "
             "Default: 900 MB/hour",
    )
    parser.add_argument(
        "--filename-pattern",
        type=str,
        default=DEFAULT_FILENAME_PATTERN,
        metavar="PATTERN",
        help=f"Pattern for parsing episode metadata from filename. Use tokens like "
             f"<Series Name>, <Episode Name>, <season:2 digits>, <episode:2 digits>, "
             f"<Year>. Default: {DEFAULT_FILENAME_PATTERN}",
    )
    parser.add_argument(
        "--no-bitmap-subs",
        action="store_true",
        help="Skip conversion of bitmap subtitles (PGS/SUP) to text. Bitmap subtitles "
             "will be ignored. Use this to speed up processing if you don't need OCR subtitles.",
    )
    parser.add_argument(
        "--source",
        type=str,
        metavar="PATH",
        help="Input file or directory to process. If a file is specified, only that file "
             "will be processed. If a directory is specified, all .mkv files in that directory "
             "will be processed. If not specified, processes all .mkv files in the current directory.",
    )
    parser.add_argument(
        "--targetDir",
        type=str,
        metavar="PATH",
        help="Output directory for transcoded files. If not specified, output files are "
             "created in the same directory as input files.",
    )
    
    return parser.parse_args()


def main() -> None:
    """Main entry point for transcoding."""
    if not check_ffmpeg_available():
        print("Error: ffmpeg or ffprobe not found. Please install ffmpeg.")
        sys.exit(1)
    
    args = parse_arguments()
    
    # Determine source path
    if args.source:
        source_path = Path(args.source).resolve()
        if not source_path.exists():
            print(f"Error: Source path does not exist: {source_path}")
            sys.exit(1)
    else:
        # Default to current directory
        source_path = Path.cwd()
    
    # Determine target directory
    target_dir = None
    if args.targetDir:
        target_dir = Path(args.targetDir).resolve()
        # Create target directory if it doesn't exist
        target_dir.mkdir(parents=True, exist_ok=True)
    
    transcode_all(
        source_path,
        rewrap=args.rewrap,
        target_size_mb_per_hour=args.targetSizePerHour,
        filename_pattern=args.filename_pattern,
        convert_bitmap_subs=not args.no_bitmap_subs,
        target_dir=target_dir,
    )

