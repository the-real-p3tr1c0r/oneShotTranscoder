# Building the Transcoder Executable

This document explains how to build a standalone executable for the transcoder project that includes bundled ffmpeg binaries.

## Overview

The build system creates a standalone executable that:
- Bundles ffmpeg and ffprobe binaries (no external installation needed)
- Includes all Python dependencies
- Works on Windows, macOS, and Linux
- Creates a single executable file (`.exe` on Windows, binary on macOS/Linux)

## Prerequisites

1. **Python 3.10 or higher**
2. **PyInstaller**: Install with `pip install pyinstaller`
3. **Internet connection** (for downloading ffmpeg binaries during build)

## Quick Start

### Windows
```batch
build.bat
```

### macOS/Linux
```bash
./build.sh
```

Or run the Python script directly:
```bash
python build.py
```

## Build Process

The build script (`build.py`) performs the following steps:

1. **Downloads FFmpeg binaries** for your platform:
   - Windows: Downloads from BtbN/FFmpeg-Builds
   - macOS: Downloads from evermeet.cx
   - Linux: Downloads from johnvansickle.com

2. **Prepares binaries** in `ffmpeg_binaries/` directory

3. **Updates PyInstaller spec file** to include bundled binaries

4. **Builds executable** using PyInstaller

5. **Output**: Executable is created in `dist/transcode` (or `dist/transcode.exe` on Windows)

## Manual Binary Placement (Alternative)

If automatic download fails, you can manually place ffmpeg binaries:

1. Create `ffmpeg_binaries/` directory in the project root
2. Place binaries in this directory:
   - **Windows**: `ffmpeg.exe`, `ffprobe.exe`
   - **macOS/Linux**: `ffmpeg`, `ffprobe`
3. Make sure binaries are executable (on Unix systems): `chmod +x ffmpeg_binaries/ffmpeg ffmpeg_binaries/ffprobe`
4. Run `python build.py` - it will skip download if binaries exist

## Output

After successful build:
- **Windows**: `dist/transcode.exe`
- **macOS/Linux**: `dist/transcode`

The executable is standalone and includes:
- All Python dependencies
- FFmpeg binaries
- EasyOCR models (if needed)
- License notices (`LICENSE`, `NOTICE.md`, `THIRD_PARTY_LICENSES.md`) for distribution compliance

## Troubleshooting

### Build fails with "FFmpeg binaries not found"
- Check internet connection
- Try manual binary placement (see above)
- Verify `ffmpeg_binaries/` directory exists and contains correct binaries

### PyInstaller errors
- Ensure PyInstaller is installed: `pip install pyinstaller`
- Try cleaning build artifacts: `rm -rf build dist` (or `rmdir /s build dist` on Windows)
- Check Python version: `python --version` (should be 3.10+)

### Executable doesn't run
- Check that bundled binaries are included: Extract executable and verify `ffmpeg/` directory exists
- Test ffmpeg binaries manually: Run `ffmpeg_binaries/ffmpeg -version`
- Check file permissions (Unix): `chmod +x dist/transcode`

## Platform-Specific Notes

### Windows
- Executable will be `transcode.exe`
- FFmpeg binaries are `ffmpeg.exe` and `ffprobe.exe`
- Build requires Visual C++ Redistributable (usually already installed)

### macOS
- Executable will be `transcode` (no extension)
- May require code signing for distribution (see PyInstaller docs)
- FFmpeg binaries must be signed or have appropriate permissions

### Linux
- Executable will be `transcode` (no extension)
- FFmpeg binaries are statically linked
- May need to install additional libraries depending on distribution

## Advanced Usage

### Custom Spec File
Modify `transcode.spec` to customize build options:
- Add icon: Set `icon='path/to/icon.ico'` in EXE section
- Change output name: Modify `name='transcode'` in EXE section
- Add additional data files: Add to `datas` list

### Build Options
Run PyInstaller directly with custom options:
```bash
pyinstaller transcode.spec --clean --onefile
```

## Distribution

The built executable can be distributed independently:
- No Python installation required on target system
- No FFmpeg installation required on target system
- All dependencies are bundled
- License documents placed next to the executable satisfy GPL/FFmpeg attribution requirements

## License Compliance Checklist

1. Keep `LICENSE`, `NOTICE.md`, and `THIRD_PARTY_LICENSES.md` alongside the built
   binary when you distribute it.
2. Use `transcode --about` to print the current version and license notice block
   for auditing.
3. Provide the full corresponding source for oneShotTranscoder (this repository)
   and direct recipients to the FFmpeg sources referenced in `NOTICE.md`.

**Note**: The executable is platform-specific. Build separate executables for each target platform.


