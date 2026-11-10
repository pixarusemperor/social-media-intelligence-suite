#!/usr/bin/env python3
"""
Custom Facebook Post Extractor & Media Downloader for https://www.facebook.com/OfficialCaresOneNo/
Target: Single native image posts only (no videos, no reels, no link cards)
Zero Apify | Zero Paid Proxies | Local Tor SOCKS5 (127.0.0.1:9050) + curl_cffi Chrome 124 TLS
"""

import os
import sys
import re
import json
import time
import html as html_lib
from datetime import datetime, timezone
from curl_cffi import requests

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

OUTPUT_DIR = '/root/Apify/facebook/OfficialCaresOneNo'
IMAGES_DIR = os.path.join(OUTPUT_DIR, 'images')
os.makedirs(IMAGES_DIR, exist_ok=True)

CANDIDATE_POST_IDS = [
    '1727494832074228',
    '1727462262077485',
    '1727429722080739',
    '1727405848749793',
    '1727339905423054',
    '1727301958760182',
    '1727269018763476',
    '1727243542099357',
]

def clean_url(u):
    return u.replace(r'\/', '/').replace(r'\\', '')

def parse_post(post_id):
    url = f"https://www.facebook.com/OfficialCaresOneNo/posts/{post_id}"
    print(f"\n[+] Processing Post: {post_id}")
    
    html = ""
    for attempt in range(3):
        try:
            r = requests.get(url, impersonate='chrome124', headers=DEFAULT_HEADERS, proxies=TOR_PROXIES, timeout=25)
            if r.status_code == 200 and len(r.text) > 10000:
                html = r.text
                break
            time.sleep(2)
        except Exception as e:
            print(f"  Attempt {attempt+1} failed: {e}")
            time.sleep(2)
            
    if not html:
        print(f"  [-] Failed to fetch post {post_id}")
        return None

    decoder = json.JSONDecoder(strict=False)

    # 1. Post Text Copy
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

    # Fallback title if text empty
    if not post_text:
        titles = re.findall(r'<title>(.*?)</title>', html)
        if titles:
            post_text = titles[0].replace('No One Cares - ', '').strip()

    # 2. Timestamp
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

    # 3. Likes / Reactions count
    rc = re.findall(r'\"reaction_count\":\{.*?\"count\":(\d+)', html) or re.findall(r'\"reaction_count\":(\d+)', html)
    likes_count = int(rc[0]) if rc else 0

    # 4. Comments count
    cc = re.findall(r'\"comment_count\":\{.*?\"total_count\":(\d+)', html) or re.findall(r'\"total_comment_count\":(\d+)', html)
    comments_count = int(cc[0]) if cc else 0
    if comments_count == 0:
        # Check comments list length
        c_matches = set(re.findall(r'\"comment_id\":\"(\d+)\"', html) + re.findall(r'\"legacy_fbid\":\"(\d+)\".*?\"body\":', html))
        comments_count = len(c_matches)

    # 5. Extract high-res image
    # Search for all image URIs in Relay store
    uris = re.findall(r'\"uri\":\"([^\"]+)\"', html)
    
    # Priority 1: High-res square or banner in t39.99422-6
    best_img_url = None
    all_imgs = []
    
    for u in uris:
        clean = clean_url(u)
        if 'scontent' in clean and ('t39.99422-6' in clean or 'dst-jpg' in clean or 'dst-png' in clean):
            # Exclude small profile icons (e.g. t39.30808-1 or small avatars)
            if 't39.30808-1' not in clean and 'rsrc.php' not in clean:
                all_imgs.append(clean)

    if all_imgs:
        # Pick the one with highest resolution / full crop
        # Often Facebook images have ?stp=c..._n.png or similar. We can remove crop constraints or take the original
        best_img_url = all_imgs[0]
        # If there's an image without c0. crop or with 1080/1638, prefer that
        for img in all_imgs:
            if '1638' in img or '1080' in img or '1122' in img:
                best_img_url = img
                break

    # Download image if found
    local_image_path = ""
    filename = f"{date_folder}_{post_id}_01.jpg"
    dest_file = os.path.join(IMAGES_DIR, filename)

    if best_img_url:
        print(f"  [*] Downloading high-res image: {best_img_url[:80]}...")
        for attempt in range(3):
            try:
                r_img = requests.get(best_img_url, impersonate='chrome124', proxies=TOR_PROXIES, timeout=30)
                if r_img.status_code == 200 and len(r_img.content) > 1000:
                    with open(dest_file, 'wb') as f:
                        f.write(r_img.content)
                    local_image_path = dest_file
                    print(f"  [+] Saved image ({len(r_img.content):,} bytes) to {dest_file}")
                    break
            except Exception as e:
                print(f"  [-] Image download attempt {attempt+1} failed: {e}")
                time.sleep(1)

    post_data = {
        "post_id": post_id,
        "post_url": url,
        "date_str": date_str,
        "date_iso": date_iso,
        "timestamp": creation_time,
        "likes_count": likes_count,
        "comments_count": comments_count,
        "post_text": post_text,
        "image_url": best_img_url or "",
        "local_image_path": local_image_path,
        "filename": filename if local_image_path else ""
    }
    return post_data

def main():
    print(f"Starting extraction for {len(CANDIDATE_POST_IDS)} single-image posts...")
    extracted_posts = []
    
    for pid in CANDIDATE_POST_IDS:
        data = parse_post(pid)
        if data:
            extracted_posts.append(data)
            
    # Save master posts.json
    json_path = os.path.join(OUTPUT_DIR, 'posts.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(extracted_posts, f, indent=2, ensure_ascii=False)
        
    print(f"\n[SUCCESS] Successfully extracted {len(extracted_posts)} posts to {json_path}")

if __name__ == '__main__':
    main()
