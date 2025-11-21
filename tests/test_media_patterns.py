from pathlib import Path

import pytest

from transcoder.media_patterns import (
    EpisodeMetadata,
    MediaType,
    MovieMetadata,
    detect_metadata,
)


@pytest.mark.parametrize(
    "filename,expected_type,expected_fields",
    [
        (
            "Series.Name.S02E05.1080p.WEB-DL-GROUP.mkv",
            MediaType.TV_SHOW,
            {
                "series_name": "Series Name",
                "season_number": 2,
                "episode_number": 5,
                "episode_title": "Series Name",
            },
        ),
        (
            "Series Name - S02E05 - Episode Title (1080p WEB-DL).mkv",
            MediaType.TV_SHOW,
            {
                "series_name": "Series Name",
                "season_number": 2,
                "episode_number": 5,
                "episode_title": "Episode Title",
            },
        ),
        (
            "Show.Name.1x02.720p.WEB.h264-GRP.mkv",
            MediaType.TV_SHOW,
            {
                "series_name": "Show Name",
                "season_number": 1,
                "episode_number": 2,
            },
        ),
        (
            "Daily Show - 2025-11-20 - Interview With Guest.mkv",
            MediaType.TV_SHOW,
            {
                "series_name": "Daily Show",
                "air_date": "2025-11-20",
                "year": 2025,
            },
        ),
        (
            "BreakingBad.305.1080p.AMZN.WEB-DL.x265-GROUP.mkv",
            MediaType.TV_SHOW,
            {
                "series_name": "BreakingBad",
                "season_number": 3,
                "episode_number": 5,
            },
        ),
    ],
)
def test_detect_metadata_tv(filename, expected_type, expected_fields):
    path = Path(filename)
    detection = detect_metadata(path)
    assert detection is not None
    assert detection.media_type == expected_type
    assert isinstance(detection.metadata, EpisodeMetadata)
    for field, expected_value in expected_fields.items():
        assert getattr(detection.metadata, field) == expected_value


@pytest.mark.parametrize(
    "filename,expected_fields",
    [
        (
            "Dune Part Two (2024) [IMAX Enhanced].mkv",
            {"movie_title": "Dune Part Two", "year": 2024},
        ),
        (
            "Blade.Runner.2049.2017.2160p.BluRay.REMUX-GRP.mkv",
            {"movie_title": "Blade Runner 2049", "year": 2017},
        ),
        (
            "Some Movie 1999 1080p NF WEB-DL.mkv",
            {"movie_title": "Some Movie", "year": 1999},
        ),
        (
            "One Battle After Another 2025 1080p 10bit WEBRip 6CH X265 HEVC-PSA.mkv",
            {"movie_title": "One Battle After Another", "year": 2025},
        ),
    ],
)
def test_detect_metadata_movie(filename, expected_fields):
    path = Path(filename)
    detection = detect_metadata(path)
    assert detection is not None
    assert detection.media_type == MediaType.MOVIE
    assert isinstance(detection.metadata, MovieMetadata)
    for field, expected_value in expected_fields.items():
        assert getattr(detection.metadata, field) == expected_value


def test_detect_metadata_manual_pattern():
    manual_pattern = "<Movie Name> (<Year>) - <Episode Name>.mkv"
    path = Path("Test Movie (2020) - Director Commentary.mkv")
    detection = detect_metadata(path, manual_pattern)
    assert detection is not None
    assert detection.media_type == MediaType.MOVIE
    assert isinstance(detection.metadata, MovieMetadata)
    assert detection.metadata.movie_title == "Test Movie"
    assert detection.metadata.year == 2020


def test_detect_metadata_fallback():
    path = Path("UnknownFile.mkv")
    detection = detect_metadata(path)
    assert detection is None


def test_codec_indicators_not_tv_shows():
    """Test that codec indicators (X265, H265, etc.) don't trigger false TV show detection."""
    test_cases = [
        "Movie Title 2024 X265 HEVC.mkv",
        "Movie Title 2024 H265 HEVC.mkv",
        "Movie Title 2024 x264.mkv",
        "Movie Title 2024 H264.mkv",
    ]
    for filename in test_cases:
        path = Path(filename)
        detection = detect_metadata(path)
        # Should either be detected as a movie or not detected at all, but NOT as TV show
        if detection:
            assert detection.media_type != MediaType.TV_SHOW, f"{filename} incorrectly detected as TV show"

