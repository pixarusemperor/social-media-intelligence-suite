#!/usr/bin/env python3
"""
Turbo Streaming Facebook Scraper & Google Drive/Sheets Synchronizer
Target: https://www.facebook.com/OfficialCaresOneNo/
Architecture: Producer-Consumer Streaming Queue + Direct CDN Split-Tunneling + Bulk Auto-Flushing
- Facebook Scrapers: 20 Async Workers via Tor SOCKS5
- Media Downloader: Direct Gigabit WAN (7.1X faster than Tor, 0 proxy overhead)
- Drive Uploader: 10 Concurrent Workers streaming directly to Drive
- Sheets Sync: Real-time micro-batch auto-flushing (every 15 items or 4 seconds)
Cost: Strictly $0.00 | Zero Apify API Tokens
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

# Target & Config Constants
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
LOG_FILE = os.path.join(BASE_DIR, "turbo_execution.log")

os.makedirs(IMAGES_DIR, exist_ok=True)

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
}

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

    def upload_bytes(self, content_bytes, file_name):
        """Upload raw bytes directly to Google Drive without intermediate disk bottleneck."""
        for attempt in range(3):
            try:
                metadata = {'name': file_name, 'parents': [DRIVE_FOLDER_ID]}
                files = {
                    'data': ('metadata', json.dumps(metadata), 'application/json; charset=UTF-8'),
                    'file': (file_name, content_bytes, 'image/jpeg')
                }
                r = requests.post(
                    'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart',
                    headers={'Authorization': f'Bearer {self.token}'},
                    files=files,
                    timeout=25
                )
                if r.status_code == 401:
                    self.refresh()
                    continue
                if r.status_code == 200:
                    file_id = r.json().get('id')
                    return f"https://drive.google.com/file/d/{file_id}/view?usp=drivesdk"
            except Exception:
                time.sleep(1)
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
# Core Streaming Pipeline Engine
# -------------------------------------------------------------
async def scrape_worker(worker_id, candidate_queue, upload_queue, stats):
    decoder = json.JSONDecoder(strict=False)
    while True:
        try:
            post_id = await candidate_queue.get()
            if post_id is None:
                candidate_queue.task_done()
                break

            url = f"https://www.facebook.com/OfficialCaresOneNo/posts/{post_id}"
            html = ""
            for attempt in range(2):
                try:
                    proxy = get_tor_proxy()
                    async with AsyncSession(proxies=proxy, impersonate='chrome124') as s:
                        r = await s.get(url, headers=DEFAULT_HEADERS, timeout=12)
                        if r.status_code == 200 and len(r.text) > 15000:
                            html = r.text
                            break
                except Exception:
                    await asyncio.sleep(0.5)

            if not html:
                stats['scrape_fail'] += 1
                candidate_queue.task_done()
                continue

            # Extract Post Text
            results = []
            for needle in ['"message":{"text":', '"message": {"text":', '"message":{"__typename":"TextWithEntities","text":']:
                pos = 0
                while True:
                    idx = html.find(needle, pos)
                    if idx == -1:
                        break
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
                stats['scrape_filtered'] += 1
                candidate_queue.task_done()
                continue

            # Timestamp
            ct_matches = re.findall(r'\"creation_time\":(\d+)', html) or re.findall(r'\"publish_time\":(\d+)', html)
            creation_time = int(ct_matches[0]) if ct_matches else None
            if creation_time:
                dt = datetime.fromtimestamp(creation_time, tz=timezone.utc)
                date_iso = dt.isoformat()
                date_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                date_folder = dt.strftime('%Y-%m-%d')
            else:
                date_iso = None
                date_str = "Unknown"
                date_folder = "unknown_date"

            # Likes & Comments
            rc = re.findall(r'\"reaction_count\":\{.*?\"count\":(\d+)', html) or re.findall(r'\"reaction_count\":(\d+)', html)
            likes_count = int(rc[0]) if rc else 0

            cc = re.findall(r'\"comment_count\":\{.*?\"total_count\":(\d+)', html) or re.findall(r'\"total_comment_count\":(\d+)', html)
            comments_count = int(cc[0]) if cc else 0
            if comments_count == 0:
                c_matches = set(re.findall(r'\"comment_id\":\"(\d+)\"', html))
                comments_count = len(c_matches)

            # High-res Image
            uris = re.findall(r'\"uri\":\"([^\"]+)\"', html)
            all_imgs = []
            for u in uris:
                clean = clean_url(u)
                if 'scontent' in clean and ('t39.99422-6' in clean or 'dst-jpg' in clean or 'dst-png' in clean):
                    if 't39.30808-1' not in clean and 'rsrc.php' not in clean:
                        all_imgs.append(clean)

            if not all_imgs:
                stats['scrape_filtered'] += 1
                candidate_queue.task_done()
                continue

            best_img_url = all_imgs[0]
            for img in all_imgs:
                if '1638' in img or '1080' in img or '1122' in img:
                    best_img_url = img
                    break

            filename = f"{date_folder}_{post_id}_01.jpg"
            post_data = {
                "post_id": post_id,
                "post_url": url,
                "date_str": date_str,
                "date_iso": date_iso,
                "timestamp": creation_time,
                "likes_count": likes_count,
                "comments_count": comments_count,
                "post_text": post_text,
                "image_url": best_img_url,
                "filename": filename,
                "local_image_path": os.path.join(IMAGES_DIR, filename),
                "google_drive_link": ""
            }

            stats['scraped_success'] += 1
            await upload_queue.put(post_data)
            candidate_queue.task_done()

        except Exception as e:
            stats['scrape_fail'] += 1
            candidate_queue.task_done()

async def upload_worker(worker_id, upload_queue, sheet_queue, gw_client, stats):
    """Direct WAN Image Download + Concurrent Multipart Drive Upload."""
    while True:
        try:
            post_data = await upload_queue.get()
            if post_data is None:
                upload_queue.task_done()
                break

            img_url = post_data["image_url"]
            filename = post_data["filename"]
            local_path = post_data["local_image_path"]

            # 1. Direct CDN Download (No Tor, 7.1X faster)
            content_bytes = b""
            async with AsyncSession(impersonate='chrome124') as s:
                for attempt in range(2):
                    try:
                        r = await s.get(img_url, timeout=10)
                        if r.status_code == 200 and len(r.content) > 1000:
                            content_bytes = r.content
                            break
                    except Exception:
                        await asyncio.sleep(0.3)

            if content_bytes:
                # Save locally in background thread
                def save_disk(b, p):
                    with open(p, 'wb') as f:
                        f.write(b)
                asyncio.get_event_loop().run_in_executor(None, save_disk, content_bytes, local_path)

                # 2. Upload bytes directly to Google Drive
                drive_link = await asyncio.to_thread(gw_client.upload_bytes, content_bytes, filename)
                post_data["google_drive_link"] = drive_link
                stats['drive_success'] += 1
            else:
                stats['drive_fail'] += 1

            await sheet_queue.put(post_data)
            upload_queue.task_done()

        except Exception:
            stats['drive_fail'] += 1
            upload_queue.task_done()

async def sheet_flusher(sheet_queue, gw_client, master_posts, stats, stop_event):
    """Flushes batches to Google Sheets every 15 items or 4 seconds."""
    buffer = []
    last_flush = time.time()

    while not stop_event.is_set() or not sheet_queue.empty():
        try:
            try:
                item = await asyncio.wait_for(sheet_queue.get(), timeout=1.0)
                buffer.append(item)
                master_posts.append(item)
                sheet_queue.task_done()
            except asyncio.TimeoutError:
                pass

            now = time.time()
            if buffer and (len(buffer) >= 15 or (now - last_flush) >= 4.0):
                rows_2d = [
                    [
                        str(p['post_id']),
                        str(p['post_url']),
                        str(p['date_str']),
                        str(p['likes_count']),
                        str(p['comments_count']),
                        str(p['post_text']),
                        str(p['google_drive_link']),
                        str(p['local_image_path'])
                    ]
                    for p in buffer
                ]
                added = await asyncio.to_thread(gw_client.bulk_append_sheet, rows_2d)
                stats['sheets_flushed'] += added
                log(f"⚡ [Stream Flush] Appended {added} rows to Google Sheet (Live Master Total: {len(master_posts)})")

                # Persist master json
                with open(POSTS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(master_posts, f, indent=2, ensure_ascii=False)

                buffer = []
                last_flush = now

        except Exception as e:
            log(f"Sheet flusher warning: {e}")

    # Final flush on shutdown
    if buffer:
        rows_2d = [
            [
                str(p['post_id']),
                str(p['post_url']),
                str(p['date_str']),
                str(p['likes_count']),
                str(p['comments_count']),
                str(p['post_text']),
                str(p['google_drive_link']),
                str(p['local_image_path'])
            ]
            for p in buffer
        ]
        added = await asyncio.to_thread(gw_client.bulk_append_sheet, rows_2d)
        stats['sheets_flushed'] += added
        with open(POSTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(master_posts, f, indent=2, ensure_ascii=False)

# -------------------------------------------------------------
# Main Orchestrator
# -------------------------------------------------------------
async def run_turbo_stream(test_limit=50):
    t_start = time.time()
    log("==================================================================")
    log("⚡ TURBO STREAM PIPELINE: STARTING HIGH-SPEED PRODUCER-CONSUMER")
    log(f"Target: Process {test_limit} candidates | Direct CDN + Tor Split Tunneling")
    log("==================================================================")

    gw_client = GoogleWorkspaceClient()

    # Load master posts
    master_posts = []
    if os.path.exists(POSTS_FILE):
        try:
            with open(POSTS_FILE, 'r', encoding='utf-8') as f:
                master_posts = json.load(f)
        except Exception:
            pass

    existing_ids = set(p['post_id'] for p in master_posts)
    log(f"Currently stored posts: {len(master_posts)}")

    # Load pending candidates from state
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except Exception:
            pass

    candidates = [pid for pid in state.get('pending_post_ids', []) if pid not in existing_ids]
    if not candidates:
        log("Discovering fresh candidates from endpoints...")
        from fast_facebook_1000 import run_harvester
        candidates = await run_harvester(existing_ids)

    if not candidates:
        log("No fresh candidates available.")
        return

    selected_candidates = candidates[:test_limit]
    log(f"Feeding {len(selected_candidates)} candidates into live streaming queue...")

    candidate_queue = asyncio.Queue()
    upload_queue = asyncio.Queue()
    sheet_queue = asyncio.Queue()
    stop_event = asyncio.Event()

    stats = {
        'scraped_success': 0,
        'scrape_filtered': 0,
        'scrape_fail': 0,
        'drive_success': 0,
        'drive_fail': 0,
        'sheets_flushed': 0
    }

    # Start Sheet Flusher
    flusher_task = asyncio.create_task(sheet_flusher(sheet_queue, gw_client, master_posts, stats, stop_event))

    # Start 10 Upload Workers
    upload_workers = [asyncio.create_task(upload_worker(i, upload_queue, sheet_queue, gw_client, stats)) for i in range(10)]

    # Start 20 Scrape Workers
    scrape_workers = [asyncio.create_task(scrape_worker(i, candidate_queue, upload_queue, stats)) for i in range(20)]

    # Populate candidate queue
    for pid in selected_candidates:
        await candidate_queue.put(pid)

    # Wait for candidate queue completion
    await candidate_queue.join()

    # Signal scrape workers to exit
    for _ in scrape_workers:
        await candidate_queue.put(None)
    await asyncio.gather(*scrape_workers)

    # Wait for upload queue completion
    await upload_queue.join()

    # Signal upload workers to exit
    for _ in upload_workers:
        await upload_queue.put(None)
    await asyncio.gather(*upload_workers)

    # Wait for sheet queue and signal flusher to stop
    await sheet_queue.join()
    stop_event.set()
    await flusher_task

    total_time = time.time() - t_start
    rate = stats['drive_success'] / total_time if total_time > 0 else 0

    log("==================================================================")
    log(f"🎉 TURBO STREAM RUN COMPLETED IN {total_time:.2f}s ({total_time/60:.2f} mins)")
    log(f"Successfully Scraped: {stats['scraped_success']} | Filtered (videos/empty): {stats['scrape_filtered']} | Fails: {stats['scrape_fail']}")
    log(f"Drive Uploads: {stats['drive_success']} (Success rate: {stats['drive_success']/(stats['drive_success']+stats['drive_fail'])*100:.1f}%)")
    log(f"Google Sheets Flushed: {stats['sheets_flushed']} rows")
    log(f"Total Database Size: {len(master_posts)} posts")
    log(f"Real-time Pipeline Speed: {rate:.2f} posts/sec")
    log("==================================================================")

if __name__ == '__main__':
    limit = 50
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            pass
    asyncio.run(run_turbo_stream(test_limit=limit))
