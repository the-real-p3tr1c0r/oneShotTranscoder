"""Bitmap subtitle conversion to text using OCR.

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

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import easyocr
from pgsrip.sup import Sup as SupSubtitle

from transcoder.constants import (
    DEFAULT_EASYOCR_LANGUAGE,
    IMAGE_BASED_SUBTITLE_CODECS,
)
from transcoder.exceptions import SubtitleError
from transcoder.language import (
    easyocr_to_iso6392,
    normalize_language_for_easyocr,
    normalize_language_tag,
)


@dataclass
class SubtitleStreamInfo:
    """Information about a subtitle stream."""
    absolute_index: int
    type_index: int
    codec_name: str
    language: str | None
    title: str | None

    @property
    def is_image_based(self) -> bool:
        """Check if subtitle is image-based."""
        return self.codec_name.lower() in IMAGE_BASED_SUBTITLE_CODECS


@dataclass
class GeneratedSubtitle:
    """Generated text subtitle from OCR."""
    path: Path
    language: str | None
    title: str | None




# Language normalization functions are now imported from transcoder.language


def probe_subtitle_streams(media: Path) -> list[SubtitleStreamInfo]:
    """
    Probe subtitle streams from media file.
    
    Args:
        media: Path to media file
    
    Returns:
        List of SubtitleStreamInfo objects
    """
    import json
    
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "s",
        "-show_entries",
        "stream=index,codec_name,codec_type:stream_tags=language,title",
        "-of",
        "json",
        str(media),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout or "{}")
    streams = []
    type_counter = -1
    for stream in payload.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        type_counter += 1
        tags = stream.get("tags") or {}
        streams.append(
            SubtitleStreamInfo(
                absolute_index=int(stream["index"]),
                type_index=type_counter,
                codec_name=stream.get("codec_name", "").lower(),
                language=normalize_language_tag(tags.get("language")),
                title=tags.get("title"),
            )
        )
    return streams


def extract_subtitle_sup(
    media: Path,
    stream: SubtitleStreamInfo,
    temp_dir: Path,
) -> Path:
    """
    Extract SUP file from media for bitmap subtitle stream.
    
    Args:
        media: Path to media file
        stream: SubtitleStreamInfo for the stream to extract
        temp_dir: Temporary directory for output
    
    Returns:
        Path to extracted SUP file
    
    Raises:
        SubtitleError: If codec is not supported
    """
    if stream.codec_name != "hdmv_pgs_subtitle":
        raise SubtitleError(
            f"Unsupported image subtitle codec '{stream.codec_name}' for OCR."
        )

    language_code = (stream.language or "und").lower()
    filename = f"{media.stem}.track{stream.type_index}.{language_code}.sup"
    sup_path = temp_dir / filename
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(media),
            "-map",
            f"0:s:{stream.type_index}",
            "-c",
            "copy",
            str(sup_path),
        ],
        check=True,
    )
    return sup_path


def extract_sup_frames(sup_path: Path, output_dir: Path) -> list[tuple[Path, float, float]]:
    """
    Extract frames from SUP file using pgsrip.
    
    Args:
        sup_path: Path to SUP file
        output_dir: Directory to save extracted frames
    
    Returns:
        List of tuples (frame_path, start_timestamp_seconds, end_timestamp_seconds)
    """
    from pgsrip.api import Pgs
    from pgsrip.options import Options
    
    # Read SUP file data
    with open(sup_path, 'rb') as f:
        sup_data = f.read()
    
    # Create options for pgsrip
    options = Options()
    
    # Create Pgs object to parse the SUP file
    pgs = Pgs(
        media_path=str(sup_path),
        options=options,
        data_reader=lambda: sup_data,
        temp_folder=str(output_dir)
    )
    
    # Use Pgs as context manager to decode the SUP file
    # This populates the items list with PgsSubtitleItem objects
    import cv2
    import numpy as np
    
    # Collect image data and timing inside context manager
    items_data = []
    with pgs as pg:
        # Check if items exist
        if not pg.items:
            raise SubtitleError(f"No PGS items found in SUP file {sup_path.name}")
        
        # Collect image data and timing info (don't save files yet)
        for idx, item in enumerate(pg.items):
            if item.image:
                # Get image data
                img_data = item.image.data
                
                # Skip empty images
                if img_data.size == 0:
                    continue
                
                # Get timestamps
                start_timestamp = 0.0
                end_timestamp = 3.0
                
                if item.start:
                    if hasattr(item.start, 'ordinal'):
                        start_timestamp = item.start.ordinal / 1000.0
                    elif isinstance(item.start, (int, float)):
                        start_timestamp = item.start / 90000.0
                
                if item.end:
                    if hasattr(item.end, 'ordinal'):
                        end_timestamp = item.end.ordinal / 1000.0
                    elif isinstance(item.end, (int, float)):
                        end_timestamp = item.end / 90000.0
                    else:
                        end_timestamp = start_timestamp + 3.0
                else:
                    end_timestamp = start_timestamp + 3.0
                
                items_data.append((idx, img_data, start_timestamp, end_timestamp))
    
    # Now save files outside the context manager
    # Ensure directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    frames_with_timing = []
    for idx, img_data, start_timestamp, end_timestamp in items_data:
        # Save image to file
        frame_path = output_dir / f"frame_{idx:04d}.png"
        
        # Convert grayscale to BGR if needed for OpenCV
        if len(img_data.shape) == 2:
            # Grayscale image - convert to BGR
            img_bgr = cv2.cvtColor(img_data, cv2.COLOR_GRAY2BGR)
        elif len(img_data.shape) == 3 and img_data.shape[2] == 4:
            # RGBA image - convert to BGR
            img_bgr = cv2.cvtColor(img_data, cv2.COLOR_RGBA2BGR)
        elif len(img_data.shape) == 3 and img_data.shape[2] == 3:
            # Already BGR or RGB - use as-is
            img_bgr = img_data
        else:
            # Unknown format - try to save as-is
            img_bgr = img_data
        
        # Ensure data type is uint8
        if img_bgr.dtype != np.uint8:
            img_bgr = img_bgr.astype(np.uint8)
        
        # Save using OpenCV - use absolute path
        abs_frame_path = frame_path.absolute()
        success = cv2.imwrite(str(abs_frame_path), img_bgr)
        if not success:
            raise SubtitleError(f"cv2.imwrite failed for {abs_frame_path}")
        
        # Verify file was created
        if not abs_frame_path.exists():
            raise SubtitleError(f"Image file was not created: {abs_frame_path}")
        
        frames_with_timing.append((abs_frame_path, start_timestamp, end_timestamp))
    
    if not frames_with_timing:
        raise SubtitleError("No frames extracted from SUP file")
    
    return frames_with_timing


def convert_sup_to_srt_easyocr(
    sup_path: Path, language_code: str | None = None
) -> Path:
    """
    Convert SUP file to SRT using EasyOCR.
    
    Args:
        sup_path: Path to SUP file
        language_code: ISO 639-1 language code for EasyOCR (e.g., 'en', 'fr')
    
    Returns:
        Path to generated SRT file
    
    Raises:
        RuntimeError: If OCR fails
    """
    import cv2
    
    temp_dir = sup_path.parent / f"{sup_path.stem}_frames"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Extract frames from SUP with timing
        frames_with_timing = extract_sup_frames(sup_path, temp_dir)
        if not frames_with_timing:
            raise SubtitleError(f"No frames extracted from {sup_path.name}")
        
        # Verify frames were actually created
        for frame_path, _, _ in frames_with_timing:
            if not frame_path.exists():
                raise SubtitleError(f"Frame file not created: {frame_path}")
        
        # Initialize EasyOCR reader
        # language_code is already in ISO 639-1 format from normalize_language_for_easyocr
        easyocr_lang = language_code or DEFAULT_EASYOCR_LANGUAGE
        reader = easyocr.Reader([easyocr_lang], gpu=True, verbose=False)
        
        # Process frames and collect text with timing
        subtitle_entries = []
        
        def seconds_to_srt_time(secs: float) -> str:
            hours = int(secs // 3600)
            minutes = int((secs % 3600) // 60)
            seconds = int(secs % 60)
            milliseconds = int((secs % 1) * 1000)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
        
        for frame_path, start_time, end_time in frames_with_timing:
            # Read image - use absolute path to avoid path issues
            img = cv2.imread(str(frame_path.absolute()))
            if img is None:
                # Try reading directly from the numpy array if file read fails
                # This shouldn't happen, but as a fallback
                continue
            
            # OCR the image
            results = reader.readtext(img)
            
            if results:
                # Combine all detected text from this frame
                text_lines = [result[1] for result in results if result[2] > 0.5]  # Confidence threshold
                if text_lines:
                    text = " ".join(text_lines)
                    
                    subtitle_entries.append({
                        "start": start_time,
                        "end": end_time,
                        "text": text,
                        "start_str": seconds_to_srt_time(start_time),
                        "end_str": seconds_to_srt_time(end_time),
                    })
        
        # Generate SRT file
        srt_path = sup_path.with_suffix(".srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            for idx, entry in enumerate(subtitle_entries, 1):
                f.write(f"{idx}\n")
                f.write(f"{entry['start_str']} --> {entry['end_str']}\n")
                f.write(f"{entry['text']}\n\n")
        
        if not subtitle_entries:
            raise SubtitleError(f"No text detected in {sup_path.name}")
        
        return srt_path
    
    finally:
        # Clean up frames
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def convert_bitmap_subtitles(
    media: Path,
    streams: list[SubtitleStreamInfo],
) -> tuple[list[GeneratedSubtitle], Path | None]:
    """
    Convert bitmap subtitle streams to text subtitles using EasyOCR.
    
    Args:
        media: Path to media file
        streams: List of bitmap subtitle streams to convert
    
    Returns:
        Tuple of (list of GeneratedSubtitle, temp directory path)
    """
    if not streams:
        return [], None

    temp_dir = Path(tempfile.mkdtemp(prefix=f"{media.stem}_subs_"))
    generated: list[GeneratedSubtitle] = []
    import sys
    import os
    
    # Enable ANSI escape sequences on Windows
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)  # Enable ANSI
        except Exception:
            pass  # If it fails, continue anyway
    
    # Print all "Converting..." messages upfront, before any processing
    # This ensures they appear immediately without delays
    total_streams = len(streams)
    for idx, stream in enumerate(streams):
        lang_display = stream.language or "unknown"
        sys.stdout.write(f"Converting bitmap subtitle track {idx} ({lang_display}) to text using OCR...\n")
        sys.stdout.flush()
    
    # Helper function to update a specific line
    def update_line(line_index: int, message: str):
        """Update a specific line (0-indexed from the first Converting message)."""
        # Calculate how many lines up we need to go
        # After printing all messages, we're at the start of a new line (total_streams lines down)
        # To update line_index, we need to go up (total_streams - line_index) lines
        lines_up = total_streams - line_index
        if lines_up > 0:
            sys.stdout.write(f"\033[{lines_up}A")  # Move up
        sys.stdout.write(f"\r{message}")
        # Clear to end of line and add newline
        sys.stdout.write("\033[K\n")  # Clear to end of line, then newline
        if lines_up > 0:
            sys.stdout.write(f"\033[{lines_up}B")  # Move back down
        sys.stdout.flush()
    
    # Now process each stream and update the corresponding line with success/failed
    try:
        for idx, stream in enumerate(streams):
            lang_display = stream.language or "unknown"
            
            # Convert language to EasyOCR format (ISO 639-1)
            easyocr_lang = normalize_language_for_easyocr(stream.language)
            
            if not easyocr_lang:
                update_line(idx, f"Converting bitmap subtitle track {idx} ({lang_display}) to text using OCR... skipped (unable to determine language)")
                continue
            
            # Ensure we have ISO 639-2 code for metadata (normalize if needed)
            # stream.language is already normalized by probe_subtitle_streams, but double-check
            metadata_lang = normalize_language_tag(stream.language)
            if not metadata_lang:
                # Fallback: try to convert EasyOCR lang back to ISO 639-2
                metadata_lang = easyocr_to_iso6392(easyocr_lang)
            if not metadata_lang:
                # Last resort: use original code (might not be ISO 639-2)
                metadata_lang = stream.language
            
            try:
                sup_path = extract_subtitle_sup(media, stream, temp_dir)
                srt_path = convert_sup_to_srt_easyocr(sup_path, easyocr_lang)
                
                if sup_path.exists():
                    sup_path.unlink(missing_ok=True)
                
                generated.append(
                    GeneratedSubtitle(
                        path=srt_path,
                        language=metadata_lang,  # ISO 639-2 for metadata
                        title=stream.title or f"{(metadata_lang or 'und').upper()} OCR",
                    )
                )
                # Update the line with success
                update_line(idx, f"Converting bitmap subtitle track {idx} ({lang_display}) to text using OCR...success")
            except Exception as e:
                # Update the line with failure
                update_line(idx, f"Converting bitmap subtitle track {idx} ({lang_display}) to text using OCR...failed: {e}")
                continue
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return generated, temp_dir

