import os
import re
import json
import urllib.request
from apify_client import ApifyClient

DATASET_ID = "wwgAsCH5h9ExfjMQA"
OUTPUT_DIR = "/root/Apify/vitalnasser"
APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
if not APIFY_TOKEN:
    env_file = os.path.join(os.path.dirname(OUTPUT_DIR), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if line.startswith("APIFY_TOKEN="):
                    APIFY_TOKEN = line.strip().split("=", 1)[1].strip()
                    break

def sanitize_filename(name):
    # Remove characters invalid in folder/file names
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r'\s+', " ", clean).strip()
    return clean[:100]

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    client = ApifyClient(APIFY_TOKEN)
    items = list(client.dataset(DATASET_ID).iterate_items())
    print(f"Retrieved {len(items)} items from dataset {DATASET_ID}")

    for idx, item in enumerate(items, 1):
        video_id = item.get("id") or item.get("videoId")
        title = item.get("title") or f"video_{video_id}"
        clean_title = sanitize_filename(title)
        folder_name = f"{idx:02d}_{clean_title}_{video_id}"
        subfolder_path = os.path.join(OUTPUT_DIR, folder_name)
        os.makedirs(subfolder_path, exist_ok=True)

        # Download thumbnail if available
        thumbnail_url = item.get("thumbnailUrl")
        thumbnail_path = os.path.join(subfolder_path, "thumbnail.jpg")
        if thumbnail_url:
            try:
                urllib.request.urlretrieve(thumbnail_url, thumbnail_path)
                print(f"Downloaded thumbnail for {video_id}")
            except Exception as e:
                print(f"Failed to download thumbnail: {e}")

        # Save raw JSON metadata
        json_path = os.path.join(subfolder_path, "metadata.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)

        # Build comprehensive metadata.md
        md_path = os.path.join(subfolder_path, "metadata.md")
        desc = item.get("text") or item.get("description") or "No description provided."
        
        md_content = f"""# {title}

## Video Overview
- **Video ID:** `{video_id}`
- **Direct URL:** [{item.get('url', f'https://www.youtube.com/watch?v={video_id}')}]({item.get('url', f'https://www.youtube.com/watch?v={video_id}')})
- **Channel:** [{item.get('channelName', 'Vital Nasser')}]({item.get('channelUrl', 'https://www.youtube.com/@vitalnasser')})
- **Channel ID:** `{item.get('channelId', '')}`
- **Published Date:** {item.get('date', 'N/A')}
- **Duration:** {item.get('duration', 'N/A')}
- **Views:** {item.get('viewCount', 'N/A'):,}
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
- **Apify Dataset ID:** `{DATASET_ID}`
- **Input URL:** `https://www.youtube.com/@vitalnasser/streams`
- **Scraped At:** {item.get('inputUrl', '')}
- **Original Thumbnail URL:** {thumbnail_url}
"""
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"Created {md_path}")

if __name__ == "__main__":
    main()
