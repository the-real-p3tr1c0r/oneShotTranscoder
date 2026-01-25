#!/usr/bin/env python3
"""
Wrapper script for PyInstaller that patches importlib.metadata
to handle corrupted numpy metadata.
"""
import sys
import importlib.metadata
from pathlib import Path
import types

# Patch importlib.metadata.version to handle None returns for numpy
_original_version = importlib.metadata.version

def patched_version(package_name: str):
    """Patched version function that handles None returns."""
    try:
        result = _original_version(package_name)
        if result is None and package_name == 'numpy':
            # Fallback: get version from numpy module itself
            try:
                import numpy
                return numpy.__version__
            except ImportError:
                pass
        return result
    except Exception:
        # If original fails, try numpy fallback
        if package_name == 'numpy':
            try:
                import numpy
                return numpy.__version__
            except ImportError:
                pass
        raise

importlib.metadata.version = patched_version

# Provide a safe stub for PyInstaller's conda support to avoid broken conda-meta entries.
conda_stub = types.ModuleType("PyInstaller.utils.hooks.conda")
conda_stub.CONDA_META_DIR = Path("__pyinstaller_conda_disabled__")

def _empty_collect_dynamic_libs(*_args, **_kwargs):
    return []

conda_stub.collect_dynamic_libs = _empty_collect_dynamic_libs
conda_stub.distribution = lambda *_args, **_kwargs: None
conda_stub.package_distribution = lambda *_args, **_kwargs: None
sys.modules["PyInstaller.utils.hooks.conda"] = conda_stub

# Also patch packaging.version to handle None gracefully
try:
    from packaging import version as packaging_version
    _original_version_init = packaging_version.Version.__init__
    
    def patched_version_init(self, version, *args, **kwargs):
        """Patched Version.__init__ that handles None."""
        if version is None:
            # Try to get numpy version if we're checking numpy
            try:
                import numpy
                version = numpy.__version__
            except ImportError:
                raise TypeError("expected string or bytes-like object, got 'NoneType'")
        return _original_version_init(self, version, *args, **kwargs)
    
    packaging_version.Version.__init__ = patched_version_init
except Exception:
    pass

# Now import and run PyInstaller
if __name__ == '__main__':
    from PyInstaller.__main__ import run
    sys.argv[0] = 'pyinstaller'
    run()















