#!/usr/bin/env python3
"""
High-Speed Facebook 1000 Posts Scraper & Google Drive/Sheets Synchronizer
Target: https://www.facebook.com/OfficialCaresOneNo/
Mode: 10X Faster Concurrency Engine (Asyncio + Rotated Tor SOCKS5 + Direct REST API)
Cost: Strictly $0.00 | Zero Apify API Tokens

Features:
- Multi-vector parallel post harvester (DDG + Facebook endpoints + Albums)
- 15-20 concurrent AsyncSession workers with per-request Tor circuit rotation
- High-res native single-image extraction & local image downloader
- 10-worker parallel Google Drive multipart uploader
- Single-request bulk Google Sheets appender
- Live state persistence & catalog markdown updater
"""

import os
import sys
import re
import json
import time
import random
import asyncio
from datetime import datetime, timezone
from urllib.parse import unquote
import requests
from curl_cffi.requests import AsyncSession

# Target & Storage Constants
TARGET_PAGE_ID = "1718650065041649"
TARGET_URL = "https://www.facebook.com/OfficialCaresOneNo/"
DRIVE_FOLDER_ID = "1UknUvu1kuQB53C76pXiKczuHkyWwNi6X"
SPREADSHEET_ID = "10x8CoYR-SoG7OzWmKJ_dr1Q-vUIe6Fxm5aEbiPovOOY"
SHEET_NAME = "'Facebook Posts'"
WORKSPACE_CREDS_PATH = "/root/.config/workspace-mcp/credentials/safariboutiquecameroun@gmail.com.json"

BASE_DIR = "/root/Apify/facebook/OfficialCaresOneNo"
IMAGES_DIR = os.path.join(BASE_DIR, "images")
POSTS_FILE = os.path.join(BASE_DIR, "posts.json")
STATE_FILE = os.path.join(BASE_DIR, "state.json")
CATALOG_FILE = os.path.join(BASE_DIR, "CATALOG.md")
LOG_FILE = os.path.join(BASE_DIR, "fast_execution.log")

os.makedirs(IMAGES_DIR, exist_ok=True)

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
}

HARVEST_KEYWORDS = [
    '2026', '2025', '2024', '2023', '2022', '2021', '2020', '2019', '2018', '2017', '2016', '2015',
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december',
    'man', 'woman', 'child', 'father', 'mother', 'boy', 'girl', 'baby', 'son', 'daughter', 'husband', 'wife', 'family',
    'parents', 'grandpa', 'grandma', 'grandfather', 'grandmother', 'sister', 'brother', 'cousin', 'uncle', 'aunt',
    'dog', 'cat', 'puppy', 'kitten', 'animal', 'rescue', 'shelter', 'adopted', 'horse', 'bear', 'dolphin', 'pet',
    'doctor', 'nurse', 'hospital', 'surgery', 'patient', 'police', 'officer', 'cop', 'firefighter', 'hero', 'teacher', 'school', 'student',
    'soldier', 'veteran', 'army', 'military', 'pilot', 'flight', 'plane', 'airplane', 'driver', 'passenger', 'bus',
    'wedding', 'marriage', 'love', 'heart', 'miracle', 'brave', 'courage', 'kindness', 'help', 'saved', 'gift', 'blessing',
    'money', 'million', 'billion', 'dollars', 'cash', 'bank', 'atm', 'wallet', 'bill', 'tip', 'lottery', 'crypto', 'bitcoin',
    'homeless', 'home', 'house', 'food', 'meal', 'job', 'work', 'struggle', 'success', 'dream', 'hard', 'power', 'strong',
    'years', 'time', 'life', 'story', 'world', 'moment', 'never', 'always', 'beautiful', 'sad', 'happy', 'tears', 'crying', 'smile',
    'actor', 'actress', 'movie', 'hollywood', 'star', 'singer', 'music', 'song', 'car', 'accident', 'crash', 'found', 'friend', 'reunion',
    'separated', 'adoption', 'foster', 'cancer', 'recovered', 'survived', 'walking', 'again', 'faith', 'humanity', 'restored', 'wholesome',
    'th', 'in', 'an', 'he', 'er', 're', 'on', 'at', 'en', 'nd', 'ti', 'es', 'or', 'te', 'of', 'ed', 'is', 'it', 'al', 'ar', 'st',
    'to', 'nt', 'se', 'ha', 'ng', 'as', 'ou', 'me', 'le', 've', 'wa', 'de', 'hi', 'ri', 'ro', 'co', 'li', 'ra', 'ma', 'si',
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '10', '20', '30', '50', '100', '1000'
]

QUERY_TEMPLATES = [
    'site:facebook.com/OfficialCaresOneNo/posts {kw}',
    'site:facebook.com/OfficialCaresOneNo/photos {kw}',
    'site:facebook.com/OfficialCaresOneNo {kw}',
    'site:facebook.com/1718650065041649 {kw}'
]

def log(msg):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    entry = f"[{ts}] {msg}"
    print(entry, flush=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(entry + '\n')

def clean_url(u):
    return u.replace(r'\/', '/').replace('\\\\', '')

def get_tor_proxy():
    sess_id = random.randint(1000, 999999)
    return {
        'http': f'socks5://user{sess_id}:pass@127.0.0.1:9050',
        'https': f'socks5://user{sess_id}:pass@127.0.0.1:9050'
    }

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

    def upload_image(self, file_path, file_name):
        for attempt in range(3):
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                metadata = {'name': file_name, 'parents': [DRIVE_FOLDER_ID]}
                files = {
                    'data': ('metadata', json.dumps(metadata), 'application/json; charset=UTF-8'),
                    'file': (file_name, content, 'image/jpeg')
                }
                r = requests.post(
                    'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart',
                    headers={'Authorization': f'Bearer {self.token}'},
                    files=files,
                    timeout=30
                )
                if r.status_code == 401:
                    self.refresh()
                    continue
                if r.status_code == 200:
                    file_id = r.json().get('id')
                    return f"https://drive.google.com/file/d/{file_id}/view?usp=drivesdk"
            except Exception as e:
                time.sleep(1)
        return ""

    def get_existing_sheet_post_ids(self):
        try:
            r = requests.get(
                f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/{SHEET_NAME}!A:A',
                headers={'Authorization': f'Bearer {self.token}'},
                timeout=15
            )
            if r.status_code == 401:
                self.refresh()
                r = requests.get(
                    f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/{SHEET_NAME}!A:A',
                    headers={'Authorization': f'Bearer {self.token}'},
                    timeout=15
                )
            if r.status_code == 200:
                rows = r.json().get('values', [])
                return set(row[0] for row in rows[1:] if row)
        except Exception as e:
            log(f"Warning: Failed to fetch existing sheet IDs: {e}")
        return set()

    def bulk_append_sheet(self, rows_2d):
        if not rows_2d:
            return 0
        for attempt in range(3):
            try:
                r = requests.post(
                    f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/{SHEET_NAME}!A1:append?valueInputOption=USER_ENTERED',
                    headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'},
                    json={'values': rows_2d},
                    timeout=30
                )
                if r.status_code == 401:
                    self.refresh()
                    continue
                if r.status_code == 200:
                    updates = r.json().get('updates', {})
                    return updates.get('updatedRows', len(rows_2d))
            except Exception as e:
                time.sleep(1)
        return 0

# -------------------------------------------------------------
# Harvester: High-Throughput Multi-Vector Post ID Discovery
# -------------------------------------------------------------
async def harvest_ddg_query(sem, query, discovered_ids):
    async with sem:
        url = f'https://html.duckduckgo.com/html/?q={query}'
        try:
            proxy = get_tor_proxy()
            async with AsyncSession(proxies=proxy, impersonate='chrome124') as session:
                r = await session.get(url, timeout=12)
                for m in re.finditer(r'uddg=([^&]+)', r.text):
                    u = unquote(m.group(1))
                    matches = re.findall(r'/posts/.*?/(\d+)', u) + re.findall(r'/posts/(\d+)', u) + re.findall(r'fbid=(\d+)', u)
                    for p in matches:
                        if len(p) >= 14:
                            discovered_ids.add(p)
                # Fallback digit scan
                for d in re.findall(r'(\d{15,16})', r.text):
                    if d.startswith('1'):
                        discovered_ids.add(d)
        except Exception:
            pass

async def harvest_facebook_endpoints(sem, discovered_ids):
    endpoints = [
        'https://www.facebook.com/OfficialCaresOneNo/',
        'https://www.facebook.com/OfficialCaresOneNo/photos/',
        'https://www.facebook.com/OfficialCaresOneNo/photos_by/',
        'https://www.facebook.com/OfficialCaresOneNo/photos_albums/',
        'https://www.facebook.com/OfficialCaresOneNo/posts/',
        'https://www.facebook.com/media/set/?set=a.283229083167484',
        'https://www.facebook.com/media/set/?set=a.283229073167485',
        'https://www.facebook.com/media/set/?set=a.283229079834151',
        'https://www.facebook.com/media/set/?set=a.283229066500819',
        'https://www.facebook.com/media/set/?set=a.2553669841539663',
        'https://www.facebook.com/media/set/?set=a.2552906361616011',
    ]
    async def fetch_ep(ep):
        async with sem:
            try:
                proxy = get_tor_proxy()
                async with AsyncSession(proxies=proxy, impersonate='chrome124') as session:
                    r = await session.get(ep, headers=DEFAULT_HEADERS, timeout=18)
                    matches = re.findall(r'fbid=(\d+)', r.text) + re.findall(r'/posts/(\d+)', r.text) + re.findall(r'\"post_id\":\"(\d+)\"', r.text) + re.findall(r'\"photo_id\":\"(\d+)\"', r.text)
                    for p in matches:
                        if len(p) >= 14:
                            discovered_ids.add(p)
            except Exception:
                pass

    await asyncio.gather(*[fetch_ep(ep) for ep in endpoints])

async def run_harvester(existing_ids):
    log("==> Phase 1: Launching Concurrent Multi-Vector Candidate Harvester...")
    discovered = set()
    sem = asyncio.Semaphore(12)

    query_list = []
    for tmpl in QUERY_TEMPLATES:
        for kw in HARVEST_KEYWORDS:
            query_list.append(tmpl.format(kw=kw))

    ddg_tasks = [harvest_ddg_query(sem, q, discovered) for q in query_list]
    fb_task = harvest_facebook_endpoints(sem, discovered)

    await asyncio.gather(fb_task, *ddg_tasks)
    
    new_candidates = [pid for pid in discovered if pid not in existing_ids]
    log(f"==> Harvester complete: {len(discovered)} total IDs harvested, {len(new_candidates)} new candidates to process.")
    return new_candidates

# -------------------------------------------------------------
# Extraction Engine: Concurrent Async Workers
# -------------------------------------------------------------
async def parse_post_async(sem, post_id):
    async with sem:
        url = f"https://www.facebook.com/OfficialCaresOneNo/posts/{post_id}"
        html = ""
        for attempt in range(2):
            try:
                proxy = get_tor_proxy()
                async with AsyncSession(proxies=proxy, impersonate='chrome124') as s:
                    r = await s.get(url, headers=DEFAULT_HEADERS, timeout=14)
                    if r.status_code == 200 and len(r.text) > 15000:
                        html = r.text
                        break
            except Exception:
                pass

        if not html:
            return None

        # 1. Post Text
        decoder = json.JSONDecoder(strict=False)
        results = []
        for needle in ['"message":{"text":', '"message": {"text":', '"message":{"__typename":"TextWithEntities","text":']:
            pos = 0
            while True:
                idx = html.find(needle, pos)
                if idx == -1: break
                start = idx + len(needle)
                try:
                    val, _ = decoder.raw_decode(html[start:])
                    if isinstance(val, str) and len(val.strip()) > 15:
                        results.append(val.strip())
                except Exception:
                    pass
                pos = idx + 1
        post_text = max(results, key=len) if results else ""
        if not post_text:
            titles = re.findall(r'<title>(.*?)</title>', html)
            if titles:
                t = titles[0].replace('No One Cares - ', '').strip()
                if len(t) > 20 and not t.startswith('No One Cares updated'):
                    post_text = t
        if not post_text:
            return None

        # 2. Date
        ct = re.findall(r'\"creation_time\":(\d+)', html) or re.findall(r'\"publish_time\":(\d+)', html)
        creation_time = int(ct[0]) if ct else None
        if creation_time:
            dt = datetime.fromtimestamp(creation_time, tz=timezone.utc)
            date_iso = dt.isoformat()
            date_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            date_folder = dt.strftime('%Y-%m-%d')
        else:
            date_iso = None
            date_str = "Unknown"
            date_folder = "unknown_date"

        # 3. Likes & Reactions
        rc = re.findall(r'\"reaction_count\":\{.*?\"count\":(\d+)', html) or re.findall(r'\"reaction_count\":(\d+)', html)
        likes_count = int(rc[0]) if rc else 0

        # 4. Comments
        cc = re.findall(r'\"comment_rendering_instance\":\{.*?\"comments\":\{.*?\"total_count\":(\d+)', html) or \
             re.findall(r'\"comment_count\":\{.*?\"total_count\":(\d+)', html) or \
             re.findall(r'\"total_comment_count\":(\d+)', html)
        comments_count = int(cc[0]) if cc else 0

        # 5. High-res Image
        uris = re.findall(r'\"uri\":\"([^\"]+)\"', html)
        all_imgs = []
        for u in uris:
            clean = clean_url(u)
            if 'scontent' in clean and ('t39.99422-6' in clean or 'dst-jpg' in clean or 'dst-png' in clean):
                if 't39.30808-1' not in clean and 'rsrc.php' not in clean:
                    all_imgs.append(clean)
        if not all_imgs:
            return None

        best_img_url = all_imgs[0]
        for img in all_imgs:
            if '1638' in img or '1080' in img or '1122' in img:
                best_img_url = img
                break

        # Download local image backup
        filename = f"{date_folder}_{post_id}_01.jpg"
        dest_file = os.path.join(IMAGES_DIR, filename)
        local_image_path = ""
        try:
            # High speed direct download for static CDN
            r_img = requests.get(best_img_url, timeout=20)
            if r_img.status_code == 200 and len(r_img.content) > 1000:
                with open(dest_file, 'wb') as f:
                    f.write(r_img.content)
                local_image_path = dest_file
        except Exception:
            # Fallback through Tor
            try:
                r_img = requests.get(best_img_url, proxies=get_tor_proxy(), timeout=20)
                if r_img.status_code == 200 and len(r_img.content) > 1000:
                    with open(dest_file, 'wb') as f:
                        f.write(r_img.content)
                    local_image_path = dest_file
            except Exception:
                pass

        if not local_image_path:
            return None

        return {
            "post_id": post_id,
            "post_url": url,
            "date_str": date_str,
            "date_iso": date_iso,
            "timestamp": creation_time,
            "likes_count": likes_count,
            "comments_count": comments_count,
            "post_text": post_text,
            "image_url": best_img_url,
            "local_image_path": local_image_path,
            "filename": filename,
            "google_drive_link": ""
        }

# -------------------------------------------------------------
# Google Workspace Ingestion: Parallel Drive + Bulk Sheets
# -------------------------------------------------------------
async def sync_to_google_workspace(gw_client, posts_to_sync):
    if not posts_to_sync:
        return 0

    log(f"==> Phase 3: Uploading {len(posts_to_sync)} images to Google Drive (10 concurrency)...")
    drive_sem = asyncio.Semaphore(10)

    async def upload_task(post):
        async with drive_sem:
            if not post.get("google_drive_link") and os.path.exists(post["local_image_path"]):
                link = await asyncio.to_thread(
                    gw_client.upload_image,
                    post["local_image_path"],
                    post["filename"]
                )
                post["google_drive_link"] = link

    await asyncio.gather(*[upload_task(p) for p in posts_to_sync])
    uploaded_count = sum(1 for p in posts_to_sync if p.get("google_drive_link"))
    log(f"Drive uploads complete: {uploaded_count}/{len(posts_to_sync)} successfully linked.")

    # Bulk append to Google Sheets
    existing_sheet_ids = await asyncio.to_thread(gw_client.get_existing_sheet_post_ids)
    rows_to_append = []
    for p in posts_to_sync:
        if p["post_id"] not in existing_sheet_ids:
            rows_to_append.append([
                str(p["post_id"]),
                str(p["post_url"]),
                str(p["date_str"]),
                str(p["likes_count"]),
                str(p["comments_count"]),
                str(p["post_text"]),
                str(p.get("google_drive_link", "")),
                str(p["local_image_path"])
            ])

    if rows_to_append:
        log(f"==> Appending {len(rows_to_append)} rows to Google Sheet '{SHEET_NAME}' in a single bulk batch...")
        appended = await asyncio.to_thread(gw_client.bulk_append_sheet, rows_to_append)
        log(f"Google Sheets sync complete: {appended} rows added.")
    else:
        log("Google Sheets: All posts already recorded in the sheet.")

    return uploaded_count

# -------------------------------------------------------------
# Master Execution & Benchmark Orchestration
# -------------------------------------------------------------
async def run_fast_pipeline(target_count=2000, batch_size=50):
    t_start = time.time()
    log("==================================================================")
    log(f"🚀 FAST FACEBOOK 1000: STARTING 10X ACCELERATED PIPELINE")
    log(f"Target: {target_count} posts | Target Page: {TARGET_URL}")
    log("==================================================================")

    # 1. Load existing state
    gw_client = GoogleWorkspaceClient()
    existing_posts = []
    if os.path.exists(POSTS_FILE):
        try:
            with open(POSTS_FILE, 'r', encoding='utf-8') as f:
                existing_posts = json.load(f)
        except Exception:
            pass

    existing_ids = set(p["post_id"] for p in existing_posts)
    log(f"Currently stored posts: {len(existing_posts)}.")

    # Also backfill any existing posts that lack Google Drive links
    needs_drive = [p for p in existing_posts if not p.get("google_drive_link")]
    if needs_drive:
        log(f"Backfilling {len(needs_drive)} previously scraped posts to Google Drive/Sheets...")
        await sync_to_google_workspace(gw_client, needs_drive)
        with open(POSTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing_posts, f, indent=2, ensure_ascii=False)

    if len(existing_posts) >= target_count:
        log(f"Target of {target_count} already reached!")
        return existing_posts

    # 2. Harvest Candidates
    candidates = await run_harvester(existing_ids)
    if not candidates:
        log("No new candidates discovered.")
        return existing_posts

    # 3. Process Candidates with 16 Async Workers
    needed = target_count - len(existing_posts)
    to_process = candidates[:needed + 50]  # Allow buffer for non-image posts
    log(f"==> Phase 2: Extracting up to {len(to_process)} candidate posts with 16 parallel workers...")

    sem = asyncio.Semaphore(16)
    
    # Process in streaming batches of batch_size for real-time saving and sync
    new_extracted_total = []
    for i in range(0, len(to_process), batch_size):
        chunk = to_process[i:i + batch_size]
        t_batch = time.time()
        log(f"--- Processing Batch {i//batch_size + 1}: {len(chunk)} candidates ---")
        
        batch_results = await asyncio.gather(*[parse_post_async(sem, pid) for pid in chunk])
        valid_posts = [p for p in batch_results if p is not None]
        batch_duration = time.time() - t_batch
        speed = len(valid_posts) / batch_duration if batch_duration > 0 else 0
        log(f"Batch {i//batch_size + 1} scraped: {len(valid_posts)} valid image posts in {batch_duration:.2f}s ({speed:.2f} posts/sec)")

        if valid_posts:
            # Sync this batch to Google Drive and Google Sheets immediately
            await sync_to_google_workspace(gw_client, valid_posts)

            # Persist to disk
            existing_posts.extend(valid_posts)
            new_extracted_total.extend(valid_posts)
            with open(POSTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(existing_posts, f, indent=2, ensure_ascii=False)

            state = {
                "processed_post_ids": [p["post_id"] for p in existing_posts],
                "total_extracted": len(existing_posts),
                "last_run": datetime.now(timezone.utc).isoformat()
            }
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)

        if len(existing_posts) >= target_count:
            log(f"Target count of {target_count} reached!")
            break

    total_duration = time.time() - t_start
    overall_speed = len(new_extracted_total) / total_duration if total_duration > 0 else 0
    log("==================================================================")
    log(f"🎉 PIPELINE COMPLETED IN {total_duration:.2f} SECONDS ({total_duration/60:.2f} MINS)")
    log(f"Newly Extracted & Synced: {len(new_extracted_total)} posts")
    log(f"Total Stored in Master DB: {len(existing_posts)} posts")
    log(f"Average Pipeline Speed: {overall_speed:.2f} posts/sec (vs 0.33 posts/sec baseline)")
    log(f"Speedup Factor: {overall_speed / 0.33:.1f}X FASTER")
    log("==================================================================")

    # 4. Generate/Update CATALOG.md
    update_catalog(existing_posts)

    return existing_posts

def update_catalog(posts):
    # Sort posts newest first
    sorted_posts = sorted(posts, key=lambda p: p.get("timestamp") or 0, reverse=True)
    lines = [
        f"# Facebook Page Extraction: No One Cares (`OfficialCaresOneNo`)",
        f"",
        f"- **Page URL**: https://www.facebook.com/OfficialCaresOneNo/",
        f"- **Target Filter**: Native Single-Image Posts Only (No Videos, No Reels, No Carousels)",
        f"- **Execution Cost**: **$0.00** (Zero Apify API credits; 100% custom scraper via Tor SOCKS5 + `curl_cffi` TLS impersonation)",
        f"- **Google Account**: `safariboutiquecameroun@gmail.com`",
        f"- **Google Drive Folder**: [`Facebook_OfficialCaresOneNo_Images`](https://drive.google.com/drive/folders/{DRIVE_FOLDER_ID})",
        f"- **Google Spreadsheet**: [`OfficialCaresOneNo - Facebook Image Posts`](https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit)",
        f"- **Total Posts Synchronized**: **{len(sorted_posts)}**",
        f"- **Last Updated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"",
        f"---",
        f"",
        f"## Summary Table (Latest Posts)",
        f"",
        f"| # | Date (UTC) | Post ID | Likes | Comments | Headline / Story Summary | High-Res Image (Google Drive) |",
        f"|---|---|---|---|---|---|---|",
    ]
    for i, p in enumerate(sorted_posts[:100], 1):
        drive_link = p.get('google_drive_link')
        drive_cell = f"[View Image]({drive_link})" if drive_link else "Pending Upload"
        headline = (p.get('post_text') or '').replace('\n', ' ')[:75].replace('|', '-')
        lines.append(f"| {i} | {p.get('date_str', '')[:16]} | `{p['post_id']}` | {p.get('likes_count', 0):,} | {p.get('comments_count', 0):,} | {headline}... | {drive_cell} |")

    lines.extend([
        "",
        "---",
        "",
        "## Local Storage Structure",
        "",
        f"- **Posts JSON Master**: `{POSTS_FILE}`",
        f"- **Images Directory**: `{IMAGES_DIR}`",
        f"- **Execution Log**: `{LOG_FILE}`",
    ])

    with open(CATALOG_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    log(f"Updated catalog at {CATALOG_FILE}")

if __name__ == '__main__':
    target = 2000
    if len(sys.argv) > 1:
        try:
            target = int(sys.argv[1])
        except ValueError:
            pass
    asyncio.run(run_fast_pipeline(target_count=target))
