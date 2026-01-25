"""Metadata utilities bridging the detection layer and ffmpeg tag generation."""

from __future__ import annotations

from pathlib import Path
from typing import Pattern

from transcoder.media_patterns import (
    DEFAULT_FILENAME_PATTERN,
    EpisodeMetadata,
    MediaType,
    MetadataDetection,
    MovieMetadata,
    PATTERN_TOKEN_MAP,
    build_pattern_regex,
    detect_metadata,
    match_manual_pattern,
)


def parse_episode_metadata(source: Path, regex: Pattern[str]) -> EpisodeMetadata | None:
    detection = match_manual_pattern(source, regex)
    if not detection:
        return None
    if detection.media_type != MediaType.TV_SHOW:
        return None
    episode = detection.metadata
    if not isinstance(episode, EpisodeMetadata):
        return None
    return episode


def detect_media_metadata(source: Path, filename_pattern: str | None = None, media_type_override: str | None = None) -> MetadataDetection | None:
    return detect_metadata(source, filename_pattern, media_type_override)


def apply_source_metadata(metadata: EpisodeMetadata, format_tags: dict[str, str]) -> EpisodeMetadata:
    """
    Apply format-level tags from the source file, overriding detected values.
    """
    title = format_tags.get("title")
    if title:
        metadata.episode_title = title
        metadata.episode_title_missing = False

    show = format_tags.get("show")
    if show:
        metadata.series_name = show

    date_tag = format_tags.get("date")
    if date_tag:
        air_date, year_value = _parse_date_tag(date_tag)
        if air_date:
            metadata.air_date = air_date
        if year_value is not None:
            metadata.year = year_value
            metadata.show_year = year_value

    season_tag = format_tags.get("season_number")
    if season_tag is not None:
        season_value = _safe_int(season_tag)
        if season_value is not None:
            metadata.season_number = season_value

    episode_tag = format_tags.get("episode_sort")
    if episode_tag is not None:
        episode_value = _safe_int(episode_tag)
        if episode_value is not None:
            metadata.episode_number = episode_value

    genre_tag = format_tags.get("genre")
    if genre_tag:
        metadata.genres = _split_genres(genre_tag)

    network_tag = format_tags.get("network") or format_tags.get("channel")
    if network_tag:
        metadata.network_name = network_tag

    status_tag = format_tags.get("status")
    if status_tag:
        metadata.show_status = status_tag

    return metadata


def metadata_to_ffmpeg_args(metadata: EpisodeMetadata | MovieMetadata) -> list[str]:
    """
    Convert movie or TV metadata into ffmpeg CLI arguments.
    """
    if isinstance(metadata, MovieMetadata):
        args: list[str] = ["-metadata", f"title={metadata.movie_title}"]
        if metadata.year:
            args.extend(["-metadata", f"date={metadata.year}"])
        if metadata.edition:
            args.extend(["-metadata", f"description={metadata.edition}"])
        return args
    args = [
        "-metadata",
        f"title={metadata.episode_title}",
        "-metadata",
        f"show={metadata.series_name}",
    ]
    if metadata.air_date:
        args.extend(["-metadata", f"date={metadata.air_date}"])
    elif metadata.show_year:
        args.extend(["-metadata", f"date={metadata.show_year}"])
    elif metadata.year:
        args.extend(["-metadata", f"date={metadata.year}"])
    if metadata.genres:
        args.extend(["-metadata", f"genre={', '.join(metadata.genres)}"])
    if metadata.network_name:
        args.extend(["-metadata", f"network={metadata.network_name}"])
    if metadata.show_status:
        args.extend(["-metadata", f"status={metadata.show_status}"])
    if metadata.season_number is not None:
        args.extend(["-metadata", f"season_number={metadata.season_number}"])
    if metadata.episode_number is not None:
        args.extend(["-metadata", f"episode_sort={metadata.episode_number}"])
    return args


def _parse_date_tag(value: str) -> tuple[str | None, int | None]:
    cleaned = value.strip()
    if not cleaned:
        return None, None
    if "-" in cleaned:
        parts = cleaned.split("T", 1)[0]
        year_value = _safe_int(parts.split("-", 1)[0])
        return parts, year_value
    year_value = _safe_int(cleaned)
    return None, year_value


def _split_genres(value: str) -> list[str]:
    tokens = [token.strip() for token in value.replace(";", ",").split(",")]
    return [token for token in tokens if token]


def _safe_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return None

