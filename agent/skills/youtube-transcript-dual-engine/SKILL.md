---
name: youtube-transcript-dual-engine
description: Zero-cost YouTube transcript extraction engine using Tor stream isolation and InnerTube Android/VisionOS clients. Bypasses 429 rate limits and bot challenges without paid APIs or browser overhead.
---

# YouTube Transcript Dual Engine

High-performance, $0-cost extraction of native YouTube captions and transcripts at scale.

## Architecture & Capabilities

1. **Tor Stream Isolation**:
   - Rotates unique Tor circuits per request via `socks5://tor_<circuit_id>@127.0.0.1:9050` or through Privoxy at `127.0.0.1:8118`.
   - Never triggers global IP ban; bypasses Google/YouTube `timedtext` HTTP 429 rate limits.

2. **InnerTube Client Emulation**:
   - Emulates `ANDROID_TESTSUITE` or `VISIONOS` InnerTube clients with `curl_cffi` Chrome TLS impersonation (`impersonate="chrome124"`).
   - Extracts XML/JSON timedtext without launching Chromium/Puppeteer.

3. **Output Artifacts**:
   - For each video: `.txt` (clean dialogue text), `.srt` (timestamped subtitles), `metadata.json`, and catalog summary.

## Usage Script
Directly invoke [`scripts/youtube_playlist_transcriber.py`](file:///root/Apify/scripts/youtube_playlist_transcriber.py) with playlist or video ID:
```bash
python3 /root/Apify/scripts/youtube_playlist_transcriber.py --playlist <PLAYLIST_ID>
```
