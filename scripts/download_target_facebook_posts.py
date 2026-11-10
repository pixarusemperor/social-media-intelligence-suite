#!/usr/bin/env python3
"""
Target Facebook Posts & High-Res Media Extractor for Page 61593527086207 (Les Hommes Tendus)
Zero Apify | Zero Paid Proxies | Uses local Tor SOCKS5 + curl_cffi Chrome 124 TLS
Downloads High-Res Creatives (1080x1080 & 1080x564), Full Post Copy, Headlines, Comments & Metrics
"""

import os
import sys
import re
import json
import subprocess
from datetime import datetime, timezone
from curl_cffi import requests

TARGET_PAGE_ID = "61593527086207"
OUTPUT_DIR = "/root/Apify/facebook/les_hommes_tendus_61593527086207"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
}
TOR_PROXIES = {
    'http': 'socks5://127.0.0.1:9050',
    'https': 'socks5://127.0.0.1:9050'
}

POSTS_CONFIG = [
    {
        "folder_name": "post_01_original_122117273379450902",
        "label": "original",
        "post_id": "122117273379450902",
    },
    {
        "folder_name": "post_02_variant_2_122103648225450902",
        "label": "2",
        "post_id": "122103648225450902",
    },
    {
        "folder_name": "post_03_guiness_4_ai_copy_122117273337450902",
        "label": "guiness 4 ai copy",
        "post_id": "122117273337450902",
    },
    {
        "folder_name": "post_04_4_ai_122117273361450902",
        "label": "4 ai",
        "post_id": "122117273361450902",
    },
    {
        "folder_name": "post_05_4_ai_copy_122117273421450902",
        "label": "4 ai copy",
        "post_id": "122117273421450902",
    },
]

def fetch_post_html(post_id):
    cached_path = f"/tmp/{post_id}.html"
    if os.path.exists(cached_path) and os.path.getsize(cached_path) > 10000:
        print(f"Loading cached HTML for {post_id} ({os.path.getsize(cached_path):,} bytes)...")
        with open(cached_path, "r", encoding="utf-8") as f:
            return f.read()

    url = f"https://www.facebook.com/{TARGET_PAGE_ID}/posts/{post_id}"
    print(f"Fetching post {post_id} from {url}...")
    try:
        r = requests.get(url, impersonate='chrome124', headers=HEADERS, proxies=TOR_PROXIES, timeout=25)
        if r.status_code == 200:
            with open(cached_path, "w", encoding="utf-8") as f:
                f.write(r.text)
            return r.text
        else:
            print(f"  HTTP {r.status_code}")
            return None
    except Exception as e:
        print(f"  Error: {e}")
        return None

def parse_post(post_id, label, html):
    url = f"https://web.facebook.com/{TARGET_PAGE_ID}/posts/{post_id}/"
    decoder = json.JSONDecoder(strict=False)
    
    # Check if content unavailable
    if not html or ("content isn't available" in html or "Ce contenu n'est pas disponible" in html):
        return {
            "post_id": post_id,
            "label": label,
            "url": url,
            "status": "unavailable_or_deleted",
            "status_details": "Facebook returns 'This content isn't available right now. The owner only shared it with a small group of people, changed who can see it or it's been deleted.'",
            "post_text": "",
            "headline": "",
            "cta": "",
            "whatsapp_url": "",
            "creation_time": None,
            "date_iso": None,
            "date_str": "N/A",
            "reactions_count": 0,
            "comments_count": 0,
            "comments": [],
            "images": []
        }

    # Extract full post copy text using decoder.raw_decode
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

    # Headline & Call-To-Action (e.g. WhatsApp, URGENCE SIGNALEE)
    headline = ""
    hl_match = re.search(r'\"title_with_entities\":\{\"text\":\"([^\"]+)\"\}', html)
    if hl_match:
        headline = hl_match.group(1)

    cta = "WhatsApp"
    cta_match = re.search(r'\"source\":\{\"text\":\"([^\"]+)\"\}', html)
    if cta_match:
        cta = cta_match.group(1)

    wa_match = re.search(r'\"external_url\":\"([^\"]+)\"', html)
    whatsapp_url = wa_match.group(1).replace(r'\/', '/') if wa_match else ""

    # Timestamp
    creation_time = None
    ct_matches = re.findall(r'\"creation_time\":(\d+)', html) or re.findall(r'\"publish_time\":(\d+)', html)
    if ct_matches:
        creation_time = int(ct_matches[0])
        dt_utc = datetime.fromtimestamp(creation_time, tz=timezone.utc)
        date_iso = dt_utc.isoformat()
        date_str = dt_utc.strftime('%Y-%m-%d %H:%M:%S UTC')
    else:
        date_iso = None
        date_str = "Unknown"

    # Reactions
    reactions_count = 0
    rc = re.findall(r'\"reaction_count\":\{.*?\"count\":(\d+)', html)
    if rc:
        reactions_count = int(rc[0])

    # Comments
    comments = []
    comment_blocks = re.findall(r'\"legacy_fbid\":\"(\d+)\".*?\"body\":\{\"text\":(\"(?:[^\"\\\\]|\\\\.)*\")\}.*?\"author\":\{[^{}]*?\"name\":\"([^\"]+)\"', html, re.DOTALL)
    seen_cids = set()
    for cid, ctext_raw, cauthor in comment_blocks:
        if cid not in seen_cids:
            seen_cids.add(cid)
            try:
                ctext = json.loads(ctext_raw, strict=False)
            except Exception:
                ctext = ctext_raw
            comments.append({
                "comment_id": cid,
                "author": cauthor,
                "text": ctext
            })

    # High-Res Media Images
    raw_uris = re.findall(r'\"uri\":\"([^\"]+)\"', html)
    t45_uris = set(u.replace(r'\/', '/') for u in raw_uris if 't45.1600-4' in u)

    images = []
    for u in t45_uris:
        if "cstp=mx1080x1080" in u or "cstp=mx1024x1024" in u:
            # Full square native resolution without ctp constraint
            sq_high = u.replace('&ctp=p526x296', '')
            dim_label = "1080x1080" if "1080" in u else "1024x1024"
            images.append({
                "type": "creative_square_high_res",
                "target_dimensions": dim_label,
                "url": sq_high,
                "filename": f"creative_square_{dim_label}.jpg"
            })
        elif "cstp=mx1080x564" in u or "cstp=mx1024x534" in u:
            # Full banner native resolution without ctp constraint
            ban_high = u.replace('&ctp=s526x296', '')
            dim_label = "1080x564" if "1080" in u else "1024x534"
            images.append({
                "type": "creative_banner_landscape",
                "target_dimensions": dim_label,
                "url": ban_high,
                "filename": f"creative_banner_{dim_label}.jpg"
            })

    return {
        "post_id": post_id,
        "label": label,
        "url": url,
        "status": "active_extracted",
        "creation_time": creation_time,
        "date_iso": date_iso,
        "date_str": date_str,
        "headline": headline,
        "cta": cta,
        "whatsapp_url": whatsapp_url,
        "post_text": post_text,
        "reactions_count": reactions_count,
        "comments_count": len(comments),
        "comments": comments,
        "images": images
    }

def download_images(images, target_dir):
    os.makedirs(target_dir, exist_ok=True)
    downloaded = []
    for item in images:
        u = item["url"]
        fname = item["filename"]
        out_path = os.path.join(target_dir, fname)
        try:
            r = requests.get(u, impersonate='chrome124', timeout=20)
            if r.status_code == 200 and len(r.content) > 1000:
                with open(out_path, 'wb') as f:
                    f.write(r.content)
                info = subprocess.check_output(['file', out_path]).decode().strip()
                res_match = re.search(r'(\d+)x(\d+)', info)
                dim = f"{res_match.group(1)}x{res_match.group(2)}" if res_match else "unknown"
                downloaded.append({
                    "filename": fname,
                    "rel_path": f"images/{fname}",
                    "abs_path": out_path,
                    "size_bytes": len(r.content),
                    "dimensions": dim,
                    "file_info": info,
                    "type": item["type"]
                })
                print(f"    Downloaded {fname}: {dim}, {len(r.content):,} bytes")
        except Exception as e:
            print(f"    Failed to download {fname}: {e}")
    return downloaded

def main():
    print("=" * 70)
    print("Facebook Ad Campaign Extraction & Organization")
    print(f"Target Page ID: {TARGET_PAGE_ID} (Les Hommes Tendus)")
    print(f"Output Directory: {OUTPUT_DIR}")
    print("=" * 70)

    summary_list = []

    for cfg in POSTS_CONFIG:
        post_id = cfg["post_id"]
        label = cfg["label"]
        folder_name = cfg["folder_name"]
        post_dir = os.path.join(OUTPUT_DIR, folder_name)
        os.makedirs(post_dir, exist_ok=True)
        images_dir = os.path.join(post_dir, "images")

        print(f"\nProcessing [{label}] Post ID: {post_id} -> {folder_name}/")

        html = fetch_post_html(post_id)
        post_data = parse_post(post_id, label, html)

        # Download images
        if post_data["images"]:
            print(f"  Downloading {len(post_data['images'])} high-resolution media images...")
            downloaded = download_images(post_data["images"], images_dir)
            post_data["downloaded_images"] = downloaded
        else:
            post_data["downloaded_images"] = []

        # 1. Save copy.txt
        copy_file = os.path.join(post_dir, "copy.txt")
        with open(copy_file, "w", encoding="utf-8") as f:
            f.write(post_data["post_text"] if post_data["post_text"] else "(Post content unavailable or restricted on Facebook)")

        # 2. Save post.json
        json_file = os.path.join(post_dir, "post.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(post_data, f, indent=2, ensure_ascii=False)

        # 3. Save post.md
        md_file = os.path.join(post_dir, "post.md")
        img_md = ""
        if post_data["downloaded_images"]:
            img_md = "\n### 🖼️ Downloaded High-Resolution Media Images\n\n"
            for im in post_data["downloaded_images"]:
                img_md += f"- **{im['type']}** (`{im['filename']}`): **{im['dimensions']}** ({im['size_bytes']:,} bytes)\n"
                img_md += f"  - Local file: `images/{im['filename']}`\n"
        
        comments_md = ""
        if post_data["comments"]:
            comments_md = "\n### 💬 Comments\n\n"
            for c in post_data["comments"]:
                comments_md += f"- **{c['author']}**: {c['text']}\n"

        md_content = f"""# Post: {label.upper()} (`{post_id}`)

- **Page:** `Les Hommes Tendus` (Page ID: `{TARGET_PAGE_ID}`)
- **Post ID:** `{post_id}`
- **Permalink:** [{post_data['url']}]({post_data['url']})
- **Status:** `{post_data['status']}`
- **Published Date:** {post_data.get('date_str', 'N/A')}
- **Headline:** `{post_data.get('headline', 'N/A')}`
- **Call-to-Action:** `{post_data.get('cta', 'N/A')}`
- **Engagement:** 👍 {post_data['reactions_count']} Reactions | 💬 {post_data['comments_count']} Comments

---

## 📝 Copy / Ad Text

```text
{post_data['post_text'] if post_data['post_text'] else "(Post content unavailable or restricted on Facebook: owner shared with small group, changed privacy, or deleted post)"}
```

{img_md}
{comments_md}

---
*Extracted via zero-cost local pipeline (Tor + Chrome TLS impersonation)*
"""
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(md_content)

        summary_list.append({
            "label": label,
            "post_id": post_id,
            "folder": folder_name,
            "status": post_data["status"],
            "date": post_data.get("date_str", "N/A"),
            "headline": post_data.get("headline", ""),
            "reactions": post_data["reactions_count"],
            "comments": post_data["comments_count"],
            "copy_length": len(post_data["post_text"]),
            "image_count": len(post_data["downloaded_images"]),
            "image_dimensions": [im["dimensions"] for im in post_data["downloaded_images"]]
        })

    # Save summary.json
    summary_path = os.path.join(OUTPUT_DIR, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_list, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("All posts processed and organized successfully!")
    print(f"Summary written to: {summary_path}")
    print("=" * 70)

if __name__ == "__main__":
    main()
