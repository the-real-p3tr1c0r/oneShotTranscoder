#!/usr/bin/env python3
"""
Wrapper script for PyInstaller that patches importlib.metadata
to handle corrupted numpy metadata.
"""
import sys
import importlib.metadata

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














