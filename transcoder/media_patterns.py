"""
Automatic and manual metadata detection for movie and TV filenames.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Pattern

from transcoder.exceptions import MetadataError

DEFAULT_FILENAME_PATTERN = "<Series Name> (<Year>) - S<season:2 digits>E<episode:2 digits> - <Episode Name> (<video specs>).mkv"

PATTERN_TOKEN_MAP: dict[str, str] = {
    "<Series Name>": r"(?P<series>.+?)",
    "<Movie Name>": r"(?P<movie>.+?)",
    "<Episode Name>": r"(?P<title>.+?)",
    "<Year>": r"(?P<year>\d{4})",
    "<season:2 digits>": r"(?P<season>\d{2})",
    "<season:1-2 digits>": r"(?P<season>\d{1,2})",
    "<episode:2 digits>": r"(?P<episode>\d{2})",
    "<episode:1-2 digits>": r"(?P<episode>\d{1,2})",
    "<Air Date>": r"(?P<air_date>\d{4}-\d{2}-\d{2})",
    "<video specs>": r"(?P<specs>.+?)",
}

RELEASE_TOKEN_BOUNDARY = re.compile(r"[ ._\-]+")
QUALITY_BREAK_WORDS = {
    "480P",
    "720P",
    "1080P",
    "2160P",
    "4K",
    "8K",
    "BLURAY",
    "BDRIP",
    "BRRIP",
    "WEB",
    "WEBRIP",
    "WEBDL",
    "WEB-DL",
    "HDR",
    "HDR10",
    "HDR10PLUS",
    "DOLBY",
    "DV",
    "ATMOS",
    "DDP5",
    "DDP5.1",
    "TRUEHD",
    "REMUX",
    "UHD",
    "IMAX",
    "AMZN",
    "HMAX",
    "MAX",
    "HULU",
    "NF",
    "NETFLIX",
    "H265",
    "X265",
    "H264",
    "X264",
    "AV1",
}
QUALITY_NUMBER_PATTERN = re.compile(r"^\d{3,4}P$", re.IGNORECASE)
EDITION_BLOCK_PATTERN = re.compile(r"{edition-(?P<edition>[^}]+)}", re.IGNORECASE)
YEAR_SUFFIX_PATTERN = re.compile(r"\((?P<year>\d{4})\)$")
YEAR_TRAILING_PATTERN = re.compile(r"(?P<year>\d{4})$")

SEASON_EPISODE_PATTERN = re.compile(r"(?i)S(?P<season>\d{1,2})E(?P<episode>\d{2})")
ALT_SEASON_EPISODE_PATTERN = re.compile(r"(?i)(?P<season>\d{1,2})x(?P<episode>\d{2})")
DATE_EPISODE_PATTERN = re.compile(r"(?P<air_date>\d{4}-\d{2}-\d{2})")
COMBINED_EPISODE_PATTERN = re.compile(r"(?<!\d)(?P<combined>\d{3})(?!\d)")
CODEC_PREFIX_PATTERN = re.compile(r"(?i)[XH][\d]{3}", re.IGNORECASE)
RESOLUTION_PATTERN = re.compile(r"(?i)\d{3,4}P", re.IGNORECASE)


class MediaType(str, Enum):
    MOVIE = "movie"
    TV_SHOW = "tv_show"


@dataclass(slots=True)
class EpisodeMetadata:
    series_name: str
    episode_title: str
    year: int | None
    season_number: int | None
    episode_number: int | None
    air_date: str | None = None
    pattern_name: str | None = None

    @property
    def episode_id(self) -> str | None:
        if self.season_number is None or self.episode_number is None:
            return None
        return f"S{self.season_number:02}E{self.episode_number:02}"


@dataclass(slots=True)
class MovieMetadata:
    movie_title: str
    year: int | None
    edition: str | None = None
    pattern_name: str | None = None


@dataclass(slots=True)
class MetadataDetection:
    media_type: MediaType
    metadata: EpisodeMetadata | MovieMetadata
    pattern_name: str
    matched: bool
    is_manual: bool


def build_pattern_regex(pattern: str) -> Pattern[str]:
    buffer: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "<":
            end_index = pattern.find(">", index)
            if end_index == -1:
                raise ValueError(f"Incomplete token in pattern near: {pattern[index:]}")
            token = pattern[index : end_index + 1]
            if token not in PATTERN_TOKEN_MAP:
                raise MetadataError(f"Unsupported token '{token}' in filename pattern.")
            buffer.append(PATTERN_TOKEN_MAP[token])
            index = end_index + 1
        else:
            buffer.append(re.escape(char))
            index += 1
    try:
        return re.compile("^" + "".join(buffer) + "$", re.IGNORECASE)
    except re.error as error:
        raise MetadataError(f"Invalid regex pattern: {error}") from error


def match_manual_pattern(source: Path, regex: Pattern[str]) -> MetadataDetection | None:
    match = regex.fullmatch(source.name)
    if not match:
        return None
    fields = match.groupdict()
    metadata: EpisodeMetadata | MovieMetadata | None = None
    media_type = MediaType.TV_SHOW
    if "season" in fields and "episode" in fields:
        season_value = _safe_int(fields.get("season"))
        episode_value = _safe_int(fields.get("episode"))
        series_name = _clean_component(fields.get("series") or fields.get("movie") or source.stem)
        episode_title = _clean_component(fields.get("title") or "")
        year_value = _safe_int(fields.get("year"))
        metadata = EpisodeMetadata(
            series_name=series_name,
            episode_title=episode_title or source.stem,
            year=year_value,
            season_number=season_value,
            episode_number=episode_value,
            air_date=fields.get("air_date"),
        )
    elif "movie" in fields or ("series" in fields and "year" in fields and "episode" not in fields):
        movie_name = _clean_component(fields.get("movie") or fields["series"])
        year_value = _safe_int(fields.get("year"))
        media_type = MediaType.MOVIE
        metadata = MovieMetadata(movie_title=movie_name, year=year_value)
    elif "title" in fields and "movie" not in fields:
        # Support episode title only patterns
        series_name = _clean_component(fields.get("series") or source.stem)
        metadata = EpisodeMetadata(
            series_name=series_name,
            episode_title=_clean_component(fields["title"]),
            year=_safe_int(fields.get("year")),
            season_number=_safe_int(fields.get("season")),
            episode_number=_safe_int(fields.get("episode")),
            air_date=fields.get("air_date"),
        )
    if metadata is None:
        return None
    return MetadataDetection(
        media_type=media_type,
        metadata=metadata,
        pattern_name="manual-pattern",
        matched=True,
        is_manual=True,
    )


def detect_metadata(source: Path, manual_pattern: str | None = None, media_type_override: str | None = None) -> MetadataDetection | None:
    if manual_pattern:
        custom_regex = build_pattern_regex(manual_pattern)
        manual_detection = match_manual_pattern(source, custom_regex)
        if manual_detection:
            # If type override is specified, enforce it
            if media_type_override:
                override_type = MediaType.TV_SHOW if media_type_override == "show" else MediaType.MOVIE
                if manual_detection.media_type != override_type:
                    # Force the override type, but keep the metadata
                    manual_detection.media_type = override_type
                    # If forcing TV show but we have movie metadata, create fallback episode metadata
                    if override_type == MediaType.TV_SHOW and isinstance(manual_detection.metadata, MovieMetadata):
                        manual_detection.metadata = EpisodeMetadata(
                            series_name=manual_detection.metadata.movie_title,
                            episode_title=manual_detection.metadata.movie_title,
                            year=manual_detection.metadata.year,
                            season_number=None,
                            episode_number=None,
                        )
                    # If forcing movie but we have episode metadata, create fallback movie metadata
                    elif override_type == MediaType.MOVIE and isinstance(manual_detection.metadata, EpisodeMetadata):
                        manual_detection.metadata = MovieMetadata(
                            movie_title=manual_detection.metadata.series_name,
                            year=manual_detection.metadata.year,
                        )
            return manual_detection
    
    # If type override is specified, force detection to that type
    if media_type_override:
        override_type = MediaType.TV_SHOW if media_type_override == "show" else MediaType.MOVIE
        if override_type == MediaType.TV_SHOW:
            episode_detection = _detect_tv_metadata(source.stem)
            if episode_detection:
                return MetadataDetection(
                    media_type=MediaType.TV_SHOW,
                    metadata=episode_detection,
                    pattern_name=episode_detection.pattern_name or "auto-tv",
                    matched=True,
                    is_manual=False,
                )
            # If TV detection failed but override is show, create fallback
            fallback_title = _clean_component(source.stem)
            return MetadataDetection(
                media_type=MediaType.TV_SHOW,
                metadata=EpisodeMetadata(
                    series_name=fallback_title,
                    episode_title=fallback_title,
                    year=None,
                    season_number=None,
                    episode_number=None,
                ),
                pattern_name="override-show",
                matched=False,
                is_manual=True,
            )
        else:  # override_type == MediaType.MOVIE
            movie_detection = _detect_movie_metadata(source.stem)
            if movie_detection:
                return MetadataDetection(
                    media_type=MediaType.MOVIE,
                    metadata=movie_detection,
                    pattern_name=movie_detection.pattern_name or "auto-movie",
                    matched=True,
                    is_manual=False,
                )
            # If movie detection failed but override is movie, create fallback
            fallback_title = _clean_component(source.stem)
            return MetadataDetection(
                media_type=MediaType.MOVIE,
                metadata=MovieMetadata(movie_title=fallback_title, year=None),
                pattern_name="override-movie",
                matched=False,
                is_manual=True,
            )
    
    auto_detection = auto_detect_metadata(source)
    return auto_detection


def auto_detect_metadata(source: Path) -> MetadataDetection | None:
    normalized_name = source.stem
    episode_detection = _detect_tv_metadata(normalized_name)
    if episode_detection:
        return MetadataDetection(
            media_type=MediaType.TV_SHOW,
            metadata=episode_detection,
            pattern_name=episode_detection.pattern_name or "auto-tv",
            matched=True,
            is_manual=False,
        )
    movie_detection = _detect_movie_metadata(normalized_name)
    if movie_detection:
        return MetadataDetection(
            media_type=MediaType.MOVIE,
            metadata=movie_detection,
            pattern_name=movie_detection.pattern_name or "auto-movie",
            matched=True,
            is_manual=False,
        )
    return None


def _detect_tv_metadata(name_without_ext: str) -> EpisodeMetadata | None:
    dash_pattern = re.compile(
        r"^(?P<series>.+?)\s*-\s*S(?P<season>\d{1,2})E(?P<episode>\d{2})\s*-\s*(?P<title>.+)$",
        re.IGNORECASE,
    )
    dash_match = dash_pattern.match(name_without_ext)
    if dash_match:
        return _build_episode_from_groups(
            dash_match.group("series"),
            dash_match.group("title"),
            dash_match.group("season"),
            dash_match.group("episode"),
            pattern_name="tv_dash_title",
        )

    standard_match = SEASON_EPISODE_PATTERN.search(name_without_ext)
    if standard_match:
        series_part = name_without_ext[: standard_match.start()]
        suffix_part = name_without_ext[standard_match.end() :]
        return _build_episode_from_parts(
            series_part,
            suffix_part,
            standard_match.group("season"),
            standard_match.group("episode"),
            pattern_name="tv_standard",
        )

    alt_match = ALT_SEASON_EPISODE_PATTERN.search(name_without_ext)
    if alt_match:
        series_part = name_without_ext[: alt_match.start()]
        suffix_part = name_without_ext[alt_match.end() :]
        return _build_episode_from_parts(
            series_part,
            suffix_part,
            alt_match.group("season"),
            alt_match.group("episode"),
            pattern_name="tv_alt_1x",
        )

    combined_match = COMBINED_EPISODE_PATTERN.search(name_without_ext)
    if combined_match:
        combined_value = combined_match.group("combined")
        match_start = combined_match.start()
        match_end = combined_match.end()
        
        # Check if this is a codec indicator (X265, H265, X264, H264, etc.)
        if match_start > 0:
            preceding_char = name_without_ext[match_start - 1].upper()
            if preceding_char in ("X", "H"):
                # This is likely a codec indicator, skip it
                combined_match = None
        
        # Check if this is part of a resolution (1080P, 2160P, etc.)
        if combined_match and match_end < len(name_without_ext):
            following_char = name_without_ext[match_end].upper()
            if following_char == "P":
                # This is part of a resolution, skip it
                combined_match = None
        
        # Check if this is a year (1900-2099 range)
        if combined_match:
            year_value = int(combined_value)
            if 1900 <= year_value <= 2099:
                # This is likely a year, skip it
                combined_match = None
        
        if combined_match:
            season_value = combined_value[0]
            episode_value = combined_value[1:]
            series_part = name_without_ext[: match_start]
            suffix_part = name_without_ext[match_end :]
            return _build_episode_from_parts(
                series_part,
                suffix_part,
                season_value,
                episode_value,
                pattern_name="tv_three_digit",
            )

    date_match = DATE_EPISODE_PATTERN.search(name_without_ext)
    if date_match:
        series_part = name_without_ext[: date_match.start()]
        suffix_part = name_without_ext[date_match.end() :]
        episode_metadata = _build_episode_from_parts(
            series_part,
            suffix_part,
            season_value=None,
            episode_value=None,
            pattern_name="tv_airdate",
        )
        if episode_metadata:
            episode_metadata.air_date = date_match.group("air_date")
            year_value = _safe_int(date_match.group("air_date")[:4])
            episode_metadata.year = year_value
        return episode_metadata

    return None


def _detect_movie_metadata(name_without_ext: str) -> MovieMetadata | None:
    paren_pattern = re.compile(
        r"^(?P<title>.+?)\s*\((?P<year>\d{4})\)(?:[ ._\-]+(?P<rest>.+))?$",
        re.IGNORECASE,
    )
    paren_match = paren_pattern.match(name_without_ext)
    if paren_match:
        return _build_movie_from_groups(
            paren_match.group("title"),
            paren_match.group("year"),
            paren_match.group("rest"),
            pattern_name="movie_paren_year",
        )

    dotted_pattern = re.compile(
        r"^(?P<title>.+)[ ._\-](?P<year>\d{4})(?:[ ._\-]+(?P<rest>.+))?$",
        re.IGNORECASE,
    )
    dotted_match = dotted_pattern.match(name_without_ext)
    if dotted_match:
        return _build_movie_from_groups(
            dotted_match.group("title"),
            dotted_match.group("year"),
            dotted_match.group("rest"),
            pattern_name="movie_dotted_year",
        )

    return None


def _build_episode_from_groups(
    raw_series: str,
    raw_title: str,
    season_value: str | None,
    episode_value: str | None,
    *,
    pattern_name: str,
) -> EpisodeMetadata:
    series_name, year_value = _split_trailing_year(raw_series)
    cleaned_series = _clean_component(series_name)
    cleaned_title = _clean_episode_title(raw_title)
    metadata = EpisodeMetadata(
        series_name=cleaned_series,
        episode_title=cleaned_title or cleaned_series,
        year=year_value,
        season_number=_safe_int(season_value),
        episode_number=_safe_int(episode_value),
        pattern_name=pattern_name,
    )
    return metadata


def _build_episode_from_parts(
    series_part: str,
    suffix_part: str,
    season_value: str | None,
    episode_value: str | None,
    *,
    pattern_name: str,
) -> EpisodeMetadata:
    series_name, year_value = _split_trailing_year(series_part)
    cleaned_series = _clean_component(series_name)
    cleaned_title = _clean_episode_title(suffix_part)
    metadata = EpisodeMetadata(
        series_name=cleaned_series or suffix_part or "",
        episode_title=cleaned_title or cleaned_series or suffix_part or "",
        year=year_value,
        season_number=_safe_int(season_value),
        episode_number=_safe_int(episode_value),
        pattern_name=pattern_name,
    )
    return metadata


def _build_movie_from_groups(
    raw_title: str,
    raw_year: str,
    rest: str | None,
    *,
    pattern_name: str,
) -> MovieMetadata:
    cleaned_title = _clean_component(raw_title)
    edition = None
    if rest:
        edition_match = EDITION_BLOCK_PATTERN.search(rest)
        if edition_match:
            edition = edition_match.group("edition").strip()
    metadata = MovieMetadata(
        movie_title=cleaned_title,
        year=_safe_int(raw_year),
        edition=edition,
        pattern_name=pattern_name,
    )
    return metadata


def _clean_component(value: str) -> str:
    cleaned = value or ""
    cleaned = re.sub(r"\[.*?\]", "", cleaned)
    cleaned = cleaned.replace("_", " ").replace(".", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" -_.")
    cleaned = re.sub(r"-[A-Za-z0-9]+$", "", cleaned).strip()
    return cleaned


def _clean_episode_title(value: str) -> str:
    if not value:
        return ""
    value = value.replace("(", " ").replace(")", " ")
    value = re.sub(r"\[.*?\]", "", value)
    tokens = RELEASE_TOKEN_BOUNDARY.split(value)
    kept_tokens: list[str] = []
    for token in tokens:
        if not token:
            continue
        uppercase_token = token.upper()
        if uppercase_token in QUALITY_BREAK_WORDS or QUALITY_NUMBER_PATTERN.match(token):
            break
        kept_tokens.append(token)
    title = " ".join(kept_tokens).strip()
    return title


def _split_trailing_year(value: str) -> tuple[str, int | None]:
    if not value:
        return "", None
    match = YEAR_SUFFIX_PATTERN.search(value.strip())
    if match:
        year_value = int(match.group("year"))
        trimmed = value[: match.start()].strip(" -_.")
        return trimmed, year_value
    match = YEAR_TRAILING_PATTERN.search(value.strip())
    if match:
        year_value = int(match.group("year"))
        trimmed = value[: match.start()].strip(" -_.")
        return trimmed, year_value
    return value, None


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

