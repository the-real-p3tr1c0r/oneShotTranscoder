# Custom hook for numpy to work around metadata version issue
# This hook handles cases where importlib.metadata.version('numpy') returns None

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import sys

# Collect numpy data files and submodules
datas = collect_data_files('numpy')
hiddenimports = collect_submodules('numpy')

# Try to get numpy version safely
try:
    import importlib.metadata
    numpy_version = importlib.metadata.version("numpy")
    if numpy_version:
        from packaging.version import Version
        numpy_version_obj = Version(numpy_version)
        # This is what the original hook tries to do, but we handle None case
        if numpy_version_obj.release[0] >= 2:
            # numpy 2.x specific handling if needed
            pass
except (Exception, TypeError):
    # If version lookup fails, just continue without version-specific logic
    pass

