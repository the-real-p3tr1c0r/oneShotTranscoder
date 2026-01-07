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

# Combine all data files
package_datas = setuptools_datas + babelfish_datas

# Modules to exclude
# Heavy deps (torch, easyocr, cv2) excluded - downloaded on-demand
excludes = [
    # OCR dependencies (downloaded on-demand)
    'torch', 'torchvision', 'easyocr', 'cv2',
    
    # Development/testing (not needed at runtime)
    'pkg_resources.py2_warn',
    'pytest', '_pytest',
    'unittest', 'unittest.mock',
    'test', 'tests',
    'doctest',
    
    # Documentation tools
    'sphinx', 'docutils', 'rst',
    
    # Interactive/notebook environments
    'IPython', 'ipykernel', 'ipywidgets',
    'notebook', 'jupyter', 'jupyter_client', 'jupyter_core',
    
    # GUI toolkits (not used - CLI only)
    'tkinter', '_tkinter',
    'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
    
    # Other unused
    'matplotlib',
    'pandas',
    'scipy.tests', 'numpy.tests',
    'setuptools._distutils',
    'xmlrpc',
    'pydoc', 'pydoc_data',
]

# Collect all Python files from transcoder package
a = Analysis(
    ['launcher.py'],  # Use launcher instead of main.py directly
    pathex=[str(project_root)],
    binaries=[],
    datas=(datas if datas else []) + package_datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
    hooksconfig={
        'pkg_resources': {
            'skip': True,
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















