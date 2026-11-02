from pathlib import Path

import pytest

from transcoder.apple_tv_library import (
    AppleTVTrack,
    find_existing_apple_tv_track,
    import_file_to_apple_tv,
    normalize_media_title,
)
from transcoder.media_patterns import EpisodeMetadata, MediaType, MovieMetadata


def test_normalize_media_title_strips_punctuation_and_year() -> None:
    assert normalize_media_title("The Agency (2024)", strip_trailing_year=True) == "the agency"
    assert normalize_media_title("The Agency 2024", strip_trailing_year=True) == "the agency"
    assert normalize_media_title("Dune: Part Two", strip_trailing_year=False) == "dune part two"


def test_find_existing_apple_tv_track_tv_show() -> None:
    library = [
        AppleTVTrack(
            name="Kick the Wasp's Nest",
            show="The Agency",
            season_number=2,
            episode_number=1,
            year=2024,
            media_kind="TV show",
        )
    ]
    ep_match = EpisodeMetadata(
        series_name="The Agency 2024",
        episode_title="Kick the Wasp's Nest",
        episode_title_missing=False,
        year=2024,
        season_number=2,
        episode_number=1,
    )
    ep_diff = EpisodeMetadata(
        series_name="The Agency",
        episode_title="Another Episode",
        episode_title_missing=False,
        year=2024,
        season_number=2,
        episode_number=3,
    )

    found = find_existing_apple_tv_track(ep_match, MediaType.TV_SHOW, library)
    assert found is not None
    assert found.name == "Kick the Wasp's Nest"
    assert find_existing_apple_tv_track(ep_diff, MediaType.TV_SHOW, library) is None


def test_find_existing_apple_tv_track_movie() -> None:
    library = [
        AppleTVTrack(
            name="Dune: Part Two",
            show="",
            season_number=None,
            episode_number=None,
            year=2024,
            media_kind="movie",
        )
    ]
    movie_match = MovieMetadata(movie_title="Dune Part Two", year=2024)
    movie_wrong_year = MovieMetadata(movie_title="Dune Part Two", year=2021)

    assert find_existing_apple_tv_track(movie_match, MediaType.MOVIE, library) is not None
    assert find_existing_apple_tv_track(movie_wrong_year, MediaType.MOVIE, library) is None


def test_import_file_to_apple_tv_cleans_up_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging_mp4 = tmp_path / "Sample.Show.S01E01.mp4"
    staging_mp4.write_bytes(b"fake-mp4-content")
    copied_location = tmp_path / "Library" / "Sample.Show.S01E01.mp4"
    copied_location.parent.mkdir(parents=True, exist_ok=True)
    copied_location.write_bytes(b"copied-mp4-content")

    monkeypatch.setattr("transcoder.apple_tv_library.is_apple_tv_import_supported", lambda: True)

    class DummyCompletedProcess:
        returncode = 0
        stdout = (
            '{"ok": true, "name": "Pilot", "show": "Sample Show", '
            f'"season": 1, "episode": 1, "year": 2024, "kind": "TV show", "location": "{copied_location}"}}'
        )
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *a, **kw: DummyCompletedProcess())

    ep = EpisodeMetadata(
        series_name="Sample Show",
        episode_title="Pilot",
        episode_title_missing=False,
        year=2024,
        season_number=1,
        episode_number=1,
    )
    ok, track = import_file_to_apple_tv(staging_mp4, metadata=ep, cleanup_staging=True)
    assert ok is True
    assert track is not None
    assert track.show == "Sample Show"
    assert track.season_number == 1
    assert track.episode_number == 1
    assert not staging_mp4.exists()
