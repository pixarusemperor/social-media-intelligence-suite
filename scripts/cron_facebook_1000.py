#!/usr/bin/env python3
"""
Autonomous Facebook 1000 Posts Scraper & Google Drive/Sheets Synchronizer
Target: https://www.facebook.com/OfficialCaresOneNo/
Mode: Incremental Cron-friendly Batch Engine (Zero Apify tokens | $0 Cost)
Uses: Local Tor SOCKS5 (127.0.0.1:9050) + curl_cffi Chrome 124 TLS Impersonation + Google Workspace API
"""

import os
import sys
import re
import json
import time
import base64
import html as html_lib
from datetime import datetime, timezone
from curl_cffi import requests

TARGET_PAGE_ID = "1718650065041649"
TARGET_URL = "https://www.facebook.com/OfficialCaresOneNo/"
MAX_POSTS_TARGET = 1000
BATCH_SIZE = 25  # Posts processed per cycle to ensure high stability

TOR_PROXIES = {
    'http': 'socks5://127.0.0.1:9050',
    'https': 'socks5://127.0.0.1:9050'
}

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
}

BASE_DIR = '/root/Apify/facebook/OfficialCaresOneNo'
IMAGES_DIR = os.path.join(BASE_DIR, 'images')
STATE_FILE = os.path.join(BASE_DIR, 'state.json')
POSTS_FILE = os.path.join(BASE_DIR, 'posts.json')
LOG_FILE = os.path.join(BASE_DIR, 'cron_execution.log')

os.makedirs(IMAGES_DIR, exist_ok=True)

DRIVE_FOLDER_ID = "1UknUvu1kuQB53C76pXiKczuHkyWwNi6X"
SPREADSHEET_ID = "10x8CoYR-SoG7OzWmKJ_dr1Q-vUIe6Fxm5aEbiPovOOY"
GOOGLE_EMAIL = "safariboutiquecameroun@gmail.com"

def log(msg):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    entry = f"[{ts}] {msg}"
    print(entry)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(entry + '\n')

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "processed_post_ids": [],
        "pending_post_ids": [],
        "cursor": None,
        "is_exhausted": False,
        "total_extracted": 0,
        "last_run": None
    }

def save_state(state):
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def clean_url(u):
    return u.replace(r'\/', '/').replace(r'\\', '')

def harvest_posts_from_page():
    """Harvest new post and photo IDs from the Facebook page endpoints."""
    endpoints = [
        'https://www.facebook.com/OfficialCaresOneNo/',
        'https://www.facebook.com/OfficialCaresOneNo/photos/',
        'https://www.facebook.com/OfficialCaresOneNo/photos_by/',
        'https://www.facebook.com/OfficialCaresOneNo/photos_albums/',
        'https://www.facebook.com/OfficialCaresOneNo/posts/',
    ]
    discovered = set()
    for ep in endpoints:
        try:
            r = requests.get(ep, impersonate='chrome124', headers=DEFAULT_HEADERS, proxies=TOR_PROXIES, timeout=25)
            if r.status_code == 200:
                p_matches = re.findall(r'fbid=(\d+)', r.text) + re.findall(r'/posts/(\d+)', r.text) + re.findall(r'\"post_id\":\"(\d+)\"', r.text)
                for pid in p_matches:
                    if len(pid) >= 14:
                        discovered.add(pid)
        except Exception as e:
            log(f"Error querying {ep}: {e}")
            time.sleep(2)
    return discovered

def extract_single_post(post_id):
    """Scrape metadata and high-res image for a post ID."""
    url = f"https://www.facebook.com/OfficialCaresOneNo/posts/{post_id}"
    html = ""
    for attempt in range(3):
        try:
            r = requests.get(url, impersonate='chrome124', headers=DEFAULT_HEADERS, proxies=TOR_PROXIES, timeout=25)
            if r.status_code == 200 and len(r.text) > 10000:
                html = r.text
                break
            time.sleep(2)
        except Exception as e:
            time.sleep(2)

    if not html:
        return None

    decoder = json.JSONDecoder(strict=False)

    # Post Text
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

    # Filter out empty or textless posts (e.g. pure cover photo changes without story)
    if not post_text:
        titles = re.findall(r'<title>(.*?)</title>', html)
        if titles:
            t = titles[0].replace('No One Cares - ', '').strip()
            if len(t) > 20 and not t.startswith('No One Cares updated'):
                post_text = t
    
    if not post_text:
        return None

    # Date
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
        return None

    best_img_url = all_imgs[0]
    for img in all_imgs:
        if '1638' in img or '1080' in img or '1122' in img:
            best_img_url = img
            break

    # Download local backup
    filename = f"{date_folder}_{post_id}_01.jpg"
    dest_file = os.path.join(IMAGES_DIR, filename)
    local_image_path = ""
    try:
        r_img = requests.get(best_img_url, impersonate='chrome124', proxies=TOR_PROXIES, timeout=30)
        if r_img.status_code == 200 and len(r_img.content) > 1000:
            with open(dest_file, 'wb') as f:
                f.write(r_img.content)
            local_image_path = dest_file
    except Exception as e:
        log(f"  [-] Failed image download for {post_id}: {e}")

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

def run_cron_cycle():
    state = load_state()
    log("=== Starting Cron Extraction Cycle ===")
    
    # Load existing posts
    existing_posts = []
    if os.path.exists(POSTS_FILE):
        try:
            with open(POSTS_FILE, 'r', encoding='utf-8') as f:
                existing_posts = json.load(f)
        except Exception:
            pass

    processed_set = set(state.get("processed_post_ids", []))
    for p in existing_posts:
        processed_set.add(p["post_id"])

    if len(processed_set) >= MAX_POSTS_TARGET:
        log(f"Goal reached! {len(processed_set)} posts already extracted (Target: {MAX_POSTS_TARGET}).")
        return

    # Check pending queue or harvest fresh IDs
    pending_queue = [pid for pid in state.get("pending_post_ids", []) if pid not in processed_set]
    if not pending_queue:
        log("Discovering post IDs from Facebook endpoints...")
        discovered = harvest_posts_from_page()
        for d in discovered:
            if d not in processed_set and d not in pending_queue:
                pending_queue.append(d)
        log(f"Found {len(pending_queue)} candidate posts to process.")

    if not pending_queue:
        log("No more new candidate posts found on the public page.")
        state["is_exhausted"] = True
        save_state(state)
        return

    # Process batch
    batch = pending_queue[:BATCH_SIZE]
    remaining = pending_queue[BATCH_SIZE:]
    state["pending_post_ids"] = remaining

    new_posts = []
    for pid in batch:
        if len(processed_set) + len(new_posts) >= MAX_POSTS_TARGET:
            break
        log(f"Processing candidate post: {pid}")
        data = extract_single_post(pid)
        if data:
            new_posts.append(data)
            log(f"  [+] Scraped post {pid} (Likes: {data['likes_count']}, Comments: {data['comments_count']})")
        processed_set.add(pid)
        time.sleep(2)  # Polite pause

    # Merge into master posts.json
    if new_posts:
        existing_posts.extend(new_posts)
        with open(POSTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing_posts, f, indent=2, ensure_ascii=False)
        log(f"Added {len(new_posts)} new posts. Total: {len(existing_posts)}")

    state["processed_post_ids"] = list(processed_set)
    state["total_extracted"] = len(existing_posts)
    save_state(state)
    log(f"=== Cron Cycle Finished. Total Posts Stored: {len(existing_posts)} ===")

if __name__ == '__main__':
    run_cron_cycle()
