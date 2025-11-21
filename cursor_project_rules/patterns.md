# MKV Naming Pattern Research

This document summarizes the filename conventions promoted by Radarr, Sonarr, Plex, Emby, Jellyfin, Kodi, Infuse, and common scene/Apple TV workflows. Each section lists representative examples, the metadata fields implied, and regex/token fragments we must support.

## Movies

### Radarr
- Examples: `Inception (2010) [WEBDL-1080p]`, `Dune Part Two (2024) [IMAX Enhanced] {edition-Extended}`, `The.Matrix.1999.2160p.UHD.BluRay.x265-GROUP`.
- Key tokens: `<Movie Name>`, `<Year>`, `<Edition>`, `<Source>`, `<Quality>`, `<Release Group>`.
- Regex fragments: `(?P<movie>.+?)\s*\((?P<year>\d{4})\)`, `(?P<movie>.+?)\.(?P<year>\d{4})`, optional suffixes `(?P<cut>{edition-[^}]+})`, `(?P<quality>(?:480|720|1080|2160)p)`, `(?P<source>WEB[-_. ]?DL|BluRay|DVDRip)`.

### Plex / Emby / Jellyfin
- Examples: `Avatar (2009).mkv`, `Blade Runner 2049 (2017) [Ultimate Edition].mkv`.
- Required pattern: `Movie Name (Year)`; folders often mirror the same string.
- Regex fragment: `^(?P<movie>.+?)\s*\((?P<year>\d{4})\)` with optional trailing descriptors `(?P<specs>.+?)`.

### Infuse
- Supports both `Movie Name (Year)` and dotted variants such as `Movie.Name.2019.4K.WEB-DL.mkv`.
- Must parse `(?P<movie>.+?)[ ._-](?P<year>\d{4})(?=[ ._-])` when parentheses absent.

### Kodi
- Accepts `MovieName (Year)` and `MovieName.Year.Resolution.Source.Codec-GRP`. Same regex fragments as Radarr scene style.

### Apple TV (iTunes Extras style)
- Prefers clean titles with optional year, e.g., `Movie Name (Year).m4v`.
- Requires `title` + `date` metadata; we should capture `movie_title` and `year` even if adornments exist.

## TV Shows

### Sonarr
- Examples: `Show.Name.S02E05.1080p.WEB-DL.DD5.1.x264-GROUP`, `Show Name - S02E05 - Episode Title.mkv`.
- Tokens: `<Series Name>`, `<Season>`, `<Episode>`, `<Episode Name>`, `<Quality>`, `<Release Group>`.
- Regex fragments: `(?P<series>.+?)[ ._-]+S(?P<season>\d{2})E(?P<episode>\d{2})`, `(?P<series>.+?)\s*-\s*S(?P<season>\d{2})E(?P<episode>\d{2})\s*-\s*(?P<title>.+?)`.

### Plex / Emby / Jellyfin
- Directory layout: `Show Name/Season 01/Show Name - s01e01 - Episode Title.ext`.
- Regex fragments identical to Sonarr but case-insensitive `s|S`, `e|E`. Need to support optional episode titles and double-episode notation `E01-E02`.

### Kodi
- Accepts multiple season/episode styles: `ShowName S01E01`, `ShowName 1x01`, `ShowName - 101`, `ShowName - 2019-11-20` (date-based).
- Regex fragments: `(?P<series>.+?)[ ._-]+(?:(?:S(?P<season>\d{1,2})E(?P<episode>\d{2}))|(?:(?P<season_alt>\d{1,2})x(?P<episode_alt>\d{2}))|(?:(?P<combined>\d{3}))|(?:(?P<airdate>\d{4}-\d{2}-\d{2})))`.

### Infuse
- Accepts `show-name_s01e02.ext`, `show.name.1x02.ext`, `show name season 01 episode 02.ext`.
- Same regex fragments as Kodi with underscores allowed.

### Jellyfin (date-friendly)
- For daily shows: `Show Name - 2023-12-01 - Episode Title.ext`. Need `(?P<series>.+?)\s*-\s*(?P<airdate>\d{4}-\d{2}-\d{2})`.

## Scene Release (applies to Radarr/Sonarr imports)
- TV: `Series.Name.S03E04.1080p.NF.WEB-DL.DDP5.1.Atmos.x264-GROUP`.
- Movies: `Movie.Title.2024.2160p.WEB.H265-HDR10Plus-GROUP`.
- Regex fragments reuse dotted splits; treat dots/underscores as separators.

## Token Coverage Summary

| Token | Meaning | Sample Regex |
| --- | --- | --- |
| `<Movie Name>` | Movie title text | `(?P<movie>.+?)` |
| `<Series Name>` | Show title text | `(?P<series>.+?)` |
| `<Year>` | Release year | `(?P<year>\d{4})` |
| `<Season>` | Season number | `(?P<season>\d{1,2})` |
| `<Episode>` | Episode number | `(?P<episode>\d{1,3})` |
| `<Episode Name>` | Episode title | `(?P<title>.+?)` |
| `<Air Date>` | YYYY-MM-DD | `(?P<air_date>\d{4}-\d{2}-\d{2})` |
| `<Quality>` | Resolution/quality string | `(?P<quality>(?:480|720|1080|2160)p|4K|8K)` |
| `<Source>` | Source token | `(?P<source>WEB[-_. ]?DL|BluRay|HDTV|AMZN|NF)` |
| `<Release Group>` | Scene group suffix | `(?P<group>-[A-Za-z0-9]+)$` |
| `<Edition>` | Edition/cut info | `(?P<edition>{edition-[^}]+})` |

These fragments should be combined with separator-aware helpers that treat `.`, `_`, space, and `-` as equivalent boundaries.

