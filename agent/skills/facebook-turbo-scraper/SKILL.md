---
name: facebook-turbo-scraper
description: High-speed zero-token Facebook page, reels, and video extractor using unmetered Tor/Privoxy tunnels and embedded GraphQL payload extraction.
---

# Facebook Turbo Scraper

Extracts public Facebook posts, reels, video streams, and native subtitles without paying for Apify Actors.

## Capabilities

1. **Direct Payload Extraction**:
   - Parses server-rendered Relay/GraphQL JSON blobs from public Meta pages (`comet_sections`, `video_channel`).
   - Extracts direct CDN MP4 links (`browser_native_hd_url`, `browser_native_sd_url`) and embedded SRT captions.

2. **Cron Automation & State Tracking**:
   - Background execution via [`scripts/cron_facebook_1000.py`](file:///root/Apify/scripts/cron_facebook_1000.py).
   - Atomic state persistence in `state.json` avoids duplicate fetching across process restarts.

3. **Rate-Limit Resilience**:
   - Routes through Tor/Privoxy proxy layer (`127.0.0.1:8118`).
   - Handles localized redirection traps (e.g. mobile m.facebook redirection) seamlessly.
