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
    if metadata.year:
        args.extend(["-metadata", f"date={metadata.year}"])
    if metadata.season_number is not None:
        args.extend(["-metadata", f"season_number={metadata.season_number}"])
    if metadata.episode_number is not None:
        args.extend(["-metadata", f"episode_sort={metadata.episode_number}"])
    return args

