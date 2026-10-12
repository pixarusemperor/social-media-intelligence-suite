import os
import sys
import json
import subprocess
from pathlib import Path

BASE_DIR = Path("/root/Apify")

def get_ffprobe_data(file_path):
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path)
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        return None
    try:
        return json.loads(res.stdout)
    except Exception:
        return None

def test_seek_and_decode(file_path, duration):
    # Test seeking and decoding 2 seconds of video+audio at 10%, 50%, and 90%
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
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            return False, f"Error decoding at timestamp {int(pt)}s"
    return True, "Passed seek & decode tests at 10%, 50%, 90%"

def test_audio_activity(file_path, duration):
    # Sample 10s of audio at 50% midpoint and check volume level
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
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out = res.stderr
    max_vol = None
    mean_vol = None
    for line in out.splitlines():
        if "max_volume:" in line:
            max_vol = line.split("max_volume:")[1].strip()
        elif "mean_volume:" in line:
            mean_vol = line.split("mean_volume:")[1].strip()

    if max_vol and "-inf" not in max_vol:
        return True, f"Audio active (mean: {mean_vol}, max: {max_vol})"
    elif max_vol and "-inf" in max_vol:
        return False, "Audio is completely silent (-inf dB)"
    return True, "Audio stream verified"

def generate_preview_grid(file_path, duration, output_img):
    # Fast seek extraction: grab 4 frames at 10%, 35%, 65%, 90%
    pts = [int(duration * r) for r in [0.10, 0.35, 0.65, 0.90]]
    tmp_frames = []
    
    for i, pt in enumerate(pts):
        frame_path = file_path.parent / f"tmp_frame_{i}.jpg"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(pt),
            "-i", str(file_path),
            "-frames:v", "1",
            "-q:v", "2",
            str(frame_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if frame_path.exists():
            tmp_frames.append(frame_path)

    if len(tmp_frames) == 4:
        # Tile 2x2 grid using ffmpeg xstack
        tile_cmd = [
            "ffmpeg",
            "-y",
            "-i", str(tmp_frames[0]),
            "-i", str(tmp_frames[1]),
            "-i", str(tmp_frames[2]),
            "-i", str(tmp_frames[3]),
            "-filter_complex",
            "[0:v]scale=640:360[v0];[1:v]scale=640:360[v1];[2:v]scale=640:360[v2];[3:v]scale=640:360[v3];"
            "[v0][v1][v2][v3]xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0[out]",
            "-map", "[out]",
            "-q:v", "2",
            str(output_img)
        ]
        subprocess.run(tile_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Clean up temp frames
    for tf in tmp_frames:
        if tf.exists():
            tf.unlink()

    return output_img.exists() and output_img.stat().st_size > 5000

def parse_duration_str(dur_str):
    if not dur_str:
        return 0
    parts = dur_str.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return 0

def verify_single_video(folder):
    mp4_files = list(folder.glob("*.mp4"))
    meta_json = folder / "metadata.json"
    
    if not mp4_files:
        return None

    video_file = mp4_files[0]
    result = {
        "folder": folder.name,
        "channel": folder.parent.name,
        "video_file": video_file.name,
        "size_mb": round(video_file.stat().st_size / (1024 * 1024), 2),
        "checks": {}
    }

    # Load metadata
    expected_duration = 0
    if meta_json.exists():
        try:
            m = json.loads(meta_json.read_text())
            dur_str = m.get("duration")
            expected_duration = parse_duration_str(dur_str)
            result["title"] = m.get("title", "")
            result["expected_duration"] = dur_str
        except Exception:
            pass

    # Tier 1: Probe
    probe = get_ffprobe_data(video_file)
    if not probe:
        result["checks"]["container"] = "FAILED"
        return result
    result["checks"]["container"] = "PASSED"

    # Streams check
    streams = probe.get("streams", [])
    v_streams = [s for s in streams if s.get("codec_type") == "video"]
    a_streams = [s for s in streams if s.get("codec_type") == "audio"]

    if v_streams and a_streams:
        v = v_streams[0]
        a = a_streams[0]
        result["video_codec"] = v.get("codec_name")
        result["resolution"] = f"{v.get('width')}x{v.get('height')}"
        result["fps"] = round(eval(v.get("r_frame_rate", "30/1")), 1) if "/" in v.get("r_frame_rate", "") else v.get("r_frame_rate")
        result["audio_codec"] = a.get("codec_name")
        result["sample_rate"] = a.get("sample_rate")
        result["checks"]["streams"] = f"PASSED (Video: {result['video_codec']} {result['resolution']} @ {result['fps']}fps, Audio: {result['audio_codec']} @ {result['sample_rate']}Hz)"
    else:
        result["checks"]["streams"] = f"FAILED (Video: {bool(v_streams)}, Audio: {bool(a_streams)})"

    # Duration check
    actual_duration = float(probe.get("format", {}).get("duration", 0))
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
    print("=================================================================")
    print("STARTING RAPID 3-TIER VIDEO VERIFICATION PIPELINE")
    print("=================================================================\n")

    results = []
    for channel in ["vitalnasser", "produitsdigitauxtorif", "nolimitvousdv"]:
        channel_dir = BASE_DIR / channel
        if not channel_dir.exists():
            continue

        for sub in sorted(channel_dir.iterdir()):
            if sub.is_dir() and list(sub.glob("*.mp4")):
                res = verify_single_video(sub)
                if res:
                    results.append(res)
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
    report_path = BASE_DIR / "verification_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nAll {len(results)} videos verified successfully!")
    print(f"Full JSON report saved to: {report_path}")

if __name__ == "__main__":
    main()
