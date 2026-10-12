# System Architecture & Technical Deep-Dive

## 1. Problem Statement: YouTube Datacenter Blocking

When attempting to download YouTube live stream recordings from cloud environments (Google Cloud, AWS, DigitalOcean), standard extraction tools like `yt-dlp` encounter immediate blocks:

```text
ERROR: [youtube] [videoId]: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies for the authentication.
```

### Why Does This Happen?
1. **ASN Filtering:** YouTube monitors incoming requests to `/youtubei/v1/player`. If the client connects from an Autonomous System Number (ASN) assigned to a public datacenter or cloud provider, YouTube marks the session as high-risk and enforces `LOGIN_REQUIRED`.
2. **Cryptographic IP-Binding on Media Fragments:**
   YouTube media URLs (`googlevideo.com/videoplayback?...&ip=<IP>&...`) embed the requester's IP in the URL signature. If an HTTP request for media fragments comes from an IP that does not match the signed IP, Google returns `403 Forbidden`.
3. **Metered Proxy Cost Problem:**
   Commercial residential proxies and Apify video downloading actors charge metered rates (e.g. `$0.006 per 1 MB` or `$6.00 / GB`). For ~11.5 hours of video archives (~3.5 GB to 10 GB), metered solutions cost upwards of `$20–$60` per channel run.

---

## 2. The Solution: Dual-Layer Unmetered Local Gateway

To achieve **unlimited, zero-cost downloads** while maintaining 100% bypass reliability, we constructed a local two-tier routing gateway:

```
┌────────────────────────────────┐
│   yt-dlp (Extraction & Mux)    │
└───────────────┬────────────────┘
                │  HTTP / HTTPS Proxy Requests
                ▼
┌────────────────────────────────┐
│   Privoxy (Port 8118)          │
│   HTTP-to-SOCKS5 Forwarder     │
└───────────────┬────────────────┘
                │  SOCKS5 Protocol (forward-socks5t)
                ▼
┌────────────────────────────────┐
│   Tor Relay Service (Port 9050)│
│   Decentralized Non-DC Exit    │
└───────────────┬────────────────┘
                │  Encrypted Multi-Hop Circuit
                ▼
┌────────────────────────────────┐
│   YouTube CDN (GoogleVideo)    │
│   Non-Datacenter IP Recognized │
└────────────────────────────────┘
```

### Layer 1: Privoxy (HTTP Bridge on Port 8118)
`ffmpeg` has limitations handling direct SOCKS5 proxies for HTTP video segment streaming. Privoxy acts as a protocol bridge:
- Listens on `http://127.0.0.1:8118`.
- Forwards all traffic via Tor using `forward-socks5t / 127.0.0.1:9050 .`.
- Ensures both `yt-dlp` manifest queries and `ffmpeg` segment downloads flow through the exact same IP route, avoiding `403 Forbidden` signature mismatches.

### Layer 2: Tor Relay Daemon (Port 9050)
- Native Ubuntu package (`tor`).
- Provides dynamic IP rotation through decentralized exit relays.
- Completely free of bandwidth metering.

---

## 3. Metadata Extraction Engine (Apify Actor)

Rather than running heavy headless browsers on the host, we delegate metadata extraction to the official Apify Actor:
- **Actor:** [`streamers/youtube-scraper`](https://apify.com/streamers/youtube-scraper)
- **Target URL:** `https://www.youtube.com/@<channel>/streams`
- **Output:** Structured Apify Dataset containing:
  - Video ID, Direct URL
  - Broadcast Title, Full Description
  - Duration, Upload Date
  - View Count, Likes, Comments Count
  - Highest-resolution Thumbnail URL

This data is then ingested locally by `scripts/process_all_channels.py` to automatically scaffold the directory hierarchy and write `metadata.md` files.
