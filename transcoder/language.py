"""Language code normalization utilities.

Copyright (C) 2025 oneShotTranscoder Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from babelfish import Language as BabelLanguage
else:
    try:
        from babelfish import Language as BabelLanguage
    except ImportError:
        BabelLanguage = None

from transcoder.constants import DEFAULT_EASYOCR_LANGUAGE


def normalize_language_tag(code: str | None) -> str | None:
    """
    Normalize language tag to ISO 639-2.
    
    Args:
        code: Language code (ISO 639-1, ISO 639-2, etc.)
    
    Returns:
        Normalized ISO 639-2 code or None
    """
    if not code:
        return None

    code_lower = code.lower().strip()
    
    # ISO 639-2 bibliographic to terminological mapping
    iso6392_map = {
        "fre": "fra",  # French bibliographic -> terminological
        "chi": "zho",  # Chinese bibliographic -> terminological
        "cze": "ces",  # Czech bibliographic -> terminological
        "dut": "nld",  # Dutch bibliographic -> terminological
        "ger": "deu",  # German bibliographic -> terminological
        "gre": "ell",  # Greek bibliographic -> terminological
        "ice": "isl",  # Icelandic bibliographic -> terminological
        "mac": "mkd",  # Macedonian bibliographic -> terminological
        "rum": "ron",  # Romanian bibliographic -> terminological
        "slo": "slk",  # Slovak bibliographic -> terminological
    }
    
    # Check if it's a known variation
    if code_lower in iso6392_map:
        return iso6392_map[code_lower]
    
    # If already 3-letter, validate with babelfish if available
    if len(code_lower) == 3 and code_lower.isalpha():
        if BabelLanguage:
            try:
                lang = BabelLanguage(code_lower)
                iso6392 = getattr(lang, 'alpha3', None)
                if iso6392 and len(iso6392) == 3:
                    return iso6392.lower()
                # If babelfish recognizes it but no alpha3, use the code as-is
                return code_lower
            except Exception:
                # If babelfish doesn't recognize it, assume it's already ISO 639-2
                return code_lower
        return code_lower

    # Try to resolve 2-letter codes using babelfish
    if len(code_lower) == 2 and code_lower.isalpha():
        if BabelLanguage:
            try:
                lang = BabelLanguage.fromietf(code_lower)
                iso6392 = getattr(lang, 'alpha3', None)
                if iso6392 and len(iso6392) == 3:
                    return iso6392.lower()
            except Exception:
                pass
    
    # Try to resolve using babelfish directly
    if BabelLanguage:
        for resolver in (BabelLanguage.fromietf, BabelLanguage):
            try:
                lang = resolver(code)
                iso6392 = getattr(lang, 'alpha3', None)
                if iso6392 and len(iso6392) == 3:
                    return iso6392.lower()
            except Exception:
                continue
    
    return None


def easyocr_to_iso6392(easyocr_code: str) -> str | None:
    """
    Convert EasyOCR language code back to ISO 639-2.
    
    Args:
        easyocr_code: EasyOCR language code (e.g., 'en', 'fr', 'ch_sim')
    
    Returns:
        ISO 639-2 code or None
    """
    if not easyocr_code:
        return None
    
    # Map EasyOCR codes to ISO 639-2
    easyocr_to_iso6392_map = {
        "en": "eng",
        "fr": "fra",
        "es": "spa",
        "de": "deu",
        "it": "ita",
        "ja": "jpn",
        "ko": "kor",
        "pt": "por",
        "ru": "rus",
        "ch_sim": "zho",
        "ch_tra": "zho",
    }
    
    return easyocr_to_iso6392_map.get(easyocr_code.lower())


def iso6392_to_iso6391(iso6392_code: str | None) -> str | None:
    """
    Convert ISO 639-2 code to ISO 639-1 (2-letter) code.
    Apple TV/macOS TV app prefers ISO 639-1 codes for subtitle language metadata.
    
    Args:
        iso6392_code: ISO 639-2 code (3-letter)
    
    Returns:
        ISO 639-1 code (2-letter) or None
    """
    if not iso6392_code:
        return None
    
    iso6392_lower = iso6392_code.lower().strip()
    
    # Try using babelfish to convert
    if BabelLanguage:
        try:
            lang = BabelLanguage(iso6392_lower)
            alpha2 = getattr(lang, 'alpha2', None)
            if alpha2:
                return alpha2.lower()
        except Exception:
            pass
    
    # Fallback mapping for common codes
    iso6392_to_iso6391_map = {
        "eng": "en",
        "fra": "fr",
        "fre": "fr",  # bibliographic variant
        "spa": "es",
        "deu": "de",
        "ger": "de",  # bibliographic variant
        "ita": "it",
        "jpn": "ja",
        "kor": "ko",
        "por": "pt",
        "rus": "ru",
        "zho": "zh",
        "chi": "zh",  # bibliographic variant
        "ces": "cs",
        "cze": "cs",  # bibliographic variant
        "nld": "nl",
        "dut": "nl",  # bibliographic variant
        "ell": "el",
        "gre": "el",  # bibliographic variant
        "isl": "is",
        "ice": "is",  # bibliographic variant
        "mkd": "mk",
        "mac": "mk",  # bibliographic variant
        "ron": "ro",
        "rum": "ro",  # bibliographic variant
        "slk": "sk",
        "slo": "sk",  # bibliographic variant
    }
    
    return iso6392_to_iso6391_map.get(iso6392_lower)


def normalize_language_for_easyocr(language_code: str | None) -> str | None:
    """
    Convert language code to EasyOCR format (ISO 639-1).
    
    Args:
        language_code: Language code (ISO 639-1, ISO 639-2, etc.)
    
    Returns:
        ISO 639-1 code for EasyOCR or None
    """
    if not language_code:
        return None

    # Handle common language code variations
    language_code = language_code.lower().strip()
    
    # Map common 3-letter codes to EasyOCR language codes
    # Note: EasyOCR uses specific codes, not always ISO 639-1
    lang_map = {
        "fre": "fr",  # French
        "fra": "fr",
        "chi": "ch_sim",  # Chinese (Simplified) - EasyOCR uses ch_sim/ch_tra
        "zho": "ch_sim",
        "eng": "en",
        "spa": "es",
        "deu": "de",
        "ger": "de",
        "ita": "it",
        "jpn": "ja",
        "kor": "ko",
        "por": "pt",
        "rus": "ru",
    }
    
    if language_code in lang_map:
        return lang_map[language_code]

    if BabelLanguage:
        for resolver in (BabelLanguage.fromietf, BabelLanguage):
            try:
                lang = resolver(language_code)
                alpha2 = getattr(lang, "alpha2", None)
                if alpha2:
                    return alpha2.lower()
            except Exception:
                continue

    # If already 2-letter, return as-is
    if len(language_code) == 2 and language_code.isalpha():
        return language_code.lower()

    return None

