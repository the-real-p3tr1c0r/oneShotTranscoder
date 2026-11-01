# Project

## Identity

- Name: oneShotTranscoder
- Status: dormant
- Scope: personal
- Profile: app (manifest+memory overlay)
- Manifest: `project.yaml`
- Code remote: https://github.com/the-real-p3tr1c0r/oneShotTranscoder

## Purpose

Transcodes MKV files to Apple TV-compatible MP4 format with automatic hardware acceleration, subtitle conversion (OCR for bitmap formats), and metadata extraction/tagging.

## Stack & Architecture

- Language: Python 3
- Core Dependencies: FFmpeg, ffprobe, EasyOCR, Mutagen
- Packaging: PyInstaller, Inno Setup (Windows), PyPI/wheel
- Configuration: `pyproject.toml`, `setup.py`, spec files

## Constraints

- Standalone executable generation for macOS and Windows.
- Apple TV playback compatibility (video/audio codecs, container, mp4 tags).
- Dormant repository: maintain stability without introducing breaking dependencies.
