# Metadata Detection Rules

1. All MKV inputs must be classified as either `movie` or `tv_show`. When detection fails, default to `movie` and log `No typematch for metadata extraction, file name used`.
2. Built-in patterns must recognize naming conventions used by Radarr, Sonarr, Plex, Emby, Jellyfin, Kodi, Infuse, and common scene releases. Support tokens for `<Series Name>`, `<Movie Name>`, `<Episode Name>`, `<Year>`, `<Season>`, `<Episode>`, and `<video specs>`.
3. Allow users to override detection with a manual pattern. Respect the manual pattern before auto-detection.
4. Metadata must expose explicit names: `series_name`, `episode_title`, `movie_title`, `year`, `season_number`, `episode_number`. Prefer descriptive variable names.
5. When metadata is available, emit ffmpeg tags compatible with Apple TV: TV episodes retain `show`, `title`, `season_number`, `episode_sort`; movies use `title` and `date`.
6. Detection logic resides in a dedicated module and is shared across CLI and transcoding workflows. Changes must not break existing functionality.

