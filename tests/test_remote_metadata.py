import logging
from pathlib import Path

import pytest

from transcoder.media_patterns import EpisodeMetadata, MediaType, MovieMetadata
from transcoder.metadata import apply_source_metadata, metadata_to_ffmpeg_args
from transcoder.remote_metadata import (
    PosterResolver,
    _fetch_json,
    _search_itunes_poster,
    resolve_poster_url,
    resolve_poster_url_auto,
    resolve_tmdb_api_key,
    resolve_tvmaze_episode_info,
)


def test_resolve_tmdb_api_key_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key_file = tmp_path / "tmdb_api_key.txt"
    key_file.write_text("FILE_KEY\n", encoding="utf-8")
    monkeypatch.setenv("TMDB_API_KEY", "ENV_KEY")
    assert resolve_tmdb_api_key(tmp_path, "CLI_KEY") == "CLI_KEY"


def test_resolve_tmdb_api_key_file_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key_file = tmp_path / "tmdb_api_key.txt"
    key_file.write_text("TMDB_API_KEY=FILE_KEY\n", encoding="utf-8")
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    assert resolve_tmdb_api_key(tmp_path, None) == "FILE_KEY"


def test_resolve_tvmaze_episode_info_by_number(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch_json(url: str):
        if "search/shows" in url:
            return [{"show": {"id": 123, "name": "Example Show"}}]
        if "episodebynumber" in url:
            return {"name": "Pilot", "airdate": "2024-01-06"}
        if "api.tvmaze.com/shows/123" in url:
            return {
                "premiered": "2024-01-05",
                "genres": ["Drama", "Sci-Fi"],
                "network": {"name": "HBO"},
                "status": "Running",
            }
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("transcoder.remote_metadata._fetch_json", fake_fetch_json)
    enrichment = resolve_tvmaze_episode_info("Example Show", 1, 1, None)
    assert enrichment is not None
    assert enrichment.episode_title == "Pilot"
    assert enrichment.air_date == "2024-01-06"
    assert enrichment.show_year == 2024
    assert enrichment.genres == ["Drama", "Sci-Fi"]
    assert enrichment.network_name == "HBO"
    assert enrichment.show_status == "Running"


def test_resolve_poster_url_explicit_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    movie = MovieMetadata(movie_title="Example Movie", year=2024)

    monkeypatch.setattr("transcoder.remote_metadata._search_itunes_poster", lambda *_: "itunes-url")
    result = resolve_poster_url(movie, MediaType.MOVIE, PosterResolver.ITUNES, None)
    assert result is not None
    assert result.url == "itunes-url"
    assert result.source == "itunes"


def test_resolve_poster_url_auto_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    episode = EpisodeMetadata(
        series_name="Example Show",
        episode_title="Episode 1",
        episode_title_missing=False,
        year=2024,
        season_number=1,
        episode_number=1,
    )

    monkeypatch.setattr("transcoder.remote_metadata._search_tvmaze_poster", lambda *_: "tvmaze-url")
    monkeypatch.setattr("transcoder.remote_metadata._search_itunes_poster", lambda *_: None)
    monkeypatch.setattr("transcoder.remote_metadata._search_tmdb_poster", lambda *_: "tmdb-url")
    monkeypatch.setattr("transcoder.remote_metadata._search_wikimedia_poster", lambda *_: "wikimedia-url")

    result = resolve_poster_url_auto(episode, MediaType.TV_SHOW, "tmdb-key")
    assert result is not None
    assert result.url == "tvmaze-url"
    assert result.source == "tvmaze"


def test_metadata_to_ffmpeg_args_tv_date_priority() -> None:
    episode = EpisodeMetadata(
        series_name="Example Show",
        episode_title="Episode 1",
        episode_title_missing=False,
        year=2020,
        season_number=1,
        episode_number=1,
        air_date="2024-02-02",
        show_year=2023,
        genres=["Drama", "Sci-Fi"],
        network_name="HBO",
        show_status="Running",
    )
    args = metadata_to_ffmpeg_args(episode)
    assert "-metadata" in args
    assert "date=2024-02-02" in args
    assert "genre=Drama, Sci-Fi" in args
    assert "network=HBO" in args
    assert "status=Running" in args


def test_apply_source_metadata_overrides() -> None:
    episode = EpisodeMetadata(
        series_name="Detected Show",
        episode_title="Detected Episode",
        episode_title_missing=False,
        year=2010,
        season_number=1,
        episode_number=2,
    )
    format_tags = {
        "title": "Tagged Episode",
        "show": "Tagged Show",
        "date": "2024-05-01",
        "genre": "Drama, Sci-Fi",
        "network": "HBO",
        "status": "Running",
        "season_number": "3",
        "episode_sort": "4",
    }
    updated = apply_source_metadata(episode, format_tags)
    assert updated.series_name == "Tagged Show"
    assert updated.episode_title == "Tagged Episode"
    assert updated.air_date == "2024-05-01"
    assert updated.show_year == 2024
    assert updated.genres == ["Drama", "Sci-Fi"]
    assert updated.network_name == "HBO"
    assert updated.show_status == "Running"
    assert updated.season_number == 3
    assert updated.episode_number == 4


def test_apply_source_metadata_skips_without_show() -> None:
    episode = EpisodeMetadata(
        series_name="Detected Show",
        episode_title="Detected Episode",
        episode_title_missing=False,
        year=2010,
        season_number=1,
        episode_number=2,
    )
    format_tags = {
        "title": "Tagged Episode",
        "date": "2024-05-01",
    }
    updated = apply_source_metadata(episode, format_tags)
    assert updated.series_name == "Detected Show"
    assert updated.episode_title == "Detected Episode"
    assert updated.air_date is None


def test_apply_source_metadata_skips_without_title() -> None:
    episode = EpisodeMetadata(
        series_name="Detected Show",
        episode_title="Detected Episode",
        episode_title_missing=False,
        year=2010,
        season_number=1,
        episode_number=2,
    )
    format_tags = {
        "show": "Tagged Show",
        "date": "2024-05-01",
    }
    updated = apply_source_metadata(episode, format_tags)
    assert updated.series_name == "Detected Show"
    assert updated.episode_title == "Detected Episode"
    assert updated.air_date is None


def test_fetch_json_logs_warning(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    def raise_error(*_args, **_kwargs):
        raise OSError("boom")

    monkeypatch.setattr("urllib.request.urlopen", raise_error)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(OSError):
            _fetch_json("https://example.com/data")
    assert "Failed to fetch URL" in caplog.text


def test_search_itunes_poster_tv_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    episode = EpisodeMetadata(
        series_name="Prison Break",
        episode_title="Manhunt",
        episode_title_missing=False,
        year=2006,
        season_number=2,
        episode_number=1,
    )
    responses = [
        {"resultCount": 0, "results": []},
        {
            "resultCount": 1,
            "results": [
                {
                    "artworkUrl100": "https://example.com/100x100bb.jpg",
                }
            ],
        },
    ]
    calls = {"count": 0}

    def fake_fetch_json(_url: str):
        index = calls["count"]
        calls["count"] += 1
        return responses[min(index, len(responses) - 1)]

    monkeypatch.setattr("transcoder.remote_metadata._fetch_json", fake_fetch_json)
    url = _search_itunes_poster(episode, MediaType.TV_SHOW)
    assert url == "https://example.com/2000x2000bb.jpg"
    assert calls["count"] >= 2


def test_search_itunes_poster_prefers_season_match(monkeypatch: pytest.MonkeyPatch) -> None:
    episode = EpisodeMetadata(
        series_name="Prison Break",
        episode_title="Manhunt",
        episode_title_missing=False,
        year=2006,
        season_number=2,
        episode_number=1,
    )
    response = {
        "resultCount": 2,
        "results": [
            {
                "collectionName": "Prison Break, Season 3",
                "artworkUrl100": "https://example.com/100x100bb.jpg",
            },
            {
                "collectionName": "Prison Break, Season 2",
                "artworkUrl100": "https://example.com/season2_100x100bb.jpg",
            },
        ],
    }

    monkeypatch.setattr("transcoder.remote_metadata._fetch_json", lambda _url: response)
    url = _search_itunes_poster(episode, MediaType.TV_SHOW)
    assert url == "https://example.com/season2_2000x2000bb.jpg"
