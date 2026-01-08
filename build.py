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
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
import multiprocessing

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


def find_upx() -> Optional[str]:
    """Find UPX executable.
    
    Returns:
        Path to UPX executable, or None if not found
    """
    # Check common locations
    upx_names = ["upx", "upx.exe"]
    
    # Check PATH
    for name in upx_names:
        upx_path = shutil.which(name)
        if upx_path:
            return upx_path
    
    # Check PyInstaller's UPX location (if bundled)
    try:
        import PyInstaller.utils.win32.versioninfo
        pyinstaller_dir = Path(PyInstaller.__file__).parent
        for name in upx_names:
            upx_path = pyinstaller_dir / "utils" / "win32" / name
            if upx_path.exists():
                return str(upx_path)
    except Exception:
        pass
    
    return None


def _compress_binary_with_upx(args: tuple[str, str]) -> tuple[bool, str]:
    """Compress a single binary with UPX (internal function for multiprocessing).
    
    Args:
        args: Tuple of (upx_path, binary_path_str)
    
    Returns:
        Tuple of (success, message)
    """
    upx_path, binary_path_str = args
    binary_path = Path(binary_path_str)
    
    try:
        # UPX options: --best for best compression, --lzma for better ratio
        result = subprocess.run(
            [upx_path, "--best", "--lzma", binary_path_str],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout per binary
        )
        
        if result.returncode == 0:
            return True, f"Compressed {binary_path.name}"
        else:
            # UPX returns non-zero for files it can't compress (e.g., already compressed)
            # This is not necessarily an error
            stderr_lower = result.stderr.lower()
            if "already compressed" in stderr_lower or "not compressible" in stderr_lower:
                return True, f"Skipped {binary_path.name} (already compressed/not compressible)"
            return False, f"Failed to compress {binary_path.name}: {result.stderr[:100]}"
    except subprocess.TimeoutExpired:
        return False, f"Timeout compressing {binary_path.name}"
    except Exception as e:
        return False, f"Error compressing {binary_path.name}: {str(e)[:100]}"


def compress_binaries_parallel(build_dir: Path, upx_path: Optional[str] = None) -> bool:
    """Compress all binaries in build directory using UPX in parallel.
    
    Args:
        build_dir: Directory containing built binaries
        upx_path: Path to UPX executable (if None, will try to find it)
    
    Returns:
        True if compression completed (with or without errors), False if UPX not found
    """
    if upx_path is None:
        upx_path = find_upx()
    
    if upx_path is None:
        print("Warning: UPX not found. Skipping binary compression.")
        print("Install UPX from https://upx.github.io/ for smaller binaries.")
        return False
    
    print(f"\nCompressing binaries with UPX (parallel)...")
    print(f"Using UPX: {upx_path}")
    
    # Find all binaries to compress
    # UPX can compress: .exe, .dll, .so, .dylib, and other executables
    binary_extensions = {".exe", ".dll", ".so", ".dylib"}
    binaries = []
    
    for file_path in build_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in binary_extensions:
            # Skip files that are too small (not worth compressing)
            if file_path.stat().st_size > 1024:  # Skip files < 1KB
                binaries.append(file_path)
    
    if not binaries:
        print("No binaries found to compress.")
        return True
    
    print(f"Found {len(binaries)} binaries to compress...")
    
    # Determine number of workers (use CPU count, but cap at reasonable number)
    num_workers = min(multiprocessing.cpu_count(), len(binaries), 16)
    
    # Compress binaries in parallel
    compressed_count = 0
    skipped_count = 0
    failed_count = 0
    
    # Prepare arguments for multiprocessing (convert Path to string for pickling)
    compression_args = [(upx_path, str(binary)) for binary in binaries]
    
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        # Submit all compression tasks
        future_to_binary = {
            executor.submit(_compress_binary_with_upx, args): binaries[i]
            for i, args in enumerate(compression_args)
        }
        
        # Process results as they complete
        for future in as_completed(future_to_binary):
            binary = future_to_binary[future]
            try:
                success, message = future.result()
                if success:
                    if "Skipped" in message:
                        skipped_count += 1
                    else:
                        compressed_count += 1
                    if compressed_count % 10 == 0 or skipped_count % 10 == 0:
                        print(f"  Progress: {compressed_count} compressed, {skipped_count} skipped, {failed_count} failed", end='\r')
                else:
                    failed_count += 1
                    print(f"\n  Warning: {message}")
            except Exception as e:
                failed_count += 1
                print(f"\n  Error compressing {binary.name}: {e}")
    
    print(f"\nCompression complete: {compressed_count} compressed, {skipped_count} skipped, {failed_count} failed")
    
    return True


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

    exe_ext = ".exe" if platform.system() == "Windows" else ""
    if build_mode == "full":
        output_dir = Path("dist") / "transcode"
        exe_path = output_dir / f"transcode{exe_ext}"
    else:
        output_dir = Path("dist") / "transcode-lightweight"
        exe_path = output_dir / f"transcode{exe_ext}"

    # Ensure old outputs won't trigger overwrite prompts
    if output_dir.exists():
        print(f"Cleaning existing output directory: {output_dir}")
        shutil.rmtree(output_dir)
    
    # Run PyInstaller with the modified spec file using wrapper script
    # The wrapper patches importlib.metadata to handle corrupted numpy metadata
    wrapper_script = Path(__file__).parent / "pyinstaller_wrapper.py"
    cmd = [sys.executable, str(wrapper_script), str(spec_file), "--clean", "--noconfirm"]
    
    result = subprocess.run(cmd, cwd=Path.cwd())
    
    if result.returncode != 0:
        print("Error: PyInstaller build failed")
        sys.exit(1)
    
    print("PyInstaller build completed!")
    
    if exe_path.exists():
        print(f"Executable location: {exe_path.resolve()}")
        
        # Compress binaries in parallel with UPX
        if output_dir.exists():
            compress_binaries_parallel(output_dir)
    else:
        print("Warning: Executable not found at expected location")


def _run_smoke_cmd(exe_path: Path, args: list[str], cwd: Path) -> tuple[bool, str]:
    cmd = [str(exe_path)] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return False, f"Timeout: {' '.join(cmd)}"
    except Exception as e:
        return False, f"Error running {' '.join(cmd)}: {e}"

    log_lines: list[str] = [f"$ {' '.join(cmd)}", f"exit={result.returncode}"]
    if result.stdout:
        log_lines.append("stdout:")
        log_lines.append(result.stdout.rstrip())
    if result.stderr:
        log_lines.append("stderr:")
        log_lines.append(result.stderr.rstrip())
    return result.returncode == 0, "\n".join(log_lines)


def smoke_test_transcode(exe_path: Path) -> bool:
    """Smoke test transcode executable.

    Runs in an empty temp directory to avoid scanning large trees:
    - transcode --about
    - transcode --dry-run
    """
    if not exe_path.exists():
        print(f"Smoke test failed: executable not found: {exe_path}")
        return False

    with tempfile.TemporaryDirectory(prefix="transcoder-smoke-") as tmp:
        tmp_dir = Path(tmp)

        for test_args in (["--about"], ["--dry-run"]):
            ok, log = _run_smoke_cmd(exe_path, test_args, tmp_dir)
            if not ok:
                print("\nSmoke test failed:")
                print(log)
                return False

    print("Smoke test passed.")
    return True


def _find_7zip() -> Optional[str]:
    for candidate in ["7z", "7z.exe", "7za", "7za.exe"]:
        found = shutil.which(candidate)
        if found:
            return found
    # Common Windows install locations
    common_paths = [
        Path(r"C:\Program Files\7-Zip\7z.exe"),
        Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
    ]
    for p in common_paths:
        if p.exists():
            return str(p)
    return None


def _find_transcode_exe(search_root: Path) -> Optional[Path]:
    candidates = [p for p in search_root.rglob("transcode.exe") if p.is_file()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: (len(p.parts), str(p).lower()))
    return candidates[0]


def _compile_validation_installer(
    iscc_path: Optional[str],
    build_mode: str,
    fast: bool,
    output_dir: Path,
) -> Optional[Path]:
    """Compile a non-admin validation installer (VALIDATION define) into output_dir."""
    system, _ = get_platform_info()
    if system != "Windows":
        return None

    if iscc_path:
        iscc_compiler = iscc_path
        if not Path(iscc_compiler).exists():
            return None
    else:
        iscc_compiler = find_inno_setup_compiler()
        if not iscc_compiler:
            return None

    output_dir.mkdir(parents=True, exist_ok=True)
    installer_script = Path("installer.iss")
    if not installer_script.exists():
        return None

    base_name = f"transcoder-setup-{build_mode}-validation"
    cmd = [
        iscc_compiler,
        f"/DBUILD_MODE={build_mode}",
        "/DVALIDATION=1",
        f"/O{output_dir}",
        f"/F{base_name}",
    ]

    if fast:
        cpu_count = multiprocessing.cpu_count()
        thread_count = max(1, cpu_count - 1)
        cmd.append(f"/DLZMA_THREADS={thread_count}")

    cmd.append(str(installer_script))
    result = subprocess.run(cmd, cwd=Path.cwd(), capture_output=True, text=True)
    if result.returncode != 0:
        return None

    candidate = output_dir / f"{base_name}.exe"
    return candidate if candidate.exists() else None


def validate_installer_payload(installer_path: Path, build_mode: str, iscc_path: Optional[str], fast: bool) -> bool:
    """Validate installer payload by extracting/installing to a temp dir and running smoke tests there."""
    if not installer_path.exists():
        print(f"Installer validation failed: installer not found: {installer_path}")
        return False

    with tempfile.TemporaryDirectory(prefix="transcoder-installer-") as tmp:
        tmp_dir = Path(tmp)

        seven_zip = _find_7zip()
        used_validation_installer = False
        if seven_zip:
            print(f"Extracting installer with 7-Zip: {seven_zip}")
            extract_cmd = [seven_zip, "x", str(installer_path), f"-o{tmp_dir}", "-y"]
            result = subprocess.run(extract_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print("Installer extraction failed:")
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(result.stderr)
                # Many Inno Setup installers are not extractable by 7-Zip. Fall back to
                # a validation-only installer that does a non-admin temp install.
                seven_zip = None

        if not seven_zip:
            used_validation_installer = True
            validation_out = tmp_dir / "validation-installer"
            validation_installer = _compile_validation_installer(iscc_path, build_mode, fast, validation_out)
            if not validation_installer:
                print("Installer validation failed: could not compile validation installer.")
                return False

            install_dir = tmp_dir / "install"
            install_dir.mkdir(parents=True, exist_ok=True)
            print(f"Installing validation installer to temp dir: {install_dir}")
            install_cmd = [
                str(validation_installer),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                "/SP-",
                f"/DIR={install_dir}",
            ]
            result = subprocess.run(install_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print("Validation install failed:")
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(result.stderr)
                return False

        extracted_exe = _find_transcode_exe(tmp_dir)
        if not extracted_exe:
            print(f"Installer validation failed: could not find transcode.exe under {tmp_dir}")
            return False

        print(f"Running smoke test against installer payload: {extracted_exe}")
        ok = smoke_test_transcode(extracted_exe)

        # No uninstall needed; temp dir is deleted automatically. Validation installer mode
        # does not write PATH/registry entries (see installer.iss VALIDATION guard).

        return ok


def find_inno_setup_compiler() -> Optional[str]:
    """Find Inno Setup compiler (ISCC.exe).
    
    Checks:
    1. PATH
    2. Common installation locations (system and user)
    
    Returns:
        Path to ISCC.exe if found, None otherwise
    """
    # Check PATH first
    iscc = shutil.which("ISCC") or shutil.which("ISCC.exe")
    if iscc:
        return iscc
    
    # Build list of paths to check
    common_paths = [
        # System-wide installations
        Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe"),
        Path("C:/Program Files/Inno Setup 6/ISCC.exe"),
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
        # User-local installations (winget default)
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe",
        # Older versions
        Path("C:/Program Files (x86)/Inno Setup 5/ISCC.exe"),
        Path("C:/Program Files/Inno Setup 5/ISCC.exe"),
    ]
    
    for path in common_paths:
        if path.exists():
            return str(path)
    
    return None


def get_directory_size(path: Path) -> int:
    """Get total size of a directory in bytes."""
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def create_zip_archive(build_dir: Path, output_path: Path) -> bool:
    """Create a ZIP archive of the build directory.
    
    Args:
        build_dir: Directory to archive
        output_path: Path for the output ZIP file
    
    Returns:
        True if successful, False otherwise
    """
    import zipfile
    
    print(f"Creating ZIP archive: {output_path.name}...")
    
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in build_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(build_dir.parent)
                    zipf.write(file_path, arcname)
        return True
    except Exception as e:
        print(f"Error creating ZIP: {e}")
        return False


def build_installer(iscc_path: Optional[str] = None, build_mode: str = "lightweight", fast: bool = False) -> bool:
    """Build Inno Setup installer for Windows.
    
    Args:
        iscc_path: Optional path to ISCC.exe. If not provided, will search.
        build_mode: "full" or "lightweight" - which build to package
        fast: If True, use parallel LZMA2 compression (faster but larger files)
    
    Returns:
        True if installer was built successfully, False otherwise
    """
    system, _ = get_platform_info()
    if system != "Windows":
        print("Installer generation is only supported on Windows")
        return False
    
    # Check if the requested build exists
    if build_mode == "full":
        build_dir = Path("dist") / "transcode"
        installer_name = "transcoder-setup-full.exe"
    else:
        build_dir = Path("dist") / "transcode-lightweight"
        installer_name = "transcoder-setup.exe"
    
    if not build_dir.exists():
        print(f"Error: {build_mode} build not found. Build it first with --mode {build_mode}")
        return False
    
    # Check build size (informational)
    build_size = get_directory_size(build_dir)
    build_size_mb = build_size / (1024 * 1024)
    print(f"\nBuild size: {build_size_mb:.1f} MB")
    
    # Find Inno Setup compiler
    if iscc_path:
        iscc_compiler = iscc_path
        if not Path(iscc_compiler).exists():
            print(f"Error: Inno Setup compiler not found at specified path: {iscc_compiler}")
            return False
    else:
        iscc_compiler = find_inno_setup_compiler()
        if not iscc_compiler:
            print("Warning: Inno Setup compiler (ISCC.exe) not found")
            print("\nTo build installer:")
            print("1. Install Inno Setup: winget install JRSoftware.InnoSetup")
            print("   Or download from: https://jrsoftware.org/isdl.php")
            print("2. Add to PATH, or use --iscc-path to specify the path")
            print("\nExample: python build.py --mode lightweight --installer --iscc-path \"C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe\"")
            return False
    
    print("\n" + "=" * 60)
    print(f"Building Inno Setup installer for {build_mode} build...")
    print("=" * 60)
    
    # Ensure dist directory exists
    Path("dist").mkdir(exist_ok=True)

    # Remove existing installer output to avoid overwrite prompts
    existing_installer = Path("dist") / installer_name
    if existing_installer.exists():
        print(f"Removing existing installer: {existing_installer}")
        existing_installer.unlink()
    
    # Build installer with build mode parameter
    installer_script = Path("installer.iss")
    if not installer_script.exists():
        print(f"Error: Installer script not found: {installer_script}")
        return False
    
    # Inno Setup uses /D for defines
    cmd = [iscc_compiler, f"/DBUILD_MODE={build_mode}"]
    
    if fast:
        # Calculate optimal thread count (CPU cores - 1) for parallel compression
        cpu_count = multiprocessing.cpu_count()
        thread_count = max(1, cpu_count - 1)  # At least 1 thread
        cmd.append(f"/DLZMA_THREADS={thread_count}")
        print(f"Fast compression mode: Using {thread_count} threads (CPU cores: {cpu_count})")
    else:
        print("Best compression mode: Using single-threaded LZMA2 (smallest files)")
    
    cmd.append(str(installer_script))
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=Path.cwd())
    
    if result.returncode != 0:
        print("Error: Inno Setup installer build failed")
        return False
    
    installer_path = Path("dist") / installer_name
    if installer_path.exists():
        size_mb = installer_path.stat().st_size / (1024 * 1024)
        print(f"\n✓ Installer created successfully: {installer_path.resolve()}")
        print(f"  Size: {size_mb:.1f} MB")
        print(f"  Build mode: {build_mode}")
        return True
    else:
        print("Error: Installer file not found after build")
        return False


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
    parser.add_argument(
        "--installer",
        action="store_true",
        help="Build NSIS installer(s) for the specified build mode(s) (Windows only)"
    )
    parser.add_argument(
        "--iscc-path",
        type=str,
        default=None,
        help="Path to ISCC.exe (Inno Setup compiler, if not in PATH)"
    )
    parser.add_argument(
        "--installer-only",
        action="store_true",
        help="Skip building executable, only create installer from existing build"
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Use parallel LZMA2 compression for faster installer builds (larger files)"
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("Transcoder Build Script")
    print("=" * 60)
    print()
    
    # If --installer-only, skip build and go straight to installer
    if args.installer_only:
        print("Installer-only mode: skipping build, using existing dist/")
        
        # Determine which installers to build
        installer_modes = []
        if args.mode == "both":
            installer_modes = ["lightweight", "full"]
        elif args.mode in ["full", "lightweight"]:
            installer_modes = [args.mode]
        
        for installer_mode in installer_modes:
            if installer_mode == "full":
                build_dir = Path("dist") / "transcode"
                exe_path = build_dir / ("transcode.exe" if platform.system() == "Windows" else "transcode")
            else:
                build_dir = Path("dist") / "transcode-lightweight"
                exe_path = build_dir / ("transcode.exe" if platform.system() == "Windows" else "transcode")
            
            if build_dir.exists():
                print("\nRunning dist smoke test (A)...")
                if not smoke_test_transcode(exe_path):
                    print("Skipping installer build due to failed dist smoke test.")
                    continue
                if build_installer(args.iscc_path, installer_mode, args.fast):
                    installer_path = Path("dist") / ("transcoder-setup-full.exe" if installer_mode == "full" else "transcoder-setup.exe")
                    print("\nValidating installer payload (B)...")
                    validate_installer_payload(installer_path, installer_mode, args.iscc_path, args.fast)
            else:
                print(f"\nError: {installer_mode} build not found at {build_dir}")
                print(f"Build it first with: python build.py --mode {installer_mode}")
        
        return
    
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
    
    # Build installer if requested
    if args.installer:
        # Determine which installers to build
        installer_modes = []
        if args.mode == "both":
            installer_modes = ["lightweight", "full"]
        elif args.mode in ["full", "lightweight"]:
            installer_modes = [args.mode]
        
        for installer_mode in installer_modes:
            # Check if the build exists
            if installer_mode == "full":
                build_dir = Path("dist") / "transcode"
                exe_path = build_dir / ("transcode.exe" if platform.system() == "Windows" else "transcode")
            else:
                build_dir = Path("dist") / "transcode-lightweight"
                exe_path = build_dir / ("transcode.exe" if platform.system() == "Windows" else "transcode")
            
            if build_dir.exists():
                print("\nRunning dist smoke test (A)...")
                if not smoke_test_transcode(exe_path):
                    print("Skipping installer build due to failed dist smoke test.")
                    continue
                if build_installer(args.iscc_path, installer_mode, args.fast):
                    installer_path = Path("dist") / ("transcoder-setup-full.exe" if installer_mode == "full" else "transcoder-setup.exe")
                    print("\nValidating installer payload (B)...")
                    validate_installer_payload(installer_path, installer_mode, args.iscc_path, args.fast)
            else:
                print(f"\nWarning: {installer_mode} build not found. Skipping installer.")
                print(f"Build it first with --mode {installer_mode}")


if __name__ == "__main__":
    main()

