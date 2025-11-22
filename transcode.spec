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
    'pkg_resources',
]

# Collect all Python files from transcoder package
# Note: datas will be populated by build script before this is executed
a = Analysis(
    ['transcoder/main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas if datas else [],  # Use datas if defined, otherwise empty list
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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

