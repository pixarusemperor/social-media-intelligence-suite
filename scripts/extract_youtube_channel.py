#!/usr/bin/env python3
"""
Zero-Cost YouTube Channel & Video Comments Intelligence Extractor
Extracts deep video metadata (views, likes, comments count, duration, categories, tags, upload dates)
and full comment threads (author, channel, text, likes, replies, timestamps).
Runs with 0 paid proxies and no Apify actors or tokens.
"""

import os
import sys
import json
import re
import time
import argparse
from datetime import datetime, timezone
from collections import Counter
import yt_dlp
from curl_cffi import requests

def format_duration(seconds):
    if not seconds:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def parse_iso_date_to_human(iso_str):
    if not iso_str:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%B %d, %Y at %I:%M %p %Z").strip()
    except Exception:
        return iso_str

def get_channel_videos(channel_url, limit=10, proxy=None):
    if not channel_url.endswith("/videos"):
        if channel_url.endswith("/"):
            channel_url = channel_url + "videos"
        else:
            channel_url = channel_url + "/videos"

    print(f"Discovering the latest {limit} videos from {channel_url}...")
    ydl_opts = {
        'extract_flat': True,
        'playlist_items': f'1-{limit}',
        'quiet': True,
        'no_warnings': True,
    }
    if proxy:
        ydl_opts['proxy'] = proxy

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        res = ydl.extract_info(channel_url, download=False)
        entries = res.get('entries', [])
        videos = []
        for e in entries[:limit]:
            videos.append({
                'id': e.get('id'),
                'title': e.get('title'),
                'url': f"https://www.youtube.com/watch?v={e.get('id')}"
            })
        return videos

def fetch_html_metadata(video_id, proxy=None):
    url = f"https://www.youtube.com/watch?v={video_id}"
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        r = requests.get(url, proxies=proxies, impersonate="chrome120", timeout=15)
        html = r.text
        
        date_iso = None
        m_date = re.search(r'itemprop="datePublished" content="([^"]+)"', html)
        if not m_date:
            m_date = re.search(r'"publishDate":"([^"]+)"', html)
        if not m_date:
            m_date = re.search(r'"uploadDate":"([^"]+)"', html)
        if m_date:
            date_iso = m_date.group(1)
            
        category = None
        keywords = []
        tags = re.findall(r'<meta property="og:video:tag" content="([^"]+)">', html)
        
        m_player = re.search(r'ytInitialPlayerResponse\s*=\s*({.+?});', html)
        if m_player:
            try:
                pdata = json.loads(m_player.group(1))
                category = pdata.get('microformat', {}).get('playerMicroformatRenderer', {}).get('category')
                keywords = pdata.get('videoDetails', {}).get('keywords', []) or []
            except Exception:
                pass
                
        return {
            'date_iso': date_iso,
            'category': category,
            'keywords': keywords,
            'tags': tags
        }
    except Exception as e:
        print(f"  [warn] curl_cffi error for {video_id}: {e}")
        return {'date_iso': None, 'category': None, 'keywords': [], 'tags': []}

def extract_video_details(video_id, url, proxy=None):
    ydl_opts = {
        'getcomments': True,
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
    }
    if proxy:
        ydl_opts['proxy'] = proxy
    
    for attempt in range(1, 4):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        except Exception as e:
            print(f"  [warn] Attempt {attempt} failed for {video_id}: {e}")
            if attempt < 3:
                time.sleep(3)
            else:
                raise e

def process_comments(raw_comments):
    if not raw_comments:
        return []
    
    replies_count_map = Counter()
    for c in raw_comments:
        parent = c.get('parent')
        if parent and parent != 'root':
            replies_count_map[parent] += 1
            
    processed = []
    for c in raw_comments:
        cid = c.get('id')
        parent = c.get('parent', 'root')
        timestamp = c.get('timestamp')
        date_iso = None
        date_human = None
        if timestamp:
            try:
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                date_iso = dt.isoformat()
                date_human = dt.strftime("%B %d, %Y at %I:%M %p UTC")
            except Exception:
                pass
                
        processed.append({
            'comment_id': cid,
            'parent_id': parent,
            'author_name': c.get('author') or 'Unknown',
            'author_channel_url': c.get('author_url'),
            'author_channel_id': c.get('author_id'),
            'author_thumbnail': c.get('author_thumbnail'),
            'text': c.get('text') or '',
            'like_count': c.get('like_count', 0) or 0,
            'published_time_text': c.get('_time_text') or c.get('time_text'),
            'published_timestamp': timestamp,
            'published_date_iso': date_iso,
            'published_date_human': date_human,
            'reply_count': replies_count_map.get(cid, 0) if parent == 'root' else 0,
            'is_pinned': bool(c.get('is_pinned', False)),
            'is_uploader': bool(c.get('author_is_uploader', False)),
            'is_favorited': bool(c.get('is_favorited', False))
        })
        
    return processed

def generate_video_markdown(video_data, comments):
    title = video_data['title']
    vid = video_data['video_id']
    url = video_data['url']
    views = f"{video_data['view_count']:,}"
    likes = f"{video_data['like_count']:,}"
    comment_count = f"{video_data['comment_count']:,}"
    duration = video_data['duration_formatted']
    upload_iso = video_data['published_at_iso'] or "N/A"
    upload_human = video_data['published_at_human'] or "N/A"
    category = ", ".join(video_data['categories']) if video_data['categories'] else "Not Specified"
    keywords = ", ".join(video_data['keywords']) if video_data['keywords'] else "None"
    tags = ", ".join(video_data['tags']) if video_data['tags'] else "None"
    description = video_data['description'] or "*No description provided.*"
    
    md = []
    md.append(f"# {title}\n")
    md.append(f"**Video ID:** `{vid}`  ")
    md.append(f"**URL:** [{url}]({url})  ")
    md.append(f"**Channel:** [{video_data['channel_title']}]({video_data['channel_url']})\n")
    
    md.append("## Video Metadata\n")
    md.append("| Metric | Value |")
    md.append("| :--- | :--- |")
    md.append(f"| **Views** | {views} |")
    md.append(f"| **Likes** | {likes} |")
    md.append(f"| **Comments** | {comment_count} (Retrieved: {len(comments)}) |")
    md.append(f"| **Duration** | {duration} ({video_data['duration_seconds']}s) |")
    md.append(f"| **Upload Date (ISO)** | `{upload_iso}` |")
    md.append(f"| **Upload Date (Human)** | {upload_human} |")
    md.append(f"| **Category** | {category} |")
    md.append(f"| **Tags** | {tags} |")
    md.append(f"| **Keywords** | {keywords} |\n")
    
    md.append("## Description Copy\n")
    md.append("```text")
    md.append(description)
    md.append("```\n")
    
    md.append(f"## Comments ({len(comments)} comments extracted)\n")
    
    top_level = [c for c in comments if c['parent_id'] == 'root']
    replies_by_parent = {}
    for c in comments:
        if c['parent_id'] != 'root':
            replies_by_parent.setdefault(c['parent_id'], []).append(c)
            
    top_level_sorted = sorted(top_level, key=lambda x: (x['is_pinned'], x['like_count']), reverse=True)
    
    if not top_level_sorted:
        md.append("*No comments available for this video.*\n")
    else:
        for idx, c in enumerate(top_level_sorted, 1):
            pin_badge = "📌 **[PINNED]** " if c['is_pinned'] else ""
            uploader_badge = " *(Creator)*" if c['is_uploader'] else ""
            time_str = c['published_time_text'] or c['published_date_human'] or "Recently"
            likes_str = f"👍 {c['like_count']:,}" if c['like_count'] > 0 else "👍 0"
            
            md.append(f"### {idx}. {pin_badge}**{c['author_name']}**{uploader_badge} • `{time_str}` • {likes_str}")
            if c['author_channel_url']:
                md.append(f"Channel: [{c['author_channel_url']}]({c['author_channel_url']})\n")
            
            clean_text = "\n> ".join(c['text'].split("\n"))
            md.append(f"> {clean_text}\n")
            
            child_replies = replies_by_parent.get(c['comment_id'], [])
            if child_replies:
                md.append(f"<details><summary><b>View {len(child_replies)} Replies</b></summary>\n")
                for r in child_replies:
                    r_up_badge = " *(Creator)*" if r['is_uploader'] else ""
                    r_time = r['published_time_text'] or r['published_date_human'] or "Recently"
                    r_likes = f"👍 {r['like_count']:,}" if r['like_count'] > 0 else "👍 0"
                    r_text = "\n>> ".join(r['text'].split("\n"))
                    md.append(f"> **{r['author_name']}**{r_up_badge} • `{r_time}` • {r_likes}")
                    md.append(f">> {r_text}\n")
                md.append("</details>\n")
                
    return "\n".join(md)

def generate_catalog_markdown(videos_summary):
    channel = videos_summary['channel']
    md = []
    md.append(f"# YouTube Video Catalog: {channel['name']}\n")
    md.append(f"**Channel:** [{channel['name']}]({channel['url']})  ")
    md.append(f"**Extraction Timestamp:** `{videos_summary['extraction_timestamp']}`  ")
    md.append(f"**Total Videos Analyzed:** `{videos_summary['total_videos_analyzed']}`  \n")
    
    ag = videos_summary['aggregate_metrics']
    md.append("## Executive Performance Overview\n")
    md.append("| Metric | Aggregate Value | Average Per Video |")
    md.append("| :--- | :--- | :--- |")
    md.append(f"| **Total Views** | **{ag['total_views']:,}** | {ag['average_views']:,} views |")
    md.append(f"| **Total Likes** | **{ag['total_likes']:,}** | {ag['average_likes']:,} likes |")
    md.append(f"| **Total Comments** | **{ag['total_comments']:,}** | {ag['average_comments']:,} comments |")
    md.append(f"| **Content Duration** | **{ag['total_duration_formatted']}** ({ag['total_duration_seconds']:,}s) | {format_duration(ag['total_duration_seconds'] // max(1, len(videos_summary['videos'])))} |")
    md.append(f"| **Date Coverage** | {videos_summary['date_range']['earliest_upload']} to {videos_summary['date_range']['latest_upload']} |\n")
    
    md.append("## Video Catalog Comparison\n")
    md.append("| # | Title | Video ID | Upload Date | Duration | Views | Likes | Comments | Link |")
    md.append("| :-: | :--- | :-: | :-: | :-: | -: | -: | -: | :--- |")
    
    for v in videos_summary['videos']:
        title_escaped = v['title'].replace('|', '\\|')
        md.append(f"| {v['index']} | [{title_escaped}]({v['folder']}/video.md) | `{v['video_id']}` | {v['published_at_human'].split(' at ')[0]} | {v['duration_formatted']} | {v['view_count']:,} | {v['like_count']:,} | {v['comment_count']:,} | [Watch Video]({v['url']}) |")
        
    return "\n".join(md)

def main():
    parser = argparse.ArgumentParser(description="Extract YouTube channel videos, deep metadata, and comments without paid proxies or Apify.")
    parser.add_argument("--channel-url", default="https://www.youtube.com/@markbuildsbrands/videos", help="Target YouTube channel URL")
    parser.add_argument("--limit", type=int, default=10, help="Number of latest videos to extract (default: 10)")
    parser.add_argument("--output-dir", default="youtube/markbuildsbrands/videos", help="Directory where results will be stored")
    parser.add_argument("--proxy", default="socks5://127.0.0.1:9050", help="Proxy URL (default: socks5://127.0.0.1:9050, pass '' for direct)")
    args = parser.parse_args()

    proxy = args.proxy if args.proxy else None
    os.makedirs(args.output_dir, exist_ok=True)

    videos = get_channel_videos(args.channel_url, limit=args.limit, proxy=proxy)
    print(f"Discovered {len(videos)} videos to extract.")

    summary_videos = []
    total_views = 0
    total_likes = 0
    total_comments = 0
    total_duration = 0
    dates_iso = []

    for idx, item in enumerate(videos, 1):
        vid = item['id']
        url = item['url']
        folder_name = f"video_{idx:02d}"
        folder_path = os.path.join(args.output_dir, folder_name)
        os.makedirs(folder_path, exist_ok=True)
        
        print(f"\n[{idx}/{len(videos)}] Extracting {vid}: {item['title']}...")
        html_meta = fetch_html_metadata(vid, proxy=proxy)
        info = extract_video_details(vid, url, proxy=proxy)
        
        date_iso = html_meta['date_iso']
        if not date_iso and info.get('upload_date'):
            ud = info.get('upload_date')
            date_iso = f"{ud[:4]}-{ud[4:6]}-{ud[6:8]}"
            
        date_human = parse_iso_date_to_human(date_iso)
        
        categories = []
        if html_meta.get('category'):
            categories.append(html_meta['category'])
        elif info.get('categories'):
            categories = info.get('categories')
            
        keywords = html_meta.get('keywords') or []
        tags = html_meta.get('tags') or info.get('tags') or []
        
        video_data = {
            "index": idx,
            "folder": folder_name,
            "video_id": vid,
            "url": url,
            "title": info.get('title') or item['title'],
            "channel_title": info.get('channel') or "Channel",
            "channel_id": info.get('channel_id') or "",
            "channel_url": info.get('channel_url') or args.channel_url,
            "description": info.get('description') or "",
            "published_at_iso": date_iso,
            "published_at_human": date_human,
            "view_count": int(info.get('view_count') or 0),
            "like_count": int(info.get('like_count') or 0),
            "comment_count": int(info.get('comment_count') or len(info.get('comments', []))),
            "duration_seconds": int(info.get('duration') or 0),
            "duration_formatted": info.get('duration_string') or format_duration(info.get('duration')),
            "categories": categories,
            "tags": tags,
            "keywords": keywords,
            "extracted_at": datetime.now(timezone.utc).isoformat()
        }
        
        comments = process_comments(info.get('comments', []))
        print(f"  -> Extracted: {video_data['view_count']:,} views, {video_data['like_count']:,} likes, {len(comments)} comments, duration: {video_data['duration_formatted']}")
        
        video_json_path = os.path.join(folder_path, "video.json")
        comments_json_path = os.path.join(folder_path, "comments.json")
        video_md_path = os.path.join(folder_path, "video.md")
        
        with open(video_json_path, "w", encoding="utf-8") as f:
            json.dump(video_data, f, indent=2, ensure_ascii=False)
            
        with open(comments_json_path, "w", encoding="utf-8") as f:
            json.dump(comments, f, indent=2, ensure_ascii=False)
            
        video_md_content = generate_video_markdown(video_data, comments)
        with open(video_md_path, "w", encoding="utf-8") as f:
            f.write(video_md_content)
            
        total_views += video_data['view_count']
        total_likes += video_data['like_count']
        total_comments += video_data['comment_count']
        total_duration += video_data['duration_seconds']
        if date_iso:
            dates_iso.append(date_iso)
            
        summary_videos.append({
            "index": idx,
            "folder": folder_name,
            "video_id": vid,
            "title": video_data['title'],
            "url": url,
            "published_at_iso": date_iso,
            "published_at_human": date_human,
            "view_count": video_data['view_count'],
            "like_count": video_data['like_count'],
            "comment_count": video_data['comment_count'],
            "duration_seconds": video_data['duration_seconds'],
            "duration_formatted": video_data['duration_formatted'],
            "categories": categories
        })
        time.sleep(1)

    dates_iso_sorted = sorted(dates_iso)
    earliest_date = dates_iso_sorted[0] if dates_iso_sorted else "Unknown"
    latest_date = dates_iso_sorted[-1] if dates_iso_sorted else "Unknown"
    
    channel_name = summary_videos[0]['title'] if summary_videos else "Channel"
    videos_summary = {
        "channel": {
            "name": channel_name,
            "url": args.channel_url
        },
        "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_videos_analyzed": len(summary_videos),
        "aggregate_metrics": {
            "total_views": total_views,
            "average_views": int(total_views / len(summary_videos)) if summary_videos else 0,
            "total_likes": total_likes,
            "average_likes": int(total_likes / len(summary_videos)) if summary_videos else 0,
            "total_comments": total_comments,
            "average_comments": int(total_comments / len(summary_videos)) if summary_videos else 0,
            "total_duration_seconds": total_duration,
            "total_duration_formatted": format_duration(total_duration)
        },
        "date_range": {
            "earliest_upload": earliest_date,
            "latest_upload": latest_date
        },
        "videos": summary_videos
    }
    
    summary_json_path = os.path.join(args.output_dir, "videos_summary.json")
    catalog_md_path = os.path.join(args.output_dir, "CATALOG.md")
    
    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(videos_summary, f, indent=2, ensure_ascii=False)
        
    catalog_md_content = generate_catalog_markdown(videos_summary)
    with open(catalog_md_path, "w", encoding="utf-8") as f:
        f.write(catalog_md_content)
        
    print("\n" + "="*50)
    print(f"EXTRACTION COMPLETED FOR {len(summary_videos)} VIDEOS!")
    print(f"Saved to: {args.output_dir}")
    print(f"Summary JSON: {summary_json_path}")
    print(f"Catalog Markdown: {catalog_md_path}")
    print(f"Total Views: {total_views:,} | Total Likes: {total_likes:,} | Total Comments: {total_comments:,}")
    print("="*50)

if __name__ == '__main__':
    main()
