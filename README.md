# YouTube Live Stream Archival & Verification Pipeline

An end-to-end, cost-free, automated pipeline to archive, extract rich metadata, download, and rigorously verify YouTube live stream broadcasts across multiple channels.

```
       ┌────────────────────────┐
       │   Apify Cloud Actor    │
       │ streamers/youtube-     │
       │        scraper         │
       └───────────┬────────────┘
                   │  Full Structured Metadata & Thumbnails
                   ▼
       ┌────────────────────────┐
       │   Local File Engine    │
       │ /vitalnasser/          │
       │ /produitsdigitaux.../  │
       │ /nolimitvousdv/        │
       └───────────┬────────────┘
                   │
                   ▼
       ┌────────────────────────┐
       │ Zero-Cost Proxy Bridge │
       │ Tor:9050 + Privoxy:8118│
       └───────────┬────────────┘
                   │  Bypasses YouTube Datacenter Bot Protection
                   ▼
       ┌────────────────────────┐
       │   yt-dlp + ffmpeg      │
       │ Stream Demuxing & Mux  │
       └───────────┬────────────┘
                   │  High-Definition MP4 Videos (~3.4 GB)
                   ▼
       ┌────────────────────────┐
       │ 3-Tier Verification QA │
       │ Container + Duration + │
       │ Demux + Audio + Visual │
       └────────────────────────┘
```

---

## 🌟 Key Features

1. **Hybrid Architecture:**
   - **Apify Cloud Actor (`streamers/youtube-scraper`):** Extracts complete livestream inventories with zero browser overhead, capturing titles, full descriptions, publish dates, durations, view counts, likes, comments counts, and high-resolution thumbnails.
   - **Local Zero-Cost Download Gateway:** Routes traffic through a local Tor + Privoxy bridge (`http://127.0.0.1:8118`), completely bypassing YouTube's datacenter anti-bot verification without paying commercial metered proxy fees.
2. **Multi-Channel Support:**
   - Archiving live streams for `@vitalnasser`, `@produitsdigitauxtorif`, and `@nolimitvousdv`.
   - Automatic directory hierarchy: channel root → video folder → `metadata.md`, `metadata.json`, `thumbnail.jpg`, `preview_grid.jpg`, and the `.mp4` video.
3. **Automated 3-Tier Quality Assurance:**
   - **Tier 1:** Instant container and index table (`moov` atom) validation, audio/video dual-track presence check, and mathematical duration reconciliation against YouTube metadata (tolerance ≤ 0.5s).
   - **Tier 2:** Multi-point timeline seekability test (`10%`, `50%`, `90%`) and audio loudness/silence detection via ITU-R BS.1770 / `volumedetect`.
   - **Tier 3:** Visual proof generation: extracts a 4-quadrant contact sheet (`preview_grid.jpg`) sampled across the broadcast timeline to detect frozen or black screens.

---

## 📊 Archived Channels & Verification Results

### 1. `@vitalnasser` (All 4 Live Streams)
- **Archive Path:** `vitalnasser/`
- **Total Download Size:** ~2.42 GB

| Video Title | Video ID | Duration | Size | Resolution | Audio Level | Verdict |
|---|---|---|---|---|---|---|
| Jour 3/3 \|\| Mon cadeau pour l'Afrique... | `WHSAbye-2zg` | 02:29:07 | 518.7 MB | 720p @ 30fps | -23.3 dB (active) | **100% Verified** |
| Jour 1/3 \|\| Mes 3 secrets de réussite... | `brSksQmoFhQ` | 04:08:13 | 764.1 MB | 720p @ 30fps | -30.1 dB (active) | **100% Verified** |
| Jour Bonus | `0skjrBGauDs` | 01:59:31 | 469.0 MB | 720p @ 30fps | -22.8 dB (active) | **100% Verified** |
| Jour 2/3 \|\| On se lance de zéro... | `v4oR7k1HxMI` | 02:49:04 | 665.4 MB | 720p @ 30fps | -18.9 dB (active) | **100% Verified** |

### 2. `@produitsdigitauxtorif` (All Live Streams)
- **Archive Path:** `produitsdigitauxtorif/`
- **Total Download Size:** ~501.7 MB

| Video Title | Video ID | Duration | Size | Resolution | Audio Level | Verdict |
|---|---|---|---|---|---|---|
| De Simples Africains Génèrent Entre 1500€... | `1sb5k9uIGWI` | 01:52:19 | 501.7 MB | 720p @ 30fps | -18.2 dB (active) | **100% Verified** |

### 3. `@nolimitvousdv` (Latest Live Stream)
- **Archive Path:** `nolimitvousdv/`
- **Total Download Size:** ~480.8 MB

| Video Title | Video ID | Duration | Size | Resolution | Audio Level | Verdict |
|---|---|---|---|---|---|---|
| POURQUOI MÊME LES CÉLÉBRITÉS ONT DU MAL... | `macbYitqP_k` | 01:07:52 | 480.8 MB | **1080p @ 60fps** | -27.8 dB (active) | **100% Verified** |

---

## 🛠️ Repository Structure

```
.
├── README.md                          # Project documentation and summary
├── .env.example                       # Environment configuration template
├── .gitignore                         # Git exclusion rules (ignores >100MB MP4 binaries)
├── verification_report.json           # Machine-readable QA audit results
├── docs/
│   ├── ARCHITECTURE.md                # Deep-dive on Tor+Privoxy gateway & yt-dlp
│   ├── FAILURES_AND_CRITERIA.md       # Taxonomy of livestream failure modes
│   └── VERIFICATION_PIPELINE.md       # 3-Tier validation engineering guide
├── scripts/
│   ├── process_all_channels.py        # Fetches Apify datasets, creates folders & metadata
│   ├── download_videos.py             # Downloads MP4 video streams via unmetered proxy
│   └── verify_videos.py               # Runs automated 3-tier validation & generates visual grids
├── vitalnasser/                       # Channel 1 archive
├── produitsdigitauxtorif/             # Channel 2 archive
└── nolimitvousdv/                     # Channel 3 archive
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- Python 3.10+
- `ffmpeg` and `ffprobe` (v6.0+)
- `yt-dlp` (latest version)
- `tor` and `privoxy` (for zero-cost unmetered gateway)

### 2. Setup Unmetered Local Gateway
```bash
sudo apt-get update && sudo apt-get install -y tor privoxy
echo 'forward-socks5t / 127.0.0.1:9050 .' | sudo tee -a /etc/privoxy/config
sudo systemctl restart tor privoxy
```

### 3. Extract Metadata via Apify
```bash
python3 scripts/process_all_channels.py
```

### 4. Download Videos
```bash
# Download all channels
python3 scripts/download_videos.py all

# Or download a specific channel
python3 scripts/download_videos.py vitalnasser
```

### 5. Run Verification Pipeline
```bash
python3 scripts/verify_videos.py
```

---

## 📜 License
MIT License.
