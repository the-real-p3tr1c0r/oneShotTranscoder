"""Bitmap subtitle conversion to text using OCR."""

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

import pytesseract
from babelfish import Language as BabelLanguage
from pgsrip.api import rip as rip_pgs
from pgsrip.sup import Sup as SupSubtitle

DEFAULT_TESSERACT_LANGUAGE = "eng"

IMAGE_BASED_SUBTITLE_CODECS = {
    "hdmv_pgs_subtitle",
    "dvd_subtitle",
    "xsub",
    "pgssub",
}


@dataclass
class SubtitleStreamInfo:
    """Information about a subtitle stream."""
    absolute_index: int
    type_index: int
    codec_name: str
    language: Optional[str]
    title: Optional[str]

    @property
    def is_image_based(self) -> bool:
        """Check if subtitle is image-based."""
        return self.codec_name.lower() in IMAGE_BASED_SUBTITLE_CODECS


@dataclass
class GeneratedSubtitle:
    """Generated text subtitle from OCR."""
    path: Path
    language: Optional[str]
    title: Optional[str]


ISO639_BIBLIOGRAPHIC_TO_TERMINOLOGICAL = {
    "alb": "sqi",
    "arm": "hye",
    "baq": "eus",
    "bur": "mya",
    "chi": "zho",
    "cze": "ces",
    "dut": "nld",
    "fre": "fra",
    "ger": "deu",
    "gre": "ell",
    "ice": "isl",
    "mac": "mkd",
    "mao": "mri",
    "may": "msa",
    "rum": "ron",
    "slo": "slk",
    "tib": "bod",
    "wel": "cym",
}

_TESSERACT_LANG_CACHE: Optional[Set[str]] = None


def resolve_tesseract_path() -> str:
    """
    Locate Tesseract executable.
    
    Returns:
        Path to tesseract executable
    
    Raises:
        RuntimeError: If Tesseract not found
    """
    import os
    
    override = os.environ.get("TESSERACT_PATH")
    candidates: List[Path] = []
    if override:
        candidates.append(Path(override))

    candidates.append(Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"))

    which = shutil.which("tesseract")
    if which:
        candidates.append(Path(which))

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    raise RuntimeError(
        "Tesseract executable not found. Install it or set TESSERACT_PATH."
    )


def list_tesseract_languages(tesseract_bin: str) -> Set[str]:
    """
    List available Tesseract languages.
    
    Args:
        tesseract_bin: Path to tesseract executable
    
    Returns:
        Set of available language codes
    
    Raises:
        RuntimeError: If unable to list languages
    """
    global _TESSERACT_LANG_CACHE
    if _TESSERACT_LANG_CACHE is not None:
        return _TESSERACT_LANG_CACHE

    try:
        result = subprocess.run(
            [tesseract_bin, "--list-langs"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "Unable to list Tesseract languages; ensure Tesseract is installed correctly."
        ) from exc

    langs = {
        line.strip().lower()
        for line in (result.stdout or "").splitlines()
        if line.strip() and not line.lower().startswith("list of available languages")
    }
    if not langs:
        raise RuntimeError(
            "No Tesseract languages detected. Install language packs in "
            "C:\\Program Files\\Tesseract-OCR\\tessdata and rerun."
        )
    _TESSERACT_LANG_CACHE = langs
    return langs


def normalize_language_hint(language_code: Optional[str]) -> Optional[str]:
    """
    Normalize language code to Tesseract format.
    
    Args:
        language_code: Language code (ISO 639-1, ISO 639-2, etc.)
    
    Returns:
        Normalized language code or None
    """
    if not language_code:
        return None

    code = language_code.lower()
    code = ISO639_BIBLIOGRAPHIC_TO_TERMINOLOGICAL.get(code, code)

    for resolver in (BabelLanguage.fromietf, BabelLanguage):
        try:
            lang = resolver(code)
            alpha3 = getattr(lang, "alpha3", None)
            if alpha3:
                return alpha3.lower()
        except Exception:
            continue

    if len(code) == 3 and code.isalpha():
        return code

    return None


def normalize_language_tag(code: Optional[str]) -> Optional[str]:
    """
    Normalize language tag for metadata.
    
    Args:
        code: Language code
    
    Returns:
        Normalized language code or None
    """
    if not code:
        return None

    for resolver in (BabelLanguage.fromietf, BabelLanguage):
        try:
            return str(resolver(code))
        except Exception:
            continue

    return code.lower()


def select_tesseract_language(
    stream_language: Optional[str], available_languages: Set[str]
) -> Optional[str]:
    """
    Select appropriate Tesseract language for subtitle stream.
    
    Args:
        stream_language: Language code from subtitle stream
        available_languages: Set of available Tesseract languages
    
    Returns:
        Selected language code or None if not available
    """
    tess_code = normalize_language_hint(stream_language)
    if tess_code and tess_code in available_languages:
        return tess_code

    if not stream_language and DEFAULT_TESSERACT_LANGUAGE in available_languages:
        return DEFAULT_TESSERACT_LANGUAGE

    return None


def probe_subtitle_streams(media: Path) -> List[SubtitleStreamInfo]:
    """
    Probe subtitle streams from media file.
    
    Args:
        media: Path to media file
    
    Returns:
        List of SubtitleStreamInfo objects
    """
    import json
    
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "s",
        "-show_entries",
        "stream=index,codec_name,codec_type:stream_tags=language,title",
        "-of",
        "json",
        str(media),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout or "{}")
    streams = []
    type_counter = -1
    for stream in payload.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        type_counter += 1
        tags = stream.get("tags") or {}
        streams.append(
            SubtitleStreamInfo(
                absolute_index=int(stream["index"]),
                type_index=type_counter,
                codec_name=stream.get("codec_name", "").lower(),
                language=normalize_language_tag(tags.get("language")),
                title=tags.get("title"),
            )
        )
    return streams


def extract_subtitle_sup(
    media: Path,
    stream: SubtitleStreamInfo,
    temp_dir: Path,
) -> Path:
    """
    Extract SUP file from media for bitmap subtitle stream.
    
    Args:
        media: Path to media file
        stream: SubtitleStreamInfo for the stream to extract
        temp_dir: Temporary directory for output
    
    Returns:
        Path to extracted SUP file
    
    Raises:
        RuntimeError: If codec is not supported
    """
    if stream.codec_name != "hdmv_pgs_subtitle":
        raise RuntimeError(
            f"Unsupported image subtitle codec '{stream.codec_name}' for OCR."
        )

    language_code = (stream.language or "und").lower()
    filename = f"{media.stem}.track{stream.type_index}.{language_code}.sup"
    sup_path = temp_dir / filename
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(media),
            "-map",
            f"0:s:{stream.type_index}",
            "-c",
            "copy",
            str(sup_path),
        ],
        check=True,
    )
    return sup_path


def rip_sup_to_srt(sup_path: Path) -> Path:
    """
    Convert SUP file to SRT using OCR.
    
    Args:
        sup_path: Path to SUP file
    
    Returns:
        Path to generated SRT file
    
    Raises:
        RuntimeError: If OCR fails
    """
    count = rip_pgs(SupSubtitle(str(sup_path)))
    srt_path = sup_path.with_suffix(".srt")
    if count == 0 or not srt_path.exists():
        raise RuntimeError(f"OCR failed for {sup_path.name}")
    return srt_path


def convert_bitmap_subtitles(
    media: Path,
    streams: List[SubtitleStreamInfo],
    available_languages: Set[str],
) -> tuple[List[GeneratedSubtitle], Optional[Path]]:
    """
    Convert bitmap subtitle streams to text subtitles using OCR.
    
    Args:
        media: Path to media file
        streams: List of bitmap subtitle streams to convert
        available_languages: Set of available Tesseract languages
    
    Returns:
        Tuple of (list of GeneratedSubtitle, temp directory path)
    """
    if not streams:
        return [], None

    temp_dir = Path(tempfile.mkdtemp(prefix=f"{media.stem}_subs_"))
    generated: List[GeneratedSubtitle] = []
    try:
        for stream in streams:
            tess_lang = select_tesseract_language(stream.language, available_languages)
            if not tess_lang:
                expected_code = (
                    normalize_language_hint(stream.language)
                    or (stream.language or "und")
                )
                print(
                    f"Skipping bitmap subtitle track {stream.type_index} "
                    f"({stream.language or 'und'}) — missing Tesseract language data "
                    f"(install '{expected_code}.traineddata')."
                )
                continue
            sup_path = extract_subtitle_sup(media, stream, temp_dir)
            srt_path = rip_sup_to_srt(sup_path)
            if sup_path.exists():
                sup_path.unlink(missing_ok=True)
            generated.append(
                GeneratedSubtitle(
                    path=srt_path,
                    language=stream.language,
                    title=stream.title or f"{(stream.language or 'und').upper()} OCR",
                )
            )
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return generated, temp_dir

