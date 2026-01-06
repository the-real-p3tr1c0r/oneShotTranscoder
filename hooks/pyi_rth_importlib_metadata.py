"""
Runtime hook to patch importlib.metadata to handle missing package metadata
in PyInstaller bundles. This fixes issues where packages try to access
their metadata but PyInstaller doesn't bundle it.
"""
import sys
import importlib.metadata

# Store original functions
_original_metadata = importlib.metadata.metadata
_original_version = importlib.metadata.version

def patched_metadata(package_name: str):
    """Patched metadata function that handles PackageNotFoundError."""
    try:
        return _original_metadata(package_name)
    except importlib.metadata.PackageNotFoundError:
        # Try to get version from module if available
        try:
            module = __import__(package_name)
            version = getattr(module, '__version__', 'unknown')
        except (ImportError, AttributeError):
            version = 'unknown'
        
        # Create a minimal metadata object using the same approach as importlib.metadata
        # We need to create a dict-like object that behaves like PackageMetadata
        from collections.abc import Mapping
        
        class MinimalMetadata(Mapping):
            def __init__(self, name, version):
                self._data = {'Name': name, 'Version': version}
            
            def __getitem__(self, key):
                return self._data.get(key, '')
            
            def __iter__(self):
                return iter(self._data)
            
            def __len__(self):
                return len(self._data)
            
            def get(self, key, default=None):
                return self._data.get(key, default)
            
            def get_all(self, key, default=None):
                """Compatibility method for PackageMetadata."""
                value = self._data.get(key, default)
                return [value] if value else []
        
        return MinimalMetadata(package_name, version)

def patched_version(package_name: str):
    """Patched version function that handles PackageNotFoundError."""
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
    except importlib.metadata.PackageNotFoundError:
        # Try to get version from module if available
        try:
            module = __import__(package_name)
            return getattr(module, '__version__', 'unknown')
        except (ImportError, AttributeError):
            return 'unknown'

# Patch the functions
importlib.metadata.metadata = patched_metadata
importlib.metadata.version = patched_version
