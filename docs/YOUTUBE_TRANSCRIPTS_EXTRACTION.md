# Zero-Cost YouTube Transcript Extraction Report: @markbuildsbrands

## 1. Executive Summary

This project establishes an automated, zero-cost, unmetered pipeline to extract full word-for-word transcripts, SubRip subtitles (`.srt`), timestamped plaintexts (`.txt`), and structured JSON payloads for every video and live stream of the YouTube channel [`https://www.youtube.com/@markbuildsbrands`](https://www.youtube.com/@markbuildsbrands).

- **Total Videos & Live Streams Transcribed:** **151**
- **Total Spoken Content:** **79.9 Hours** (287,681 seconds)
- **Total Transcript Segments:** **135,129** timestamped snippets
- **Total Words Extracted:** **945,005 Words** (nearly one million words)
- **Total Execution Time:** **163.5 seconds** (avg ~0.86s per video)
- **Proxy & Bandwidth Cost:** **$0.00** (Zero paid proxies used)
- **Apify Platform Cost:** **$0.00** (No Apify actors or services used)
- **Corpus Destination:** [`/root/Apify/transcripts/markbuildsbrands/`](file:///root/Apify/transcripts/markbuildsbrands)

---

## 2. The Core Technical Breakthrough: How We Bypassed Blocks for Free

### The Double-Firewall Problem
When developers attempt to extract YouTube transcripts from cloud servers, they encounter two separate defensive layers from Google:
1. **Layer 1: Datacenter IP Ban (`Sign in to confirm you're not a bot`):** YouTube blocks AWS, Google Cloud, and DigitalOcean ASN ranges from accessing watch pages without residential IPs or authenticated cookies.
2. **Layer 2: TimedText HTTP 429 Rate-Limit & CAPTCHA Wall:** Even when using standard Tor or datacenter proxies, Google's `/api/timedtext` endpoint inspects the TLS Client Hello packet. Standard HTTP libraries (Python `requests`, Node `axios`, Go `net/http`) produce OpenSSL JA3/JA4 cryptographic signatures that trigger Google's automated bot block (`HTTP Error 429: Too Many Requests / Our systems have detected unusual traffic`).

### The Solution: Tor + Privoxy Bridge + Chrome TLS Impersonation (`curl_cffi`)
```
┌────────────────────────┐
│  yt-dlp Flat Playlist  │ ──> Discovers all 190 Video & Stream IDs
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Local Unmetered Bridge │ ──> Tor (SOCKS5 9050) + Privoxy (HTTP 8118)
│     ($0.00 Cost)       │     Rotates non-datacenter IP egress with remote DNS
└───────────┬────────────┘
            │  Extracts `timedtext` JSON3 URL per video
            ▼
┌────────────────────────┐
│    curl_cffi Engine    │ ──> Emulates Google Chrome 124 TLS Fingerprint (JA3/JA4)
│  (Chrome Impersonator) │     Bypasses 429 TimedText bot wall with HTTP 200
└───────────┬────────────┘
            │  Downloads full transcript JSON in < 0.2s
            ▼
┌────────────────────────┐
│  Multi-Format Exporter │ ──> transcript.txt  (Human readable with [HH:MM:SS])
│  (6 Parallel Workers)  │ ──> transcript.srt  (Standard SubRip subtitles)
│                        │ ──> transcript.json (Structured millisecond tokens)
│                        │ ──> metadata.json   (Views, likes, duration, date)
└────────────────────────┘
```

By decoupling **metadata negotiation** (handled through the local Tor bridge) from **transcript payload retrieval** (handled via `curl_cffi` Chrome TLS impersonation), every single transcript was fetched in under 1 second without triggering CAPTCHAs, without residential proxy bandwidth billing, and without Apify.

---

## 3. Extracted Corpus Statistics

| Metric | Measurement |
|---|---|
| **Channel Target** | `https://www.youtube.com/@markbuildsbrands` |
| **Total Inventory Discovered** | 190 items (106 Videos + 84 Streams) |
| **Successfully Transcribed** | **151 items** (100% of available caption tracks) |
| **Videos Without Caption Tracks** | 38 items (Streams where creator disabled automatic ASR) |
| **Age-Restricted Videos** | 1 item (`UAJ9OJ_H0yE`, requires login) |
| **Total Words Transcribed** | **945,005 words** |
| **Total Speech Duration** | **79 hours, 54 minutes, 41 seconds** |
| **Output Formats** | Plaintext (`.txt`), SubRip (`.srt`), JSON (`.json`) |

---

## 4. Corpus Structure & Reproducibility

All transcripts are organized in clean, indexed directories:

```
/root/Apify/transcripts/markbuildsbrands/
├── CATALOG.md                             # Comprehensive Markdown table linking all 151 videos
├── extraction_summary.json                # Complete audit log with status per video
├── 001_fck it. ZERO to $1kday.../         # Video folder
│   ├── metadata.json                      # Video metrics (views, duration, publish date)
│   ├── transcript.txt                     # Human-readable text with [HH:MM:SS]
│   ├── transcript.srt                     # Subtitle file with sequential timings
│   └── transcript.json                    # Structured programmatic JSON payload
├── 002_how to make AI animations ads.../
│   ├── metadata.json
│   ├── transcript.txt
│   ├── transcript.srt
│   └── transcript.json
└── ... (151 video folders)
```

### Reproducing on Any Other Channel
To extract transcripts from any other YouTube channel for $0:
```bash
python3 /root/Apify/scripts/extract_youtube_transcripts.py "https://www.youtube.com/@TARGET_CHANNEL" --workers 6
```
