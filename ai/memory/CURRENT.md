# Current state

- Repository status: dormant.
- Added app overlay (`manifest+memory`) contract.
- Tool is a complete MKV-to-Apple-TV MP4 transcoder with GPU acceleration and subtitle OCR.
- Fixed macOS `arm64` bundled FFmpeg/ffprobe architecture mismatch (`[Errno 86] Bad CPU type in executable` without Rosetta 2):
  - `build.py` now fetches native `arm64` builds from `ffmpeg.martin-riedl.de` on Apple Silicon (`evermeet.cx` restricted to `x86_64`) and validates Mach-O architecture before bundling.
  - `transcoder/utils.py` now verifies that bundled `ffmpeg`/`ffprobe` binaries can execute on the host before caching/using them, falling back to runnable system binaries on `PATH`.
  - Patched local `/Applications/oneShotTranscoder.app` installation in place with native `arm64` `ffmpeg`/`ffprobe`.

## Immediate priorities

- Keep dormant; no active feature development planned.
- Maintain metadata and configuration consistency.

## Open questions

- None.
