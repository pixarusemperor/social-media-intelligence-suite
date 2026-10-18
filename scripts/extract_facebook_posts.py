#!/usr/bin/env python3
"""
Facebook Public Page Posts & Media Extractor for https://www.facebook.com/cnicsarl/?locale=fr_FR
Extracts 20 latest posts: full post copy, high-resolution images, comments, and engagement metadata.
Completely free, 0 paid proxies (uses local Tor SOCKS5 proxy + Chrome TLS impersonation via curl_cffi).
"""

import os
import sys
import re
import json
import time
import html as html_lib
from datetime import datetime, timezone
from urllib.parse import unquote
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

OUTPUT_BASE_DIR = '/root/Apify/facebook/cnicsarl'


def harvest_candidate_post_ids():
    """Harvest candidate post IDs from multiple public page views."""
    endpoints = [
        'https://www.facebook.com/cnicsarl/?locale=fr_FR',
        'https://www.facebook.com/cnicsarl/photos/?locale=fr_FR',
        'https://www.facebook.com/cnicsarl/photos_by/?locale=fr_FR',
        'https://www.facebook.com/cnicsarl/videos/?locale=fr_FR',
        'https://www.facebook.com/cnicsarl/reels/?locale=fr_FR',
        'https://www.facebook.com/cnicsarl/posts/?locale=fr_FR',
    ]

    found_ids = set()
    print("Harvesting post IDs from Facebook endpoints...")

    for ep in endpoints:
        print(f"  Querying: {ep}")
        for attempt in range(3):
            try:
                r = requests.get(ep, impersonate='chrome124', headers=DEFAULT_HEADERS, proxies=TOR_PROXIES, timeout=25)
                if r.status_code == 200:
                    matches = (
                        re.findall(r'\"post_id\":\"(\d+)\"', r.text) +
                        re.findall(r'/posts/(\d+)', r.text) +
                        re.findall(r'/photos/[^/]+/(\d+)', r.text) +
                        re.findall(r'\"story_fbid\":\"(\d+)\"', r.text) +
                        re.findall(r'\"legacy_fbid\":\"(\d+)\"', r.text) +
                        re.findall(r'\"id\":\"(14\d{14})\"', r.text) +
                        re.findall(r'\"node\":\{\"id\":\"(14\d{14})\"', r.text)
                    )
                    valid = [m for m in matches if m.startswith('14') and len(m) >= 15]
                    found_ids.update(valid)
                    print(f"    -> Extracted {len(valid)} IDs (Total so far: {len(found_ids)})")
                    break
                else:
                    print(f"    -> Status {r.status_code}, retrying...")
                    time.sleep(2)
            except Exception as e:
                print(f"    -> Attempt {attempt+1} failed: {e}")
                time.sleep(2)

    return sorted(list(found_ids))


def fetch_and_parse_post(post_id):
    """Fetch an individual post and parse its copy, images, comments, and metrics."""
    url = f"https://www.facebook.com/cnicsarl/posts/{post_id}?locale=fr_FR"
    print(f"\nFetching Post {post_id} ({url})...")

    html = ""
    for attempt in range(3):
        try:
            r = requests.get(url, impersonate='chrome124', headers=DEFAULT_HEADERS, proxies=TOR_PROXIES, timeout=25)
            if r.status_code == 200 and len(r.text) > 10000:
                html = r.text
                break
            else:
                print(f"  Attempt {attempt+1}: Status {r.status_code}, len={len(r.text)}. Retrying...")
                time.sleep(2)
        except Exception as e:
            print(f"  Attempt {attempt+1} exception: {e}")
            time.sleep(2)

    if not html:
        print(f"  Failed to retrieve post {post_id}")
        return None

    # 1. Post Text Copy
    UI_BLACKLIST = {
        'reels similaires', 'vidéos connexes', 'pages connexes', 'autres vidéos',
        'plus de vidéos', 'commentaires', 'fil d\'actualité', 'reels', 'facebook'
    }
    candidates = []

    # Pattern A: story message text inside Relay / GraphQL
    for m in re.finditer(r'\"story\":\{.*?\"message\":\{.*?\"text\":(\"(?:[^\"\\\\]|\\\\.)*\")', html, re.DOTALL):
        try:
            val = json.loads(m.group(1), strict=False).strip()
            if val.lower() not in UI_BLACKLIST and len(val) > 5:
                candidates.append((val, len(val), 'story_json'))
        except Exception:
            pass

    # Pattern B: any message with text
    for m in re.finditer(r'\"message\":\s*\{[^{}]*?\"text\":\s*(\"(?:[^\"\\\\]|\\\\.)*\")', html, re.DOTALL):
        try:
            val = json.loads(m.group(1), strict=False).strip()
            if val.lower() not in UI_BLACKLIST and len(val) > 5:
                candidates.append((val, len(val), 'relay_json'))
        except Exception:
            pass

    # Pattern C: TextWithEntities
    for m in re.finditer(r'\"__typename\":\"TextWithEntities\",\"text\":\s*(\"(?:[^\"\\\\]|\\\\.)*\")', html, re.DOTALL):
        try:
            val = json.loads(m.group(1), strict=False).strip()
            if val.lower() not in UI_BLACKLIST and len(val) > 5:
                candidates.append((val, len(val), 'text_with_entities'))
        except Exception:
            pass

    # Pattern D: og:description meta tag with re.DOTALL
    og_desc = re.findall(r'<meta\s+property=[\"\']og:description[\"\']\s+content=[\"\'](.*?)[\"\']', html, re.DOTALL)
    if og_desc:
        val = html_lib.unescape(og_desc[0]).strip()
        if val.lower() not in UI_BLACKLIST and len(val) > 5:
            candidates.append((val, len(val), 'og_description'))

    # Pattern E: meta name description
    meta_desc = re.findall(r'<meta\s+name=[\"\']description[\"\']\s+content=[\"\'](.*?)[\"\']', html, re.DOTALL)
    if meta_desc:
        val = html_lib.unescape(meta_desc[0]).strip()
        if val.lower() not in UI_BLACKLIST and len(val) > 5:
            candidates.append((val, len(val), 'meta_description'))

    # Pattern F: title tag fallback
    title_matches = re.findall(r'<title>(.*?)</title>', html, re.DOTALL)
    if title_matches:
        val = html_lib.unescape(title_matches[0]).replace(' - Dr Claudel Noubissie', '').replace(' | Dr Claudel Noubissie', '').strip()
        if val.lower() not in UI_BLACKLIST and len(val) > 5 and not val.startswith('1,') and not val.startswith('Facebook'):
            candidates.append((val, len(val), 'title'))

    post_text = ""
    if candidates:
        candidates.sort(key=lambda x: x[1], reverse=True)
        post_text = candidates[0][0]

    # 2. Timestamp / Creation Time
    creation_time = None
    ct_matches = re.findall(r'\"creation_time\":(\d+)', html)
    if ct_matches:
        creation_time = int(ct_matches[0])
    else:
        # Fallback timestamp search
        time_matches = re.findall(r'\"publish_time\":(\d+)', html) or re.findall(r'\"created_time\":(\d+)', html)
        if time_matches:
            creation_time = int(time_matches[0])

    if creation_time:
        dt_utc = datetime.fromtimestamp(creation_time, tz=timezone.utc)
        date_iso = dt_utc.isoformat()
        date_str = dt_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
    else:
        date_iso = None
        date_str = "Unknown"

    # 3. Reactions & Engagement Metrics
    reactions_count = 0
    rc_matches = re.findall(r'\"reaction_count\":\{.*?\"count\":(\d+)', html)
    if rc_matches:
        reactions_count = int(rc_matches[0])

    shares_count = 0
    sc_matches = re.findall(r'\"share_count\":\{.*?\"count\":(\d+)', html)
    if sc_matches:
        shares_count = int(sc_matches[0])

    top_reactions = []
    tr_matches = re.findall(r'\"localized_name\":\"([^\"]+)\"', html)
    for r_name in tr_matches:
        if r_name in ["J’aime", "J'aime", "J’adore", "J'adore", "Solidaire", "Haha", "Wouah", "Triste", "En colère"]:
            if r_name not in top_reactions:
                top_reactions.append(r_name)

    # 4. Comments Extraction
    # Parse comment objects containing legacy_fbid, text, and author
    comments = []
    seen_comment_ids = set()

    # Search pattern 1: legacy_fbid + body text + author name (with DOTALL)
    comment_blocks = re.findall(r'\"legacy_fbid\":\"(\d+)\".*?\"body\":\{\"text\":(\"(?:[^\"\\\\]|\\\\.)*\")\}.*?\"author\":\{[^{}]*?\"name\":\"([^\"]+)\"', html, re.DOTALL)
    for cid, ctext_raw, cauthor in comment_blocks:
        if cid not in seen_comment_ids:
            try:
                ctext = json.loads(ctext_raw, strict=False)
            except Exception:
                ctext = ctext_raw
            comments.append({
                "comment_id": cid,
                "author": cauthor,
                "text": ctext,
            })
            seen_comment_ids.add(cid)

    # Search pattern 2: legacy_fbid + author name + body text
    comment_blocks_rev = re.findall(r'\"legacy_fbid\":\"(\d+)\".*?\"author\":\{[^{}]*?\"name\":\"([^\"]+)\"\}.*?\"body\":\{\"text\":(\"(?:[^\"\\\\]|\\\\.)*\")\}', html, re.DOTALL)
    for cid, cauthor, ctext_raw in comment_blocks_rev:
        if cid not in seen_comment_ids:
            try:
                ctext = json.loads(ctext_raw, strict=False)
            except Exception:
                ctext = ctext_raw
            comments.append({
                "comment_id": cid,
                "author": cauthor,
                "text": ctext,
            })
            seen_comment_ids.add(cid)

    # Search pattern 3: fallback legacy_fbid + body text
    fallback_blocks = re.findall(r'\"legacy_fbid\":\"(\d+)\".*?\"body\":\{\"text\":(\"(?:[^\"\\\\]|\\\\.)*\")\}', html, re.DOTALL)
    for cid, ctext_raw in fallback_blocks:
        if cid not in seen_comment_ids:
            try:
                ctext = json.loads(ctext_raw, strict=False)
            except Exception:
                ctext = ctext_raw
            pos = html.find(cid)
            author = "Abonné Facebook"
            if pos != -1:
                snippet = html[max(0, pos - 200):min(len(html), pos + 500)]
                auth_match = re.search(r'\"author\":\{[^{}]*?\"name\":\"([^\"]+)\"', snippet)
                if auth_match:
                    author = auth_match.group(1)
            comments.append({
                "comment_id": cid,
                "author": author,
                "text": ctext,
            })
            seen_comment_ids.add(cid)

    # 5. Image Attachment URLs
    # Search for CDN images: scontent*.xx.fbcdn.net
    all_raw_uris = re.findall(r'\"uri\":\"([^\"]+)\"', html)
    image_urls = []
    seen_img_keys = set()

    for u in all_raw_uris:
        if 'fbcdn' in u or 'scontent' in u:
            clean_url = u.replace('\\/', '/')
            # Filter out tiny icon / avatar thumbnails
            if any(dim in clean_url for dim in ['s16x16', 's20x20', 's24x24', 's32x32', 's40x40', 's50x50', 'rsrc.php']):
                continue
            # Avoid duplicate image signatures
            filename_match = re.search(r'/([^/?]+)\.(jpg|png|jpeg)', clean_url)
            file_key = filename_match.group(1) if filename_match else clean_url[:60]
            if file_key not in seen_img_keys:
                image_urls.append(clean_url)
                seen_img_keys.add(file_key)

    # If no attachment photos found in raw URIs, check backup pattern
    if not image_urls:
        backup_matches = re.findall(r'https?:\\/\\/[^\"]+scontent[^\"]+\.(?:jpg|png)', html)
        for b_url in backup_matches:
            clean_b = b_url.replace('\\/', '/')
            if not any(dim in clean_b for dim in ['s16x16', 's24x24', 's32x32', 's40x40', 's50x50']):
                if clean_b not in image_urls:
                    image_urls.append(clean_b)

    return {
        "post_id": post_id,
        "url": url,
        "creation_time": creation_time,
        "date_iso": date_iso,
        "date_str": date_str,
        "post_text": post_text,
        "reactions_count": reactions_count,
        "shares_count": shares_count,
        "comments_count": len(comments) if comments else len(re.findall(r'\"legacy_fbid\"', html)),
        "top_reactions": top_reactions,
        "comments": comments,
        "image_urls": image_urls[:10], # Keep up to top 10 unique attachment photos
    }


def download_post_images(image_urls, post_folder):
    """Download image binaries into post_folder/images/."""
    images_dir = os.path.join(post_folder, "images")
    os.makedirs(images_dir, exist_ok=True)
    downloaded_files = []

    for idx, img_url in enumerate(image_urls, start=1):
        ext = "jpg"
        if ".png" in img_url:
            ext = "png"
        filename = f"image_{idx:02d}.{ext}"
        filepath = os.path.join(images_dir, filename)

        for attempt in range(3):
            try:
                r = requests.get(img_url, impersonate='chrome124', timeout=25)
                if r.status_code == 200 and len(r.content) > 1000:
                    with open(filepath, 'wb') as f:
                        f.write(r.content)
                    downloaded_files.append({
                        "filename": filename,
                        "rel_path": f"images/{filename}",
                        "abs_path": filepath,
                        "size_bytes": len(r.content),
                        "cdn_url": img_url
                    })
                    print(f"    Downloaded {filename} ({len(r.content):,} bytes)")
                    break
                else:
                    time.sleep(1)
            except Exception as e:
                time.sleep(1)

    return downloaded_files


def main():
    print("=" * 70)
    print("CNIC SARL Facebook Posts & Comments Extractor (20 Latest Posts)")
    print("Zero Paid Proxies | Zero Apify | Local Tor + Chrome TLS Fingerprinting")
    print("=" * 70)

    os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

    # 1. Gather all candidate IDs
    candidate_ids = harvest_candidate_post_ids()
    print(f"\nTotal candidate post IDs found: {len(candidate_ids)}")

    # 2. Fetch all candidates
    all_posts = []
    for pid in candidate_ids:
        post_data = fetch_and_parse_post(pid)
        if post_data and (post_data["post_text"] or post_data["image_urls"]):
            all_posts.append(post_data)
        time.sleep(1)

    # 3. Sort by creation_time descending (newest first)
    all_posts.sort(key=lambda p: (p.get("creation_time") or 0, int(p.get("post_id", 0))), reverse=True)

    # Select the top 20 latest posts
    selected_posts = all_posts[:20]
    print(f"\nSuccessfully selected {len(selected_posts)} latest posts.")

    # 4. Save and download media for each post
    catalog_entries = []

    for idx, post in enumerate(selected_posts, start=1):
        folder_name = f"post_{idx:02d}"
        post_folder = os.path.join(OUTPUT_BASE_DIR, folder_name)
        os.makedirs(post_folder, exist_ok=True)

        print(f"\nProcessing Post {idx:02d} [ID: {post['post_id']}] -> {folder_name}/")

        # Download attached images
        downloaded_images = download_post_images(post["image_urls"], post_folder)
        post["downloaded_images"] = downloaded_images

        # Save post.json
        with open(os.path.join(post_folder, "post.json"), "w", encoding="utf-8") as f:
            json.dump(post, f, indent=2, ensure_ascii=False)

        # Save comments.json
        with open(os.path.join(post_folder, "comments.json"), "w", encoding="utf-8") as f:
            json.dump(post["comments"], f, indent=2, ensure_ascii=False)

        # Save post.md
        post_md_content = f"""# Post {idx:02d} — CNIC SARL (Dr Claudel Noubissie)

**Post ID:** `{post['post_id']}`  
**Published Date:** {post['date_str']}  
**Permalink:** [{post['url']}]({post['url']})  
**Engagement:** 👍 {post['reactions_count']} Reactions ({', '.join(post['top_reactions']) if post['top_reactions'] else 'J’aime'}) | 🔄 {post['shares_count']} Shares | 💬 {post['comments_count']} Comments  

---

## 📝 Post Content / Description Copy

```text
{post['post_text']}
```

---

## 🖼️ Attached Media ({len(downloaded_images)} images downloaded)

"""
        for img in downloaded_images:
            post_md_content += f"- **[{img['filename']}](./{img['rel_path']})** ({img['size_bytes']:,} bytes)  \n"
            post_md_content += f"  CDN Source: `{img['cdn_url'][:100]}...`\n"

        post_md_content += f"""
---

## 💬 Comments ({len(post['comments'])} extracted)

"""
        if post["comments"]:
            for c_idx, comm in enumerate(post["comments"], start=1):
                post_md_content += f"### Comment #{c_idx} by **{comm['author']}** (`ID: {comm['comment_id']}`)\n"
                post_md_content += f"> {comm['text']}\n\n"
        else:
            post_md_content += "_No direct user comments extracted for this publication._\n\n"

        with open(os.path.join(post_folder, "post.md"), "w", encoding="utf-8") as f:
            f.write(post_md_content)

        catalog_entries.append({
            "index": idx,
            "post_id": post["post_id"],
            "folder": folder_name,
            "date": post["date_str"],
            "reactions": post["reactions_count"],
            "shares": post["shares_count"],
            "comments_count": len(post["comments"]),
            "images_count": len(downloaded_images),
            "text_preview": post["post_text"][:120].replace('\n', ' ') + "..." if len(post["post_text"]) > 120 else post["post_text"].replace('\n', ' ')
        })

    # 5. Master summary JSON
    with open(os.path.join(OUTPUT_BASE_DIR, "posts_summary.json"), "w", encoding="utf-8") as f:
        json.dump({
            "source_url": "https://www.facebook.com/cnicsarl/?locale=fr_FR",
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "total_posts": len(selected_posts),
            "posts": selected_posts
        }, f, indent=2, ensure_ascii=False)

    # 6. Master CATALOG.md
    catalog_md = f"""# CNIC SARL (Dr Claudel Noubissie) — 20 Latest Facebook Posts Catalog

**Target Page:** `https://www.facebook.com/cnicsarl/?locale=fr_FR`  
**Extraction Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  
**Zero-Cost Stack:** Local Tor daemon (`127.0.0.1:9050`) + Chrome TLS Impersonation via `curl_cffi`.  
**Total Posts Archived:** {len(selected_posts)}  

---

| # | Date (UTC) | Post ID | Text Copy Preview | Photos | Comments | Reactions | Post Folder |
|---|---|---|---|:---:|:---:|:---:|---|
"""
    for entry in catalog_entries:
        catalog_md += f"| **{entry['index']:02d}** | {entry['date']} | `{entry['post_id']}` | {entry['text_preview']} | **{entry['images_count']}** | **{entry['comments_count']}** | 👍 {entry['reactions']} | [{entry['folder']}](./{entry['folder']}/post.md) |\n"

    catalog_md += """
---

## Directory Structure

```text
/root/Apify/facebook/cnicsarl/
├── CATALOG.md
├── posts_summary.json
├── post_01/
│   ├── post.md
│   ├── post.json
│   ├── comments.json
│   └── images/
│       ├── image_01.jpg
│       └── ...
├── post_02/
...
└── post_20/
```
"""
    with open(os.path.join(OUTPUT_BASE_DIR, "CATALOG.md"), "w", encoding="utf-8") as f:
        f.write(catalog_md)

    print("\n" + "=" * 70)
    print("EXTRACTION COMPLETE!")
    print(f"Catalog saved to {OUTPUT_BASE_DIR}/CATALOG.md")
    print(f"Master JSON saved to {OUTPUT_BASE_DIR}/posts_summary.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
