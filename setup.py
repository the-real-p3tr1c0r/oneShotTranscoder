"""Setup script with conditional GPU dependency installation.

Copyright (C) 2025 oneShotTranscoder Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import subprocess
import sys
from setuptools import setup, find_packages
from setuptools.command.install import install


def detect_nvidia_gpu() -> bool:
    """Check if NVIDIA GPU is available.
    
    Returns:
        True if NVIDIA GPU is detected, False otherwise.
    """
    try:
        # Try nvidia-smi first (most reliable method)
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass
    
    # Fallback: try to import torch and check CUDA (if already installed)
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        pass
    
    return False


# GPU-accelerated packages configuration
# Add additional GPU packages here as needed
GPU_PACKAGES = {
    "pytorch": {
        "gpu": {
            "packages": ["torch", "torchvision"],
            "index_url": "https://download.pytorch.org/whl/cu121",
            "description": "PyTorch with CUDA 12.1 support (for EasyOCR GPU acceleration)",
        },
        "cpu": {
            "packages": ["torch", "torchvision"],
            "description": "CPU-only PyTorch",
        },
    },
    # Future GPU packages can be added here, e.g.:
    # "tensorrt": {
    #     "gpu": {
    #         "packages": ["nvidia-tensorrt"],
    #         "description": "NVIDIA TensorRT for optimized inference",
    #     },
    # },
}


def install_gpu_dependencies():
    """Install GPU-accelerated dependencies if GPU is available.
    
    Installs GPU-optimized versions of packages when NVIDIA GPU is detected,
    otherwise installs CPU-only versions.
    
    Currently installs:
    - PyTorch with CUDA 12.1 support (for EasyOCR GPU acceleration)
    - torchvision (for PyTorch image processing)
    
    Note: If packages are already installed (e.g., CPU-only), they will be
    upgraded to GPU versions if GPU is available.
    """
    gpu_available = detect_nvidia_gpu()
    
    for package_name, config in GPU_PACKAGES.items():
        if gpu_available:
            gpu_config = config.get("gpu", {})
            print(f"✓ NVIDIA GPU detected. Installing {gpu_config.get('description', package_name)}...")
            try:
                # Uninstall existing packages if present (to avoid conflicts)
                packages_to_uninstall = gpu_config.get("packages", [])
                try:
                    subprocess.run(
                        [sys.executable, "-m", "pip", "uninstall"] + packages_to_uninstall + ["-y"],
                        capture_output=True,
                        check=False,
                    )
                except Exception:
                    pass  # Ignore errors if not installed
                
                # Install GPU version
                install_cmd = [
                    sys.executable, "-m", "pip", "install",
                ] + packages_to_uninstall
                
                if "index_url" in gpu_config:
                    install_cmd.extend(["--index-url", gpu_config["index_url"]])
                
                subprocess.check_call(install_cmd)
                print(f"✓ {package_name.capitalize()} with GPU support installed successfully.")
            except subprocess.CalledProcessError as e:
                print(f"⚠ Warning: Failed to install GPU {package_name}: {e}")
                print(f"  Falling back to CPU-only {package_name}...")
                install_cpu_package(package_name, config)
        else:
            print(f"ℹ No NVIDIA GPU detected. Installing CPU-only {package_name}...")
            install_cpu_package(package_name, config)


def install_cpu_package(package_name: str, config: dict):
    """Install CPU-only version of a GPU package."""
    cpu_config = config.get("cpu", {})
    packages = cpu_config.get("packages", [])
    
    if not packages:
        return
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
        ] + packages)
        print(f"✓ CPU-only {package_name} installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"⚠ Warning: Failed to install CPU {package_name}: {e}")
        print(f"  {package_name} may need to be installed manually.")


def install_cpu_dependencies():
    """Install CPU-only versions of GPU dependencies.
    
    Deprecated: Use install_gpu_dependencies() instead, which handles both cases.
    Kept for backward compatibility.
    """
    for package_name, config in GPU_PACKAGES.items():
        install_cpu_package(package_name, config)


class PostInstallCommand(install):
    """Post-installation command to install GPU dependencies conditionally.
    
    This runs after the main package installation to detect GPU availability
    and install the appropriate PyTorch version (CUDA-enabled or CPU-only).
    """
    
    def run(self):
        # Run standard installation first
        install.run(self)
        # Then install GPU dependencies based on hardware
        install_gpu_dependencies()


setup(
    name="transcoder",
    version="0.1.0",
    description="Transcoder project",
    packages=find_packages(),
    python_requires=">=3.10",
    license="GPL-3.0-or-later",
    license_files=[
        "LICENSE",
        "NOTICE.md",
        "THIRD_PARTY_LICENSES.md",
    ],
    install_requires=[
        "easyocr",
        "opencv-python",
        "babelfish",
        "pgsrip",
        # Note: PyTorch is installed conditionally via PostInstallCommand
        # based on GPU availability (CUDA-enabled or CPU-only)
    ],
    entry_points={
        "console_scripts": [
            "transcode=transcoder.main:main",
        ],
    },
    cmdclass={
        "install": PostInstallCommand,
    },
)

