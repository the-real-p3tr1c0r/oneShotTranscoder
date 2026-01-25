# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for transcoder project.

This spec file configures PyInstaller to create a standalone executable
that bundles ffmpeg binaries along with the Python application.
"""

import os
import sys
from pathlib import Path

block_cipher = None

# Get the project root directory
project_root = Path(SPECPATH).parent

# Data files to include (ffmpeg binaries will be added by build script)
# Build script will update this before running PyInstaller
datas = []

# Hidden imports (modules that PyInstaller might miss)
hiddenimports = [
    'easyocr',
    'cv2',
    'babelfish',
    'pgsrip',
    'torch',
    'torchvision',
    'numpy',
    'PIL',
    'certifi',
]

# Collect setuptools data files for pkg_resources
# This is needed because pkg_resources tries to access setuptools data files
try:
    import setuptools
    from PyInstaller.utils.hooks import collect_data_files
    setuptools_datas = collect_data_files('setuptools')
except Exception:
    setuptools_datas = []

try:
    certifi_datas = collect_data_files('certifi')
except Exception:
    certifi_datas = []

# Collect all Python files from transcoder package
# Note: datas will be populated by build script before this is executed
a = Analysis(
    ['transcoder/main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=(datas if datas else []) + setuptools_datas + certifi_datas,  # Use datas if defined, otherwise empty list
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
    hooksconfig={
        'pkg_resources': {
            'skip': True,  # Skip pkg_resources hook to avoid setuptools data file issues
        },
    },
    runtime_hooks=['hooks/pyi_rth_importlib_metadata.py'],
    excludes=['pkg_resources.py2_warn'],  # Exclude pkg_resources warnings
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Remove duplicate entries
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Create executable
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='transcode',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Console application (not GUI)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Can add icon file here if desired
)

