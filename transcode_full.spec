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
    'torch.distributed',  # Required by torch
    'torch.package',  # Required by torch._jit_internal
    'torchvision',
    'numpy',
    'PIL',
]

# Collect data files for packages that need them
from PyInstaller.utils.hooks import collect_data_files

try:
    setuptools_datas = collect_data_files('setuptools')
except Exception:
    setuptools_datas = []

# Babelfish needs its language/country data files
try:
    babelfish_datas = collect_data_files('babelfish')
except Exception:
    babelfish_datas = []

# EasyOCR may need model data
try:
    easyocr_datas = collect_data_files('easyocr')
except Exception:
    easyocr_datas = []

# Cleanit data files
try:
    cleanit_datas = collect_data_files('cleanit')
except Exception:
    cleanit_datas = []

# pgsrip data files
try:
    pgsrip_datas = collect_data_files('pgsrip')
except Exception:
    pgsrip_datas = []

# trakit data files
try:
    trakit_datas = collect_data_files('trakit')
except Exception:
    trakit_datas = []

# guessit data files
try:
    guessit_datas = collect_data_files('guessit')
except Exception:
    guessit_datas = []

# rebulk data files
try:
    rebulk_datas = collect_data_files('rebulk')
except Exception:
    rebulk_datas = []

# Combine all data files
package_datas = setuptools_datas + babelfish_datas + easyocr_datas + cleanit_datas + pgsrip_datas + trakit_datas + guessit_datas + rebulk_datas

# Modules to exclude
# SYSTEMATIC FIX: We stop manually excluding anything for the full build.
# The size savings from excluding stdlib/helper modules (pydoc, unittest, etc.)
# are negligible compared to the ~2GB torch bundle, but they frequently
# break internal imports in complex libraries like scipy and torch.
excludes = []

# Collect all Python files from transcoder package
a = Analysis(
    ['transcoder/main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=(datas if datas else []) + package_datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
    hooksconfig={
        'pkg_resources': {
            'skip': True,  # Skip pkg_resources hook to avoid setuptools data file issues
        },
    },
    runtime_hooks=['hooks/pyi_rth_importlib_metadata.py'],
    excludes=excludes,
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
    upx=False,  # Disabled: we compress in parallel after build
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
    upx=False,  # Disabled: we compress in parallel after build
    upx_exclude=[],
    name='transcode',
)















