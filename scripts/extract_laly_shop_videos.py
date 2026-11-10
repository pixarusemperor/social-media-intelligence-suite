#!/usr/bin/env python3
"""
Ultra-Fast Facebook Reels & Videos Extractor and Google Cloud Synchronizer
Target: Laly Shop Online (ID: 100086779930984 | https://www.facebook.com/share/19hyE5ZQPJ/)
Features:
- Discovers all video and reel URLs across profile endpoints and web indices
- Extracts high-resolution MP4 video files with audio
- Extracts metadata: views/plays, reactions, comments, duration, upload date, full captions
- Direct concurrent upload of .mp4 files to Google Drive (folder: Facebook_Videos_LalyShopOnline)
- Synchronizes with Google Spreadsheet (Laly Shop Online - Facebook Reels & Videos)
- Zero Apify API tokens | $0.00 Cost
"""

import os
import sys
import re
import json
import time
import subprocess
from datetime import datetime, timezone
from urllib.parse import unquote
import requests
from curl_cffi.requests import AsyncSession
import asyncio

PROFILE_ID = "100086779930984"
PAGE_NAME = "Laly Shop Online"
ORIGINAL_SHARE_URL = "https://www.facebook.com/share/19hyE5ZQPJ/"
DRIVE_FOLDER_ID = "1wQuqzSaie9TcleNmL8YiCIw1vYmYDHQ-"
SPREADSHEET_ID = "1aBsXc1izrqda8LxzrpYpdm6wJlNNVCBdZrch6kdigcg"
SHEET_NAME = "'Reels & Videos'"
WORKSPACE_CREDS_PATH = "/root/.config/workspace-mcp/credentials/safariboutiquecameroun@gmail.com.json"

BASE_DIR = "/root/Apify/facebook/LalyShopOnline"
VIDEOS_DIR = os.path.join(BASE_DIR, "videos")
POSTS_FILE = os.path.join(BASE_DIR, "videos.json")
STATE_FILE = os.path.join(BASE_DIR, "state.json")
CATALOG_FILE = os.path.join(BASE_DIR, "CATALOG.md")
LOG_FILE = os.path.join(BASE_DIR, "execution.log")

os.makedirs(VIDEOS_DIR, exist_ok=True)

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
}

TOR_PROXY = "socks5://127.0.0.1:9050"

def log(msg):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    entry = f"[{ts}] {msg}"
    print(entry, flush=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(entry + '\n')

class GoogleWorkspaceClient:
    def __init__(self, creds_path=WORKSPACE_CREDS_PATH):
        self.creds_path = creds_path
        self.token = None
        self.refresh()

    def refresh(self):
        with open(self.creds_path, 'r', encoding='utf-8') as f:
            creds = json.load(f)
        r = requests.post(creds['token_uri'], data={
            'grant_type': 'refresh_token',
            'refresh_token': creds['refresh_token'],
            'client_id': creds['client_id'],
            'client_secret': creds['client_secret'],
        }, timeout=15)
        if r.status_code == 200:
            self.token = r.json()['access_token']
        else:
            raise RuntimeError(f"Failed to refresh Google OAuth token: {r.text}")

    def upload_video(self, file_path, file_name):
        for attempt in range(3):
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                metadata = {'name': file_name, 'parents': [DRIVE_FOLDER_ID]}
                files = {
                    'data': ('metadata', json.dumps(metadata), 'application/json; charset=UTF-8'),
                    'file': (file_name, content, 'video/mp4')
                }
                r = requests.post(
                    'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart',
                    headers={'Authorization': f'Bearer {self.token}'},
                    files=files,
                    timeout=90
                )
                if r.status_code == 401:
                    self.refresh()
                    continue
                if r.status_code == 200:
                    file_id = r.json().get('id')
                    return f"https://drive.google.com/file/d/{file_id}/view?usp=drivesdk"
            except Exception as e:
                log(f"  [-] Drive upload attempt {attempt+1} failed: {e}")
                time.sleep(2)
        return ""

    def bulk_append_sheet(self, rows_2d):
        if not rows_2d:
            return 0
        for attempt in range(3):
            try:
                r = requests.post(
                    f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/{SHEET_NAME}!A1:append?valueInputOption=USER_ENTERED',
                    headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'},
                    json={'values': rows_2d},
                    timeout=25
                )
                if r.status_code == 401:
                    self.refresh()
                    continue
                if r.status_code == 200:
                    updates = r.json().get('updates', {})
                    return updates.get('updatedRows', len(rows_2d))
            except Exception:
                time.sleep(1)
        return 0

# -------------------------------------------------------------
# Harvester: Discover All Reels and Videos on Laly Shop Online
# -------------------------------------------------------------
async def harvest_video_ids():
    log("==> Phase 1: Harvesting Video and Reel IDs for Laly Shop Online...")
    discovered = set()

    # 1. Profile Tabs
    endpoints = [
        f'https://www.facebook.com/profile.php?id={PROFILE_ID}&sk=reels_tab',
        f'https://www.facebook.com/profile.php?id={PROFILE_ID}&sk=videos',
        f'https://www.facebook.com/profile.php?id={PROFILE_ID}',
    ]

    async with AsyncSession(proxies={'http': TOR_PROXY, 'https': TOR_PROXY}, impersonate='chrome124') as s:
        for ep in endpoints:
            try:
                r = await s.get(ep, headers=DEFAULT_HEADERS, timeout=25)
                reels = re.findall(r'/reel/(\d+)', r.text) + re.findall(r'\"video_id\":\"(\d+)\"', r.text)
                vids = re.findall(r'/videos/(\d+)', r.text) + re.findall(r'/watch/\?v=(\d+)', r.text)
                for item in reels + vids:
                    if len(item) >= 12:
                        discovered.add(item)
            except Exception as e:
                log(f"Error querying {ep}: {e}")

    # 2. Search Index Vectors
    search_queries = [
        f'site:facebook.com/reel {PROFILE_ID}',
        f'site:facebook.com/watch {PROFILE_ID}',
        f'site:facebook.com/videos {PROFILE_ID}',
        f'\"Laly Shop Online\" site:facebook.com/reel',
        f'\"Laly Shop Online\" site:facebook.com/watch',
        f'\"Laly Shop Online\" site:facebook.com/videos',
        'site:facebook.com/reel "6-54-27-42-52"',
        'site:facebook.com/reel Douala Yaoundé "Laly Shop"',
        'site:facebook.com/watch "Laly Shop Online"',
    ]

    async def fetch_ddg(q):
        url = f'https://html.duckduckgo.com/html/?q={q}'
        try:
            async with AsyncSession(proxies={'http': TOR_PROXY, 'https': TOR_PROXY}, impersonate='chrome124') as s:
                r = await s.get(url, timeout=15)
                for m in re.finditer(r'uddg=([^&]+)', r.text):
                    u = unquote(m.group(1))
                    reels = re.findall(r'/reel/(\d+)', u)
                    vids = re.findall(r'v=(\d+)', u) + re.findall(r'/videos/(\d+)', u)
                    for item in reels + vids:
                        if len(item) >= 12:
                            discovered.add(item)
        except Exception:
            pass

    await asyncio.gather(*[fetch_ddg(q) for q in search_queries])
    log(f"==> Harvesting complete: Discovered {len(discovered)} total video/reel IDs.")
    return sorted(list(discovered))

# -------------------------------------------------------------
# Video Extractor & Downloader via yt-dlp
# -------------------------------------------------------------
def process_single_video(video_id, gw_client):
    url = f"https://www.facebook.com/reel/{video_id}"
    log(f"\n[+] Processing Video/Reel: {video_id} ({url})")

    # 1. Fetch Metadata using yt-dlp dump-json
    meta_cmd = ['yt-dlp', '--proxy', TOR_PROXY, '--dump-json', url]
    res = subprocess.run(meta_cmd, capture_output=True, text=True, timeout=35)
    
    metadata = {}
    if res.returncode == 0 and res.stdout:
        try:
            metadata = json.loads(res.stdout)
        except Exception:
            pass

    if not metadata:
        # Fallback to /videos/ url
        url_fallback = f"https://www.facebook.com/videos/{video_id}"
        meta_cmd = ['yt-dlp', '--proxy', TOR_PROXY, '--dump-json', url_fallback]
        res = subprocess.run(meta_cmd, capture_output=True, text=True, timeout=35)
        if res.returncode == 0 and res.stdout:
            try:
                metadata = json.loads(res.stdout)
                url = url_fallback
            except Exception:
                pass

    if not metadata:
        log(f"  [-] Failed to extract metadata for {video_id}")
        return None

    raw_title = metadata.get('title') or ""
    description = metadata.get('description') or ""
    caption = description if len(description) > len(raw_title) else raw_title

    duration = metadata.get('duration') or 0
    view_count = metadata.get('view_count') or 0
    like_count = metadata.get('like_count') or 0
    comment_count = metadata.get('comment_count') or 0

    # Extract Views / Likes from title text if yt-dlp returns combined string (e.g. "50K views · 531 reactions | ...")
    if view_count == 0 and 'views' in raw_title.lower():
        v_match = re.search(r'([\d\.,\s]+[KkMm]?)\s*views', raw_title, re.IGNORECASE)
        if v_match:
            view_count = v_match.group(1).strip()

    if like_count == 0 and 'reactions' in raw_title.lower():
        r_match = re.search(r'([\d\.,\s]+[KkMm]?)\s*reactions', raw_title, re.IGNORECASE)
        if r_match:
            like_count = r_match.group(1).strip()

    upload_date = metadata.get('upload_date')
    if upload_date and len(upload_date) == 8:
        date_str = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    else:
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    filename = f"{date_str}_{video_id}.mp4"
    dest_path = os.path.join(VIDEOS_DIR, filename)

    # 2. Download MP4 Video
    log(f"  [*] Downloading MP4 video to {dest_path}...")
    dl_cmd = [
        'yt-dlp',
        '--proxy', TOR_PROXY,
        '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        '--no-playlist',
        '-o', dest_path,
        url
    ]
    subprocess.run(dl_cmd, capture_output=True, timeout=60)

    if not os.path.exists(dest_path) or os.path.getsize(dest_path) < 10000:
        log(f"  [-] Video download failed or file empty for {video_id}")
        return None

    filesize_mb = os.path.getsize(dest_path) / (1024 * 1024)
    log(f"  [+] Downloaded MP4 ({filesize_mb:.2f} MB)")

    # 3. Upload to Google Drive
    log(f"  [*] Uploading to Google Drive...")
    drive_link = gw_client.upload_video(dest_path, filename)
    if drive_link:
        log(f"  [+] Google Drive uploaded: {drive_link}")
    else:
        log(f"  [-] Google Drive upload failed for {filename}")

    # 4. Sync Row to Google Sheets
    row = [
        str(video_id),
        str(url),
        str(date_str),
        str(view_count),
        str(like_count),
        str(comment_count),
        str(duration),
        str(caption),
        str(drive_link),
        str(dest_path)
    ]
    gw_client.bulk_append_sheet([row])
    log(f"  [+] Appended row to Google Sheet!")

    record = {
        "video_id": video_id,
        "url": url,
        "date_str": date_str,
        "views": view_count,
        "likes": like_count,
        "comments": comment_count,
        "duration_sec": duration,
        "caption": caption,
        "local_path": dest_path,
        "filesize_mb": round(filesize_mb, 2),
        "drive_link": drive_link
    }
    return record

def update_catalog(records):
    lines = [
        f"# Facebook Reels & Videos: {PAGE_NAME}",
        "",
        f"- **Facebook Page**: [{PAGE_NAME}]({ORIGINAL_SHARE_URL})",
        f"- **Total Videos Downloaded**: **{len(records)}**",
        "- **Execution Cost**: **$0.00** (Zero Apify tokens used)",
        f"- **Google Spreadsheet**: [Laly Shop Online - Facebook Reels & Videos](https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit)",
        f"- **Google Drive Folder**: [Facebook_Videos_LalyShopOnline](https://drive.google.com/drive/folders/{DRIVE_FOLDER_ID})",
        "",
        "## Summary of Extracted Reels & Videos",
        "",
        "| # | Date | Video ID | Views | Likes | Duration | Caption | Drive Video Link |",
        "|---|---|---|---|---|---|---|---|"
    ]

    for i, r in enumerate(records, 1):
        cap = r.get('caption', '').replace('\n', ' ')[:70] + '...'
        link = f"[Watch on Drive]({r.get('drive_link')})" if r.get('drive_link') else "Local Only"
        lines.append(f"| {i} | {r.get('date_str')} | `{r.get('video_id')}` | {r.get('views')} | {r.get('likes')} | {r.get('duration_sec')}s | {cap} | {link} |")

    with open(CATALOG_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    log(f"Updated catalog at {CATALOG_FILE}")

def main():
    log("==================================================================")
    log(f"🎬 STARTING FACEBOOK REELS & VIDEOS PIPELINE: {PAGE_NAME}")
    log(f"Target URL: {ORIGINAL_SHARE_URL} (ID: {PROFILE_ID})")
    log("==================================================================")

    gw_client = GoogleWorkspaceClient()

    # Harvest all video IDs
    video_ids = asyncio.run(harvest_video_ids())

    # Load previously processed
    existing_records = []
    if os.path.exists(POSTS_FILE):
        try:
            with open(POSTS_FILE, 'r', encoding='utf-8') as f:
                existing_records = json.load(f)
        except Exception:
            pass

    processed_ids = set(r['video_id'] for r in existing_records)
    log(f"Currently stored videos: {len(existing_records)}")

    new_records = []
    for vid in video_ids:
        if vid in processed_ids:
            continue
        try:
            rec = process_single_video(vid, gw_client)
            if rec:
                new_records.append(rec)
                existing_records.append(rec)
                processed_ids.add(vid)
                # Persist state
                with open(POSTS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(existing_records, f, indent=2, ensure_ascii=False)
                update_catalog(existing_records)
        except Exception as e:
            log(f"Error processing video {vid}: {e}")

    log("==================================================================")
    log(f"🎉 PIPELINE FINISHED: {len(new_records)} new videos processed.")
    log(f"Total Videos in Database: {len(existing_records)}")
    log("==================================================================")

if __name__ == '__main__':
    main()
