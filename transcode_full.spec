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

# Combine all data files
package_datas = setuptools_datas + babelfish_datas + easyocr_datas

# Modules to exclude (keeping all GPU/CUDA support)
excludes = [
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
    
    # PyTorch modules not needed for inference
    'torch.testing',
    'torch.utils.tensorboard',
    'torch.utils.bottleneck',
    'torch.utils.benchmark',
    'torch.onnx',  # ONNX export (not used)
    'torch.ao',  # Quantization/AO tools (not used for inference)
    'torch.fx',  # FX graph tools (not used)
    # Note: torch.package is required by torch._jit_internal, so cannot be excluded
    'torch.profiler',  # Profiling
    
    # TorchVision modules not needed
    'torchvision.datasets',  # Dataset loaders
    'torchvision.prototype',  # Prototype features
    
    # GUI toolkits (not used - CLI only)
    'tkinter', '_tkinter',
    'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
    
    # Other unused
    'matplotlib',  # Plotting (not used at runtime)
    'pandas',  # Data analysis (not used)
    'scipy.tests', 'numpy.tests',
    'setuptools._distutils',
    'xmlrpc',
    'pydoc', 'pydoc_data',
]

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















