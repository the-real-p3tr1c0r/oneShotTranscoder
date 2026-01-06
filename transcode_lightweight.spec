# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for LIGHTWEIGHT build (onedir mode).
Excludes heavy dependencies that will be downloaded on-demand.
"""

import os
import sys
from pathlib import Path

block_cipher = None
project_root = Path(SPECPATH).parent

# Data files to include (ffmpeg binaries will be added by build script)
datas = []

# Only include essential dependencies
# Heavy deps (torch, easyocr, cv2) excluded - downloaded on-demand
hiddenimports = [
    'babelfish',
    'pgsrip',
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
    ['launcher.py'],  # Use launcher instead of main.py directly
    pathex=[str(project_root)],
    binaries=[],
    datas=(datas if datas else []) + setuptools_datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
    hooksconfig={
        'pkg_resources': {
            'skip': True,
        },
    },
    runtime_hooks=['hooks/pyi_rth_importlib_metadata.py'],
    excludes=['pkg_resources.py2_warn', 'torch', 'torchvision', 'easyocr', 'cv2'],
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
    exclude_binaries=True,
    name='transcode',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name='transcode-lightweight',
)














