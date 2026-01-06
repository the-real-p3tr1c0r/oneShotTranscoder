# Windows Installer Guide

This document explains how to build and use the Windows installer for Transcoder.

## Building the Installer

### Prerequisites

1. **NSIS** (Nullsoft Scriptable Install System)
   - Download from: https://nsis.sourceforge.io/
   - Install and ensure `makensis.exe` is in your PATH
   - Verify installation: `makensis /VERSION`

2. **Build the executable(s) first**:
   ```bash
   # For lightweight installer
   python build.py --mode lightweight
   
   # For full installer
   python build.py --mode full
   
   # For both installers
   python build.py --mode both
   ```

3. **Build the installer(s)**:
   ```bash
   # Lightweight installer
   python build.py --mode lightweight --installer
   
   # Full installer
   python build.py --mode full --installer
   
   # Both installers
   python build.py --mode both --installer
   ```

### Manual Installer Build

If you prefer to build the installer manually:

**Lightweight installer:**
```bash
makensis /DBUILD_MODE=lightweight installer.nsi
```

**Full installer:**
```bash
makensis /DBUILD_MODE=full installer.nsi
```

The installers will be created at:
- `dist\transcoder-setup.exe` (lightweight)
- `dist\transcoder-setup-full.exe` (full)

## Installer Features

The NSIS installer provides:

1. **Professional Installation**
   - Standard Windows installer interface
   - License agreement display
   - Component selection (PATH, shortcuts)
   - Progress indicators

2. **System Integration**
   - Installs to `C:\Program Files\Transcoder\`
   - Registers in Windows Control Panel (Apps & Features)
   - Optional: Adds to system PATH
   - Optional: Creates Start Menu shortcuts

3. **Uninstaller**
   - Complete removal of installed files
   - Removes PATH entries
   - Removes registry entries
   - Removes Start Menu shortcuts

4. **Version Information**
   - Displays version in Control Panel
   - Includes publisher information
   - Links to project URL

## Installation Components

The installer includes three optional components:

1. **Core Application** (Required)
   - The transcoder executable and dependencies
   - FFmpeg binaries
   - License files
   - **Lightweight**: OCR dependencies loaded on-demand (requires system Python)
   - **Full**: All OCR dependencies included (self-contained)

2. **Add to PATH** (Optional)
   - Adds `C:\Program Files\Transcoder\` to system PATH
   - Allows calling `transcode` from any command prompt
   - Uses `transcode.bat` wrapper script

3. **Start Menu Shortcuts** (Optional)
   - Creates shortcuts in Start Menu
   - Provides easy access to the application

## Usage After Installation

### Command Line

If PATH was added during installation:
```cmd
transcode input.mkv
```

If PATH was not added:
```cmd
"C:\Program Files\Transcoder\transcode.exe" input.mkv
```

Or use the batch wrapper:
```cmd
"C:\Program Files\Transcoder\transcode.bat" input.mkv
```

### OCR Dependencies

**Lightweight Installer:**
The lightweight build requires OCR dependencies (torch, easyocr, opencv) to be installed on first use:

1. **Automatic Installation** (if system Python is available):
   - Dependencies are downloaded and installed automatically
   - Cached in `%LOCALAPPDATA%\transcoder\`

2. **Manual Installation** (if system Python is not found):
   ```cmd
   pip install torch torchvision easyocr opencv-python
   ```

**Full Installer:**
The full build includes all OCR dependencies:
- No system Python required
- OCR works immediately after installation
- Larger installer size (~500 MB - 2 GB)

## Uninstallation

### Via Control Panel

1. Open **Settings** → **Apps** → **Apps & Features**
2. Find "Transcoder"
3. Click **Uninstall**

### Via Uninstaller

1. Navigate to `C:\Program Files\Transcoder\`
2. Run `uninstall.exe`

The uninstaller will:
- Remove all installed files
- Remove PATH entries (if added)
- Remove Start Menu shortcuts
- Remove registry entries

## Troubleshooting

### Installer Build Fails

**Error**: "NSIS compiler (makensis) not found"
- **Solution**: Install NSIS and ensure it's in PATH
- Verify: `makensis /VERSION` should show version number

**Error**: "Lightweight build not found"
- **Solution**: Build lightweight version first: `python build.py --mode lightweight`

### Installation Issues

**Error**: "Access Denied" during installation
- **Solution**: Run installer as Administrator (right-click → Run as administrator)

**Error**: PATH not updated
- **Solution**: 
  - Restart command prompt after installation
  - Or manually add to PATH via System Properties

### Runtime Issues

**Error**: "Cannot find system Python" when using OCR
- **Solution**: 
  - Install Python 3.10+ from python.org
  - Or use the full build which includes all dependencies

## Customization

### Modifying Installer Script

Edit `installer.nsi` to customize:
- Installation directory
- Application name and version
- License file
- Icons
- Additional components

### Version Updates

Update version in:
1. `transcoder/__init__.py` - `__version__`
2. `setup.py` - `version` in setup()
3. `installer.nsi` - `!define VERSION`

Then rebuild installer.

## Distribution

The installer (`transcoder-setup.exe`) can be distributed independently:
- No additional files required
- Self-contained installation package
- Includes all license notices
- Suitable for distribution via website, GitHub releases, etc.

## License Compliance

The installer includes:
- `LICENSE` - GPL-3.0-or-later
- `NOTICE.md` - FFmpeg attribution
- `THIRD_PARTY_LICENSES.md` - Third-party library licenses

These are installed alongside the application and satisfy GPL/FFmpeg distribution requirements.

