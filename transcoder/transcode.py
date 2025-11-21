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

from transcoder.constants import DEFAULT_TARGET_SIZE_MB_PER_HOUR, SUPPORTED_VIDEO_FORMATS
from transcoder.ffmpeg import (
    build_rewrap_command,
    build_transcode_command,
    run_ffmpeg_with_progress,
)
from transcoder.metadata import (
    DEFAULT_FILENAME_PATTERN,
    EpisodeMetadata,
    MediaType,
    MovieMetadata,
    detect_media_metadata,
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
    find_video_files,
    get_output_path,
    get_text_subtitle_streams,
    get_total_frames,
    get_video_duration,
    get_video_fps,
    probe_video_file,
)




def _format_fallback_title(raw_title: str) -> str:
    cleaned = raw_title.replace("_", " ").replace(".", " ").strip()
    return cleaned or raw_title


def transcode_file(
    input_path: Path,
    rewrap: bool = False,
    target_size_mb_per_hour: float = DEFAULT_TARGET_SIZE_MB_PER_HOUR,
    filename_pattern: str | None = DEFAULT_FILENAME_PATTERN,
    convert_bitmap_subs: bool = True,
    target_dir: Path | None = None,
    media_type_override: str | None = None,
    overwrite: bool = False,
) -> bool:
    """
    Transcode a single video file to MP4.
    
    Args:
        input_path: Path to input video file
        rewrap: If True, copy streams without transcoding
        target_size_mb_per_hour: Target file size in MB per hour
        filename_pattern: Optional manual pattern for parsing metadata from filename
        convert_bitmap_subs: If True, convert bitmap subtitles to text using OCR
        target_dir: Optional target directory for output. If None, output is in same directory as input.
        media_type_override: Optional type override ("show" or "movie") to force type detection
        overwrite: If True, overwrite existing output files. If False, add incremental suffix to avoid overwriting.
    
    Returns:
        True if successful, False otherwise
    """
    output_path = get_output_path(input_path, target_dir, overwrite)
    
    print(f"Processing: {input_path.name}")
    
    temp_dirs = []
    generated_subtitles = []
    media_metadata: EpisodeMetadata | MovieMetadata | None = None
    cover_image_path = None
    
    try:
        manual_pattern = filename_pattern or None
        detection = detect_media_metadata(input_path, manual_pattern, media_type_override)
        if detection:
            media_metadata = detection.metadata
            if detection.media_type == MediaType.TV_SHOW and isinstance(media_metadata, EpisodeMetadata):
                episode_label = media_metadata.episode_id or "S??E??"
                print(
                    f"Detected TV Show ({detection.pattern_name}): "
                    f"{media_metadata.series_name} - {episode_label} - {media_metadata.episode_title}"
                )
            elif detection.media_type == MediaType.MOVIE and isinstance(media_metadata, MovieMetadata):
                year_suffix = f" ({media_metadata.year})" if media_metadata.year else ""
                print(f"Detected Movie ({detection.pattern_name}): {media_metadata.movie_title}{year_suffix}")
        if media_metadata is None:
            print("No typematch for metadata extraction, file name used")
            fallback_title = _format_fallback_title(input_path.stem)
            media_metadata = MovieMetadata(movie_title=fallback_title, year=None)
            print(f"Detected Movie (fallback): {media_metadata.movie_title}")
        
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
                generated_subtitles, media_metadata, cover_image_path
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
                encoder, generated_subtitles, media_metadata, cover_image_path
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
    filename_pattern: str | None = DEFAULT_FILENAME_PATTERN,
    convert_bitmap_subs: bool = True,
    target_dir: Path | None = None,
    media_type_override: str | None = None,
    overwrite: bool = False,
) -> None:
    """
    Transcode video files from source path (file or directory).
    
    Args:
        source_path: Path to input video file or directory containing video files
        rewrap: If True, copy streams without transcoding
        target_size_mb_per_hour: Target file size in MB per hour
        filename_pattern: Optional manual pattern for parsing metadata from filename
        convert_bitmap_subs: If True, convert bitmap subtitles to text using OCR
        target_dir: Optional target directory for output. If None, output is in same directory as input.
        media_type_override: Optional type override ("show" or "movie") to force type detection
        overwrite: If True, overwrite existing output files. If False, add incremental suffix to avoid overwriting.
    """
    # Check if source is a file or directory
    if source_path.is_file():
        # Process single file
        if source_path.suffix.lower() not in SUPPORTED_VIDEO_FORMATS:
            supported_exts = ", ".join(sorted(SUPPORTED_VIDEO_FORMATS))
            print(f"Error: {source_path.name} is not a supported video format. Supported formats: {supported_exts}")
            return
        video_files = [source_path]
        print(f"Processing single file: {source_path.name}\n")
    elif source_path.is_dir():
        # Process all video files in directory
        video_files = find_video_files(source_path)
        if not video_files:
            print(f"No supported video files found in {source_path}")
            return
        print(f"Found {len(video_files)} video file(s) in {source_path}\n")
    else:
        print(f"Error: {source_path} does not exist or is not a valid file or directory")
        return
    
    success_count = 0
    for video_file in video_files:
        if transcode_file(video_file, rewrap, target_size_mb_per_hour, filename_pattern, convert_bitmap_subs, target_dir, media_type_override, overwrite):
            success_count += 1
    
    print(f"\nCompleted: {success_count}/{len(video_files)} files processed successfully")



