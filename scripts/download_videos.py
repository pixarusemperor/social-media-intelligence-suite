import os
import sys
import json
import subprocess
from pathlib import Path

BASE_DIR = Path("/root/Apify")
DEFAULT_PROXY = "http://127.0.0.1:8118"

def download_channel(channel_dir, proxy):
    print(f"\n========================================================")
    print(f"Processing Channel Directory: {channel_dir.name}")
    print(f"========================================================")

    subfolders = sorted([p for p in channel_dir.iterdir() if p.is_dir()])
    print(f"Found {len(subfolders)} video directories to process.")

    for folder in subfolders:
        meta_json_path = folder / "metadata.json"
        if not meta_json_path.exists():
            continue

        with open(meta_json_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        video_id = metadata.get("id") or metadata.get("videoId")
        title = metadata.get("title") or video_id
        video_url = metadata.get("url") or f"https://www.youtube.com/watch?v={video_id}"
        output_file = folder / f"{video_id}.mp4"

        if output_file.exists() and output_file.stat().st_size > 5 * 1024 * 1024:
            print(f"[DONE] Video already downloaded: {output_file.name} ({output_file.stat().st_size / (1024*1024):.1f} MB)")
            continue

        print(f"\n--------------------------------------------------------")
        print(f"Starting download for: {title}")
        print(f"URL: {video_url}")
        print(f"Target: {output_file}")
        print(f"--------------------------------------------------------")

        cmd = [
            "yt-dlp",
            "--proxy", proxy,
            "--format", "bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "--output", str(output_file),
            "--no-playlist",
            "--retries", "15",
            "--fragment-retries", "15",
            "--continue",
            video_url,
        ]

        try:
            subprocess.run(cmd, check=True)
            print(f"Successfully downloaded {output_file.name}!")
        except subprocess.CalledProcessError as e:
            print(f"Failed to download {video_url}: Exit code {e.returncode}")

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    proxy = os.environ.get("PROXY_URL", DEFAULT_PROXY)
    print(f"Using proxy: {proxy}")

    if target == "all":
        channels = ["vitalnasser", "produitsdigitauxtorif", "nolimitvousdv"]
    else:
        channels = [target]

    for ch_name in channels:
        ch_path = BASE_DIR / ch_name
        if ch_path.exists() and ch_path.is_dir():
            download_channel(ch_path, proxy)
        else:
            print(f"Directory not found: {ch_path}")

if __name__ == "__main__":
    main()
