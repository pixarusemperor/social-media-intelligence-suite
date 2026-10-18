#!/usr/bin/env python3
"""
extract_youtube_transcripts.py - Zero-Cost YouTube Transcript & Caption Harvester

Extracts transcripts and captions for every video of any YouTube channel for $0.00
using local unmetered Tor+Privoxy gateway + Chrome TLS impersonation (curl_cffi).
No paid proxies. No Apify.

Outputs for each video:
  - transcript.txt  (clean human-readable text with [HH:MM:SS] timestamps)
  - transcript.srt  (standard SubRip subtitle format)
  - transcript.json (structured timestamps, duration, text segments)
  - metadata.json   (video metadata: title, duration, view count, etc.)
"""

import os
import sys
import re
import json
import time
import argparse
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests

DEFAULT_PROXY = "http://127.0.0.1:8118"
BASE_DIR = Path("/root/Apify")

def sanitize_filename(name: str, max_length: int = 80) -> str:
    """Sanitizes strings for safe cross-platform directory and file naming."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r'\s+', " ", clean).strip()
    return clean[:max_length]

def format_timestamp_txt(seconds: float) -> str:
    """Formats seconds into [HH:MM:SS] string."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"[{h:02d}:{m:02d}:{s:02d}]"

def format_timestamp_srt(seconds: float) -> str:
    """Formats seconds into HH:MM:SS,mmm string for SRT subtitles."""
    millis = int(round((seconds - int(seconds)) * 1000))
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"

def get_channel_inventory(channel_url: str, proxy: str, include_streams: bool = True, include_shorts: bool = False):
    """
    Retrieves full inventory of videos for a YouTube channel via yt-dlp flat playlist.
    """
    endpoints = []
    base = channel_url.rstrip("/")
    endpoints.append((f"{base}/videos", "video"))
    if include_streams:
        endpoints.append((f"{base}/streams", "stream"))
    if include_shorts:
        endpoints.append((f"{base}/shorts", "short"))

    all_items = []
    seen_ids = set()

    for url, category in endpoints:
        print(f"[*] Discovering {category}s from: {url}")
        cmd = ["yt-dlp", "--proxy", proxy, "--flat-playlist", "--dump-json", url]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            print(f"  [!] Warning querying {url}: {res.stderr[:120]}")
            continue

        count = 0
        for line in res.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                vid_id = item.get("id")
                if vid_id and vid_id not in seen_ids:
                    seen_ids.add(vid_id)
                    item["_category"] = category
                    all_items.append(item)
                    count += 1
            except Exception:
                pass
        print(f"  [+] Found {count} {category}s")

    return all_items

def fetch_video_transcript(video_id: str, proxy: str, retries: int = 3):
    """
    Extracts transcript track URL via yt-dlp through Tor, then fetches raw json3
    using curl_cffi with Chrome TLS impersonation to bypass 429/bot checks.
    """
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = ["yt-dlp", "--proxy", proxy, "--dump-json", video_url]
    
    data = None
    for attempt in range(retries):
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            try:
                data = json.loads(res.stdout)
                break
            except Exception:
                pass
        time.sleep(1)

    if not data:
        return None, "Failed to retrieve video metadata from YouTube"

    title = data.get("title") or f"video_{video_id}"
    duration = data.get("duration") or 0
    upload_date = data.get("upload_date") or ""
    view_count = data.get("view_count") or 0
    like_count = data.get("like_count") or 0

    auto_subs = data.get("automatic_captions", {})
    manual_subs = data.get("subtitles", {})

    track = None
    # 1. Prefer manual English subtitles
    for lang in ["en", "en-US", "en-GB"]:
        if lang in manual_subs and manual_subs[lang]:
            track = manual_subs[lang][0]
            track_type = "manual"
            break

    # 2. Fall back to automatic captions
    if not track:
        for lang in ["en-orig", "en", "en-US"]:
            if lang in auto_subs and auto_subs[lang]:
                # Prefer json3 format if already available
                for item in auto_subs[lang]:
                    if item.get("ext") == "json3":
                        track = item
                        break
                if not track:
                    track = auto_subs[lang][0]
                track_type = "auto"
                break

    if not track:
        return None, "No English transcript track found on YouTube for this video"

    caption_url = track["url"]
    # Ensure json3 format is requested
    if "fmt=" not in caption_url:
        caption_url += "&fmt=json3"
    elif "&fmt=" in caption_url and "fmt=json3" not in caption_url:
        caption_url = re.sub(r"&fmt=[^&]+", "&fmt=json3", caption_url)

    # Fetch transcript with curl_cffi using Chrome TLS impersonation
    r = None
    for attempt in range(retries):
        try:
            r = requests.get(caption_url, impersonate="chrome124", timeout=15)
            if r.status_code == 200 and len(r.text) > 0:
                break
        except Exception:
            pass
        time.sleep(1)

    if not r or r.status_code != 200:
        status = r.status_code if r else "Timeout"
        return None, f"HTTP {status} fetching transcript from timedtext"

    try:
        subs_json = r.json()
    except Exception as e:
        return None, f"Failed to parse transcript JSON: {e}"

    events = subs_json.get("events", [])
    snippets = []
    full_text_parts = []

    for ev in events:
        start_ms = ev.get("tStartMs", 0)
        dur_ms = ev.get("dDurationMs", 0)
        segs = ev.get("segs", [])
        seg_text = "".join([s.get("utf8", "") for s in segs]).strip()
        if seg_text and seg_text != "\n":
            start_sec = start_ms / 1000.0
            dur_sec = dur_ms / 1000.0
            snippets.append({
                "start": round(start_sec, 2),
                "duration": round(dur_sec, 2),
                "text": seg_text
            })
            full_text_parts.append(seg_text)

    result = {
        "id": video_id,
        "title": title,
        "duration": duration,
        "upload_date": upload_date,
        "view_count": view_count,
        "like_count": like_count,
        "url": video_url,
        "track_type": track_type,
        "snippets_count": len(snippets),
        "snippets": snippets,
        "plain_text": " ".join(full_text_parts)
    }

    return result, None

def process_single_video(index: int, total: int, item: dict, out_dir: Path, proxy: str):
    """Worker task: extracts, formats, and persists transcript for a single video."""
    video_id = item.get("id")
    title = item.get("title") or f"video_{video_id}"
    category = item.get("_category", "video")
    clean_title = sanitize_filename(title)
    folder_name = f"{index:03d}_{clean_title}_{video_id}"
    target_dir = out_dir / folder_name

    txt_file = target_dir / "transcript.txt"
    srt_file = target_dir / "transcript.srt"
    json_file = target_dir / "transcript.json"
    meta_file = target_dir / "metadata.json"

    # Skip if already downloaded
    if txt_file.exists() and json_file.exists() and txt_file.stat().st_size > 50:
        return {
            "status": "SKIPPED",
            "id": video_id,
            "title": title,
            "folder": folder_name,
            "category": category,
            "reason": "Already exists"
        }

    data, err = fetch_video_transcript(video_id, proxy)
    if err or not data:
        return {
            "status": "FAILED",
            "id": video_id,
            "title": title,
            "folder": folder_name,
            "category": category,
            "error": err
        }

    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write transcript.txt (human-readable with timestamps)
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n")
        f.write(f"URL: {data['url']}\n")
        f.write(f"Category: {category}\n")
        f.write(f"Duration: {data['duration']}s\n")
        f.write(f"Published: {data['upload_date']}\n")
        f.write(f"Transcript Type: {data['track_type']}\n\n")
        f.write("=" * 60 + "\n\n")
        for snip in data["snippets"]:
            ts = format_timestamp_txt(snip["start"])
            f.write(f"{ts} {snip['text']}\n")

    # 2. Write transcript.srt (standard SubRip)
    with open(srt_file, "w", encoding="utf-8") as f:
        for idx, snip in enumerate(data["snippets"], 1):
            start_ts = format_timestamp_srt(snip["start"])
            end_ts = format_timestamp_srt(snip["start"] + snip["duration"])
            f.write(f"{idx}\n{start_ts} --> {end_ts}\n{snip['text']}\n\n")

    # 3. Write transcript.json
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(data["snippets"], f, indent=2, ensure_ascii=False)

    # 4. Write metadata.json
    meta = {
        "id": video_id,
        "title": title,
        "category": category,
        "duration": data["duration"],
        "upload_date": data["upload_date"],
        "view_count": data["view_count"],
        "like_count": data["like_count"],
        "url": data["url"],
        "track_type": data["track_type"],
        "snippets_count": data["snippets_count"],
        "word_count": len(data["plain_text"].split())
    }
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    return {
        "status": "SUCCESS",
        "id": video_id,
        "title": title,
        "folder": folder_name,
        "category": category,
        "snippets_count": data["snippets_count"],
        "word_count": meta["word_count"]
    }

def main():
    parser = argparse.ArgumentParser(description="Extract transcripts of all YouTube videos for $0.00 without Apify.")
    parser.add_argument("channel", nargs="?", default="https://www.youtube.com/@markbuildsbrands",
                        help="Channel URL to process (default: @markbuildsbrands)")
    parser.add_argument("--output-dir", default=str(BASE_DIR / "transcripts" / "markbuildsbrands"),
                        help="Output directory for transcript folders")
    parser.add_argument("--proxy", default=DEFAULT_PROXY,
                        help="Local unmetered proxy (default: http://127.0.0.1:8118)")
    parser.add_argument("--workers", type=int, default=6,
                        help="Parallel worker threads (default: 6)")
    parser.add_argument("--include-streams", action="store_true", default=True,
                        help="Include live streams tab (default: True)")
    parser.add_argument("--include-shorts", action="store_true", default=False,
                        help="Include shorts tab (default: False)")
    args = parser.parse_args()

    out_path = Path(args.output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    print("==================================================================")
    print(" ZERO-COST YOUTUBE TRANSCRIPT EXTRACTION ENGINE")
    print("==================================================================")
    print(f"Target Channel: {args.channel}")
    print(f"Proxy Gateway:  {args.proxy} (Tor + Privoxy: $0.00)")
    print(f"Concurrency:    {args.workers} worker threads")
    print(f"Destination:    {out_path}")
    print("==================================================================\n")

    # Step 1: Discover all videos
    items = get_channel_inventory(args.channel, args.proxy, include_streams=args.include_streams, include_shorts=args.include_shorts)
    total = len(items)
    print(f"\n[+] Total items discovered: {total}\n")

    if total == 0:
        print("[!] No videos discovered. Check channel URL or proxy status.")
        return

    # Step 2: Extract transcripts concurrently
    results = []
    success_count = 0
    skipped_count = 0
    failed_count = 0

    print("Starting transcript extraction...\n")
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_item = {
            executor.submit(process_single_video, idx, total, item, out_path, args.proxy): (idx, item)
            for idx, item in enumerate(items, 1)
        }

        for future in as_completed(future_to_item):
            idx, item = future_to_item[future]
            try:
                res = future.result()
                results.append(res)
                st = res["status"]
                vid_id = res["id"]
                title = res["title"][:45]

                if st == "SUCCESS":
                    success_count += 1
                    snips = res["snippets_count"]
                    words = res["word_count"]
                    print(f"[{success_count + skipped_count}/{total}] [SUCCESS] ({snips} segments, {words} words) {vid_id} | {title}")
                elif st == "SKIPPED":
                    skipped_count += 1
                    print(f"[{success_count + skipped_count}/{total}] [SKIPPED] {vid_id} | {title}")
                else:
                    failed_count += 1
                    err = res.get("error", "Unknown error")
                    print(f"[{success_count + skipped_count + failed_count}/{total}] [FAILED]  {vid_id} | {err} | {title}")
            except Exception as e:
                failed_count += 1
                print(f"[ERROR] Worker error on {item.get('id')}: {e}")

    elapsed = time.time() - start_time
    print("\n==================================================================")
    print(" EXTRACTION COMPLETED")
    print("==================================================================")
    print(f"Total Videos Processed: {total}")
    print(f"Successfully Extracted: {success_count}")
    print(f"Skipped (Already Done): {skipped_count}")
    print(f"Failed / No Captions:   {failed_count}")
    print(f"Time Elapsed:           {elapsed:.1f} seconds (avg {elapsed/total:.2f}s per video)")
    print(f"Total Bandwidth Cost:   $0.00 (Unmetered)")
    print(f"Saved into:             {out_path}")
    print("==================================================================")

    # Save summary report
    summary_file = out_path / "extraction_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump({
            "channel": args.channel,
            "total_videos": total,
            "success": success_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "elapsed_seconds": round(elapsed, 1),
            "results": results
        }, f, indent=2)
    print(f"\nSummary JSON saved to: {summary_file}")

if __name__ == "__main__":
    main()
