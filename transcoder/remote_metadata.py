"""Remote metadata lookups for episode titles and poster images."""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transcoder.media_patterns import EpisodeMetadata, MediaType, MovieMetadata


DEFAULT_USER_AGENT = "oneShotTranscoder/1.0 (+https://github.com/the-real-p3tr1c0r/oneShotTranscoder)"
DEFAULT_HTTP_TIMEOUT_SECONDS = 10
DEFAULT_TMDB_KEY_FILENAME = "tmdb_api_key.txt"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/original"
ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
TVMAZE_SEARCH_URL = "https://api.tvmaze.com/search/shows"
TVMAZE_EPISODES_URL = "https://api.tvmaze.com/shows/{show_id}/episodes"
TVMAZE_EPISODE_BY_NUMBER_URL = "https://api.tvmaze.com/shows/{show_id}/episodebynumber"
TVMAZE_EPISODES_BY_DATE_URL = "https://api.tvmaze.com/shows/{show_id}/episodesbydate"
WIKIMEDIA_API_URL = "https://commons.wikimedia.org/w/api.php"

logger = logging.getLogger(__name__)


def _create_ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


class PosterResolver(str):
    AUTO = "auto"
    LOCAL = "local"
    TVMAZE = "tvmaze"
    ITUNES = "itunes"
    TMDB = "tmdb"
    WIKIMEDIA = "wikimedia"


@dataclass(slots=True)
class PosterResolutionResult:
    url: str
    source: str


@dataclass(slots=True)
class TvmazeEpisodeEnrichment:
    episode_title: str | None
    air_date: str | None
    show_year: int | None
    genres: list[str]
    network_name: str | None
    show_status: str | None


def _fetch_json(url: str, timeout_seconds: int = DEFAULT_HTTP_TIMEOUT_SECONDS) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": DEFAULT_USER_AGENT},
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
            context=_create_ssl_context(),
        ) as response:
            payload = response.read().decode("utf-8")
    except Exception as error:
        logger.warning("Failed to fetch URL %s: %s", url, error)
        raise
    return json.loads(payload)


def resolve_tmdb_api_key(
    source_dir: Path,
    cli_key: str | None,
    key_filename: str = DEFAULT_TMDB_KEY_FILENAME,
) -> str | None:
    if cli_key:
        return cli_key.strip() or None

    key_path = source_dir / key_filename
    if key_path.is_file():
        try:
            for line in key_path.read_text(encoding="utf-8").splitlines():
                cleaned = line.strip()
                if not cleaned or cleaned.startswith("#"):
                    continue
                if "=" in cleaned:
                    cleaned = cleaned.split("=", 1)[1].strip()
                if cleaned:
                    return cleaned
        except OSError:
            pass

    env_key = os.environ.get("TMDB_API_KEY")
    return env_key.strip() if env_key else None


def resolve_tvmaze_episode_info(
    series_name: str,
    season_number: int | None,
    episode_number: int | None,
    air_date: str | None,
) -> TvmazeEpisodeEnrichment | None:
    show_id = _search_tvmaze_show_id(series_name)
    if show_id is None:
        return None

    show_info = _fetch_tvmaze_show_info(show_id)
    show_year = _extract_show_year(show_info)
    genres = _extract_show_genres(show_info)
    network_name = _extract_show_network(show_info)
    show_status = _extract_show_status(show_info)

    episode_title = None
    episode_air_date = None
    if season_number is not None and episode_number is not None:
        episode_title, episode_air_date = _fetch_tvmaze_episode_by_number(show_id, season_number, episode_number)
    elif air_date:
        episode_title, episode_air_date = _fetch_tvmaze_episode_by_date(show_id, air_date)

    if (
        not episode_title
        and not episode_air_date
        and show_year is None
        and not genres
        and not network_name
        and not show_status
    ):
        return None

    return TvmazeEpisodeEnrichment(
        episode_title=episode_title,
        air_date=episode_air_date,
        show_year=show_year,
        genres=genres,
        network_name=network_name,
        show_status=show_status,
    )


def resolve_tvmaze_episode_title(
    series_name: str,
    season_number: int | None,
    episode_number: int | None,
    air_date: str | None,
) -> str | None:
    enrichment = resolve_tvmaze_episode_info(series_name, season_number, episode_number, air_date)
    return enrichment.episode_title if enrichment else None


def _search_tvmaze_show_id(series_name: str) -> int | None:
    query = urllib.parse.urlencode({"q": series_name})
    url = f"{TVMAZE_SEARCH_URL}?{query}"
    try:
        results = _fetch_json(url)
    except Exception:
        return None
    if not isinstance(results, list) or not results:
        return None

    normalized_target = _normalize_title(series_name)
    for entry in results:
        show = entry.get("show") if isinstance(entry, dict) else None
        if not isinstance(show, dict):
            continue
        name = show.get("name")
        if name and _normalize_title(name) == normalized_target:
            return show.get("id")

    first = results[0].get("show") if isinstance(results[0], dict) else None
    if isinstance(first, dict):
        return first.get("id")
    return None


def _fetch_tvmaze_episode_by_number(show_id: int, season: int, episode: int) -> tuple[str | None, str | None]:
    query = urllib.parse.urlencode({"season": season, "number": episode})
    url = f"{TVMAZE_EPISODE_BY_NUMBER_URL.format(show_id=show_id)}?{query}"
    try:
        data = _fetch_json(url)
    except Exception:
        return None, None
    if not isinstance(data, dict):
        return None, None
    return data.get("name"), data.get("airdate")


def _fetch_tvmaze_episode_by_date(show_id: int, air_date: str) -> tuple[str | None, str | None]:
    query = urllib.parse.urlencode({"date": air_date})
    url = f"{TVMAZE_EPISODES_BY_DATE_URL.format(show_id=show_id)}?{query}"
    try:
        data = _fetch_json(url)
    except Exception:
        return None, None
    if not isinstance(data, list) or not data:
        return None, None
    first = data[0]
    if not isinstance(first, dict):
        return None, None
    return first.get("name"), first.get("airdate")


def _fetch_tvmaze_show_info(show_id: int) -> dict[str, Any] | None:
    url = f"https://api.tvmaze.com/shows/{show_id}"
    try:
        data = _fetch_json(url)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _extract_show_year(show_info: dict[str, Any] | None) -> int | None:
    if not show_info:
        return None
    premiered = show_info.get("premiered")
    if not premiered or not isinstance(premiered, str):
        return None
    try:
        return int(premiered.split("-", 1)[0])
    except (ValueError, IndexError):
        return None


def _extract_show_genres(show_info: dict[str, Any] | None) -> list[str]:
    if not show_info:
        return []
    genres = show_info.get("genres")
    if not isinstance(genres, list):
        return []
    return [genre for genre in genres if isinstance(genre, str) and genre.strip()]


def _extract_show_network(show_info: dict[str, Any] | None) -> str | None:
    if not show_info:
        return None
    network = show_info.get("network")
    if isinstance(network, dict):
        name = network.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    web_channel = show_info.get("webChannel")
    if isinstance(web_channel, dict):
        name = web_channel.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _extract_show_status(show_info: dict[str, Any] | None) -> str | None:
    if not show_info:
        return None
    status = show_info.get("status")
    if isinstance(status, str) and status.strip():
        return status.strip()
    return None


def resolve_poster_url(
    metadata: EpisodeMetadata | MovieMetadata,
    media_type: MediaType,
    resolver: str,
    tmdb_api_key: str | None,
) -> PosterResolutionResult | None:
    if resolver == PosterResolver.TVMAZE:
        url = _search_tvmaze_poster(metadata, media_type)
        return PosterResolutionResult(url, "tvmaze") if url else None
    if resolver == PosterResolver.ITUNES:
        url = _search_itunes_poster(metadata, media_type)
        return PosterResolutionResult(url, "itunes") if url else None
    if resolver == PosterResolver.TMDB:
        if not tmdb_api_key:
            return None
        url = _search_tmdb_poster(metadata, media_type, tmdb_api_key)
        return PosterResolutionResult(url, "tmdb") if url else None
    if resolver == PosterResolver.WIKIMEDIA:
        url = _search_wikimedia_poster(metadata, media_type)
        return PosterResolutionResult(url, "wikimedia") if url else None
    return None


def resolve_poster_url_auto(
    metadata: EpisodeMetadata | MovieMetadata,
    media_type: MediaType,
    tmdb_api_key: str | None,
) -> PosterResolutionResult | None:
    url = _search_tvmaze_poster(metadata, media_type)
    if url:
        return PosterResolutionResult(url, "tvmaze")

    url = _search_itunes_poster(metadata, media_type)
    if url:
        return PosterResolutionResult(url, "itunes")

    if tmdb_api_key:
        url = _search_tmdb_poster(metadata, media_type, tmdb_api_key)
        if url:
            return PosterResolutionResult(url, "tmdb")

    url = _search_wikimedia_poster(metadata, media_type)
    if url:
        return PosterResolutionResult(url, "wikimedia")

    return None


def _search_tvmaze_poster(metadata: EpisodeMetadata | MovieMetadata, media_type: MediaType) -> str | None:
    if media_type == MediaType.TV_SHOW and isinstance(metadata, EpisodeMetadata):
        term = metadata.series_name
    else:
        term = metadata.movie_title if isinstance(metadata, MovieMetadata) else ""
    if not term:
        return None
    show_id = _search_tvmaze_show_id(term)
    if show_id is None:
        return None
    show_info = _fetch_tvmaze_show_info(show_id)
    if not isinstance(show_info, dict):
        return None
    image_info = show_info.get("image")
    if isinstance(image_info, dict):
        original = image_info.get("original")
        if isinstance(original, str) and original.strip():
            return original.strip()
        medium = image_info.get("medium")
        if isinstance(medium, str) and medium.strip():
            return medium.strip()
    return None


def download_poster_image(url: str, dest_dir: Path, filename_prefix: str) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    extension = _guess_extension(url)
    safe_prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", filename_prefix).strip("_") or "poster"
    output_path = dest_dir / f"{safe_prefix}_poster{extension}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": DEFAULT_USER_AGENT},
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=DEFAULT_HTTP_TIMEOUT_SECONDS,
            context=_create_ssl_context(),
        ) as response:
            with output_path.open("wb") as handle:
                handle.write(response.read())
    except Exception as error:
        logger.warning("Failed to download poster %s: %s", url, error)
        raise
    return output_path


def _search_itunes_poster(metadata: EpisodeMetadata | MovieMetadata, media_type: MediaType) -> str | None:
    if media_type == MediaType.TV_SHOW and isinstance(metadata, EpisodeMetadata):
        term = metadata.series_name
        entity = "tvSeason"
        if not term:
            return None
        attempts = []
        if metadata.season_number is not None:
            attempts.extend(
                [
                    {"term": f"{term}, Season {metadata.season_number}", "entity": entity, "limit": 5},
                    {"term": f"{term} Season {metadata.season_number}", "entity": entity, "limit": 5},
                ]
            )
        attempts.extend(
            [
                {"term": term, "media": "tvShow", "entity": entity, "limit": 5},
                {"term": term, "entity": entity, "limit": 5},
            ]
        )
    else:
        term = metadata.movie_title if isinstance(metadata, MovieMetadata) else ""
        if not term:
            return None
        query_terms = term
        if isinstance(metadata, MovieMetadata) and metadata.year:
            query_terms = f"{term} {metadata.year}"
        attempts = [{"term": query_terms, "media": "movie", "entity": "movie", "limit": 5}]

    attempts_with_country = attempts + [{**params, "country": "us"} for params in attempts]
    season_token = None
    if media_type == MediaType.TV_SHOW and isinstance(metadata, EpisodeMetadata):
        if metadata.season_number is not None:
            season_token = f"Season {metadata.season_number}"

    for params in attempts_with_country:
        url = f"{ITUNES_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        try:
            data = _fetch_json(url)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        results = data.get("results")
        if not isinstance(results, list) or not results:
            continue
        candidate_results = results
        if season_token:
            season_matches = [
                result
                for result in results
                if isinstance(result, dict)
                and isinstance(result.get("collectionName"), str)
                and season_token.lower() in result.get("collectionName", "").lower()
            ]
            if season_matches:
                candidate_results = season_matches
        for result in candidate_results:
            if not isinstance(result, dict):
                continue
            artwork = result.get("artworkUrl100") or result.get("artworkUrl60")
            if not artwork:
                continue
            return _upgrade_itunes_artwork_url(str(artwork))
    return None


def _upgrade_itunes_artwork_url(url: str, target_size: int = 2000) -> str:
    size_token = f"{target_size}x{target_size}bb"
    upgraded = re.sub(r"\d+x\d+bb", size_token, url)
    upgraded = re.sub(r"\d+x\d+", size_token, upgraded)
    upgraded = upgraded.replace("bbbb", "bb")
    return upgraded


def _search_tmdb_poster(
    metadata: EpisodeMetadata | MovieMetadata,
    media_type: MediaType,
    api_key: str,
) -> str | None:
    if not api_key:
        return None
    if media_type == MediaType.TV_SHOW and isinstance(metadata, EpisodeMetadata):
        endpoint = "https://api.themoviedb.org/3/search/tv"
        params = {"api_key": api_key, "query": metadata.series_name}
        if metadata.year:
            params["first_air_date_year"] = metadata.year
    else:
        endpoint = "https://api.themoviedb.org/3/search/movie"
        title = metadata.movie_title if isinstance(metadata, MovieMetadata) else ""
        params = {"api_key": api_key, "query": title}
        if isinstance(metadata, MovieMetadata) and metadata.year:
            params["year"] = metadata.year
    url = f"{endpoint}?{urllib.parse.urlencode(params)}"
    try:
        data = _fetch_json(url)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    if not isinstance(first, dict):
        return None
    poster_path = first.get("poster_path")
    if not poster_path:
        return None
    return f"{TMDB_IMAGE_BASE_URL}{poster_path}"


def _search_wikimedia_poster(metadata: EpisodeMetadata | MovieMetadata, media_type: MediaType) -> str | None:
    if media_type == MediaType.TV_SHOW and isinstance(metadata, EpisodeMetadata):
        query = f"{metadata.series_name} poster"
    else:
        title = metadata.movie_title if isinstance(metadata, MovieMetadata) else ""
        query = f"{title} poster"
    if not query.strip():
        return None
    search_params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srnamespace": 6,
        "srlimit": 1,
        "srsearch": query,
    }
    search_url = f"{WIKIMEDIA_API_URL}?{urllib.parse.urlencode(search_params)}"
    try:
        search_data = _fetch_json(search_url)
    except Exception:
        return None
    search_results = search_data.get("query", {}).get("search") if isinstance(search_data, dict) else None
    if not isinstance(search_results, list) or not search_results:
        return None
    title = search_results[0].get("title")
    if not title:
        return None
    info_params = {
        "action": "query",
        "format": "json",
        "prop": "imageinfo",
        "iiprop": "url",
        "iiurlwidth": 2000,
        "titles": title,
    }
    info_url = f"{WIKIMEDIA_API_URL}?{urllib.parse.urlencode(info_params)}"
    try:
        info_data = _fetch_json(info_url)
    except Exception:
        return None
    pages = info_data.get("query", {}).get("pages") if isinstance(info_data, dict) else None
    if not isinstance(pages, dict):
        return None
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        imageinfo = page.get("imageinfo")
        if not isinstance(imageinfo, list) or not imageinfo:
            continue
        entry = imageinfo[0]
        if not isinstance(entry, dict):
            continue
        return entry.get("thumburl") or entry.get("url")
    return None


def _normalize_title(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "", value or "").lower()
    return normalized


def _guess_extension(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    if "." in path:
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in {"jpg", "jpeg", "png", "webp", "gif", "bmp"}:
            return f".{ext}"
    return ".jpg"
