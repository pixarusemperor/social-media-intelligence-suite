"""
process_all_channels.py - Metadata & Asset Scaffolding from Apify Datasets

Connects to Apify Client, iterates through datasets for @vitalnasser, @produitsdigitauxtorif,
and @nolimitvousdv, and scaffolds channel directory structures containing:
  - metadata.json (raw schema dump)
  - metadata.md (human-readable markdown summary)
  - thumbnail.jpg (high-resolution stream thumbnail)
"""

import os
import re
import sys
import json
import argparse
import urllib.request
from apify_client import ApifyClient

CHANNELS = [
    {
        "name": "vitalnasser",
        "dataset_id": "wwgAsCH5h9ExfjMQA",
        "url": "https://www.youtube.com/@vitalnasser"
    },
    {
        "name": "produitsdigitauxtorif",
        "dataset_id": "DaUda2lzr8Wzq8meo",
        "url": "https://www.youtube.com/@produitsdigitauxtorif"
    },
    {
        "name": "nolimitvousdv",
        "dataset_id": "sJd57OIMFUqHPRKT9",
        "url": "https://www.youtube.com/@nolimitvousdv"
    }
]

BASE_DIR = "/root/Apify"

def get_apify_token():
    """Retrieves Apify API token from environment or local .env file."""
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        env_file = os.path.join(BASE_DIR, ".env")
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                for line in f:
                    if line.startswith("APIFY_TOKEN="):
                        token = line.strip().split("=", 1)[1].strip()
                        break
    return token

def sanitize_filename(name):
    """Sanitizes strings for safe cross-platform folder and file naming."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r'\s+', " ", clean).strip()
    return clean[:100]

def process_channel(channel_info, token):
    """
    Scaffolds video subfolders and extracts metadata for a target channel.
    
    Args:
        channel_info: Dict containing channel name, dataset_id, and url.
        token: Valid Apify API token.
    """
    name = channel_info["name"]
    dataset_id = channel_info["dataset_id"]
    output_dir = os.path.join(BASE_DIR, name)
    os.makedirs(output_dir, exist_ok=True)

    client = ApifyClient(token)
    items = list(client.dataset(dataset_id).iterate_items())
    print(f"\n==========================================")
    print(f"Processing channel @{name} ({len(items)} live streams)")
    print(f"==========================================")

    for idx, item in enumerate(items, 1):
        video_id = item.get("id") or item.get("videoId")
        title = item.get("title") or f"video_{video_id}"
        clean_title = sanitize_filename(title)
        folder_name = f"{idx:02d}_{clean_title}_{video_id}"
        subfolder_path = os.path.join(output_dir, folder_name)
        os.makedirs(subfolder_path, exist_ok=True)

        # Download thumbnail
        thumbnail_url = item.get("thumbnailUrl")
        thumbnail_path = os.path.join(subfolder_path, "thumbnail.jpg")
        if thumbnail_url and not os.path.exists(thumbnail_path):
            try:
                req = urllib.request.Request(
                    thumbnail_url,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                with urllib.request.urlopen(req, timeout=15) as resp, open(thumbnail_path, "wb") as out:
                    out.write(resp.read())
            except Exception as e:
                print(f"  [!] Failed to download thumbnail for {video_id}: {e}")

        # Save metadata.json
        json_path = os.path.join(subfolder_path, "metadata.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(item, f, indent=2, ensure_ascii=False)

        # Save metadata.md
        md_path = os.path.join(subfolder_path, "metadata.md")
        desc = item.get("text") or item.get("description") or "No description provided."
        duration = item.get("duration") or "N/A"
        date = item.get("date") or "N/A"
        views = item.get("viewCount") or item.get("views") or 0
        likes = item.get("likes") or 0
        comments = item.get("commentsCount") or 0
        url = item.get("url") or f"https://www.youtube.com/watch?v={video_id}"
        channel_name = item.get("channelName") or name

        md_content = f"""# {title}

- **Video ID:** `{video_id}`
- **Channel:** {channel_name}
- **URL:** [{url}]({url})
- **Published Date:** {date}
- **Duration:** {duration}
- **Views:** {views:,}
- **Likes:** {likes:,}
- **Comments:** {comments:,}

---

## Thumbnail
![Thumbnail](thumbnail.jpg)

---

## Description
```
{desc}
```
"""
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        print(f"[{idx:02d}/{len(items):02d}] {clean_title[:50]}... -> OK")

def main():
    parser = argparse.ArgumentParser(description="Extract livestream metadata from Apify datasets.")
    parser.add_argument("channel", nargs="?", default="all", choices=["all", "vitalnasser", "produitsdigitauxtorif", "nolimitvousdv"],
                        help="Target channel to process (default: all)")
    args = parser.parse_args()

    token = get_apify_token()
    if not token:
        print("ERROR: APIFY_TOKEN is not set in environment or .env file.")
        sys.exit(1)

    channels = CHANNELS if args.channel == "all" else [c for c in CHANNELS if c["name"] == args.channel]

    for ch in channels:
        process_channel(ch, token)

    print("\nMetadata processing complete!")

if __name__ == "__main__":
    main()
