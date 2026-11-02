"""Apple TV (TV.app) library duplicate detection and automatic import."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from transcoder.media_patterns import EpisodeMetadata, MediaType, MovieMetadata


@dataclass(slots=True)
class AppleTVTrack:
    """Metadata for an existing track in Apple TV (TV.app)."""

    name: str
    show: str
    season_number: int | None
    episode_number: int | None
    year: int | None
    media_kind: str


_TRAILING_YEAR_RE = re.compile(r"\s*\(?(19\d{2}|20\d{2})\)?$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_media_title(value: str, *, strip_trailing_year: bool = False) -> str:
    """Normalize a show, episode, or movie title for case/punctuation-insensitive comparison."""
    cleaned = (value or "").strip()
    if strip_trailing_year:
        cleaned = _TRAILING_YEAR_RE.sub("", cleaned).strip()
    cleaned = cleaned.lower()
    cleaned = _NON_ALNUM_RE.sub(" ", cleaned).strip()
    return cleaned


def is_apple_tv_import_supported() -> bool:
    """Return True if running on macOS with osascript available."""
    return sys.platform == "darwin" and Path("/usr/bin/osascript").exists()


def fetch_apple_tv_library_tracks() -> list[AppleTVTrack]:
    """
    Fetch all existing tracks from Apple TV's primary library playlist via JXA.

    Uses bulk property array retrieval on `libraryPlaylists[0].tracks` so even large
    libraries are queried in a single Apple Event round-trip.
    """
    if not is_apple_tv_import_supported():
        return []

    jxa_script = """
const tv = Application("TV");
const playlists = tv.libraryPlaylists();
if (!playlists || playlists.length === 0) {
  JSON.stringify([]);
} else {
  const lib = playlists[0];
  const names = lib.tracks.name();
  const shows = lib.tracks.show();
  const seasons = lib.tracks.seasonNumber();
  const episodes = lib.tracks.episodeNumber();
  const years = lib.tracks.year();
  const kinds = lib.tracks.mediaKind();
  const out = [];
  for (let i = 0; i < names.length; i++) {
    out.push({
      name: names[i] || "",
      show: shows[i] || "",
      season: seasons[i] || 0,
      episode: episodes[i] || 0,
      year: years[i] || 0,
      kind: kinds[i] || ""
    });
  }
  JSON.stringify(out);
}
"""
    try:
        result = subprocess.run(
            ["/usr/bin/osascript", "-l", "JavaScript", "-e", jxa_script],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        raw_items = json.loads(result.stdout.strip() or "[]")
    except Exception as e:
        raise RuntimeError(f"Could not query Apple TV library: {e}") from e

    tracks: list[AppleTVTrack] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        season_val = int(item.get("season") or 0)
        episode_val = int(item.get("episode") or 0)
        year_val = int(item.get("year") or 0)
        tracks.append(
            AppleTVTrack(
                name=str(item.get("name") or ""),
                show=str(item.get("show") or ""),
                season_number=season_val if season_val > 0 else None,
                episode_number=episode_val if episode_val > 0 else None,
                year=year_val if year_val > 0 else None,
                media_kind=str(item.get("kind") or ""),
            )
        )
    return tracks


def find_existing_apple_tv_track(
    metadata: EpisodeMetadata | MovieMetadata,
    media_type: MediaType | None,
    library_tracks: list[AppleTVTrack],
) -> AppleTVTrack | None:
    """
    Check if a track matching `metadata` already exists in `library_tracks`.
    """
    if media_type == MediaType.TV_SHOW and isinstance(metadata, EpisodeMetadata):
        target_show_exact = normalize_media_title(metadata.series_name, strip_trailing_year=False)
        target_show_no_year = normalize_media_title(metadata.series_name, strip_trailing_year=True)
        target_shows = {s for s in (target_show_exact, target_show_no_year) if s}
        if not target_shows:
            return None

        target_title = (
            normalize_media_title(metadata.episode_title)
            if metadata.has_real_episode_title
            else ""
        )

        for track in library_tracks:
            track_show_exact = normalize_media_title(track.show, strip_trailing_year=False)
            track_show_no_year = normalize_media_title(track.show, strip_trailing_year=True)
            track_shows = {s for s in (track_show_exact, track_show_no_year) if s}
            if not (target_shows & track_shows):
                continue

            # Primary match: Season + Episode number
            if (
                metadata.season_number is not None
                and metadata.episode_number is not None
                and track.season_number == metadata.season_number
                and track.episode_number == metadata.episode_number
            ):
                return track

            # Fallback match when episode/season numbers are absent: episode title
            if (
                (metadata.season_number is None or metadata.episode_number is None)
                and target_title
                and normalize_media_title(track.name) == target_title
            ):
                return track

        return None

    if isinstance(metadata, MovieMetadata):
        target_title_exact = normalize_media_title(metadata.movie_title, strip_trailing_year=False)
        target_title_no_year = normalize_media_title(metadata.movie_title, strip_trailing_year=True)
        target_titles = {t for t in (target_title_exact, target_title_no_year) if t}
        if not target_titles:
            return None

        for track in library_tracks:
            # Ignore TV episodes that happen to share a title with a movie
            if track.show and (track.season_number or track.episode_number):
                continue

            track_title_exact = normalize_media_title(track.name, strip_trailing_year=False)
            track_title_no_year = normalize_media_title(track.name, strip_trailing_year=True)
            track_titles = {t for t in (track_title_exact, track_title_no_year) if t}
            if not (target_titles & track_titles):
                continue

            # If both have a known year, require them to match
            if metadata.year and track.year and metadata.year != track.year:
                continue

            return track

    return None


def import_file_to_apple_tv(
    mp4_path: Path,
    metadata: EpisodeMetadata | MovieMetadata | None = None,
    cleanup_staging: bool = True,
) -> tuple[bool, AppleTVTrack | None]:
    """
    Import an MP4 file into Apple TV (`TV.app`) and optionally remove the staging file.

    Also applies key metadata properties (`media kind`, `show`, `season number`,
    `episode number`, `year`) on the newly imported track so `TV.app` categorizes it
    under TV Shows or Movies immediately.
    """
    if not is_apple_tv_import_supported():
        raise RuntimeError("Apple TV import (--import) is only supported on macOS.")

    resolved_mp4 = mp4_path.resolve()
    if not resolved_mp4.exists():
        raise FileNotFoundError(f"MP4 file not found for import: {resolved_mp4}")

    payload = {
        "file_path": str(resolved_mp4),
        "is_tv": isinstance(metadata, EpisodeMetadata),
        "show": metadata.series_name if isinstance(metadata, EpisodeMetadata) else "",
        "season": metadata.season_number if isinstance(metadata, EpisodeMetadata) else None,
        "episode": metadata.episode_number if isinstance(metadata, EpisodeMetadata) else None,
        "episode_id": metadata.episode_id if isinstance(metadata, EpisodeMetadata) else None,
        "title": (
            metadata.episode_title
            if isinstance(metadata, EpisodeMetadata)
            else (metadata.movie_title if isinstance(metadata, MovieMetadata) else resolved_mp4.stem)
        ),
        "year": (
            (metadata.show_year or metadata.year)
            if isinstance(metadata, EpisodeMetadata)
            else (metadata.year if isinstance(metadata, MovieMetadata) else None)
        ),
    }

    jxa_script = """
function run(argv) {
  const params = JSON.parse(argv[0]);
  const tv = Application("TV");
  const added = tv.add([Path(params.file_path)]);
  if (!added) {
    return JSON.stringify({ok: false, error: "TV.app returned no track on add()"});
  }
  const track = Array.isArray(added) ? added[0] : added;
  if (!track) {
    return JSON.stringify({ok: false, error: "TV.app returned empty track list"});
  }

  try {
    if (params.is_tv) {
      track.mediaKind = "TV show";
      if (params.show) track.show = params.show;
      if (params.season !== null && params.season !== undefined) track.seasonNumber = params.season;
      if (params.episode !== null && params.episode !== undefined) track.episodeNumber = params.episode;
      if (params.episode_id) track.episodeID = params.episode_id;
    } else {
      track.mediaKind = "movie";
    }
    if (params.title) track.name = params.title;
    if (params.year) track.year = params.year;
  } catch (e) {
    // Best-effort property assignment; embedded MP4 atoms are already present
  }

  let loc = "";
  try {
    const locObj = track.location();
    if (locObj) loc = locObj.toString();
  } catch (e) {}

  return JSON.stringify({
    ok: true,
    name: track.name() || "",
    show: track.show() || "",
    season: track.seasonNumber() || 0,
    episode: track.episodeNumber() || 0,
    year: track.year() || 0,
    kind: track.mediaKind() || "",
    location: loc
  });
}
"""
    result = subprocess.run(
        ["/usr/bin/osascript", "-l", "JavaScript", "-e", jxa_script, json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"TV.app import failed: {err}")

    try:
        resp = json.loads(result.stdout.strip() or "{}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Unexpected response from TV.app import: {result.stdout}") from e

    if not resp.get("ok"):
        raise RuntimeError(resp.get("error") or "Unknown TV.app import failure")

    track_location_str = str(resp.get("location") or "")
    track_location = Path(track_location_str).resolve() if track_location_str else None

    if cleanup_staging and resolved_mp4.exists():
        # Wait briefly if TV.app is still copying the file in the background
        for _ in range(10):
            if track_location and track_location != resolved_mp4 and track_location.exists():
                break
            time.sleep(0.2)

        if track_location and track_location == resolved_mp4:
            # TV.app referenced the staging file in place ("Copy files to Media folder" is off)
            print(
                f"Note: Apple TV referenced {resolved_mp4.name} in place (Copy files to Media folder is disabled); keeping file."
            )
        else:
            try:
                resolved_mp4.unlink()
                print(f"Cleaned up staging MP4: {resolved_mp4.name}")
            except OSError as e:
                print(f"Warning: Could not remove staging MP4 {resolved_mp4.name}: {e}")

    imported_track = AppleTVTrack(
        name=str(resp.get("name") or ""),
        show=str(resp.get("show") or ""),
        season_number=int(resp.get("season") or 0) or None,
        episode_number=int(resp.get("episode") or 0) or None,
        year=int(resp.get("year") or 0) or None,
        media_kind=str(resp.get("kind") or ""),
    )
    return True, imported_track
