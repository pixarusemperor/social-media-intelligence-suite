"""
download_videos.py - YouTube Livestream Downloader via Zero-Cost Unmetered Proxy

Downloads YouTube livestream recordings through a local Privoxy/Tor proxy bridge
(http://127.0.0.1:8118), preventing datacenter IP blocks without incurring metered bandwidth costs.
"""

import os
import sys
import json
import socket
import argparse
import subprocess
from pathlib import Path

BASE_DIR = Path("/root/Apify")
DEFAULT_PROXY = "http://127.0.0.1:8118"

# Channel-specific download rules:
# vitalnasser & produitsdigitauxtorif: all live streams
# nolimitvousdv: strictly latest live stream per user requirement
CHANNEL_CONFIG = {
    "vitalnasser": {"all": True},
    "produitsdigitauxtorif": {"all": True},
    "nolimitvousdv": {"all": False, "latest_only": True}
}

def check_proxy_reachability(proxy_url):
    """Verifies that the proxy endpoint is listening before starting yt-dlp."""
    try:
        host = proxy_url.split("://")[-1].split(":")[0]
        port = int(proxy_url.split(":")[-1].split("/")[0])
        with socket.create_connection((host, port), timeout=3):
            return True
    except Exception:
        return False

def download_channel(channel_dir, proxy, latest_only=False, timeout=7200):
    """
    Downloads videos for a given channel directory.
    
    Args:
        channel_dir: Path to the channel directory.
        proxy: Proxy URL (e.g. http://127.0.0.1:8118).
        latest_only: If True, only downloads the latest livestream.
        timeout: Subprocess execution timeout in seconds.
    """
    print(f"\n========================================================")
    print(f"Processing Channel Directory: {channel_dir.name}")
    print(f"========================================================")

    subfolders = sorted([p for p in channel_dir.iterdir() if p.is_dir()])
    if latest_only:
        # Find folder with newest publication date in metadata
        latest_folder = None
        latest_date = ""
        for folder in subfolders:
            meta_json = folder / "metadata.json"
            if meta_json.exists():
                try:
                    data = json.loads(meta_json.read_text(encoding="utf-8"))
                    d = data.get("date", "")
                    if d > latest_date:
                        latest_date = d
                        latest_folder = folder
                except Exception:
                    pass
        subfolders = [latest_folder] if latest_folder else subfolders[-1:]
        print(f"Scope: Latest live stream only -> {subfolders[0].name}")
    else:
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
            subprocess.run(cmd, check=True, timeout=timeout)
            print(f"Successfully downloaded {output_file.name}!")
        except subprocess.TimeoutExpired:
            print(f"ERROR: Download timed out after {timeout} seconds for {video_url}")
        except subprocess.CalledProcessError as e:
            print(f"ERROR: Failed to download {video_url}: Exit code {e.returncode}")

def main():
    parser = argparse.ArgumentParser(description="Download YouTube livestreams through unmetered local proxy.")
    parser.add_argument("channel", nargs="?", default="all", choices=["all", "vitalnasser", "produitsdigitauxtorif", "nolimitvousdv"],
                        help="Target channel to download (default: all)")
    parser.add_argument("--proxy", default=os.environ.get("PROXY_URL", DEFAULT_PROXY),
                        help="Proxy endpoint URL (default: http://127.0.0.1:8118)")
    parser.add_argument("--skip-proxy-check", action="store_true",
                        help="Skip pre-flight proxy socket connectivity check")
    parser.add_argument("--timeout", type=int, default=7200,
                        help="Timeout in seconds per video download (default: 7200s)")
    args = parser.parse_args()

    if not args.skip_proxy_check and not check_proxy_reachability(args.proxy):
        print(f"ERROR: Proxy {args.proxy} is not reachable! Ensure Tor and Privoxy are running.")
        sys.exit(1)

    channels = ["vitalnasser", "produitsdigitauxtorif", "nolimitvousdv"] if args.channel == "all" else [args.channel]

    for ch_name in channels:
        ch_path = BASE_DIR / ch_name
        if ch_path.exists() and ch_path.is_dir():
            config = CHANNEL_CONFIG.get(ch_name, {})
            latest_only = config.get("latest_only", False)
            download_channel(ch_path, args.proxy, latest_only=latest_only, timeout=args.timeout)
        else:
            print(f"Directory not found: {ch_path}")

if __name__ == "__main__":
    main()
