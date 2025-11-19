"""Metadata extraction from filenames.

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

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Pattern

DEFAULT_FILENAME_PATTERN = "<Series Name> (<Year>) - S<season:2 digits>E<episode:2 digits> - <Episode Name> (<video specs>).mkv"

PATTERN_TOKEN_MAP: dict[str, str] = {
    "<Series Name>": r"(?P<series>.+?)",
    "<Year>": r"(?P<year>\d{4})",
    "<season:2 digits>": r"(?P<season>\d{2})",
    "<episode:2 digits>": r"(?P<episode>\d{2})",
    "<season:1-2 digits>": r"(?P<season>\d{1,2})",
    "<episode:1-2 digits>": r"(?P<episode>\d{1,2})",
    "<Episode Name>": r"(?P<title>.+?)",
    "<video specs>": r"(?P<specs>.+?)",
}


@dataclass
class EpisodeMetadata:
    """Episode metadata extracted from filename."""
    series_name: str
    episode_title: str
    year: int
    season_number: int
    episode_number: int

    @property
    def episode_id(self) -> str:
        """Get episode ID in format S01E01."""
        return f"S{self.season_number:02}E{self.episode_number:02}"


def build_pattern_regex(pattern: str) -> Pattern[str]:
    """
    Build regex pattern from human-readable filename template.
    
    Args:
        pattern: Human-readable pattern with tokens like <Series Name>, <Year>, etc.
    
    Returns:
        Compiled regex pattern
    
    Raises:
        ValueError: If pattern contains unsupported tokens or is malformed
    """
    buffer: List[str] = []
    i = 0
    while i < len(pattern):
        if pattern[i] == "<":
            end = pattern.find(">", i)
            if end == -1:
                raise ValueError(f"Incomplete token in pattern near: {pattern[i:]}")
            token = pattern[i : end + 1]
            if token not in PATTERN_TOKEN_MAP:
                raise ValueError(f"Unsupported token '{token}' in filename pattern.")
            buffer.append(PATTERN_TOKEN_MAP[token])
            i = end + 1
        else:
            buffer.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(buffer) + "$", re.IGNORECASE)


def parse_episode_metadata(source: Path, regex: Pattern[str]) -> Optional[EpisodeMetadata]:
    """
    Parse episode metadata from filename using regex pattern.
    
    Args:
        source: Source file path
        regex: Compiled regex pattern from build_pattern_regex()
    
    Returns:
        EpisodeMetadata if pattern matches, None otherwise
    """
    match = regex.fullmatch(source.name)
    if not match:
        return None
    
    groups = match.groupdict()
    try:
        return EpisodeMetadata(
            series_name=groups["series"].strip(),
            episode_title=groups["title"].strip(),
            year=int(groups["year"]),
            season_number=int(groups["season"]),
            episode_number=int(groups["episode"]),
        )
    except (KeyError, ValueError):
        return None


def metadata_to_ffmpeg_args(metadata: EpisodeMetadata) -> List[str]:
    """
    Convert episode metadata to ffmpeg metadata arguments for Apple TV.
    
    Args:
        metadata: EpisodeMetadata instance
    
    Returns:
        List of ffmpeg metadata arguments
    """
    return [
        "-metadata",
        f"title={metadata.episode_title}",
        "-metadata",
        f"show={metadata.series_name}",
        "-metadata",
        f"date={metadata.year}",
        "-metadata",
        f"season_number={metadata.season_number}",
        "-metadata",
        f"episode_sort={metadata.episode_number}",
    ]

