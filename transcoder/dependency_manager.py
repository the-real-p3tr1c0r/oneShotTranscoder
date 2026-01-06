"""Dependency manager for on-demand component loading."""

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

# Python embeddable download URLs
PYTHON_EMBED_URLS = {
    "Windows": {
        "x86_64": "https://www.python.org/ftp/python/3.12.0/python-3.12.0-embed-amd64.zip",
    },
    # Add other platforms as needed
}

# Heavy dependencies that can be downloaded on-demand
HEAVY_DEPS = {
    "torch": {
        "cpu": ["torch", "torchvision"],
        "gpu": {
            "packages": ["torch", "torchvision"],
            "index_url": "https://download.pytorch.org/whl/cu121",
        },
    },
    "easyocr": {
        "packages": ["easyocr"],
    },
    "opencv": {
        "packages": ["opencv-python"],
    },
}


def get_app_data_dir() -> Path:
    """Get application data directory for storing dependencies."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
    
    return base / "transcoder"


def ensure_python() -> Optional[str]:
    """Ensure Python is available, download embeddable if needed."""
    # Check if system Python is available
    python_exe = shutil.which("python3") or shutil.which("python")
    if python_exe:
        try:
            result = subprocess.run(
                [python_exe, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and "3.1" in result.stdout:
                return python_exe
        except Exception:
            pass
    
    # Download embeddable Python
    app_data = get_app_data_dir()
    python_dir = app_data / "python"
    
    if sys.platform == "win32":
        python_exe = python_dir / "python.exe"
    else:
        python_exe = python_dir / "bin" / "python3"
    
    if python_exe.exists():
        return str(python_exe)
    
    print("Python not found. Downloading Python embeddable...")
    url = PYTHON_EMBED_URLS.get(sys.platform, {}).get("x86_64")
    if not url:
        print(f"Warning: Python embeddable not available for {sys.platform}")
        print("Please install Python 3.10+ manually.")
        return None
    
    zip_path = app_data / "python.zip"
    python_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Downloading Python from {url}...")
    try:
        urllib.request.urlretrieve(url, zip_path)
    except Exception as e:
        print(f"Error downloading Python: {e}")
        return None
    
    print("Extracting Python...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(python_dir)
    except Exception as e:
        print(f"Error extracting Python: {e}")
        return None
    finally:
        if zip_path.exists():
            zip_path.unlink()
    
    # Install pip
    try:
        subprocess.run(
            [str(python_exe), "-m", "ensurepip", "--upgrade"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        print("Warning: Failed to install pip in embeddable Python")
    
    return str(python_exe)


def ensure_dependency(dep_name: str, python_exe: Optional[str] = None) -> bool:
    """Ensure a heavy dependency is installed."""
    if python_exe is None:
        python_exe = sys.executable
    
    dep_config = HEAVY_DEPS.get(dep_name)
    if not dep_config:
        return False
    
    # Check if already installed
    try:
        if dep_name == "torch":
            import torch
            return True
        elif dep_name == "easyocr":
            import easyocr
            return True
        elif dep_name == "opencv":
            import cv2
            return True
    except ImportError:
        pass
    
    # Install dependency
    print(f"Installing {dep_name}...")
    
    if dep_name == "torch":
        # Detect GPU and install appropriate version
        try:
            result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True,
                timeout=5,
            )
            has_gpu = result.returncode == 0
        except Exception:
            has_gpu = False
        
        if has_gpu and "gpu" in dep_config:
            packages = dep_config["gpu"]["packages"]
            cmd = [python_exe, "-m", "pip", "install"] + packages
            cmd.extend(["--index-url", dep_config["gpu"]["index_url"]])
        else:
            packages = dep_config["cpu"]
            cmd = [python_exe, "-m", "pip", "install"] + packages
    else:
        packages = dep_config["packages"]
        cmd = [python_exe, "-m", "pip", "install"] + packages
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✓ {dep_name} installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install {dep_name}: {e}")
        return False


def ensure_all_dependencies() -> bool:
    """Ensure all required dependencies are available."""
    # For lightweight build, check if we're running from PyInstaller bundle
    # If so, we need to use system Python, not the bundled executable
    python_exe = sys.executable
    
    # Check if we're running from PyInstaller bundle
    if hasattr(sys, 'frozen') and sys.frozen:
        # Try to find system Python
        import shutil
        system_python = shutil.which("python3") or shutil.which("python")
        if system_python:
            python_exe = system_python
            print(f"Using system Python: {python_exe}")
        else:
            print("Error: Cannot find system Python. Please install Python 3.10+")
            print("Or use the full build which includes all dependencies.")
            return False
    
    success = True
    for dep_name in ["torch", "easyocr", "opencv"]:
        if not ensure_dependency(dep_name, python_exe):
            print(f"Warning: Failed to install {dep_name}")
            success = False
    
    return success


def check_dependencies() -> tuple[bool, list[str]]:
    """Check if required dependencies are available.
    
    Returns:
        Tuple of (all_available, missing_deps)
    """
    missing = []
    
    try:
        import torch
    except ImportError:
        missing.append("torch")
    
    try:
        import easyocr
    except ImportError:
        missing.append("easyocr")
    
    try:
        import cv2
    except ImportError:
        missing.append("opencv-python")
    
    return len(missing) == 0, missing

