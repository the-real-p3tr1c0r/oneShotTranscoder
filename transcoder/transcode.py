"""Main transcoding logic for MKV to MP4 conversion.

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

import shutil
from pathlib import Path

from transcoder.constants import DEFAULT_TARGET_SIZE_MB_PER_HOUR
from transcoder.ffmpeg import (
    build_rewrap_command,
    build_transcode_command,
    run_ffmpeg_with_progress,
)
from transcoder.metadata import (
    DEFAULT_FILENAME_PATTERN,
    EpisodeMetadata,
    build_pattern_regex,
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
    convert_image_for_apple_tv,
    detect_gpu_encoder,
    expand_path_pattern,
    find_cover_image,
    find_mkv_files,
    get_output_path,
    get_text_subtitle_streams,
    get_total_frames,
    get_video_duration,
    get_video_fps,
    probe_video_file,
)




def transcode_file(
    input_path: Path,
    rewrap: bool = False,
    target_size_mb_per_hour: float = DEFAULT_TARGET_SIZE_MB_PER_HOUR,
    filename_pattern: str = DEFAULT_FILENAME_PATTERN,
    convert_bitmap_subs: bool = True,
    target_dir: Path | None = None,
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
            if cover_image_path:
                print(f"Embedding cover image: {cover_image_path.name}")
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
            if cover_image_path:
                print(f"Embedding cover image: {cover_image_path.name}")
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
        
        # Get input file size for rewrap percentage calculation
        input_size_bytes = None
        if rewrap and input_path.exists():
            try:
                input_size_bytes = input_path.stat().st_size
            except (OSError, AttributeError):
                pass
        
        # Get total frames and source FPS for transcode percentage calculation and time display
        total_frames = None
        source_fps = None
        if not rewrap:
            try:
                total_frames = get_total_frames(probe_data)
                source_fps = get_video_fps(probe_data)
            except (ValueError, KeyError):
                pass
        
        returncode, error_output = run_ffmpeg_with_progress(cmd, duration, output_path, input_size_bytes, total_frames, source_fps)
        
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
    target_size_mb_per_hour: float = DEFAULT_TARGET_SIZE_MB_PER_HOUR,
    filename_pattern: str = DEFAULT_FILENAME_PATTERN,
    convert_bitmap_subs: bool = True,
    target_dir: Path | None = None,
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



