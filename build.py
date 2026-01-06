#!/usr/bin/env python3
"""
Build script for creating standalone executable with bundled ffmpeg binaries.

This script:
1. Downloads platform-specific ffmpeg binaries
2. Bundles them with the application using PyInstaller
3. Creates a standalone executable that works without external dependencies

Usage:
    python build.py

Requirements:
    - Python 3.10+
    - pip install pyinstaller
"""

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# FFmpeg download URLs (using static builds from BtbN/ffmpeg-builds)
FFMPEG_URLS = {
    "Windows": {
        "x86_64": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    },
    "Darwin": {
        "x86_64": "https://evermeet.cx/ffmpeg/ffmpeg-7.0.zip",
        "arm64": "https://evermeet.cx/ffmpeg/ffmpeg-7.0.zip",  # Same URL for both
    },
    "Linux": {
        "x86_64": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
    },
}

FFPROBE_URLS = {
    "Windows": {
        "x86_64": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    },
    "Darwin": {
        "x86_64": "https://evermeet.cx/ffmpeg/ffprobe-7.0.zip",
        "arm64": "https://evermeet.cx/ffmpeg/ffprobe-7.0.zip",
    },
    "Linux": {
        "x86_64": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
    },
}


def get_platform_info():
    """Get current platform information."""
    system = platform.system()
    machine = platform.machine().lower()
    
    # Normalize machine architecture
    if machine in ("x86_64", "amd64"):
        arch = "x86_64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = machine
    
    return system, arch


def download_file(url: str, dest_path: Path) -> None:
    """Download a file from URL to destination path."""
    print(f"Downloading {url}...")
    try:
        urllib.request.urlretrieve(url, dest_path)
        print(f"Downloaded to {dest_path}")
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        raise


def extract_ffmpeg_windows(zip_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """Extract ffmpeg and ffprobe from Windows zip file."""
    print(f"Extracting {zip_path}...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(output_dir)
    
    # Find ffmpeg.exe and ffprobe.exe in extracted files
    ffmpeg_exe = None
    ffprobe_exe = None
    
    for root, dirs, files in os.walk(output_dir):
        for file in files:
            if file == "ffmpeg.exe":
                ffmpeg_exe = Path(root) / file
            elif file == "ffprobe.exe":
                ffprobe_exe = Path(root) / file
    
    if not ffmpeg_exe or not ffprobe_exe:
        raise FileNotFoundError("Could not find ffmpeg.exe or ffprobe.exe in extracted archive")
    
    return ffmpeg_exe, ffprobe_exe


def extract_ffmpeg_macos(zip_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """Extract ffmpeg and ffprobe from macOS zip files."""
    print(f"Extracting {zip_path}...")
    
    # macOS downloads are separate zip files for ffmpeg and ffprobe
    # Extract the main zip (ffmpeg)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(output_dir)
    
    ffmpeg_bin = output_dir / "ffmpeg"
    if not ffmpeg_bin.exists():
        # Try to find it in subdirectories
        for root, dirs, files in os.walk(output_dir):
            if "ffmpeg" in files:
                ffmpeg_bin = Path(root) / "ffmpeg"
                break
    
    # For ffprobe, we need to download it separately
    # This is a simplified version - in practice, you'd download both
    ffprobe_bin = None
    
    return ffmpeg_bin, ffprobe_bin


def extract_ffmpeg_linux(tar_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """Extract ffmpeg and ffprobe from Linux tar.xz file."""
    import tarfile
    print(f"Extracting {tar_path}...")
    
    with tarfile.open(tar_path, 'r:xz') as tar_ref:
        tar_ref.extractall(output_dir)
    
    # Find ffmpeg and ffprobe binaries
    ffmpeg_bin = None
    ffprobe_bin = None
    
    for root, dirs, files in os.walk(output_dir):
        for file in files:
            if file == "ffmpeg" and not ffmpeg_bin:
                ffmpeg_bin = Path(root) / file
            elif file == "ffprobe" and not ffprobe_bin:
                ffprobe_bin = Path(root) / file
    
    if not ffmpeg_bin or not ffprobe_bin:
        raise FileNotFoundError("Could not find ffmpeg or ffprobe in extracted archive")
    
    return ffmpeg_bin, ffprobe_bin


def prepare_ffmpeg_binaries() -> Path:
    """
    Download and prepare ffmpeg binaries for the current platform.
    
    Returns:
        Path to directory containing ffmpeg binaries ready to bundle
    """
    system, arch = get_platform_info()
    
    print(f"Platform: {system} {arch}")
    
    # Create temporary directory for ffmpeg binaries
    ffmpeg_dir = Path("ffmpeg_binaries")
    ffmpeg_dir.mkdir(exist_ok=True)
    
    # Check if binaries already exist
    if system == "Windows":
        ffmpeg_exe = ffmpeg_dir / "ffmpeg.exe"
        ffprobe_exe = ffmpeg_dir / "ffprobe.exe"
        if ffmpeg_exe.exists() and ffprobe_exe.exists():
            print("FFmpeg binaries already exist, skipping download")
            return ffmpeg_dir
    else:
        ffmpeg_bin = ffmpeg_dir / "ffmpeg"
        ffprobe_bin = ffmpeg_dir / "ffprobe"
        if ffmpeg_bin.exists() and ffprobe_bin.exists():
            print("FFmpeg binaries already exist, skipping download")
            return ffmpeg_dir
    
    # Get download URL
    if system not in FFMPEG_URLS:
        raise ValueError(f"Unsupported platform: {system}")
    
    if arch not in FFMPEG_URLS[system]:
        raise ValueError(f"Unsupported architecture: {arch} on {system}")
    
    url = FFMPEG_URLS[system][arch]
    
    # Download and extract
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        if system == "Windows":
            zip_path = temp_path / "ffmpeg.zip"
            download_file(url, zip_path)
            ffmpeg_exe, ffprobe_exe = extract_ffmpeg_windows(zip_path, temp_path)
            
            # Copy to output directory
            shutil.copy2(ffmpeg_exe, ffmpeg_dir / "ffmpeg.exe")
            shutil.copy2(ffprobe_exe, ffmpeg_dir / "ffprobe.exe")
            
        elif system == "Darwin":
            # macOS: Download ffmpeg and ffprobe separately
            ffmpeg_zip = temp_path / "ffmpeg.zip"
            ffprobe_zip = temp_path / "ffprobe.zip"
            
            download_file(url, ffmpeg_zip)
            download_file(FFPROBE_URLS[system][arch], ffprobe_zip)
            
            # Extract ffmpeg
            with zipfile.ZipFile(ffmpeg_zip, 'r') as z:
                z.extractall(temp_path)
                ffmpeg_bin = temp_path / "ffmpeg"
                if not ffmpeg_bin.exists():
                    # Look for it in extracted files
                    for item in temp_path.iterdir():
                        if item.name == "ffmpeg":
                            ffmpeg_bin = item
                            break
            
            # Extract ffprobe
            with zipfile.ZipFile(ffprobe_zip, 'r') as z:
                z.extractall(temp_path)
                ffprobe_bin = temp_path / "ffprobe"
                if not ffprobe_bin.exists():
                    for item in temp_path.iterdir():
                        if item.name == "ffprobe":
                            ffprobe_bin = item
                            break
            
            # Copy to output directory
            shutil.copy2(ffmpeg_bin, ffmpeg_dir / "ffmpeg")
            shutil.copy2(ffprobe_bin, ffmpeg_dir / "ffprobe")
            
            # Make executable
            os.chmod(ffmpeg_dir / "ffmpeg", 0o755)
            os.chmod(ffmpeg_dir / "ffprobe", 0o755)
            
        elif system == "Linux":
            tar_path = temp_path / "ffmpeg.tar.xz"
            download_file(url, tar_path)
            ffmpeg_bin, ffprobe_bin = extract_ffmpeg_linux(tar_path, temp_path)
            
            # Copy to output directory
            shutil.copy2(ffmpeg_bin, ffmpeg_dir / "ffmpeg")
            shutil.copy2(ffprobe_bin, ffmpeg_dir / "ffprobe")
            
            # Make executable
            os.chmod(ffmpeg_dir / "ffmpeg", 0o755)
            os.chmod(ffmpeg_dir / "ffprobe", 0o755)
    
    print(f"FFmpeg binaries prepared in {ffmpeg_dir}")
    return ffmpeg_dir


def update_spec_file(ffmpeg_dir: Path, spec_name: str = "transcode.spec") -> Path:
    """
    Create a modified spec file with ffmpeg binaries included.
    
    Args:
        ffmpeg_dir: Directory containing ffmpeg binaries
        spec_name: Name of the spec file to use
    
    Returns:
        Path to the modified spec file
    """
    spec_path = Path(spec_name)
    
    if not spec_path.exists():
        raise FileNotFoundError("transcode.spec not found")
    
    # Read spec file
    with open(spec_path, 'r', encoding='utf-8') as f:
        spec_content = f.read()
    
    # Convert to absolute path for PyInstaller
    abs_ffmpeg_dir = ffmpeg_dir.resolve()

    def format_src(path: Path) -> str:
        """Return a repr-safe string literal for embedding in spec file."""
        return repr(str(path))
    
    # Add ffmpeg binaries and license notices to datas
    # PyInstaller will bundle them in the executable
    license_files = [
        Path("LICENSE"),
        Path("NOTICE.md"),
        Path("THIRD_PARTY_LICENSES.md"),
    ]
    for license_file in license_files:
        if not license_file.exists():
            raise FileNotFoundError(f"Required license file not found: {license_file}")
    data_entries = [f"({format_src(abs_ffmpeg_dir)}, 'ffmpeg')"]
    data_entries.extend(
        f"({format_src(license_file.resolve())}, '{license_file.name}')"
        for license_file in license_files
    )
    datas_block = ",\n        ".join(data_entries)
    
    # Find and replace the datas line
    import re
    # Match datas = [] or datas = [anything]
    pattern = r"datas\s*=\s*\[.*?\]"
    
    replacement_block = f"datas = [\n        {datas_block}\n    ]"

    if re.search(pattern, spec_content, re.DOTALL):
        # Replace existing datas definition, preserving literal backslashes
        spec_content = re.sub(
            pattern,
            lambda _: replacement_block,
            spec_content,
            count=1,
            flags=re.DOTALL,
        )
    else:
        # Add datas definition before Analysis if it doesn't exist
        datas_section_pattern = r"(# Data files.*?\n)(datas = \[\])"

        def insert_datas(match: re.Match) -> str:
            return f"{match.group(1)}{replacement_block}"

        spec_content, subs = re.subn(
            datas_section_pattern,
            insert_datas,
            spec_content,
            count=1,
            flags=re.DOTALL,
        )

        if subs == 0:
            raise ValueError("Could not locate datas block to update in spec file")
    
    # Write to a temporary spec file
    modified_spec = Path("transcode_build.spec")
    with open(modified_spec, 'w', encoding='utf-8') as f:
        f.write(spec_content)
    
    print(f"Created modified spec file: {modified_spec}")
    return modified_spec


def build_executable(spec_file: Path, build_mode: str = "full") -> None:
    """Build the executable using PyInstaller.
    
    Args:
        spec_file: Path to spec file
        build_mode: "full" for self-contained, "lightweight" for on-demand
    """
    print(f"Building executable in {build_mode} mode...")
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Error: PyInstaller is not installed.")
        print("Install it with: pip install pyinstaller")
        sys.exit(1)
    
    # Run PyInstaller with the modified spec file using wrapper script
    # The wrapper patches importlib.metadata to handle corrupted numpy metadata
    wrapper_script = Path(__file__).parent / "pyinstaller_wrapper.py"
    cmd = [sys.executable, str(wrapper_script), str(spec_file), "--clean"]
    
    result = subprocess.run(cmd, cwd=Path.cwd())
    
    if result.returncode != 0:
        print("Error: PyInstaller build failed")
        sys.exit(1)
    
    print("Build completed successfully!")
    exe_ext = ".exe" if platform.system() == "Windows" else ""
    
    if build_mode == "full":
        exe_path = Path("dist") / "transcode" / f"transcode{exe_ext}"
    else:
        exe_path = Path("dist") / "transcode-lightweight" / f"transcode{exe_ext}"
    
    if exe_path.exists():
        print(f"Executable location: {exe_path.resolve()}")
    else:
        print("Warning: Executable not found at expected location")


def main():
    """Main build function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Build transcoder executable")
    parser.add_argument(
        "--mode",
        choices=["full", "lightweight", "both"],
        default="both",
        help="Build mode: 'full' (self-contained), 'lightweight' (on-demand), or 'both'"
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("Transcoder Build Script")
    print("=" * 60)
    print()
    
    # Step 1: Prepare ffmpeg binaries
    print("Step 1: Preparing FFmpeg binaries...")
    try:
        ffmpeg_dir = prepare_ffmpeg_binaries()
    except Exception as e:
        print(f"Error preparing FFmpeg binaries: {e}")
        print("\nNote: You can manually place ffmpeg binaries in 'ffmpeg_binaries/' directory:")
        print("  - Windows: ffmpeg.exe, ffprobe.exe")
        print("  - macOS/Linux: ffmpeg, ffprobe")
        sys.exit(1)
    
    build_modes = []
    if args.mode in ["full", "both"]:
        build_modes.append(("full", "transcode_full.spec"))
    if args.mode in ["lightweight", "both"]:
        build_modes.append(("lightweight", "transcode_lightweight.spec"))
    
    for mode_name, spec_name in build_modes:
        print(f"\n{'=' * 60}")
        print(f"Building {mode_name} version...")
        print("=" * 60)
        
        # Step 2: Update spec file
        print(f"\nStep 2: Updating {spec_name}...")
        try:
            modified_spec = update_spec_file(ffmpeg_dir, spec_name)
        except Exception as e:
            print(f"Error updating spec file: {e}")
            continue
        
        # Step 3: Build executable
        print(f"\nStep 3: Building {mode_name} executable...")
        try:
            build_executable(modified_spec, mode_name)
        except Exception as e:
            print(f"Error building executable: {e}")
        finally:
            # Clean up temporary spec file
            if modified_spec.exists():
                modified_spec.unlink()
    
    print("\n" + "=" * 60)
    print("Build completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()

