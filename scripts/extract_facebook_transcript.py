#!/usr/bin/env python3
"""
extract_facebook_transcript.py - Zero-Cost Facebook Video & Reel Transcript Pipeline

Unified dual-method pipeline to extract transcripts and subtitles from any Facebook video or reel:
  - Method A (Native Facebook Captions):
      Extracts official creator-uploaded or Meta auto-generated WebVTT/SRT subtitles
      via SSR HTML, Relay GraphQL cache nodes, and yt-dlp.
  - Method B (Zero-Cost Local ASR Fallback):
      When native captions are absent (common across ~80% of reels/videos),
      extracts the lightweight audio stream and transcribes locally using
      faster-whisper (CTranslate2 int8 on CPU) with $0.00 cost and zero external paid APIs.

Outputs for each video:
  - transcript.srt  (standard SubRip subtitle format)
  - transcript.txt  (clean formatted text with [HH:MM:SS] timestamps)
  - transcript.json (structured timestamps, duration, segment metadata)
  - metadata.json   (rich video & extraction metadata)

Also generates master CATALOG.md and transcripts_summary.json.
"""

import os
import sys
import re
import json
import time
import shutil
import argparse
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from curl_cffi import requests

# Groq High-Accuracy Transcriber & Telemetry Monitor
try:
    from groq_transcriber import GroqTranscriber, GroqRateLimitMonitor, load_groq_api_key
    GROQ_AVAILABLE = True
except ImportError:
    try:
        from scripts.groq_transcriber import GroqTranscriber, GroqRateLimitMonitor, load_groq_api_key
        GROQ_AVAILABLE = True
    except ImportError:
        GROQ_AVAILABLE = False

DEFAULT_TOR_PROXY = "socks5://127.0.0.1:9050"
DEFAULT_PRIVOXY = "http://127.0.0.1:8118"
DEFAULT_OUTPUT_DIR = "/root/Apify/facebook/transcripts"

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
}

# Cached Whisper model instance for batch processing
_WHISPER_MODEL_CACHE = {}


def get_whisper_model(model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
    """Loads and caches faster-whisper model."""
    key = (model_size, device, compute_type)
    if key not in _WHISPER_MODEL_CACHE:
        from faster_whisper import WhisperModel
        print(f"  [ASR] Loading faster-whisper model '{model_size}' (device={device}, compute_type={compute_type})...")
        t0 = time.time()
        _WHISPER_MODEL_CACHE[key] = WhisperModel(model_size, device=device, compute_type=compute_type)
        print(f"  [ASR] Model loaded in {time.time() - t0:.2f}s")
    return _WHISPER_MODEL_CACHE[key]


def sanitize_filename(name: str, max_length: int = 50) -> str:
    """Sanitizes strings for safe cross-platform folder and file naming."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r'\s+', " ", clean).strip()
    return clean[:max_length] if clean else "video"


def format_timestamp_srt(seconds: float) -> str:
    """Formats seconds into standard SubRip timestamp HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        seconds += 1
        millis = 0
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"


def format_timestamp_txt(seconds: float) -> str:
    """Formats seconds into [HH:MM:SS] display."""
    if seconds < 0:
        seconds = 0.0
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def format_duration(seconds: float) -> str:
    """Formats duration seconds into human readable string e.g. '10m 11s'."""
    m, s = divmod(int(round(seconds)), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


def parse_subtitles_text(text: str) -> list:
    """
    Parses WebVTT or SRT formatted string into structured segment dictionaries.
    Handles HTML tags, header markers, and varied timestamp precision.
    """
    text = re.sub(r'^WEBVTT[^\n]*\n', '', text.strip(), flags=re.MULTILINE)
    blocks = re.split(r'\n\s*\n', text.strip())
    entries = []
    idx = 1

    def to_seconds(s: str) -> float:
        s = s.replace(',', '.')
        parts = s.split(':')
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(parts[0])

    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        time_line_idx = -1
        for i, l in enumerate(lines):
            if '-->' in l:
                time_line_idx = i
                break
        if time_line_idx == -1:
            continue

        raw_timing = lines[time_line_idx]
        time_parts = raw_timing.split('-->')
        if len(time_parts) != 2:
            continue

        start_token = time_parts[0].strip().split()[0]
        end_token = time_parts[1].strip().split()[0]

        try:
            start_sec = to_seconds(start_token)
            end_sec = to_seconds(end_token)
        except Exception:
            continue

        content_lines = lines[time_line_idx + 1:]
        clean_text = ' '.join(content_lines).strip()
        # Strip HTML and styling tags
        clean_text = re.sub(r'<[^>]+>', '', clean_text)
        clean_text = re.sub(r'\{[^\}]+\}', '', clean_text)

        if clean_text:
            entries.append({
                'id': idx,
                'start': round(start_sec, 3),
                'end': round(end_sec, 3),
                'duration': round(end_sec - start_sec, 3),
                'start_srt': format_timestamp_srt(start_sec),
                'end_srt': format_timestamp_srt(end_sec),
                'start_txt': format_timestamp_txt(start_sec),
                'text': clean_text
            })
            idx += 1

    return entries


def extract_video_id(url_or_id: str) -> str:
    """Extracts the numeric Facebook Video/Reel ID from varied URL formats or raw string."""
    clean = str(url_or_id).strip()
    if clean.isdigit():
        return clean
    patterns = [
        r'/reel/(\d+)',
        r'/videos/(\d+)',
        r'[?&]v=(\d+)',
        r'story_fbid=(\d+)',
        r'/watch/\?v=(\d+)',
        r'/posts/(\d+)',
        r'(\d{10,25})'
    ]
    for pat in patterns:
        m = re.search(pat, clean)
        if m:
            return m.group(1)
    return clean


def normalize_facebook_url(url_or_id: str) -> str:
    """Normalizes any input to canonical Facebook watch/reel URL."""
    vid = extract_video_id(url_or_id)
    if "reel" in str(url_or_id).lower():
        return f"https://www.facebook.com/reel/{vid}"
    return f"https://www.facebook.com/watch/?v={vid}"


def probe_facebook_ssr_captions(url: str, proxy: str = DEFAULT_TOR_PROXY) -> dict:
    """
    Directly inspects Facebook SSR HTML response for video_available_captions_locales
    and direct CDN .srt URLs.
    """
    proxies = {'http': proxy, 'https': proxy} if proxy else None
    result = {'captions': {}, 'title': None}
    try:
        r = requests.get(url, impersonate='chrome124', headers=DEFAULT_HEADERS, proxies=proxies, timeout=20)
        if r.status_code == 200:
            # Extract og:title
            m_title = re.search(r'<meta\s+property=\"og:title\"\s+content=\"([^\"]+)\"', r.text)
            if m_title:
                result['title'] = m_title.group(1).replace("&quot;", '"').replace("&#039;", "'").replace("&amp;", "&")

            # Extract video_available_captions_locales JSON snippet
            m_locales = re.search(r'\"video_available_captions_locales\":(\[[^\]]+\])', r.text)
            if m_locales:
                try:
                    locales_json = json.loads(m_locales.group(1))
                    for item in locales_json:
                        c_url = item.get('captions_url', '').replace(r'\/', '/').replace(r'\u0025', '%')
                        c_loc = item.get('locale', 'und')
                        c_method = item.get('localized_creation_method', '')
                        if c_url:
                            result['captions'][c_loc] = {
                                'url': c_url,
                                'creation_method': c_method,
                                'type': 'automatic' if ('auto' in c_method.lower() or 'généré' in c_method.lower()) else 'uploaded'
                            }
                except Exception:
                    pass

            # Search direct .srt CDN URLs
            if not result['captions']:
                for srt_match in re.finditer(r'(https://[^\"]+?\.srt[^\"]*)', r.text):
                    clean_srt_url = srt_match.group(1).replace(r'\/', '/').replace(r'\u0025', '%')
                    result['captions']['und'] = {
                        'url': clean_srt_url,
                        'creation_method': 'detected',
                        'type': 'detected'
                    }
                    break
    except Exception as e:
        # Ignore network errors in probe; will fallback to yt-dlp probe
        pass
    return result


def extract_metadata_and_captions_ytdlp(url: str, proxy: str = DEFAULT_TOR_PROXY) -> dict:
    """Uses yt-dlp to inspect video metadata, native subtitles and auto-captions."""
    cmd = [
        "yt-dlp",
        "-j",
        "--skip-download",
        "--no-playlist",
    ]
    if proxy:
        cmd.extend(["--proxy", proxy])
    cmd.append(url)

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=35)
        if res.returncode == 0 and res.stdout.strip():
            info = json.loads(res.stdout)
            return {
                'id': info.get('id'),
                'title': info.get('title'),
                'uploader': info.get('uploader'),
                'duration': info.get('duration'),
                'subtitles': info.get('subtitles', {}) or {},
                'automatic_captions': info.get('automatic_captions', {}) or {},
                'view_count': info.get('view_count'),
                'like_count': info.get('like_count'),
                'comment_count': info.get('comment_count'),
                'raw_info': info
            }
        else:
            err_msg = res.stderr.strip()[:300]
            return {'error': err_msg}
    except Exception as e:
        return {'error': str(e)}


def select_best_caption_track(captions_dict: dict, preferred_lang: str = "auto") -> tuple:
    """
    Selects the optimal subtitle track matching preferred_lang or defaults to original.
    Returns (lang_key, track_info_dict).
    """
    if not captions_dict:
        return None, None

    keys = list(captions_dict.keys())

    if preferred_lang and preferred_lang.lower() != "auto":
        pref = preferred_lang.lower()
        # Direct match
        for k in keys:
            if k.lower() == pref or k.lower().startswith(pref + "_") or k.lower().startswith(pref + "-"):
                track = captions_dict[k]
                return k, track[0] if isinstance(track, list) else track

    # Priority to French or English if present, else first
    priority_order = ['fr_CA', 'fr_FR', 'fr', 'en_US', 'en_GB', 'en', keys[0]]
    for p in priority_order:
        for k in keys:
            if k.lower() == p.lower() or k.lower().startswith(p.lower() + "_"):
                track = captions_dict[k]
                return k, track[0] if isinstance(track, list) else track

    first_key = keys[0]
    track = captions_dict[first_key]
    return first_key, track[0] if isinstance(track, list) else track


def download_subtitles_from_url(sub_url: str, proxy: str = DEFAULT_TOR_PROXY) -> str:
    """Downloads raw subtitle file (.srt / .vtt) from CDN."""
    proxies = {'http': proxy, 'https': proxy} if proxy else None
    r = requests.get(sub_url, impersonate='chrome124', headers=DEFAULT_HEADERS, proxies=proxies, timeout=25)
    if r.status_code == 200 and len(r.text.strip()) > 10:
        return r.text
    raise RuntimeError(f"Failed to fetch subtitle stream from {sub_url} (HTTP {r.status_code})")


def download_audio_stream_ytdlp(url: str, output_path: str, proxy: str = DEFAULT_TOR_PROXY) -> str:
    """
    Downloads lightweight audio-only track using yt-dlp to MP3.
    Audio track is typically only 2-5 MB, minimizing network payload.
    """
    cmd = [
        "yt-dlp",
        "-f", "ba/b",
        "--extract-audio",
        "--audio-format", "mp3",
        "-o", output_path,
        "--no-playlist",
    ]
    if proxy:
        cmd.extend(["--proxy", proxy])
    cmd.append(url)

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
    actual_path = output_path
    if not os.path.isfile(actual_path):
        base, _ = os.path.splitext(output_path)
        actual_path = f"{base}.mp3"

    if os.path.isfile(actual_path) and os.path.getsize(actual_path) > 1000:
        return actual_path
    raise RuntimeError(f"Audio stream extraction failed via yt-dlp: {res.stderr[:300]}")


def transcribe_audio_whisper(
    audio_path: str,
    language: str = "auto",
    model_size: str = "base",
    device: str = "cpu",
    compute_type: str = "int8"
) -> tuple:
    """
    Transcribes audio using faster-whisper with CTranslate2 int8 quantization on CPU.
    Returns (segments_list, detected_lang, info_dict, duration_sec).
    """
    model = get_whisper_model(model_size=model_size, device=device, compute_type=compute_type)

    lang_arg = None if (not language or language.lower() == "auto") else language.lower()

    t0 = time.time()
    segments_iter, info = model.transcribe(
        audio_path,
        language=lang_arg,
        beam_size=1,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500)
    )

    detected_lang = info.language
    segments = []
    idx = 1
    for seg in segments_iter:
        clean_text = seg.text.strip()
        if clean_text:
            segments.append({
                'id': idx,
                'start': round(seg.start, 3),
                'end': round(seg.end, 3),
                'duration': round(seg.end - seg.start, 3),
                'start_srt': format_timestamp_srt(seg.start),
                'end_srt': format_timestamp_srt(seg.end),
                'start_txt': format_timestamp_txt(seg.start),
                'text': clean_text
            })
            idx += 1

    transcribe_duration = time.time() - t0
    audio_duration = getattr(info, 'duration', 0.0) or (segments[-1]['end'] if segments else 0.0)

    meta = {
        'detected_language': detected_lang,
        'language_probability': round(getattr(info, 'language_probability', 1.0), 3),
        'transcription_time_sec': round(transcribe_duration, 2),
        'audio_duration_sec': round(audio_duration, 2),
        'speedup_factor': round(audio_duration / max(transcribe_duration, 0.001), 2),
        'model_size': model_size,
        'compute_type': compute_type,
        'device': device
    }
    return segments, detected_lang, meta, audio_duration


def save_transcript_outputs(
    output_dir: str,
    metadata: dict,
    segments: list
) -> dict:
    """
    Writes transcript.srt, transcript.txt, transcript.json, and metadata.json.
    """
    os.makedirs(output_dir, exist_ok=True)

    srt_path = os.path.join(output_dir, "transcript.srt")
    txt_path = os.path.join(output_dir, "transcript.txt")
    json_path = os.path.join(output_dir, "transcript.json")
    meta_path = os.path.join(output_dir, "metadata.json")

    # 1. Write transcript.srt
    with open(srt_path, "w", encoding="utf-8") as f:
        for seg in segments:
            f.write(f"{seg['id']}\n")
            f.write(f"{seg['start_srt']} --> {seg['end_srt']}\n")
            f.write(f"{seg['text']}\n\n")

    # 2. Write transcript.txt
    total_words = sum(len(seg['text'].split()) for seg in segments)
    metadata['word_count'] = total_words
    metadata['segments_count'] = len(segments)

    formatted_duration = format_duration(metadata.get('duration', 0.0))
    metadata['formatted_duration'] = formatted_duration

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"# {metadata.get('title', 'Facebook Video')}\n")
        f.write(f"URL: {metadata.get('url', '')}\n")
        f.write(f"Video ID: {metadata.get('id', '')}\n")
        f.write(f"Duration: {metadata.get('duration', 0)}s ({formatted_duration})\n")
        f.write(f"Language: {metadata.get('language', 'und')}\n")
        f.write(f"Method: {metadata.get('method_description', metadata.get('method', ''))}\n")
        f.write(f"Word Count: {total_words}\n")
        f.write(f"Segments Count: {len(segments)}\n")
        f.write(f"Extracted At: {metadata.get('extracted_at', '')}\n")
        f.write(f"Cost: $0.00 (Zero paid proxies / Zero Apify)\n")
        f.write("\n" + "=" * 80 + "\n\n")

        for seg in segments:
            f.write(f"{seg['start_txt']} {seg['text']}\n\n")

    # 3. Write transcript.json
    full_json = dict(metadata)
    full_json['segments'] = segments
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(full_json, f, indent=2, ensure_ascii=False)

    # 4. Write metadata.json
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return {
        'srt': srt_path,
        'txt': txt_path,
        'json': json_path,
        'metadata': meta_path,
        'word_count': total_words,
        'segments_count': len(segments)
    }


def find_local_video_for_id(video_id: str, search_roots: list = None) -> str:
    """Searches local filesystem for pre-existing downloaded MP4 file for this video ID."""
    if search_roots is None:
        search_roots = [
            "/root/Apify/facebook/cnicsarl/reels",
            "/root/Apify/facebook/cnicsarl",
            "/root/Apify/facebook",
        ]
    for root in search_roots:
        if not os.path.exists(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            # Check if directory name or reel.json matches
            reel_json = os.path.join(dirpath, "reel.json")
            if os.path.exists(reel_json):
                try:
                    with open(reel_json) as f:
                        data = json.load(f)
                    if str(data.get('fbid')) == str(video_id) or str(data.get('id')) == str(video_id):
                        mp4_candidate = os.path.join(dirpath, "video.mp4")
                        if os.path.isfile(mp4_candidate) and os.path.getsize(mp4_candidate) > 10000:
                            return mp4_candidate
                except Exception:
                    pass

            # Check filename pattern
            for fn in filenames:
                if fn.endswith(".mp4") and video_id in fn:
                    p = os.path.join(dirpath, fn)
                    if os.path.getsize(p) > 10000:
                        return p
    return None


def extract_facebook_transcript(
    url_or_id: str,
    output_base_dir: str = DEFAULT_OUTPUT_DIR,
    method: str = "auto",
    language: str = "auto",
    groq_model: str = "whisper-large-v3",
    whisper_model: str = "large-v3",
    whisper_device: str = "cpu",
    whisper_compute: str = "int8",
    proxy: str = DEFAULT_TOR_PROXY,
    overwrite: bool = False,
    local_file: str = None,
    groq_api_key: str = None
) -> dict:
    """
    Main extraction function for a single Facebook video or reel.
    Methods:
      - 'auto': Native CDN captions -> Groq whisper-large-v3 -> Local faster-whisper
      - 'native': Force Native CDN captions only
      - 'groq': Force Groq whisper-large-v3 LPU transcription
      - 'local' / 'asr': Force local faster-whisper
    """
    video_id = extract_video_id(url_or_id)
    canonical_url = normalize_facebook_url(url_or_id)

    print(f"\n{'='*75}")
    print(f"PROCESSING FACEBOOK TRANSCRIPT: Video ID {video_id}")
    print(f"URL: {canonical_url}")
    print(f"Requested Mode: {method} | Preferred Language: {language}")
    print(f"{'='*75}")

    t_start = time.time()

    # Step 1: Probe metadata & native captions
    print("  [1/4] Probing video metadata and native Facebook captions...")
    yt_meta = extract_metadata_and_captions_ytdlp(canonical_url, proxy=proxy)
    video_title = yt_meta.get('title')
    duration_sec = yt_meta.get('duration') or 0.0

    # Probe direct SSR if yt-dlp did not provide title
    ssr_data = probe_facebook_ssr_captions(canonical_url, proxy=proxy)
    if not video_title and ssr_data.get('title'):
        video_title = ssr_data['title']

    if not video_title:
        video_title = f"Facebook Video {video_id}"

    clean_title_snippet = sanitize_filename(video_title, 40)
    item_folder_name = f"{video_id}_{clean_title_snippet}"
    item_output_dir = os.path.join(output_base_dir, item_folder_name)

    # Check if already processed
    existing_txt = os.path.join(item_output_dir, "transcript.txt")
    if not overwrite and os.path.isfile(existing_txt) and os.path.getsize(existing_txt) > 100:
        print(f"  -> Transcript already exists at {item_output_dir}. Skipping (use --overwrite to force).")
        meta_path = os.path.join(item_output_dir, "metadata.json")
        if os.path.isfile(meta_path):
            with open(meta_path) as f:
                return json.load(f)
        return {'id': video_id, 'folder': item_output_dir, 'status': 'already_exists'}

    # Determine native captions availability
    native_captions_pool = {}
    for loc, tracks in yt_meta.get('subtitles', {}).items():
        native_captions_pool[loc] = {'tracks': tracks, 'type': 'uploaded'}
    for loc, tracks in yt_meta.get('automatic_captions', {}).items():
        if loc not in native_captions_pool:
            native_captions_pool[loc] = {'tracks': tracks, 'type': 'automatic'}
    for loc, data in ssr_data.get('captions', {}).items():
        if loc not in native_captions_pool:
            native_captions_pool[loc] = {'tracks': [{'url': data['url']}], 'type': data.get('type', 'automatic')}

    has_native = len(native_captions_pool) > 0

    if has_native:
        print(f"  [Native Captions Available] Found native captions for languages: {list(native_captions_pool.keys())}")
    else:
        print("  [Native Captions Unavailable] No native subtitles or auto-captions found on Facebook.")

    use_native = False
    if method == "native":
        if not has_native:
            raise RuntimeError(f"Method 'native' was strictly requested, but no native captions exist for {video_id}")
        use_native = True
    elif method in ("asr", "local", "groq"):
        use_native = False
    elif method == "auto":
        use_native = has_native

    # Execute extraction
    extracted_segments = []
    final_method = ""
    method_desc = ""
    final_lang = language
    track_type = ""
    asr_stats = {}

    if use_native:
        # METHOD A: Extract native captions
        print("  [2/4] Executing Method A: Native Transcript Extraction...")
        chosen_lang, chosen_track_wrapper = select_best_caption_track(native_captions_pool, preferred_lang=language)
        track_info = chosen_track_wrapper.get('tracks', [{}])[0]
        track_url = track_info.get('url')
        track_type = chosen_track_wrapper.get('type', 'automatic')
        final_lang = chosen_lang

        print(f"  Selected track: {chosen_lang} (Type: {track_type})")
        raw_caption_text = download_subtitles_from_url(track_url, proxy=proxy)
        extracted_segments = parse_subtitles_text(raw_caption_text)
        final_method = "native_facebook_captions"
        method_desc = f"Method A: Native Facebook Captions ({track_type.capitalize()} {chosen_lang})"

        if extracted_segments and duration_sec == 0.0:
            duration_sec = extracted_segments[-1]['end']
    else:
        # ASR FALLBACK (Groq whisper-large-v3 primary -> Local faster-whisper secondary)
        # Determine audio source: local media file or streaming download
        target_audio_file = None
        temp_audio_dir = None

        if local_file and os.path.isfile(local_file):
            print(f"  Using specified local media file: {local_file}")
            target_audio_file = local_file
        else:
            local_found = find_local_video_for_id(video_id)
            if local_found:
                print(f"  Found pre-existing local video file: {local_found}")
                target_audio_file = local_found
            else:
                print("  Extracting lightweight audio-only stream from Facebook via yt-dlp...")
                temp_audio_dir = tempfile.mkdtemp(prefix="fb_audio_")
                temp_mp3 = os.path.join(temp_audio_dir, f"{video_id}.mp3")
                target_audio_file = download_audio_stream_ytdlp(canonical_url, temp_mp3, proxy=proxy)
                print(f"  -> Downloaded audio stream: {os.path.getsize(target_audio_file):,} bytes")

        # Check if Groq should be used
        groq_key_resolved = load_groq_api_key(groq_api_key) if GROQ_AVAILABLE else None
        use_groq = (method in ("auto", "groq")) and (groq_key_resolved is not None)

        groq_success = False
        if use_groq:
            print(f"  [2/4] Executing High-Accuracy Groq Fallback: Model '{groq_model}'...")
            try:
                transcriber = GroqTranscriber(api_key=groq_key_resolved, model=groq_model)
                segments, detected_lang, groq_meta, audio_dur = transcriber.transcribe_file(
                    target_audio_file,
                    language=None if language == "auto" else language
                )
                extracted_segments = segments
                final_lang = detected_lang
                final_method = "groq_whisper_large_v3"
                method_desc = f"Groq LPU High-Accuracy ASR ({groq_model})"
                track_type = "groq_whisper_large_v3"
                asr_stats = groq_meta
                if duration_sec == 0.0:
                    duration_sec = audio_dur
                groq_success = True
                print(f"  -> Groq transcription successful: {len(segments)} segments in {groq_meta['transcription_time_sec']}s ({groq_meta['speedup_factor']}x real-time)")
                if "rate_limits" in groq_meta:
                    rl = groq_meta["rate_limits"]
                    print(f"  -> Groq Rate Limits: Remaining {rl.get('remaining_requests')}/{rl.get('limit_requests')} requests | Reset: {rl.get('reset_requests')}")
            except Exception as e:
                print(f"  [Warning] Groq transcription error: {e}")
                if method == "groq":
                    raise e
                print("  -> Seamlessly falling back to local faster-whisper...")

        if not groq_success:
            # Local faster-whisper fallback
            print(f"  [3/4] Transcribing locally with faster-whisper ({whisper_model} int8 CPU)...")
            segments, detected_lang, local_meta, audio_dur = transcribe_audio_whisper(
                target_audio_file,
                language=language,
                model_size=whisper_model,
                device=whisper_device,
                compute_type=whisper_compute
            )
            extracted_segments = segments
            final_lang = detected_lang
            final_method = "local_whisper_asr"
            method_desc = f"Local High-Accuracy ASR (faster-whisper {whisper_model} int8)"
            track_type = "asr_generated"
            asr_stats = local_meta
            if duration_sec == 0.0:
                duration_sec = audio_dur

        # Cleanup temporary audio files if created
        if temp_audio_dir and os.path.exists(temp_audio_dir):
            try:
                shutil.rmtree(temp_audio_dir)
            except Exception:
                pass

    print(f"  [4/4] Writing structured files (.srt, .txt, .json, metadata.json)...")
    total_time = round(time.time() - t_start, 2)

    metadata = {
        'id': str(video_id),
        'title': video_title,
        'url': canonical_url,
        'uploader': yt_meta.get('uploader') or 'Facebook Creator',
        'duration': round(float(duration_sec), 2),
        'method': final_method,
        'method_description': method_desc,
        'language': final_lang,
        'track_type': track_type,
        'views': yt_meta.get('view_count'),
        'likes': yt_meta.get('like_count'),
        'comments': yt_meta.get('comment_count'),
        'extraction_time_sec': total_time,
        'cost_usd': 0.0,
        'extracted_at': datetime.now(timezone.utc).isoformat(),
        'asr_stats': asr_stats if asr_stats else None
    }

    saved_info = save_transcript_outputs(item_output_dir, metadata, extracted_segments)

    print(f"\n  SUCCESS:")
    print(f"  - Folder:   {item_output_dir}")
    print(f"  - Method:   {method_desc}")
    print(f"  - Duration: {duration_sec:.1f}s ({format_duration(duration_sec)})")
    print(f"  - Segments: {saved_info['segments_count']} cues")
    print(f"  - Words:    {saved_info['word_count']} words")
    print(f"  - Time:     {total_time}s | Cost: $0.00")

    metadata['folder'] = item_output_dir
    metadata['files'] = saved_info
    return metadata


def generate_master_catalog(output_base_dir: str = DEFAULT_OUTPUT_DIR) -> str:
    """
    Scans output_base_dir for metadata.json files and builds master
    transcripts_summary.json and CATALOG.md.
    """
    entries = []
    base_path = Path(output_base_dir)
    if not base_path.exists():
        return ""

    for meta_file in sorted(base_path.glob("*/metadata.json")):
        try:
            with open(meta_file, encoding="utf-8") as f:
                data = json.load(f)
            folder_dir = meta_file.parent
            txt_file = folder_dir / "transcript.txt"
            srt_file = folder_dir / "transcript.srt"
            json_file = folder_dir / "transcript.json"

            # Extract short preview snippet
            preview_snippet = ""
            if txt_file.exists():
                with open(txt_file, encoding="utf-8") as tf:
                    lines = tf.readlines()
                    # Skip header until ====
                    in_body = False
                    body_lines = []
                    for line in lines:
                        if in_body and line.strip():
                            body_lines.append(line.strip())
                            if len(body_lines) >= 2:
                                break
                        if "====" in line:
                            in_body = True
                    preview_snippet = " ".join(body_lines)[:160]

            data['preview_snippet'] = preview_snippet
            data['folder_rel'] = folder_dir.name
            entries.append(data)
        except Exception:
            pass

    # Sort by extraction date / ID
    entries.sort(key=lambda x: x.get('extracted_at', ''), reverse=True)

    # 1. Save master transcripts_summary.json
    total_seconds = sum(e.get('duration', 0.0) for e in entries)
    total_words = sum(e.get('word_count', 0) for e in entries)
    native_count = sum(1 for e in entries if 'native' in e.get('method', ''))
    groq_count = sum(1 for e in entries if 'groq' in e.get('method', ''))
    local_asr_count = sum(1 for e in entries if ('whisper' in e.get('method', '') or 'asr' in e.get('method', '')) and 'groq' not in e.get('method', ''))

    summary_data = {
        'catalog_generated_at': datetime.now(timezone.utc).isoformat(),
        'total_transcripts': len(entries),
        'total_duration_sec': round(total_seconds, 1),
        'total_duration_formatted': format_duration(total_seconds),
        'total_words': total_words,
        'total_cost_usd': 0.0,
        'methods_breakdown': {
            'native_facebook_captions': native_count,
            'groq_whisper_large_v3': groq_count,
            'local_whisper_asr': local_asr_count
        },
        'transcripts': entries
    }

    summary_file = base_path / "transcripts_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)

    # 2. Save master CATALOG.md
    catalog_file = base_path / "CATALOG.md"
    with open(catalog_file, "w", encoding="utf-8") as f:
        f.write("# Facebook Video & Reel Transcripts Master Catalog\n\n")
        f.write(f"> **Pipeline:** High-Accuracy Facebook Video & Reel Transcript Extractor  \n")
        f.write(f"> **Total Transcripts:** {len(entries)} | **Total Transcribed Time:** {format_duration(total_seconds)} ({total_seconds:.1f}s)  \n")
        f.write(f"> **Total Word Count:** {total_words:,} words | **Total Cost:** $0.00 (Zero paid proxies / Zero Apify)  \n")
        f.write(f"> **Method Distribution:** Native Captions: **{native_count}** | Groq whisper-large-v3: **{groq_count}** | Local Whisper ASR: **{local_asr_count}**  \n")
        f.write(f"> **Last Updated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  \n\n")
        f.write("---\n\n")

        f.write("## 1. Summary Statistics\n\n")
        f.write("| Metric | Value |\n")
        f.write("|:---|:---|\n")
        f.write(f"| **Total Processed Items** | **{len(entries)}** |\n")
        f.write(f"| **Method A (Native Captions)** | **{native_count}** (WebVTT / SRT downloaded from CDN) |\n")
        f.write(f"| **Method B (Groq whisper-large-v3)** | **{groq_count}** (High-Accuracy Groq LPU Speech-to-Text) |\n")
        f.write(f"| **Method C (Local Whisper ASR)** | **{local_asr_count}** (faster-whisper CPU int8) |\n")
        f.write(f"| **Total Audio Duration** | **{format_duration(total_seconds)}** |\n")
        f.write(f"| **Total Spoken Words** | **{total_words:,}** |\n")
        f.write(f"| **Average Spoken Rate** | **{round((total_words / max(total_seconds, 1)) * 60, 1)} words/min** |\n")
        f.write(f"| **External API / Proxy Cost** | **$0.00** |\n\n")

        f.write("---\n\n")
        f.write("## 2. Transcripts Inventory\n\n")
        f.write("| # | Video ID | Title | Method | Lang | Duration | Words | Links |\n")
        f.write("|:---:|---|---|:---:|:---:|:---:|:---:|:---|\n")

        for idx, item in enumerate(entries, 1):
            vid = item.get('id', '')
            title = item.get('title', 'Unknown')
            if "native" in item.get('method', ''):
                method_str = "🟢 Native"
            elif "groq" in item.get('method', ''):
                method_str = "🚀 Groq Large-v3"
            else:
                method_str = "⚡ Local ASR"
            lang = item.get('language', 'und')
            dur = format_duration(item.get('duration', 0.0))
            words = f"{item.get('word_count', 0):,}"
            folder = item.get('folder_rel', '')

            f.write(f"| **{idx:02d}** | `{vid}` | [{title}]({item.get('url', '')}) | {method_str} | `{lang}` | ⏱️ {dur} | 📝 {words} | [SRT]({folder}/transcript.srt) · [TXT]({folder}/transcript.txt) · [JSON]({folder}/transcript.json) |\n")

        f.write("\n---\n\n")
        f.write("## 3. Transcripts Text Previews\n\n")
        for idx, item in enumerate(entries, 1):
            vid = item.get('id', '')
            title = item.get('title', 'Unknown')
            folder = item.get('folder_rel', '')
            method_desc = item.get('method_description', item.get('method', ''))
            f.write(f"### #{idx:02d} — `{vid}`: {title}\n\n")
            f.write(f"- **URL:** {item.get('url', '')}\n")
            f.write(f"- **Method:** `{method_desc}`\n")
            f.write(f"- **Duration:** {format_duration(item.get('duration', 0.0))} | **Word Count:** {item.get('word_count', 0):,} words\n")
            f.write(f"- **Directory:** [`/root/Apify/facebook/transcripts/{folder}/`](file:///root/Apify/facebook/transcripts/{folder}/)\n\n")
            if item.get('preview_snippet'):
                f.write(f"> {item['preview_snippet']} ...\n\n")

    print(f"\n[Catalog] Generated master summary: {summary_file}")
    print(f"[Catalog] Generated master markdown: {catalog_file}")
    return str(catalog_file)


def main():
    parser = argparse.ArgumentParser(
        description="High-Accuracy Facebook Video & Reel Transcript Pipeline (Native Captions + Groq whisper-large-v3 + Local Whisper ASR)"
    )
    parser.add_argument("--url", help="Facebook Video or Reel URL (or ID)")
    parser.add_argument("--urls", nargs="+", help="Multiple Facebook Video/Reel URLs")
    parser.add_argument("--input-file", help="Path to file containing list of Facebook URLs (one per line)")
    parser.add_argument("--local-dir", help="Directory containing downloaded Facebook reel folders to transcribe")
    parser.add_argument("--local-file", help="Direct path to a single local MP4 or audio file to transcribe")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Destination directory for transcripts")
    parser.add_argument("--proxy", default=DEFAULT_TOR_PROXY, help="Proxy for scraping & stream extraction (defaults to Tor socks5://127.0.0.1:9050)")
    parser.add_argument("--method", choices=["auto", "native", "groq", "local", "asr"], default="auto", help="Extraction strategy: auto (native -> Groq whisper-large-v3 -> local ASR), native (only native captions), groq (force Groq LPU), local/asr (force local faster-whisper)")
    parser.add_argument("--groq-model", default="whisper-large-v3", help="Groq Whisper model for high accuracy (default: whisper-large-v3)")
    parser.add_argument("--groq-key", default=None, help="Groq API key (defaults to GROQ_API_KEY in environment or .env)")
    parser.add_argument("--groq-stats", "--monitor", action="store_true", help="Display live Groq rate limit & consumption telemetry summary and exit")
    parser.add_argument("--whisper-model", default="large-v3", choices=["tiny", "base", "small", "medium", "large-v3"], help="faster-whisper local model size for high accuracy (default: large-v3)")
    parser.add_argument("--whisper-device", default="cpu", choices=["cpu", "cuda"], help="Inference device (default: cpu)")
    parser.add_argument("--whisper-compute", default="int8", choices=["int8", "float16", "float32"], help="Computation quantization (default: int8)")
    parser.add_argument("--language", default="auto", help="Target language code (e.g. fr, en, or auto)")
    parser.add_argument("--overwrite", action="store_true", help="Force re-extraction even if transcript exists")

    args = parser.parse_args()

    # If monitor/stats requested, display telemetry and exit
    if args.groq_stats:
        if GROQ_AVAILABLE:
            monitor = GroqRateLimitMonitor()
            print("\n" + "=" * 68)
            print("GROQ LPU TRANSCRIPTION CONSUMPTION & RATE LIMIT TELEMETRY")
            print("=" * 68)
            print(json.dumps(monitor.get_summary(), indent=2))
        else:
            print("Groq transcriber module not available.")
        sys.exit(0)

    # Collect target items
    targets = []
    if args.url:
        targets.append({'url_or_id': args.url, 'local_file': args.local_file})
    if args.urls:
        for u in args.urls:
            targets.append({'url_or_id': u, 'local_file': None})
    if args.input_file and os.path.isfile(args.input_file):
        with open(args.input_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    targets.append({'url_or_id': line, 'local_file': None})

    # If local-dir specified, discover reels/videos
    if args.local_dir and os.path.isdir(args.local_dir):
        print(f"Scanning local directory for videos: {args.local_dir}")
        for dirpath, _, filenames in sorted(os.walk(args.local_dir)):
            reel_json = os.path.join(dirpath, "reel.json")
            video_mp4 = os.path.join(dirpath, "video.mp4")
            if os.path.isfile(video_mp4):
                vid = os.path.basename(dirpath)
                url = None
                if os.path.isfile(reel_json):
                    try:
                        with open(reel_json) as rf:
                            rdata = json.load(rf)
                        vid = str(rdata.get('fbid') or rdata.get('id') or vid)
                        url = rdata.get('reel_url') or rdata.get('watch_url')
                    except Exception:
                        pass
                if not url:
                    url = f"https://www.facebook.com/reel/{vid}" if vid.isdigit() else vid
                targets.append({'url_or_id': url, 'local_file': video_mp4})

    if not targets:
        print("No targets provided. Use --url, --urls, --input-file, --local-dir, or --groq-stats.")
        sys.exit(1)

    print(f"\nDiscovered {len(targets)} target items to transcribe.")
    results = []
    for idx, t in enumerate(targets, 1):
        print(f"\n[{idx}/{len(targets)}] Processing target: {t['url_or_id']}")
        try:
            res = extract_facebook_transcript(
                url_or_id=t['url_or_id'],
                output_base_dir=args.output_dir,
                method=args.method,
                language=args.language,
                groq_model=args.groq_model,
                whisper_model=args.whisper_model,
                whisper_device=args.whisper_device,
                whisper_compute=args.whisper_compute,
                proxy=args.proxy,
                overwrite=args.overwrite,
                local_file=t.get('local_file'),
                groq_api_key=args.groq_key
            )
            results.append(res)
        except Exception as e:
            print(f"  ERROR processing {t['url_or_id']}: {e}")

    # Generate master catalog and summary
    generate_master_catalog(args.output_dir)
    print(f"\nFinished processing {len(results)}/{len(targets)} items successfully.")


if __name__ == "__main__":
    main()
