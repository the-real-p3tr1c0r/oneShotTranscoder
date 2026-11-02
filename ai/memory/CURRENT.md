# Current state

- Repository status: dormant.
- Added app overlay (`manifest+memory`) contract.
- Tool is a complete MKV-to-Apple-TV MP4 transcoder with GPU acceleration and subtitle OCR.
- Fixed macOS `arm64` bundled FFmpeg/ffprobe architecture mismatch (`[Errno 86] Bad CPU type in executable` without Rosetta 2):
  - `build.py` now fetches native `arm64` builds from `ffmpeg.martin-riedl.de` on Apple Silicon (`evermeet.cx` restricted to `x86_64`) and validates Mach-O architecture before bundling.
  - `transcoder/utils.py` now verifies that bundled `ffmpeg`/`ffprobe` binaries can execute on the host before caching/using them, falling back to runnable system binaries on `PATH`.
  - Patched local `/Applications/oneShotTranscoder.app` installation in place with native `arm64` `ffmpeg`/`ffprobe`.
- Added `--import` flag for macOS Apple TV (`TV.app`) integration (`transcoder/apple_tv_library.py`):
  - Queries `TV.app` via JXA before transcoding to skip movies or TV episodes that already exist in the library (avoiding duplicates and wasted transcoding).
  - Embeds MP4 `media_type` (`stik` atom: `10` for TV Show, `9` for Movie) and strips trailing dots before year suffixes in series names (e.g. `The.Agency.2024.`).
  - Automatically imports newly converted `.mp4` files into `TV.app`, sets track metadata (`mediaKind`, `show`, `seasonNumber`, `episodeNumber`, `year`), and removes the staging `.mp4` afterwards.

## Immediate priorities

- Keep dormant; no active feature development planned.
- Maintain metadata and configuration consistency.

## Open questions

- None.
