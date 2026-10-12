import os
import re
import json
import urllib.request
from apify_client import ApifyClient

CHANNELS = [
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
APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
if not APIFY_TOKEN:
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if line.startswith("APIFY_TOKEN="):
                    APIFY_TOKEN = line.strip().split("=", 1)[1].strip()
                    break

def sanitize_filename(name):
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r'\s+', " ", clean).strip()
    return clean[:100]

def process_channel(channel_info):
    name = channel_info["name"]
    dataset_id = channel_info["dataset_id"]
    output_dir = os.path.join(BASE_DIR, name)
    os.makedirs(output_dir, exist_ok=True)

    client = ApifyClient(APIFY_TOKEN)
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
                urllib.request.urlretrieve(thumbnail_url, thumbnail_path)
                print(f"  [{idx}/{len(items)}] Downloaded thumbnail for {video_id}")
            except Exception as e:
                print(f"  [{idx}/{len(items)}] Thumbnail error: {e}")

        # Save metadata.json
        json_path = os.path.join(subfolder_path, "metadata.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)

        # Build metadata.md
        md_path = os.path.join(subfolder_path, "metadata.md")
        desc = item.get("text") or item.get("description") or "No description provided."
        
        views_formatted = f"{item.get('viewCount', 0):,}" if isinstance(item.get('viewCount'), (int, float)) else str(item.get('viewCount', 'N/A'))

        md_content = f"""# {title}

## Video Overview
- **Video ID:** `{video_id}`
- **Direct URL:** [{item.get('url', f'https://www.youtube.com/watch?v={video_id}')}]({item.get('url', f'https://www.youtube.com/watch?v={video_id}')})
- **Channel:** [{item.get('channelName', name)}]({item.get('channelUrl', channel_info['url'])})
- **Channel ID:** `{item.get('channelId', '')}`
- **Published Date:** {item.get('date', 'N/A')}
- **Duration:** {item.get('duration', 'N/A')}
- **Views:** {views_formatted}
- **Likes:** {item.get('likes', 'N/A')}
- **Comments Count:** {item.get('commentsCount', 'N/A')}
- **Type:** Live Stream Recording

---

## Thumbnail
![Thumbnail](thumbnail.jpg)

---

## Full Description
```text
{desc}
```

---

## Technical & Extraction Details
- **Apify Dataset ID:** `{dataset_id}`
- **Original Thumbnail URL:** {thumbnail_url}
"""
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

    print(f"Finished generating metadata for @{name}")

def main():
    for ch in CHANNELS:
        process_channel(ch)

if __name__ == "__main__":
    main()
