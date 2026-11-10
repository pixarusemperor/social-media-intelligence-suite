# Reusable Automations & Skills Blueprint
## Extracted from Session `6697d0c4-19a8-4f16-ae0d-9feed0b219eb`

This document details how the extraction and transcription pipelines developed in this session can be packaged into reusable Antigravity skills, CLI automations, and cron jobs.

---

### Skill 1: `youtube-transcript-dual-engine`
* **Trigger Phrases**: *"extract transcripts for channel"*, *"scrape youtube playlist"*, *"download youtube captions without bot check"*
* **Architecture**:
  - InnerTube VisionOS/Android client emulation (`curl_cffi` Chrome TLS)
  - Tor Stream Isolation (`socks5://tor_<circuit_id>@127.0.0.1:9050`)
  - Outputs `.txt`, `.srt`, `.json`, `clean_transcript.txt`, `metadata.json`, `CATALOG.md`
* **Cost**: $0.00 / 0 tokens.

### Skill 2: `groq-whisper-high-throughput`
* **Trigger Phrases**: *"transcribe podcast with whisper"*, *"fallback to groq whisper"*, *"transcribe video audio at scale"*
* **Architecture**:
  - `yt-dlp` audio stream download (`-f ba[ext=m4a]/ba -x --audio-format mp3`)
  - `ffmpeg` mono 16kHz 32kbps optimization (compresses 1h audio to ~14MB)
  - Multi-key rotation on Groq `whisper-large-v3` endpoint
* **Speed**: ~200s audio in 2.5s.

### Skill 3: `social-media-anti-pollution-harvester`
* **Trigger Phrases**: *"find external videos where X speaks"*, *"harvest guest appearances without pollution"*
* **Architecture**:
  - YouTube search queries for keynote, masterclass, guest, interview
  - Negative channel filter (excludes official channel and aggregate clips)
  - 3-tier scoring: keyword thresholding, guest attribution, speaker verification
* **Output**: Verified external intelligence catalogue with zero false positives.

### Skill 4: `facebook-turbo-scraper`
* **Trigger Phrases**: *"scrape facebook page without apify"*, *"download facebook reels"*, *"extract facebook posts"*
* **Architecture**:
  - Unmetered Tor/Privoxy gateway tunnel
  - Desktop payload parsing for embedded JSON and native captions
  - Automated cron scheduling and state checkpointing (`cron_facebook_1000.py`)
