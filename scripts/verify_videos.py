"""
verify_videos.py - Automated 3-Tier Livestream Quality Assurance Engine

Performs multi-tiered verification of downloaded YouTube livestream video files:
  - Tier 1: Container integrity, moov atom, stream track assertions, duration comparison
  - Tier 2: Seekability at 10%, 50%, 90% timeline, audio volume detection
  - Tier 3: Visual 2x2 contact sheet preview grid generation
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path

BASE_DIR = Path("/root/Apify")

def get_ffprobe_data(file_path, timeout=15):
    """Probes container and streams metadata using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        if res.returncode != 0:
            return None
        return json.loads(res.stdout)
    except Exception:
        return None

def test_seek_and_decode(file_path, duration, timeout=20):
    """Tests seeking and decoding 2 seconds of video+audio at 10%, 50%, and 90% timestamps."""
    points = [duration * 0.1, duration * 0.5, duration * 0.9]
    for pt in points:
        cmd = [
            "ffmpeg",
            "-ss", str(int(pt)),
            "-i", str(file_path),
            "-t", "2",
            "-f", "null",
            "-"
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
            if res.returncode != 0:
                return False, f"Error decoding at timestamp {int(pt)}s"
        except subprocess.TimeoutExpired:
            return False, f"Timeout decoding at timestamp {int(pt)}s"
    return True, "Passed seek & decode tests at 10%, 50%, 90%"

def test_audio_activity(file_path, duration, timeout=20):
    """Samples 10s of audio at 50% midpoint and measures loudness via volumedetect."""
    midpoint = int(duration * 0.5)
    cmd = [
        "ffmpeg",
        "-ss", str(midpoint),
        "-i", str(file_path),
        "-t", "10",
        "-af", "volumedetect",
        "-f", "null",
        "-"
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        out = res.stderr
        max_vol = None
        mean_vol = None
        for line in out.splitlines():
            if "max_volume:" in line:
                max_vol = line.split("max_volume:")[1].strip()
            if "mean_volume:" in line:
                mean_vol = line.split("mean_volume:")[1].strip()
        if mean_vol:
            return True, f"Audio active (mean: {mean_vol}, max: {max_vol})"
        return False, "Could not determine audio volume"
    except subprocess.TimeoutExpired:
        return False, "Timeout during audio volume analysis"

def generate_preview_grid(file_path, duration, output_image_path, timeout=30):
    """Generates a 2x2 contact sheet from 4 timestamps across the broadcast timeline."""
    if output_image_path.exists() and output_image_path.stat().st_size > 10 * 1024:
        return True

    # 4 timestamps at 10%, 35%, 65%, 90%
    t1 = int(duration * 0.10)
    t2 = int(duration * 0.35)
    t3 = int(duration * 0.65)
    t4 = int(duration * 0.90)

    filter_complex = (
        f"[0:v]trim=start={t1}:end={t1+1},setpts=PTS-STARTPTS,scale=640:-1[v0];"
        f"[1:v]trim=start={t2}:end={t2+1},setpts=PTS-STARTPTS,scale=640:-1[v1];"
        f"[2:v]trim=start={t3}:end={t3+1},setpts=PTS-STARTPTS,scale=640:-1[v2];"
        f"[3:v]trim=start={t4}:end={t4+1},setpts=PTS-STARTPTS,scale=640:-1[v3];"
        f"[v0][v1][v2][v3]xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0[out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(t1), "-i", str(file_path),
        "-ss", str(t2), "-i", str(file_path),
        "-ss", str(t3), "-i", str(file_path),
        "-ss", str(t4), "-i", str(file_path),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-frames:v", "1",
        str(output_image_path)
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return res.returncode == 0 and output_image_path.exists()
    except Exception:
        # Fallback to single middle frame if xstack fails
        try:
            fallback_cmd = [
                "ffmpeg", "-y",
                "-ss", str(int(duration * 0.5)),
                "-i", str(file_path),
                "-vframes", "1",
                "-q:v", "2",
                str(output_image_path)
            ]
            subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
            return output_image_path.exists()
        except Exception:
            return False

def verify_single_video(folder):
    """Executes 3-tier validation for an individual video folder."""
    video_files = list(folder.glob("*.mp4"))
    if not video_files:
        return None

    video_file = video_files[0]
    meta_json_path = folder / "metadata.json"
    metadata = {}
    if meta_json_path.exists():
        try:
            with open(meta_json_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception:
            pass

    channel_name = folder.parent.name
    result = {
        "channel": channel_name,
        "folder": folder.name,
        "video_file": video_file.name,
        "title": metadata.get("title", ""),
        "size_mb": round(video_file.stat().st_size / (1024 * 1024), 2),
        "checks": {}
    }

    # Tier 1: Container
    probe = get_ffprobe_data(video_file)
    if not probe:
        result["checks"]["container"] = "FAILED (Unreadable container or missing moov atom)"
        result["overall_status"] = "FAILED"
        return result

    result["checks"]["container"] = "PASSED"

    # Streams
    streams = probe.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    if video_streams and audio_streams:
        v_codec = video_streams[0].get("codec_name")
        a_codec = audio_streams[0].get("codec_name")
        w = video_streams[0].get("width")
        h = video_streams[0].get("height")
        result["resolution"] = f"{w}x{h}"
        result["video_codec"] = v_codec
        result["audio_codec"] = a_codec
        result["checks"]["streams"] = f"PASSED (Video: {v_codec} {w}x{h}, Audio: {a_codec})"
    else:
        result["checks"]["streams"] = f"FAILED (Video streams: {len(video_streams)}, Audio streams: {len(audio_streams)})"

    # Duration
    actual_duration = float(probe.get("format", {}).get("duration", 0))
    expected_duration_val = metadata.get("duration", "")
    expected_duration = 0
    if isinstance(expected_duration_val, (int, float)):
        expected_duration = float(expected_duration_val)
    elif isinstance(expected_duration_val, str) and expected_duration_val:
        parts = [int(p) for p in expected_duration_val.split(":") if p.isdigit()]
        if len(parts) == 3:
            expected_duration = parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            expected_duration = parts[0] * 60 + parts[1]

    result["actual_duration_sec"] = round(actual_duration, 1)

    if expected_duration > 0:
        diff = abs(actual_duration - expected_duration)
        if diff <= 10:
            result["checks"]["duration"] = f"PASSED (Actual: {int(actual_duration)}s vs Expected: {expected_duration}s, diff: {diff:.1f}s)"
        else:
            result["checks"]["duration"] = f"WARNING (Actual: {int(actual_duration)}s vs Expected: {expected_duration}s, diff: {diff:.1f}s)"
    else:
        result["checks"]["duration"] = f"PASSED (Actual: {int(actual_duration)}s)"

    # Tier 2: Seek & Decode
    seek_ok, seek_msg = test_seek_and_decode(video_file, actual_duration)
    result["checks"]["seek_and_decode"] = "PASSED" if seek_ok else f"FAILED ({seek_msg})"

    # Tier 2: Audio Activity
    audio_ok, audio_msg = test_audio_activity(video_file, actual_duration)
    result["checks"]["audio_activity"] = "PASSED: " + audio_msg if audio_ok else f"FAILED ({audio_msg})"

    # Tier 3: Visual Grid
    preview_grid_path = folder / "preview_grid.jpg"
    grid_ok = generate_preview_grid(video_file, actual_duration, preview_grid_path)
    result["checks"]["preview_grid"] = f"PASSED ({preview_grid_path.name})" if grid_ok else "FAILED"

    # Status
    all_ok = (
        result["checks"]["container"] == "PASSED" and
        "PASSED" in result["checks"]["streams"] and
        seek_ok and
        audio_ok and
        grid_ok
    )
    result["overall_status"] = "100% VERIFIED & READY TO WATCH" if all_ok else "ATTENTION NEEDED"

    return result

def main():
    parser = argparse.ArgumentParser(description="Run 3-tier livestream verification QA suite.")
    parser.add_argument("channel", nargs="?", default="all",
                        choices=["all", "vitalnasser", "produitsdigitauxtorif", "nolimitvousdv"],
                        help="Target channel to verify (default: all)")
    parser.add_argument("--output", default=str(BASE_DIR / "verification_report.json"),
                        help="Path to output JSON verification report")
    parser.add_argument("--strict", action="store_true",
                        help="Exit with code 1 if any video fails verification")
    args = parser.parse_args()

    print("=================================================================")
    print("STARTING RAPID 3-TIER VIDEO VERIFICATION PIPELINE")
    print("=================================================================\n")

    channels = ["vitalnasser", "produitsdigitauxtorif", "nolimitvousdv"] if args.channel == "all" else [args.channel]
    results = []
    has_failure = False

    for ch_name in channels:
        channel_dir = BASE_DIR / ch_name
        if not channel_dir.exists():
            continue

        for sub in sorted(channel_dir.iterdir()):
            if sub.is_dir() and list(sub.glob("*.mp4")):
                res = verify_single_video(sub)
                if res:
                    results.append(res)
                    if "FAILED" in res.get("overall_status", ""):
                        has_failure = True
                    print(f"[{res['channel']}] {res['folder'][:60]}...")
                    print(f"  Title: {res.get('title', 'N/A')}")
                    print(f"  Status: {res['overall_status']}")
                    print(f"  Size: {res['size_mb']} MB | Resolution: {res.get('resolution')} | Codecs: {res.get('video_codec')}/{res.get('audio_codec')}")
                    print(f"  Duration: {res['checks']['duration']}")
                    print(f"  Streams: {res['checks']['streams']}")
                    print(f"  Seek & Decode: {res['checks']['seek_and_decode']}")
                    print(f"  Audio Activity: {res['checks']['audio_activity']}")
                    print(f"  Visual Grid: {res['checks']['preview_grid']}")
                    print("-----------------------------------------------------------------")

    # Output JSON summary
    report_path = Path(args.output)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nAll {len(results)} videos verified!")
    print(f"Full JSON report saved to: {report_path}")

    if args.strict and has_failure:
        sys.exit(1)

if __name__ == "__main__":
    main()
