# Building the Transcoder Executable

This document explains how to build a standalone executable for the transcoder project that includes bundled ffmpeg binaries.

## Overview

The build system supports multiple packaging options:

1. **Full Build**: Self-contained executable with all dependencies (including OCR libraries)
2. **Lightweight Build**: Smaller executable with on-demand dependency loading
3. **Windows Installer**: Professional installer that registers the application in Control Panel and adds to PATH

All builds:
- Bundle ffmpeg and ffprobe binaries (no external installation needed)
- Work on Windows, macOS, and Linux
- Include license notices for distribution compliance

## Prerequisites

1. **Python 3.10 or higher**
2. **PyInstaller**: Install with `pip install pyinstaller`
3. **Internet connection** (for downloading ffmpeg binaries during build)
4. **NSIS** (Windows only, for installer): Download from https://nsis.sourceforge.io/ and add to PATH

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

### Build Modes

Build lightweight version (recommended for smaller size):
```bash
python build.py --mode lightweight
```

Build full version (includes all dependencies):
```bash
python build.py --mode full
```

Build both versions:
```bash
python build.py --mode both
```

### Windows Installer

To create Windows installers that register in Control Panel:

**Lightweight installer:**
```bash
python build.py --mode lightweight --installer
```

**Full installer:**
```bash
python build.py --mode full --installer
```

**Both installers:**
```bash
python build.py --mode both --installer
```

The installers will:
- Install to `C:\Program Files\Transcoder\`
- Register in Windows Control Panel (Apps & Features)
- Optionally add to system PATH
- Create Start Menu shortcuts
- Provide uninstaller

**Output files:**
- `dist/transcoder-setup.exe` (lightweight build)
- `dist/transcoder-setup-full.exe` (full build)

**Note**: Requires NSIS to be installed and in PATH.

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

### Lightweight Build
- **Windows**: `dist/transcode-lightweight/transcode.exe` (directory with dependencies)
- **macOS/Linux**: `dist/transcode-lightweight/transcode` (directory with dependencies)
- **Size**: ~50-100 MB (OCR dependencies loaded on-demand)
- **OCR Support**: Requires system Python or will download dependencies on first use

### Full Build
- **Windows**: `dist/transcode/transcode.exe` (directory with all dependencies)
- **macOS/Linux**: `dist/transcode/transcode` (directory with all dependencies)
- **Size**: ~500 MB - 2 GB (includes all OCR dependencies)
- **OCR Support**: Fully self-contained

### Windows Installer

**Lightweight Installer:**
- **Output**: `dist/transcoder-setup.exe`
- **Size**: ~50-100 MB (lightweight build packaged)
- **Features**: 
  - Control Panel registration
  - PATH integration (optional)
  - Start Menu shortcuts
  - Uninstaller

**Full Installer:**
- **Output**: `dist/transcoder-setup-full.exe`
- **Size**: ~500 MB - 2 GB (full build packaged)
- **Features**: 
  - Control Panel registration
  - PATH integration (optional)
  - Start Menu shortcuts
  - Uninstaller
  - All OCR dependencies included (no system Python required)

All builds include:
- FFmpeg binaries
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

### Standalone Executable
The built executable can be distributed independently:
- No Python installation required on target system (for full build)
- No FFmpeg installation required on target system
- License documents placed next to the executable satisfy GPL/FFmpeg attribution requirements

### Windows Installer (Recommended)
The installer provides the best user experience:
- Professional installation process
- Appears in Windows Control Panel
- Easy uninstallation
- PATH integration for command-line access
- System-wide installation

**Lightweight Build Notes**:
- First OCR use may require downloading dependencies (~2GB for torch/easyocr)
- Requires system Python 3.10+ for dependency installation
- Dependencies are cached in `%LOCALAPPDATA%\transcoder\` after first use

## License Compliance Checklist

1. Keep `LICENSE`, `NOTICE.md`, and `THIRD_PARTY_LICENSES.md` alongside the built
   binary when you distribute it.
2. Use `transcode --about` to print the current version and license notice block
   for auditing.
3. Provide the full corresponding source for oneShotTranscoder (this repository)
   and direct recipients to the FFmpeg sources referenced in `NOTICE.md`.

**Note**: The executable is platform-specific. Build separate executables for each target platform.


