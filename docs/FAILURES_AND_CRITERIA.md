# Livestream Archival: Failure Modes & Evaluation Criteria

## 1. Possible Failure Modes in Live Stream Archiving (10 Failure Cases)

| # | Failure Mode | Root Cause | Impact | Detection Strategy |
|---|---|---|---|---|
| **1** | **Truncated Duration (DVR Cutoff)** | Downloading while stream is processing or before VOD is finalized. | Missing first or last hours of broadcast. | Math comparison of probed duration vs YouTube metadata (tolerance ≤ 5s). |
| **2** | **Corrupt Moov Atom (Container Failure)** | Interrupted muxing, crashed process, or disk space exhaustion. | File cannot be opened by media players or indexed. | `ffprobe -show_format` exit code test. |
| **3** | **Missing or Muted Audio** | Separate DASH audio track failed to download or mux correctly. | Video plays silently with no sound. | Stream track count assertion + volume analysis (`volumedetect`). |
| **4** | **PTS / DTS Timestamp Drift (Desync)** | Frame drops during live stream transmission resulting in PTS jitter. | Audio leads or lags behind video by seconds/minutes. | Timestamp monotonicity check and packet delta inspection. |
| **5** | **Packet Corruption & Macroblocking** | Network packet loss during fragment transfer without retry. | Visual glitches, green screens, decoding errors. | `ffmpeg -xerror -c copy -f null -` demux test. |
| **6** | **Frozen Video Stream** | Streamer encoder stall where audio continues over a frozen frame. | Stagnant visual with audio playing. | Multi-point timeline frame comparison or `freezedetect`. |
| **7** | **Resolution Downscaling Fallback** | `yt-dlp` fallback to lower resolution (360p) due to rate limits. | Blurry video, loss of visual quality. | Probe width/height and assert ≥ 720p. |
| **8** | **Zero-Byte / Partial Files** | Script timeout or unhandled exit during download. | Incomplete, corrupt partial download. | File size assertion (> 10MB) + part-file cleanup. |
| **9** | **CDN Token / Signature Expiration Mid-Download** | Multi-hour download exceeds YouTube playback URL signature TTL (`expire=...`). | HTTP 403 Forbidden on later stream segments. | Detection via `yt-dlp` return code and fragment retry mechanism (`--fragment-retries`). |
| **10** | **Dynamic Format & VFR Codec Switch Glitch** | Broadcast resolution or FPS changed dynamically during the live event. | Playback stall or aspect distortion at transition points. | Parse frame rate consistency (`r_frame_rate` vs `avg_frame_rate`). |

---

## 2. Evaluation Criteria for Verification Techniques

When choosing testing methods to verify large multi-gigabyte video archives, six criteria dictate the optimal strategy:

1. **Detection Precision:** Must detect both fatal errors (unplayable container) and subtle flaws (audio volume muted, truncated by 15 minutes).
2. **Computational Speed:** Multi-hour livestreams (2–4 hours) cannot undergo full software decoding in CI/CD without excessive wait times.
3. **Headless Automation:** Must run unattended on Linux servers, producing unambiguous pass/fail status and structured reports.
4. **False Positive Immunity:** Must not fail legitimate live broadcasts (e.g. static intro cards or quiet intermissions).
5. **Resource Efficiency:** Must avoid CPU throttling or disk I/O thrashing during mass batch processing.
6. **Non-Destructive Read-Only Operation:** Preserves original media bitstreams without re-encoding or modifying file hashes.
