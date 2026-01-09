"""Main module for transcoder project.

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

import argparse
import os
import shlex
import sys
import traceback
from pathlib import Path

from transcoder import license as license_info
from transcoder.constants import DEFAULT_EASYOCR_LANGUAGE, DEFAULT_TARGET_SIZE_MB_PER_HOUR
from transcoder.exceptions import TranscoderError
from transcoder.metadata import DEFAULT_FILENAME_PATTERN
from transcoder.transcode import dry_run_all, dry_run_analyze, transcode_all, transcode_file
from transcoder.utils import check_ffmpeg_available, expand_path_pattern


def configure_console_output() -> None:
    """Configure stdout/stderr for better streaming output in packaged builds."""
    try:
        if not bool(getattr(sys, "frozen", False)):
            return
    except Exception:
        return

    # In frozen Windows executables, stdout/stderr can be heavily buffered even when
    # invoked from an interactive terminal. Force line-buffering/write-through when possible.
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            # Python 3.7+: TextIOWrapper supports reconfigure()
            stream.reconfigure(line_buffering=True, write_through=True)
        except Exception:
            # Best-effort only; do not fail startup if not supported.
            pass


def run_diagnostics() -> None:
    """Print environment diagnostics (useful for debugging packaged builds)."""
    print("=== oneShotTranscoder diagnostics ===")
    print(f"sys.platform: {sys.platform}")
    print(f"python_version: {sys.version.replace(os.linesep, ' ')}")
    print(f"sys.executable: {sys.executable}")

    frozen = bool(getattr(sys, "frozen", False))
    print(f"frozen: {frozen}")
    if frozen:
        print(f"sys._MEIPASS: {getattr(sys, '_MEIPASS', None)}")

    print(f"cwd: {Path.cwd()}")
    print(f"argv: {sys.argv}")

    path_env = os.environ.get("PATH", "")
    path_entries = [p for p in path_env.split(os.pathsep) if p]
    print(f"PATH_entries: {len(path_entries)}")
    for idx, entry in enumerate(path_entries[:20], start=1):
        print(f"  PATH[{idx:02d}]: {entry}")
    if len(path_entries) > 20:
        print("  ... (truncated)")

    print("\n--- torch ---")
    try:
        import torch  # type: ignore

        print(f"torch.__version__: {getattr(torch, '__version__', None)}")
        print(f"torch.version.cuda: {getattr(getattr(torch, 'version', None), 'cuda', None)}")
        cuda_available = bool(getattr(torch, "cuda", None) and torch.cuda.is_available())
        print(f"torch.cuda.is_available: {cuda_available}")
        if cuda_available:
            try:
                print(f"torch.cuda.device_count: {torch.cuda.device_count()}")
                print(f"torch.cuda.current_device: {torch.cuda.current_device()}")
                print(f"torch.cuda.get_device_name: {torch.cuda.get_device_name(torch.cuda.current_device())}")
            except Exception as e:
                print(f"torch.cuda.details_error: {e}")
        try:
            cudnn_version = None
            if getattr(torch, "backends", None) and getattr(torch.backends, "cudnn", None):
                cudnn_version = torch.backends.cudnn.version()
            print(f"torch.backends.cudnn.version: {cudnn_version}")
        except Exception as e:
            print(f"torch.backends.cudnn.version_error: {e}")
    except Exception as e:
        print(f"torch_import_error: {e}")

    print("\n--- easyocr ---")
    try:
        import easyocr  # type: ignore

        print(f"easyocr.__version__: {getattr(easyocr, '__version__', None)}")
        # Avoid downloading models; just instantiate a Reader with minimal verbosity.
        # This may still fail in broken CUDA/DLL environments, which is exactly what we want to surface.
        try:
            import torch  # type: ignore

            use_gpu = bool(getattr(torch, "cuda", None) and torch.cuda.is_available())
        except Exception:
            use_gpu = False

        try:
            reader = easyocr.Reader([DEFAULT_EASYOCR_LANGUAGE], gpu=use_gpu, verbose=False)
            # Access a trivial attribute to ensure initialization completed.
            _ = getattr(reader, "lang_list", None)
            print(f"easyocr.Reader.init_ok: True (gpu={use_gpu})")
            # Try a minimal OCR call to catch runtime-only failures that occur after init.
            try:
                import numpy as np  # type: ignore

                test_img = np.zeros((32, 256, 3), dtype=np.uint8)
                _ = reader.readtext(test_img)
                print("easyocr.Reader.readtext_smoke_ok: True")
            except Exception as e:
                print("easyocr.Reader.readtext_smoke_ok: False")
                print(f"easyocr.Reader.readtext_smoke_error: {e}")
        except Exception as e:
            print(f"easyocr.Reader.init_ok: False (gpu={use_gpu})")
            print(f"easyocr.Reader.init_error: {e}")
    except Exception as e:
        print(f"easyocr_import_error: {e}")

    print("=== end diagnostics ===")


def _parse_arguments_powershell() -> list[str]:
    """Fallback argument parsing for PowerShell-specific issues."""
    fixed_argv = [sys.argv[0]]
    i = 1

    while i < len(sys.argv):
        arg = sys.argv[i]

        if arg.startswith("--") and i + 1 < len(sys.argv):
            value = sys.argv[i + 1]

            split_result = _split_embedded_tail(value)

            if split_result:
                prefix, extra_tokens = split_result
                cleaned = _clean_token(prefix)
                fixed_argv.append(arg)
                if cleaned:
                    fixed_argv.append(cleaned)
                fixed_argv.extend(extra_tokens)
                i += 2
                continue

            cleaned_value = _clean_token(value)
            fixed_argv.append(arg)
            fixed_argv.append(cleaned_value or value)
            i += 2
            continue

        split_result = _split_embedded_tail(arg)
        if split_result:
            prefix, extra_tokens = split_result
            cleaned = _clean_token(prefix)
            if cleaned:
                fixed_argv.append(cleaned)
            fixed_argv.extend(extra_tokens)
            i += 1
            continue

        cleaned_arg = _clean_token(arg)
        fixed_argv.append(cleaned_arg or arg)
        i += 1

    return fixed_argv


def _clean_token(value: str) -> str:
    cleaned = value.strip()
    while len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ("'", '"'):
        cleaned = cleaned[1:-1]
    cleaned = cleaned.strip('"').strip("'")
    return cleaned


def _tokenize_tail(tail: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    quote: str | None = None

    for char in tail:
        if quote:
            if char == quote:
                quote = None
            else:
                current.append(char)
        else:
            if char in ("'", '"'):
                quote = char
            elif char.isspace():
                if current:
                    tokens.append("".join(current))
                    current = []
            else:
                current.append(char)

    if current:
        tokens.append("".join(current))

    return tokens


def _split_embedded_tail(token: str) -> tuple[str, list[str]] | None:
    idx = token.find(" --")
    if idx == -1:
        return None

    tail = token[idx + 1 :].lstrip()
    if not tail.startswith("--"):
        return None

    prefix = token[:idx]
    extra_tokens = _tokenize_tail(tail)
    return prefix, extra_tokens


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments, with special handling for PowerShell quoting issues."""
    original_argv = sys.argv
    
    # On Unix-like systems, sys.argv is usually already properly parsed
    # On Windows/PowerShell, we may need custom handling for quote issues
    # Try using shlex to clean up any malformed arguments first
    if sys.platform != 'win32':
        # On Unix-like systems, arguments are usually fine, but clean up if needed
        # Most of the time, sys.argv is already correct, so we can use it directly
        pass
    else:
        # On Windows, check if we need custom PowerShell handling
        # Look for signs of PowerShell quote issues (embedded -- in values)
        needs_custom_parsing = any(
            ' --' in arg for arg in sys.argv[1:] if not arg.startswith('--')
        )
        if needs_custom_parsing:
            fixed_argv = _parse_arguments_powershell()
            sys.argv = fixed_argv
    parser = argparse.ArgumentParser(
        description="Convert video files to Apple TV compatible MP4 files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Transcode all video files in current directory (default: 900MB/hour target size)
  transcode

  # Process a specific file
  transcode "video.mkv"
  transcode "video.mp4"
  transcode "video.avi"

  # Process all video files in a specific directory
  transcode "C:\\Videos\\TV Shows"

  # Output to a specific directory
  transcode --targetDir "C:\\Output"

  # Process specific file and output to specific directory
  transcode "video.mkv" --targetDir "C:\\Output"

  # Rewrap/copy streams without transcoding (faster, preserves original quality)
  transcode --rewrap

  # Set custom target file size (e.g., 500MB per hour for smaller files)
  transcode --targetSizePerHour 500

  # Use custom filename pattern for metadata extraction
  transcode --fileNamePattern "<Series Name> - S<season:1-2 digits>E<episode:1-2 digits> - <Episode Name>.mkv"

  # Skip bitmap subtitle conversion (faster, but no OCR subtitles)
  transcode --noBitmapSubs

  # Combine options: rewrap with custom target size and output directory
  transcode --rewrap --targetSizePerHour 1200 --targetDir "C:\\Output"

Supported Input Formats:
  MKV, MP4, M4V, M4A, AVI, MOV, QT, WebM, FLV, TS, MTS, M2TS, OGV, OGG,
  3GP, 3G2, ASF, WMV, VOB, MPG, MPEG, DivX, Xvid

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
        "--about",
        action="store_true",
        help="Print version, license, and attribution details then exit.",
    )
    parser.add_argument(
        "--rewrap",
        dest="rewrap",
        action="store_const",
        const=True,
        default=None,
        help="Rewrap/copy streams without transcoding. Much faster but preserves "
             "original file size. Use when source video is already HEVC/H.265. "
             "If not specified, the tool will automatically select the best mode.",
    )
    parser.add_argument(
        "--transcode",
        dest="transcode",
        action="store_true",
        help="Force transcode even if the file is Apple TV compatible. "
             "Use with --targetSizePerHour to control output size (default 900 MB/hour).",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Print environment diagnostics (torch/easyocr/CUDA details) and exit.",
    )
    parser.add_argument(
        "--targetSizePerHour",
        type=float,
        default=DEFAULT_TARGET_SIZE_MB_PER_HOUR,
        metavar="MB",
        help="Target file size in MB per hour of video. Lower values = smaller files "
             "but lower quality. Higher values = larger files but better quality. "
             f"Default: {DEFAULT_TARGET_SIZE_MB_PER_HOUR} MB/hour",
    )
    parser.add_argument(
        "--fileNamePattern",
        type=str,
        default=DEFAULT_FILENAME_PATTERN,
        metavar="PATTERN",
        help=(
            "Manual filename pattern for metadata extraction. Supports tokens like "
            "<Series Name>, <Movie Name>, <Episode Name>, <season:2 digits>, "
            "<episode:2 digits>, <Year>, <Air Date>, <video specs>. "
            f"Default: {DEFAULT_FILENAME_PATTERN}. Provide an empty string to rely solely on auto-detection."
        ),
    )
    parser.add_argument(
        "--noBitmapSubs",
        action="store_true",
        help="Skip conversion of bitmap subtitles (PGS/SUP) to text. Bitmap subtitles "
             "will be ignored. Use this to speed up processing if you don't need OCR subtitles.",
    )
    parser.add_argument(
        "source",
        type=str,
        nargs="?",
        metavar="PATH",
        help="Input file or directory to process. If a file is specified, only that file "
             "will be processed. If a directory is specified, all supported video files in that directory "
             "will be processed. If not specified, processes all supported video files in the current directory.",
    )
    parser.add_argument(
        "--targetDir",
        type=str,
        metavar="PATH",
        help="Output directory for transcoded files. If not specified, output files are "
             "created in the same directory as input files.",
    )
    parser.add_argument(
        "--type",
        type=str,
        choices=["show", "movie"],
        metavar="TYPE",
        help="Override automatic type detection. Use 'show' to force TV show detection or "
             "'movie' to force movie detection. If not specified, type is auto-detected from filename.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files. If not specified, output files with existing names "
             "will have an incremental suffix added (e.g., video_1.mp4, video_2.mp4) to avoid overwriting.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Analyze files without processing. Shows detected metadata, Apple TV compatibility, "
             "required actions, and output paths. No files will be modified.",
    )
    
    try:
        return parser.parse_args()
    finally:
        sys.argv = original_argv


def main() -> None:
    """Main entry point for transcoding."""
    try:
        args = parse_arguments()
    except ValueError as e:
        print(f"Error during initialization: {e}")
        traceback.print_exc()
        sys.exit(1)
    except SystemExit as e:
        if getattr(e, "code", None) in (0, None):
            raise
        print(f"Error during initialization: {e}")
        sys.exit(e.code or 1)

    if getattr(args, "about", False):
        print(license_info.format_about_text())
        return

    configure_console_output()

    if getattr(args, "diagnose", False):
        run_diagnostics()
        return

    if not check_ffmpeg_available():
        print("Error: ffmpeg or ffprobe not found. Please install ffmpeg.")
        sys.exit(1)
    
    # Mode detection: determine if any explicit transcode parameters were provided
    # If any are provided, we force transcode mode unless --rewrap is explicitly requested.
    # DEFAULT_TARGET_SIZE_MB_PER_HOUR is the default, so if it's different, it was provided.
    explicit_transcode_params = (
        args.targetSizePerHour != DEFAULT_TARGET_SIZE_MB_PER_HOUR
        or getattr(args, "transcode", False)
    )
    
    # Set rewrap/transcode mode
    # - If --transcode is passed, force transcode (rewrap_mode=False).
    # - If rewrap is None and transcode params are provided, force transcode.
    # - Otherwise keep user choice or auto-detect (None).
    rewrap_mode = args.rewrap
    if getattr(args, "transcode", False):
        rewrap_mode = False
    elif rewrap_mode is None and explicit_transcode_params:
        print("Explicit transcode parameters provided. Forcing Transcode mode.")
        rewrap_mode = False
    
    # Check dependencies (only if bitmap subtitle conversion is enabled)
    if not getattr(args, "noBitmapSubs", False):
        try:
            from transcoder.dependency_manager import check_dependencies
            all_available, missing = check_dependencies()
            if not all_available:
                print(f"Warning: Missing dependencies for bitmap subtitle conversion: {', '.join(missing)}")
                print("Bitmap subtitle conversion will be skipped. Install dependencies with:")
                print("  pip install torch torchvision easyocr opencv-python")
                # Continue anyway, but disable bitmap subs
                args.noBitmapSubs = True
        except ImportError:
            # dependency_manager not available (full build), assume deps are bundled
            pass
    # Determine target directory first (needed for both wildcard and normal processing)
    target_dir = None
    if args.targetDir:
        # Strip quotes and trailing backslashes that PowerShell might add
        target_str = args.targetDir.strip().strip('"').strip("'").rstrip('\\')
        target_dir = Path(target_str).resolve()
        # Create target directory if it doesn't exist
        target_dir.mkdir(parents=True, exist_ok=True)
    
    # Determine source path (now a positional argument)
    if args.source:
        # Strip quotes and trailing backslashes that PowerShell might add
        source_str = args.source.strip().strip('"').strip("'").rstrip('\\')
        
        # Check if path contains wildcards
        if '*' in source_str or '?' in source_str:
            try:
                # Expand glob pattern using utility function
                video_files = expand_path_pattern(source_str)
                
                # Check if dry-run mode
                if getattr(args, "dry_run", False):
                    print(f"[DRY RUN] Found {len(video_files)} video file(s) matching pattern: {source_str}\n")
                    for video_file in video_files:
                        dry_run_analyze(
                            video_file,
                            rewrap=rewrap_mode,
                            target_size_mb_per_hour=args.targetSizePerHour,
                            filename_pattern=args.fileNamePattern,
                            convert_bitmap_subs=not args.noBitmapSubs,
                            target_dir=target_dir,
                            media_type_override=args.type,
                        )
                    return
                
                # Process matched files directly
                print(f"Found {len(video_files)} video file(s) matching pattern: {source_str}\n")
                success_count = 0
                for video_file in video_files:
                    if transcode_file(
                        video_file,
                        rewrap=rewrap_mode,
                        target_size_mb_per_hour=args.targetSizePerHour,
                        filename_pattern=args.fileNamePattern,
                        convert_bitmap_subs=not args.noBitmapSubs,
                        target_dir=target_dir,
                        media_type_override=args.type,
                        overwrite=args.overwrite,
                    ):
                        success_count += 1
                
                print(f"\nCompleted: {success_count}/{len(video_files)} files processed successfully")
                return
            except (ValueError, TranscoderError) as e:
                print(f"Error: {e}")
                sys.exit(1)
        
        # No wildcards, proceed normally
        source_path = Path(source_str).resolve()
        if not source_path.exists():
            print(f"Error: Source path does not exist: {source_path}")
            sys.exit(1)
    else:
        # Default to current directory
        source_path = Path.cwd()
    
    try:
        # Check if dry-run mode
        if getattr(args, "dry_run", False):
            dry_run_all(
                source_path,
                rewrap=rewrap_mode,
                target_size_mb_per_hour=args.targetSizePerHour,
                filename_pattern=args.fileNamePattern,
                convert_bitmap_subs=not args.noBitmapSubs,
                target_dir=target_dir,
                media_type_override=args.type,
            )
        else:
            transcode_all(
                source_path,
                rewrap=rewrap_mode,
                target_size_mb_per_hour=args.targetSizePerHour,
                filename_pattern=args.fileNamePattern,
                convert_bitmap_subs=not args.noBitmapSubs,
                target_dir=target_dir,
                media_type_override=args.type,
                overwrite=args.overwrite,
            )
    except TranscoderError as e:
        print(f"Error during transcoding: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error during transcoding: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
