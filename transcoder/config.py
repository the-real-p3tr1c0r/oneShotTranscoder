"""Configuration management for transcoder.

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

from dataclasses import dataclass
from pathlib import Path

from transcoder.constants import DEFAULT_TARGET_SIZE_MB_PER_HOUR
from transcoder.exceptions import ConfigurationError
from transcoder.metadata import DEFAULT_FILENAME_PATTERN


@dataclass
class TranscodeConfig:
    """Configuration for transcoding operations."""
    
    rewrap: bool = False
    target_size_mb_per_hour: float = DEFAULT_TARGET_SIZE_MB_PER_HOUR
    filename_pattern: str = DEFAULT_FILENAME_PATTERN
    convert_bitmap_subs: bool = True
    target_dir: Path | None = None
    
    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.target_size_mb_per_hour <= 0:
            raise ConfigurationError("target_size_mb_per_hour must be positive")
        
        if self.target_dir is not None:
            self.target_dir = Path(self.target_dir).resolve()

