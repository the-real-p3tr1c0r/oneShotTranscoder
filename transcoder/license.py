"""License, version, and attribution helpers for the CLI."""

from __future__ import annotations

from importlib import metadata

PACKAGE_NAME = "transcoder"
PROJECT_URL = "https://github.com/the-real-p3tr1c0r/oneShotTranscoder"
LICENSE_NAME = "GPL-3.0-or-later"

FFMPEG_SOURCES = {
    "Windows": "BtbN FFmpeg Builds (https://github.com/BtbN/FFmpeg-Builds)",
    "macOS": "evermeet.cx FFmpeg distributions (https://evermeet.cx/ffmpeg)",
    "Linux": "johnvansickle.com static builds (https://johnvansickle.com/ffmpeg/)",
}

THIRD_PARTY_LIBRARIES = [
    ("easyocr", "Apache-2.0", "https://github.com/JaidedAI/EasyOCR"),
    ("opencv-python", "Apache-2.0", "https://github.com/opencv/opencv-python"),
    ("babelfish", "BSD-3-Clause", "https://github.com/Diaoul/babelfish"),
    ("pgsrip", "MIT", "https://pypi.org/project/pgsrip/"),
    ("torch / torchvision (conditional)", "BSD-3-Clause", "https://pytorch.org/"),
]


def get_version() -> str:
    """Return the installed package version using importlib metadata."""
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        from . import __version__

        return __version__


def format_about_text() -> str:
    """Return a human-readable about/attribution message."""
    version = get_version()
    third_party_lines = "\n".join(
        f"  - {name}: {license_name} ({url})"
        for name, license_name, url in THIRD_PARTY_LIBRARIES
    )
    ffmpeg_lines = "\n".join(
        f"  - {platform}: {source}" for platform, source in FFMPEG_SOURCES.items()
    )
    return (
        f"oneShotTranscoder {version}\n"
        f"License: {LICENSE_NAME}\n"
        f"Project: {PROJECT_URL}\n"
        "\n"
        "This executable bundles FFmpeg and ffprobe binaries provided by:\n"
        f"{ffmpeg_lines}\n"
        "Corresponding FFmpeg source code can be retrieved from the same locations.\n"
        "No local modifications are applied.\n"
        "\n"
        "Third-party Python dependencies:\n"
        f"{third_party_lines}\n"
        "\n"
        "See NOTICE.md and THIRD_PARTY_LICENSES.md for the complete text of these notices.\n"
        "Refer to LICENSE for the full GPL terms."
    )
















