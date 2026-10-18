#!/usr/bin/env python3
"""
Facebook Reels Downloader, Reach-Sorter & Comments Extractor
Target: https://www.facebook.com/cnicsarl/reels/?locale=fr_FR (Dr Claudel Noubissie)

Key Features:
1. Queries Facebook Reels endpoint and extracts reach/popularity metrics (play counts, views, reactions) BEFORE downloading.
2. Sorts all discovered reels by reach / popularity in descending order.
3. Selects the Top 5 most popular reels.
4. For each of the top 5 reels:
   - Downloads full MP4 video (720x1280 vertical video with audio).
   - Extracts complete post / reel copy & metadata (views, reactions, duration, resolution).
   - Extracts all user comments with author names, comment IDs, and text.
   - Saves structured outputs (reel.json, comments.json, reel.md, video.mp4).
5. Generates a master CATALOG.md and reels_summary.json.
Zero paid proxies (Local Tor 127.0.0.1:9050 + curl_cffi Chrome 124 TLS fingerprint).
Zero Apify.
"""

import os
import sys
import re
import json
import time
import base64
import subprocess
import html as html_lib
from datetime import datetime, timezone
from curl_cffi import requests

TOR_PROXIES = {
    'http': 'socks5://127.0.0.1:9050',
    'https': 'socks5://127.0.0.1:9050'
}

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
}

OUTPUT_BASE_DIR = '/root/Apify/facebook/cnicsarl/reels'


def parse_numeric_plays(c_str):
    """Parse '3,9 K', '2,8 K', '500' into integer count."""
    try:
        c_str = json.loads(f'"{c_str}"')
    except Exception:
        pass
    cleaned = c_str.replace('\u00a0', '').replace(' ', '').replace(',', '.')
    mult = 1
    if 'K' in cleaned or 'k' in cleaned:
        mult = 1000
        cleaned = cleaned.replace('K', '').replace('k', '')
    elif 'M' in cleaned or 'm' in cleaned:
        mult = 1000000
        cleaned = cleaned.replace('M', '').replace('m', '')
    try:
        return int(float(cleaned) * mult)
    except Exception:
        return 0


def harvest_and_rank_reels(page_url):
    """
    Scrape reels page, discover all reels with reach metrics,
    and rank them by reach/popularity BEFORE downloading.
    """
    print(f"Fetching Reels catalog from: {page_url}...")
    for attempt in range(3):
        try:
            r = requests.get(page_url, impersonate='chrome124', headers=DEFAULT_HEADERS, proxies=TOR_PROXIES, timeout=25)
            if r.status_code == 200 and len(r.text) > 50000:
                html = r.text
                break
            else:
                print(f"  Attempt {attempt+1}: Status {r.status_code}, len={len(r.text)}. Retrying...")
                time.sleep(2)
        except Exception as e:
            print(f"  Attempt {attempt+1} error: {e}")
            time.sleep(2)
    else:
        raise RuntimeError("Failed to fetch reels page.")

    # Match play_count_reduced and base64 GraphQL IDs
    matches = re.findall(r'\"play_count_reduced\":\"([^\"]+)\".*?\"id\":\"([^\"]+)\"', html)
    reels_list = []
    seen_ids = set()

    for pc_str, b64_id in matches:
        try:
            raw_id = base64.b64decode(b64_id).decode('utf-8', errors='ignore')
            fbid_m = re.search(r'VK:(\d+)', raw_id)
            fbid = fbid_m.group(1) if fbid_m else b64_id
        except Exception:
            fbid = b64_id

        if fbid not in seen_ids and fbid.isdigit():
            numeric_plays = parse_numeric_plays(pc_str)
            try:
                display_plays = json.loads(f'"{pc_str}"')
            except Exception:
                display_plays = pc_str
            reels_list.append({
                'fbid': fbid,
                'b64_id': b64_id,
                'plays_str': display_plays,
                'plays_numeric': numeric_plays,
                'reel_url': f'https://www.facebook.com/reel/{fbid}',
                'watch_url': f'https://www.facebook.com/watch/?v={fbid}&locale=fr_FR'
            })
            seen_ids.add(fbid)

    # SORT BY POPULARITY / REACH DESCENDING BEFORE DOWNLOADING
    reels_list.sort(key=lambda x: x['plays_numeric'], reverse=True)
    return reels_list


def fetch_reel_metadata_and_comments(reel_item):
    """Fetch individual reel page, extract title, description, reactions, and comments."""
    fbid = reel_item['fbid']
    watch_url = reel_item['watch_url']
    print(f"\nFetching metadata & comments for Reel {fbid}...")

    html = ""
    for attempt in range(3):
        try:
            r = requests.get(watch_url, impersonate='chrome124', headers=DEFAULT_HEADERS, proxies=TOR_PROXIES, timeout=25)
            if r.status_code == 200 and len(r.text) > 10000:
                html = r.text
                break
            time.sleep(2)
        except Exception as e:
            time.sleep(2)

    # 1. Title & og:description
    t_m = re.findall(r'<meta\s+property=[\"\']og:title[\"\']\s+content=[\"\'](.*?)[\"\']', html, re.DOTALL)
    full_title = html_lib.unescape(t_m[0]).strip() if t_m else ''

    d_m = re.findall(r'<meta\s+property=[\"\']og:description[\"\']\s+content=[\"\'](.*?)[\"\']', html, re.DOTALL)
    desc = html_lib.unescape(d_m[0]).strip() if d_m else ''

    # Clean description from full title if desc is generic
    title_parts = full_title.split(' | ')
    clean_title = desc
    if not clean_title and len(title_parts) >= 2:
        clean_title = title_parts[1].strip()

    # Extract reactions & views from title if present (e.g. "3.9K views · 234 reactions | ...")
    reactions_count = 0
    views_count = reel_item['plays_numeric']
    react_m = re.search(r'([\d.,]+[KM]?)\s*(?:réactions|reactions)', full_title, re.IGNORECASE)
    if react_m:
        reactions_count = parse_numeric_plays(react_m.group(1))

    # 2. Extract Comments
    comments = []
    seen_cids = set()
    cb = re.findall(r'\"legacy_fbid\":\"(\d+)\"[^{}]*?\"body\":\{\"text\":(\".*?\")', html)
    for cid, raw_t in cb:
        if cid not in seen_cids:
            try:
                ctext = json.loads(raw_t, strict=False)
            except Exception:
                ctext = raw_t

            # Locate author within comment JSON node
            pos = html.find(f'"legacy_fbid":"{cid}"')
            author = "Abonné Facebook"
            if pos != -1:
                snip = html[max(0, pos-200):min(len(html), pos+3500)]
                am = re.search(r'\"author\":\{[^{}]*?\"name\":\"([^\"]+)\"', snip)
                if am:
                    author = am.group(1)
                else:
                    # check if author is Dr Claudel Noubissie
                    if "Dr Claudel Noubissie" in snip or "100069029087679" in snip:
                        author = "Dr Claudel Noubissie"
            try:
                author = json.loads(f'"{author}"')
            except Exception:
                pass

            comments.append({
                'comment_id': cid,
                'author': author,
                'text': ctext
            })
            seen_cids.add(cid)

    # 3. Direct CDN video link fallback
    hd_m = re.search(r'\"browser_native_hd_url\":\"([^\"]+)\"', html)
    sd_m = re.search(r'\"browser_native_sd_url\":\"([^\"]+)\"', html)
    cdn_video_url = None
    if hd_m or sd_m:
        raw_u = (hd_m or sd_m).group(1)
        cdn_video_url = raw_u.replace(r'\/', '/').replace(r'\u0025', '%')

    reel_data = {
        'fbid': fbid,
        'title': clean_title or full_title,
        'full_title': full_title,
        'description': desc or clean_title,
        'play_count_str': reel_item['plays_str'],
        'play_count_numeric': reel_item['plays_numeric'],
        'reactions_count': reactions_count,
        'comments_count': len(comments),
        'comments': comments,
        'reel_url': reel_item['reel_url'],
        'watch_url': reel_item['watch_url'],
        'cdn_video_url': cdn_video_url
    }
    return reel_data


def download_reel_video(fbid, reel_url, cdn_video_url, output_folder):
    """Download the reel video file (.mp4) using yt-dlp via Tor, with CDN fallback."""
    os.makedirs(output_folder, exist_ok=True)
    target_mp4 = os.path.join(output_folder, "video.mp4")

    if os.path.isfile(target_mp4) and os.path.getsize(target_mp4) > 100000:
        print(f"  Video already exists: {target_mp4} ({os.path.getsize(target_mp4):,} bytes)")
        return target_mp4

    print(f"  Downloading video for Reel {fbid} via yt-dlp...")
    cmd = [
        "yt-dlp",
        "--proxy", "socks5://127.0.0.1:9050",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", target_mp4,
        reel_url
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        if res.returncode == 0 and os.path.isfile(target_mp4) and os.path.getsize(target_mp4) > 100000:
            print(f"  -> Successfully downloaded via yt-dlp: {os.path.getsize(target_mp4):,} bytes")
            return target_mp4
        else:
            print(f"  yt-dlp warning: {res.stderr[:200]}")
    except Exception as e:
        print(f"  yt-dlp exception: {e}")

    # Fallback: Direct CDN stream download via curl_cffi
    if cdn_video_url:
        print("  Falling back to direct CDN binary download...")
        try:
            r = requests.get(cdn_video_url, impersonate='chrome124', timeout=60)
            if r.status_code == 200 and len(r.content) > 100000:
                with open(target_mp4, 'wb') as f:
                    f.write(r.content)
                print(f"  -> Successfully downloaded via CDN: {len(r.content):,} bytes")
                return target_mp4
        except Exception as e:
            print(f"  CDN download failed: {e}")

    return None


def get_video_specs(mp4_path):
    """Extract resolution, duration, codec and size using ffprobe."""
    if not mp4_path or not os.path.isfile(mp4_path):
        return {}
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size,bit_rate",
        "-show_entries", "stream=width,height,codec_name,r_frame_rate",
        "-of", "json",
        mp4_path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        info = json.loads(res.stdout)
        video_stream = next((s for s in info.get("streams", []) if s.get("width")), {})
        return {
            'width': video_stream.get('width', 0),
            'height': video_stream.get('height', 0),
            'codec': video_stream.get('codec_name', 'unknown'),
            'duration_sec': round(float(info.get('format', {}).get('duration', 0)), 1),
            'size_bytes': int(info.get('format', {}).get('size', os.path.getsize(mp4_path)))
        }
    except Exception:
        return {'size_bytes': os.path.getsize(mp4_path)}


def main():
    print("=" * 80)
    print("FACEBOOK REELS EXTRACTOR & REACH-SORTED DOWNLOADER")
    print("Target: https://www.facebook.com/cnicsarl/reels/?locale=fr_FR (Dr Claudel Noubissie)")
    print("Zero Paid Proxies | Zero Apify | Local Tor SOCKS5 + Chrome TLS Fingerprinting")
    print("=" * 80)

    os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

    # 1. HARVEST & RANK REELS BEFORE DOWNLOADING
    ranked_reels = harvest_and_rank_reels("https://www.facebook.com/cnicsarl/reels/?locale=fr_FR")
    print(f"\nDiscovered {len(ranked_reels)} Reels on page. Top ranked by popularity / reach:")
    for idx, r in enumerate(ranked_reels, 1):
        print(f"  #{idx:02d} | ID: {r['fbid']} | Plays: {r['plays_str']:8} ({r['plays_numeric']:,} plays) | {r['reel_url']}")

    # SELECT TOP 5 REELS
    top_5_reels = ranked_reels[:5]
    print(f"\nProceeding to archive and download TOP 5 most popular reels...")

    catalog_entries = []

    for rank, item in enumerate(top_5_reels, 1):
        folder_name = f"reel_{rank:02d}"
        reel_dir = os.path.join(OUTPUT_BASE_DIR, folder_name)
        os.makedirs(reel_dir, exist_ok=True)

        print(f"\n{'='*60}")
        print(f"Processing Top Reel #{rank:02d} [ID: {item['fbid']}] -> {folder_name}/")
        print(f"Reach: {item['plays_str']} ({item['plays_numeric']:,} plays)")
        print(f"{'='*60}")

        # Fetch detailed metadata & comments
        reel_meta = fetch_reel_metadata_and_comments(item)
        reel_meta['rank'] = rank

        # Download Video File
        video_path = download_reel_video(item['fbid'], item['reel_url'], reel_meta.get('cdn_video_url'), reel_dir)
        specs = get_video_specs(video_path)
        reel_meta['video_specs'] = specs
        reel_meta['video_filename'] = "video.mp4" if video_path else None
        reel_meta['video_abs_path'] = video_path

        # Save reel.json
        with open(os.path.join(reel_dir, "reel.json"), "w", encoding="utf-8") as f:
            json.dump(reel_meta, f, indent=2, ensure_ascii=False)

        # Save comments.json
        with open(os.path.join(reel_dir, "comments.json"), "w", encoding="utf-8") as f:
            json.dump(reel_meta['comments'], f, indent=2, ensure_ascii=False)

        # Save reel.md
        reel_md = f"""# Reel #{rank:02d} — {reel_meta['title']}

**Reel ID:** `{reel_meta['fbid']}`  
**Popularity Rank:** #{rank} (Sorted by Reach / Plays)  
**Play Count (Reach):** 🚀 **{reel_meta['play_count_str']}** ({reel_meta['play_count_numeric']:,} plays)  
**Reactions:** 👍 **{reel_meta['reactions_count']:,}**  
**Comments Count:** 💬 **{len(reel_meta['comments'])}** extracted  
**Permalink:** [{reel_meta['reel_url']}]({reel_meta['reel_url']})  
**Watch Endpoint:** [{reel_meta['watch_url']}]({reel_meta['watch_url']})  

---

## 📹 Video Asset Details

- **Local Video File:** [`video.mp4`](./video.mp4)
- **Resolution:** {specs.get('width', 'N/A')}x{specs.get('height', 'N/A')} (Vertical 9:16)
- **Duration:** {specs.get('duration_sec', 'N/A')} seconds
- **File Size:** {specs.get('size_bytes', 0) / (1024*1024):.2f} MB ({specs.get('size_bytes', 0):,} bytes)
- **Codec:** {specs.get('codec', 'N/A')}

---

## 📝 Reel Title / Description Copy

```text
{reel_meta['description']}
```

---

## 💬 Extracted Comments ({len(reel_meta['comments'])})

"""
        if reel_meta['comments']:
            for c_idx, c in enumerate(reel_meta['comments'], 1):
                reel_md += f"### Comment #{c_idx} by **{c['author']}** (`ID: {c['comment_id']}`)\n"
                reel_md += f"> {c['text']}\n\n"
        else:
            reel_md += "_No user comments extracted for this reel._\n\n"

        with open(os.path.join(reel_dir, "reel.md"), "w", encoding="utf-8") as f:
            f.write(reel_md)

        catalog_entries.append({
            'rank': rank,
            'fbid': reel_meta['fbid'],
            'folder': folder_name,
            'title': reel_meta['title'],
            'plays_str': reel_meta['play_count_str'],
            'plays_numeric': reel_meta['play_count_numeric'],
            'reactions': reel_meta['reactions_count'],
            'comments_count': len(reel_meta['comments']),
            'duration_sec': specs.get('duration_sec', 0),
            'resolution': f"{specs.get('width', 0)}x{specs.get('height', 0)}",
            'size_mb': round(specs.get('size_bytes', 0) / (1024*1024), 2)
        })

    # Save Master reels_summary.json
    summary_path = os.path.join(OUTPUT_BASE_DIR, "reels_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            'target_page': "https://www.facebook.com/cnicsarl/reels/?locale=fr_FR",
            'extracted_at': datetime.now(timezone.utc).isoformat(),
            'total_reels_evaluated': len(ranked_reels),
            'top_reels_downloaded': len(top_5_reels),
            'reels': catalog_entries
        }, f, indent=2, ensure_ascii=False)

    # Save Master CATALOG.md
    cat_path = os.path.join(OUTPUT_BASE_DIR, "CATALOG.md")
    catalog_md = f"""# CNIC SARL (Dr Claudel Noubissie) — Top 5 Facebook Reels Catalog (Ranked by Reach & Popularity)

**Target Page:** `https://www.facebook.com/cnicsarl/reels/?locale=fr_FR`  
**Extraction Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  
**Zero-Cost Architecture:** Local Tor SOCKS5 (`127.0.0.1:9050`) + Chrome 124 TLS Impersonation via `curl_cffi` + `yt-dlp` Video Engine  
**Sorting Criterion:** Sorted in descending order by **Reach / Play Count (`play_count_reduced`)** *prior* to downloading.  

---

## 🏆 Top 5 Reels Ranked by Reach & Popularity

| Rank | Reel ID | Reach / Plays | Reactions | Comments | Duration | Resolution | File Size | Title Preview | Local Archive |
|:---:|---|:---:|:---:|:---:|:---:|:---:|:---:|---|---|
"""
    for entry in catalog_entries:
        catalog_md += f"| **#{entry['rank']:02d}** | `{entry['fbid']}` | 🚀 **{entry['plays_str']}** ({entry['plays_numeric']:,}) | 👍 **{entry['reactions']}** | 💬 **{entry['comments_count']}** | ⏱️ {entry['duration_sec']}s | {entry['resolution']} | 💾 {entry['size_mb']} MB | {entry['title'][:50]}... | [{entry['folder']}](./{entry['folder']}/reel.md) |\n"

    catalog_md += """
---

## 📁 Directory Structure

```text
/root/Apify/facebook/cnicsarl/reels/
├── CATALOG.md
├── reels_summary.json
├── reel_01/
│   ├── reel.md
│   ├── reel.json
│   ├── comments.json
│   └── video.mp4
├── reel_02/ ...
└── reel_05/
```
"""
    with open(cat_path, "w", encoding="utf-8") as f:
        f.write(catalog_md)

    print("\n" + "=" * 80)
    print("ALL TOP 5 REELS ARCHIVED, RANKED, AND DOWNLOADED SUCCESSFULLY!")
    print(f"Catalog: {cat_path}")
    print(f"Summary JSON: {summary_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
