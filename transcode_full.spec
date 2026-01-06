# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for FULL self-contained build (onedir mode).
Includes all dependencies bundled.
"""

import os
import sys
from pathlib import Path

block_cipher = None
project_root = Path(SPECPATH).parent

# Data files to include (ffmpeg binaries will be added by build script)
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
]

# Collect setuptools data files for pkg_resources
try:
    import setuptools
    from PyInstaller.utils.hooks import collect_data_files
    setuptools_datas = collect_data_files('setuptools')
except Exception:
    setuptools_datas = []

# Collect all Python files from transcoder package
a = Analysis(
    ['transcoder/main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=(datas if datas else []) + setuptools_datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
    hooksconfig={
        'pkg_resources': {
            'skip': True,  # Skip pkg_resources hook to avoid setuptools data file issues
        },
    },
    runtime_hooks=['hooks/pyi_rth_importlib_metadata.py'],
    excludes=['pkg_resources.py2_warn'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Remove duplicate entries
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ONEDIR mode - creates directory with separate files
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # Don't bundle binaries in exe
    name='transcode',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Console application (not GUI)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='transcode',
)














