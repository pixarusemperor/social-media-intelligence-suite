# 🌐 Zero-Cost Social Media Intelligence & Media Archival Suite

An enterprise-grade, $0.00-budget social media intelligence, data extraction, and media archival suite. Built with zero paid proxies, zero commercial scraping API subscriptions (no Apify tokens required), and automated quality-assurance pipelines.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Proxy Cost: $0.00](https://img.shields.io/badge/Proxy_Cost-$0.00_Free-brightgreen.svg)](#-zero-cost-network-architecture)
[![Code Style: Black](https://img.shields.io/badge/Code_Style-Clean-black.svg)](https://github.com/psf/black)

---

## 📑 Table of Contents

- [Architectural Overview](#-architectural-overview)
- [Zero-Cost Network Architecture](#-zero-cost-network-architecture)
- [Core Feature Modules](#-core-feature-modules)
  - [1. YouTube Livestream Archiving & 3-Tier Verification](#1-youtube-livestream-archiving--3-tier-verification)
  - [2. YouTube Channel Intelligence & Deep Comments Extraction](#2-youtube-channel-intelligence--deep-comments-extraction)
  - [3. YouTube Free Transcript Extraction Engine](#3-youtube-free-transcript-extraction-engine)
  - [4. Facebook Public Page Scraping (Posts, 123 Images, Comments)](#4-facebook-public-page-scraping-posts-123-images-comments)
  - [5. Facebook Reels Reach-Sorting & HD Video Downloader](#5-facebook-reels-reach-sorting--hd-video-downloader)
  - [6. 50 Social Media Extraction Alternatives & Decision Matrix](#6-50-social-media-extraction-alternatives--decision-matrix)
- [Repository Structure](#-repository-structure)
- [Quickstart & Installation](#-quickstart--installation)
- [CLI Reproduction Commands](#-cli-reproduction-commands)
- [Technical Documentation Index](#-technical-documentation-index)
- [License](#-license)

---

## 🏛️ Architectural Overview

```
                               ┌────────────────────────────────────────────────────────┐
                               │           Target Social Media Platforms                │
                               │  YouTube (Videos, Lives, Shorts, Transcripts, Comments)│
                               │  Facebook (Pages, Posts, Photos, Reels, Reach Metrics) │
                               └───────────────────────────┬────────────────────────────┘
                                                           │
                                                           ▼
                        ┌──────────────────────────────────────────────────────────────────┐
                        │             Zero-Cost Bypass & Traffic Transport                │
                        │  • Local Tor SOCKS5 Gateway (127.0.0.1:9050)                     │
                        │  • Privoxy HTTP/HTTPS Forwarder (127.0.0.1:8118)                 │
                        │  • curl_cffi Browser Impersonation (TLS JA3/JA4 + HTTP/2 Finger) │
                        │  • YouTube InnerTube API Direct Protocol Handshake               │
                        │  • Facebook Relay SSR Stream Chunk Decoding                      │
                        └───────────────────────────┬──────────────────────────────────────┘
                                                    │
                                                    ▼
                     ┌────────────────────────────────────────────────────────────────────────┐
                     │                       Extraction & Media Engines                       │
                     ├──────────────────────────┬─────────────────────────────┬───────────────┤
                     │  YouTube Intelligence    │    Facebook Intelligence    │ Livestream QA │
                     │  • Channel Audit         │  • Relay SSR Stream Parser  │ • ffprobe     │
                     │  • Video Metadata        │  • High-Res Image Pipeline  │ • volumedetect│
                     │  • Deep Comments Thread  │  • Reach-Ranked Reels       │ • Visual Grid │
                     │  • Subtitle Transcripts  │  • Reel Comments & HD MP4   │ • Checksums   │
                     └──────────────────────────┴──────────────┬──────────────┴───────────────┘
                                                               │
                                                               ▼
                     ┌────────────────────────────────────────────────────────────────────────┐
                     │                  Structured Output & Persistent Artifacts              │
                     │  • JSON Datasets (metadata.json, comments.json, channel_info.json)     │
                     │  • Markdown Catalogs (CATALOG.md, CHANNEL_OVERVIEW.md)                 │
                     │  • Multi-Format Subtitles (.srt, .txt, .json)                          │
                     │  • High-Res Image Assets & HD Video Binaries (720p/1080p)              │
                     └────────────────────────────────────────────────────────────────────────┘
```

---

## 🛡️ Zero-Cost Network Architecture

Commercial scraping proxies charge between **$2.50 to $15.00 per GB**, which quickly becomes prohibitive when archiving gigabytes of video streams and high-resolution images. This repository implements a robust, completely free network routing stack:

1. **Tor SOCKS5 Daemon (`127.0.0.1:9050`):** Provides unmetered, dynamic IP rotation that circumvents IP-level rate-limiting and datacenter subnet bans without costing a dime.
2. **Privoxy HTTP Forwarder (`127.0.0.1:8118`):** Bridges tools requiring standard HTTP/HTTPS proxies to Tor's SOCKS5 interface.
3. **`curl_cffi` TLS Impersonation:** Simulates exact Chrome 120/124 TLS fingerprints (ciphers, extensions, elliptic curves, and HTTP/2 settings) to bypass Cloudflare and Akamai bot management systems.
4. **Protobuf & SSR Stream Extraction:** Interacts directly with internal platform APIs (YouTube InnerTube and Facebook Relay SSR streams) rather than relying on heavy headless browsers.

---

## 🚀 Core Feature Modules

### 1. YouTube Livestream Archiving & 3-Tier Verification
- **Target Channels:**
  - `@vitalnasser` (4 complete broadcasts, 2.42 GB)
  - `@produitsdigitauxtorif` (1 complete broadcast, 501.7 MB)
  - `@nolimitvousdv` (26 live broadcasts cataloged, latest stream downloaded, 480.8 MB)
- **3-Tier Automated QA Pipeline:**
  - **Tier 1 (Container & Duration):** Validates MP4 `moov` atom integrity, dual-stream (AVC/AAC) synchronization, and duration matching within a 0.5-second tolerance.
  - **Tier 2 (Audio & Seekability):** Multi-point timeline seekability test (`10%`, `50%`, `90%`) and integrated audio loudness auditing via ITU-R BS.1770 (`volumedetect`).
  - **Tier 3 (Visual QA):** Automatically generates a 4-quadrant visual preview contact sheet (`preview_grid.jpg`) sampled across the broadcast to verify non-black, non-frozen video playback.
- **Reference Documentation:** [`docs/VERIFICATION_PIPELINE.md`](docs/VERIFICATION_PIPELINE.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), and [`docs/FAILURES_AND_CRITERIA.md`](docs/FAILURES_AND_CRITERIA.md).

### 2. YouTube Channel Intelligence & Deep Comments Extraction
- **Target Channel:** [`@markbuildsbrands`](https://www.youtube.com/@markbuildsbrands) (Mark Builds Brands)
- **Channel Inventory Audit:** Extracted complete channel inventory across all tabs:
  - **Total Uploads Identified:** 1,534 uploaded assets
  - **Regular Videos:** 106 long-form videos
  - **Shorts / Reels:** 1,344 vertical videos
  - **Livestreams:** 84 live broadcasts
  - **Community Posts:** 27 text/image posts
- **10-Video Deep Metadata & Comments Extraction:**
  - **Total Views:** 961,842 views
  - **Total Likes:** 33,267 likes
  - **Total Comments Extracted:** 1,291 full comment records (including parent-child replies, author channel URLs, like counts, and timestamps).
- **Data Location:** [`youtube/markbuildsbrands/`](youtube/markbuildsbrands/)
- **Reference Documentation:** [`docs/YOUTUBE_CHANNEL_AND_VIDEO_INTELLIGENCE.md`](docs/YOUTUBE_CHANNEL_AND_VIDEO_INTELLIGENCE.md).

### 3. YouTube Free Transcript Extraction Engine
- **Features:**
  - Extracts full closed captions and automatic speech recognition (ASR) transcripts directly from YouTube's InnerTube API.
  - 100% free with 0 paid proxies and no Apify tokens.
  - Generates 3 synchronized output formats:
    - **Clean Prose (`.txt`):** Formatted for LLM ingestion, semantic search, and summary generation.
    - **Standard Subtitles (`.srt`):** Complete SubRip timestamps for video editing and media players.
    - **Structured JSON (`.json`):** Full segment-by-segment timing (`start`, `dur`, `text`).
- **Data Location:** [`transcripts/`](transcripts/)
- **Reference Documentation:** [`docs/YOUTUBE_TRANSCRIPTS_EXTRACTION.md`](docs/YOUTUBE_TRANSCRIPTS_EXTRACTION.md).

### 4. Facebook Public Page Scraping (Posts, 123 Images, Comments)
- **Target:** [`cnicsarl`](https://www.facebook.com/cnicsarl/?locale=fr_FR) (Dr Claudel Noubissie — 330k+ followers)
- **Breakthrough Engineering:**
  - Circumvents Facebook's forced login modal without credentials.
  - Intercepts and parses Facebook's React 18 / Relay Server-Side Rendered (SSR) stream chunks (`bigpipe`, `preloader`, `require` modules).
  - Extracts 20 latest posts with:
    - Full post text and marketing copy.
    - **123 High-Resolution Original Photos** downloaded locally to disk.
    - Post permalinks, publish dates, reaction metrics, and comment counts.
    - Extracted user comments with author names, timestamps, and full comment body.
- **Data Location:** [`facebook/cnicsarl/`](facebook/cnicsarl/)
- **Reference Documentation:** [`docs/FACEBOOK_PAGE_POSTS_EXTRACTION.md`](docs/FACEBOOK_PAGE_POSTS_EXTRACTION.md).

### 5. Facebook Reels Reach-Sorting & HD Video Downloader
- **Target:** `cnicsarl` Facebook Reels
- **Pre-Download Reach Discovery:**
  - Decoded Facebook's embedded SSR GraphQL payloads to extract `play_count_reduced` (e.g. `24 K`, `18 K`, `12 K`) **before** downloading video binaries.
  - Algorithmic reach sorting by popularity prior to consuming disk space or bandwidth.
- **Top 5 Reels Downloaded:**
  - Extracted 265 MB of clean, high-definition (720p HD) progressive MP4 video streams.
  - Fully archived without watermarks.
  - Extracted comments and user discussions for each reel.
- **Data Location:** [`facebook/cnicsarl/reels/`](facebook/cnicsarl/reels/)
- **Reference Documentation:** [`docs/FACEBOOK_REELS_REACH_AND_DOWNLOAD.md`](docs/FACEBOOK_REELS_REACH_AND_DOWNLOAD.md).

### 6. 50 Social Media Extraction Alternatives & Decision Matrix
- A comprehensive evaluation matrix covering 50 alternative ways to extract social media data (Facebook, TikTok, Instagram, YouTube, Reddit, X/Twitter, etc.) without Apify or paid proxies.
- Evaluated and ranked on a 100-point scale across 5 criteria:
  1. Reliability & Stability (25 pts)
  2. Maintenance Overhead (20 pts)
  3. Cost & Proxy Independence (25 pts)
  4. Data Completeness & Media Support (15 pts)
  5. Ban & Bot Detection Risk (15 pts)
- **Reference Documentation:** [`docs/50_SOCIAL_MEDIA_EXTRACTION_ALTERNATIVES.md`](docs/50_SOCIAL_MEDIA_EXTRACTION_ALTERNATIVES.md).

---

## 📂 Repository Structure

```
.
├── README.md                                  # Unified master documentation
├── LICENSE                                    # MIT Open Source License
├── requirements.txt                           # Core Python dependencies
├── .env.example                               # Optional environment variable template
├── .gitignore                                 # Clean exclusion rules (excludes >100MB MP4s & cache)
├── verification_report.json                   # Machine-readable 3-Tier QA verification report
│
├── docs/                                      # Comprehensive Engineering Documentation
│   ├── 50_SOCIAL_MEDIA_EXTRACTION_ALTERNATIVES.md # 50 Scraper alternatives matrix & ranking
│   ├── ARCHITECTURE.md                        # Unmetered Tor+Privoxy gateway & networking
│   ├── FACEBOOK_PAGE_POSTS_EXTRACTION.md      # Facebook Relay SSR scraping reverse-engineering
│   ├── FACEBOOK_REELS_REACH_AND_DOWNLOAD.md   # Facebook Reels pre-download reach & HD downloading
│   ├── FAILURES_AND_CRITERIA.md               # Livestream failure taxonomy & QA criteria
│   ├── VERIFICATION_PIPELINE.md               # 3-Tier validation engineering guide
│   ├── YOUTUBE_CHANNEL_AND_VIDEO_INTELLIGENCE.md # YouTube channel & deep comments documentation
│   └── YOUTUBE_TRANSCRIPTS_EXTRACTION.md      # YouTube InnerTube transcript extraction guide
│
├── scripts/                                   # Production-Ready CLI Extraction Engines
│   ├── download_facebook_reels.py             # Facebook Reels reach discovery & HD video downloader
│   ├── download_videos.py                     # YouTube livestream unmetered downloader
│   ├── extract_facebook_posts.py              # Facebook page posts, high-res images & comments
│   ├── extract_youtube_channel.py             # YouTube channel inventory, videos & deep comments
│   ├── extract_youtube_transcripts.py         # YouTube InnerTube transcript scraper (.srt, .txt, .json)
│   ├── generate_catalog.py                    # Catalog generator utility
│   ├── process_all_channels.py                # YouTube livestream cataloger
│   └── verify_videos.py                       # Automated 3-tier video QA validator
│
├── facebook/                                  # Facebook Extracted Data & Assets
│   └── cnicsarl/                              # Public page archive (Dr Claudel Noubissie)
│       ├── CATALOG.md                         # Markdown catalog of 20 extracted posts
│       ├── posts_summary.json                 # Aggregated JSON metadata for all 20 posts
│       ├── post_01/ ... post_20/              # Individual post folders:
│       │   ├── post.md                        # Clean post documentation
│       │   ├── post.json                      # Structured post metadata
│       │   ├── comments.json                  # Extracted comments array
│       │   └── images/                        # High-resolution JPEG images (123 total)
│       └── reels/                             # Top Facebook Reels by Reach
│           ├── CATALOG.md                     # Markdown catalog of reach-sorted reels
│           ├── reels_summary.json             # Aggregated JSON metrics
│           └── reel_01/ ... reel_05/          # Top 5 reels folders (metadata, comments, video.mp4)
│
├── youtube/                                   # YouTube Channel & Video Intelligence
│   └── markbuildsbrands/                      # Target: Mark Builds Brands
│       ├── CHANNEL_OVERVIEW.md                # Channel profile, bio & 1,534 uploads audit
│       ├── channel_info.json                  # Full structured channel metadata
│       ├── community_posts.json               # Extracted community posts
│       └── videos/                            # 10 Latest Videos & Deep Comments
│           ├── CATALOG.md                     # Markdown comparison catalog (views, likes, comments)
│           ├── videos_summary.json            # Aggregated performance metrics
│           └── video_01/ ... video_10/        # Individual video folders:
│               ├── video.md                   # Full video copy, metadata, and comments log
│               ├── video.json                 # Structured video metadata
│               └── comments.json              # Full extracted comments array (1,291 comments total)
│
├── transcripts/                               # Extracted YouTube Transcripts
│   ├── markbuildsbrands/                      # Clean .txt, .srt, and .json transcripts
│   └── raw/                                   # Original timestamped caption segments
│
├── vitalnasser/                               # YouTube Livestreams Archive 1 (4 broadcasts)
├── produitsdigitauxtorif/                     # YouTube Livestreams Archive 2 (1 broadcast)
└── nolimitvousdv/                             # YouTube Livestreams Archive 3 (26 cataloged)
```

---

## 🛠️ Quickstart & Installation

### 1. Prerequisites
- Linux / macOS / WSL
- Python 3.10+
- `ffmpeg` and `ffprobe` (v6.0+)
- `tor` and `privoxy` (for zero-cost unmetered traffic routing)

### 2. Install Dependencies
```bash
# Clone the repository
git clone https://github.com/pixarusemperor/social-media-intelligence-suite.git
cd social-media-intelligence-suite

# Install Python requirements
pip install -r requirements.txt
```

### 3. Start Unmetered Proxy Bridge (Optional but Recommended)
```bash
sudo apt-get update && sudo apt-get install -y tor privoxy
echo 'forward-socks5t / 127.0.0.1:9050 .' | sudo tee -a /etc/privoxy/config
sudo systemctl restart tor privoxy
```

---

## 💻 CLI Reproduction Commands

### Extract YouTube Channel & Deep Comments
```bash
# Extract the 10 latest videos and all comment threads from any channel
python3 scripts/extract_youtube_channel.py \
  --channel-url "https://www.youtube.com/@markbuildsbrands/videos" \
  --limit 10 \
  --output-dir "youtube/markbuildsbrands/videos" \
  --proxy "socks5://127.0.0.1:9050"
```

### Extract YouTube Transcripts (Subtitles)
```bash
# Extract transcripts in clean .txt, .srt, and .json without paid proxies
python3 scripts/extract_youtube_transcripts.py \
  --channel "https://www.youtube.com/@markbuildsbrands" \
  --output-dir "transcripts/markbuildsbrands" \
  --proxy "socks5://127.0.0.1:9050"
```

### Extract Facebook Page Posts, Images & Comments
```bash
# Extract the 20 latest posts, download high-res photos and extract comments
python3 scripts/extract_facebook_posts.py \
  --page-url "https://www.facebook.com/cnicsarl/?locale=fr_FR" \
  --limit 20 \
  --output-dir "facebook/cnicsarl"
```

### Download Facebook Reels Sorted by Reach
```bash
# Pre-sort reels by play count and download top 5 HD videos + comments
python3 scripts/download_facebook_reels.py \
  --page-url "https://www.facebook.com/cnicsarl/?locale=fr_FR" \
  --top-n 5 \
  --output-dir "facebook/cnicsarl/reels"
```

### Download YouTube Livestreams & Run 3-Tier QA
```bash
# Download all archived livestream channels
python3 scripts/download_videos.py all

# Run automated 3-Tier validation and generate preview contact sheets
python3 scripts/verify_videos.py
```

---

## 📚 Technical Documentation Index

Detailed engineering write-ups and analysis reports are located in the [`docs/`](docs/) directory:

| Document | Description |
|---|---|
| [`docs/50_SOCIAL_MEDIA_EXTRACTION_ALTERNATIVES.md`](docs/50_SOCIAL_MEDIA_EXTRACTION_ALTERNATIVES.md) | Exhaustive 50-method matrix comparing scrapers across TikTok, Instagram, Facebook, YouTube, Reddit, X. |
| [`docs/FACEBOOK_PAGE_POSTS_EXTRACTION.md`](docs/FACEBOOK_PAGE_POSTS_EXTRACTION.md) | Reverse-engineering Facebook Relay SSR streaming chunks, unauthenticated scraping & comment parsing. |
| [`docs/FACEBOOK_REELS_REACH_AND_DOWNLOAD.md`](docs/FACEBOOK_REELS_REACH_AND_DOWNLOAD.md) | Pre-download reach discovery via `play_count_reduced` and HD video stream demuxing. |
| [`docs/YOUTUBE_TRANSCRIPTS_EXTRACTION.md`](docs/YOUTUBE_TRANSCRIPTS_EXTRACTION.md) | YouTube InnerTube API reverse engineering for zero-cost transcript extraction. |
| [`docs/YOUTUBE_CHANNEL_AND_VIDEO_INTELLIGENCE.md`](docs/YOUTUBE_CHANNEL_AND_VIDEO_INTELLIGENCE.md) | Multi-tab channel inventory audit, video performance metrics, and deep comment thread parsing. |
| [`docs/VERIFICATION_PIPELINE.md`](docs/VERIFICATION_PIPELINE.md) | Detailed 3-tier QA validation pipeline specification (containers, audio levels, preview grids). |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Tor + Privoxy proxy bridge architecture and network flow diagrams. |
| [`docs/FAILURES_AND_CRITERIA.md`](docs/FAILURES_AND_CRITERIA.md) | 10 livestream failure modes and scoring criteria for archival integrity. |

---

## ⚖️ License & Ethical Notice

This repository is distributed under the [MIT License](LICENSE). 

> [!NOTE]
> All extraction techniques implemented in this suite target publicly accessible data without bypassing authentication walls or capturing private information. Users are responsible for complying with the terms of service of respective platforms and applicable data privacy regulations.
