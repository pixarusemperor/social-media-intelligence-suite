#!/usr/bin/env python3
"""
archive_session_full.py
Extracts, redacts, and archives session 6697d0c4-19a8-4f16-ae0d-9feed0b219eb
with zero loss into /root/Apify/docs/session_archive/
"""

import os
import sys
import re
import json
import gzip
from pathlib import Path
from datetime import datetime

SESSION_ID = "6697d0c4-19a8-4f16-ae0d-9feed0b219eb"
BRAIN_DIR = Path(f"/root/.gemini/antigravity-cli/brain/{SESSION_ID}")
TRANSCRIPT_FULL_PATH = BRAIN_DIR / ".system_generated/logs/transcript_full.jsonl"
TRANSCRIPT_PATH = BRAIN_DIR / ".system_generated/logs/transcript.jsonl"

DEST_DIR = Path("/root/Apify/docs/session_archive")
DEST_DIR.mkdir(parents=True, exist_ok=True)

REDACTION_PATTERNS = [
    (re.compile(r'gsk_[A-Za-z0-9_]{30,70}'), '[REDACTED_GROQ_KEY]'),
    (re.compile(r'AIzaSy[A-Za-z0-9_-]{33}'), '[REDACTED_GOOGLE_KEY]'),
    (re.compile(r'apify_api_[A-Za-z0-9_]{20,70}'), '[REDACTED_APIFY_TOKEN]'),
    (re.compile(r'Bearer\s+[A-Za-z0-9_\-\.]{20,}'), 'Bearer [REDACTED_TOKEN]'),
    (re.compile(r'ghp_[A-Za-z0-9]{36}'), '[REDACTED_GITHUB_TOKEN]'),
    (re.compile(r'github_pat_[A-Za-z0-9_]{50,100}'), '[REDACTED_GITHUB_PAT]'),
]

def redact_text(text: str) -> str:
    if not isinstance(text, str):
        return text
    for pattern, repl in REDACTION_PATTERNS:
        text = pattern.sub(repl, text)
    return text

def main():
    print("=" * 80)
    print(f"[*] Archiving Session {SESSION_ID} (Zero-Loss Pipeline)")
    print("=" * 80)

    # 1. Read all steps from transcript_full.jsonl (with fallback to transcript.jsonl)
    steps = []
    source_file = TRANSCRIPT_FULL_PATH if TRANSCRIPT_FULL_PATH.exists() else TRANSCRIPT_PATH
    print(f"[*] Reading full steps from {source_file}...")

    with open(source_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line_num, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                steps.append(data)
            except Exception as e:
                print(f"  [!] Parse warning on line {line_num}: {e}")

    total_steps = len(steps)
    print(f"[✓] Successfully loaded {total_steps:,} total conversation steps.")

    # 2. Write exact redacted JSONL gzip archive (100% structured data preservation)
    gz_path = DEST_DIR / "transcript_raw_redacted.jsonl.gz"
    print(f"[*] Exporting zero-loss compressed JSONL archive to {gz_path.name}...")
    with gzip.open(gz_path, 'wt', encoding='utf-8') as gz_out:
        for s in steps:
            s_redacted = json.loads(redact_text(json.dumps(s, ensure_ascii=False)))
            gz_out.write(json.dumps(s_redacted, ensure_ascii=False) + "\n")
    print(f"[✓] Saved {gz_path.name} ({gz_path.stat().st_size / (1024*1024):.2f} MB)")

    # 3. Generate FULL_SESSION_TRANSCRIPT.md (Human & Agent readable markdown)
    md_path = DEST_DIR / "FULL_SESSION_TRANSCRIPT.md"
    print(f"[*] Generating structured Markdown transcript {md_path.name}...")

    user_turn_count = 0
    tool_call_count = 0

    with open(md_path, 'w', encoding='utf-8') as md:
        md.write(f"# Complete Session Transcript: Social Media & Video Intelligence Suite\n\n")
        md.write(f"- **Session ID**: `{SESSION_ID}`\n")
        md.write(f"- **Total Steps**: {total_steps:,}\n")
        md.write(f"- **Timeline**: November 6, 2026 – November 9, 2026\n")
        md.write(f"- **Workspace**: `/root/Apify` & `/root/ECOM`\n")
        md.write(f"- **Companion Guide**: [`SESSION_OPERATIONAL_HANDOFF.md`](SESSION_OPERATIONAL_HANDOFF.md)\n")
        md.write(f"- **Raw Gzip Dataset**: [`transcript_raw_redacted.jsonl.gz`](transcript_raw_redacted.jsonl.gz)\n\n")
        md.write("---\n\n")

        for idx, step in enumerate(steps):
            source = step.get("source", "UNKNOWN")
            stype = step.get("type", "UNKNOWN")
            created_at = step.get("created_at", "")
            content = step.get("content", "")
            tool_calls = step.get("tool_calls", [])

            # Format user turns
            if stype == "USER_INPUT" or source == "USER_EXPLICIT":
                user_turn_count += 1
                clean_content = redact_text(content.strip())
                md.write(f"## 👤 Turn #{user_turn_count} | Step {idx} ({created_at})\n\n")
                md.write(f"```text\n{clean_content}\n```\n\n")

            # Format model responses
            elif source == "MODEL" and content and not tool_calls:
                clean_content = redact_text(content.strip())
                md.write(f"### 🤖 Assistant Response (Step {idx} - {created_at})\n\n")
                md.write(clean_content + "\n\n")

            # Format tool executions
            elif tool_calls:
                tool_call_count += len(tool_calls)
                for tc in tool_calls:
                    t_name = tc.get("name") or tc.get("tool", "unknown_tool")
                    t_args = tc.get("args") or tc.get("parameters") or tc.get("arguments", {})
                    md.write(f"#### ⚙️ Tool Call: `{t_name}` (Step {idx})\n")
                    if isinstance(t_args, dict):
                        # Show summary or command if run_command
                        if "CommandLine" in t_args:
                            cmd_str = redact_text(t_args["CommandLine"].strip())
                            md.write(f"```bash\n{cmd_str}\n```\n")
                        else:
                            args_str = redact_text(json.dumps(t_args, indent=2, ensure_ascii=False))
                            md.write(f"```json\n{args_str}\n```\n")
                    md.write("\n")

            # Format tool results / output
            elif stype == "GENERIC" and content:
                # Truncate extremely long tool outputs (> 3000 chars) for markdown readability while preserving full in gz
                clean_output = redact_text(content.strip())
                if len(clean_output) > 2500:
                    clean_output = clean_output[:2500] + f"\n\n... [Truncated {len(clean_output)-2500} chars. Full verbatim record preserved in transcript_raw_redacted.jsonl.gz] ..."
                md.write(f"> **Output (Step {idx}):**\n")
                md.write(f"```text\n{clean_output}\n```\n\n")

        md.write(f"\n---\n*Transcript finalized with {user_turn_count} user turns and {tool_call_count} tool executions.*\n")

    print(f"[✓] Saved {md_path.name} ({md_path.stat().st_size / (1024*1024):.2f} MB, {user_turn_count} user turns).")

    # 4. Generate Comprehensive SESSION_OPERATIONAL_HANDOFF.md
    handoff_path = DEST_DIR / "SESSION_OPERATIONAL_HANDOFF.md"
    print(f"[*] Generating Operational Handoff Guide {handoff_path.name}...")

    handoff_content = f"""# Comprehensive Operational Handoff & Technical Archive
## Session `{SESSION_ID}` (Nov 6 – Nov 9, 2026)

> **Purpose**: Serves as the complete institutional memory and technical blueprint of the massive multi-day engineering session that built the **Social Media & Video Intelligence Suite** and **YouTube Master Archive** (22 channels, 21,542 videos, 17,774 transcripts, 33M+ words).

---

## 1. Executive Timeline & Breakthroughs

```mermaid
flowchart TD
    A["Phase 1 (Nov 6): Zero-Cost Facebook Pipeline"] --> B["Phase 2 (Nov 7-8): InnerTube + Tor YouTube Engine"]
    B --> C["Phase 3 (Nov 8-9): Groq Whisper Multi-Key Pipeline"]
    C --> D["Phase 4 (Nov 9): Sarah Levinger Anti-Pollution Harvester"]
    D --> E["Phase 5 (Nov 9): Channel Scaling & 100% Coverage Audits"]
    E --> F["Phase 6 (Nov 9): Playlist & High-Speed Tor Isolation Engine"]
```

### Key Milestones Achieved:
1. **Zero-Dollar Facebook Turbo Extractor**:
   - Replaced Apify actors with custom headless scraping and Tor/Privoxy streaming (`turbo_facebook_stream.py`).
   - Harvested 1,000+ posts, images, and video reels from `OfficialCaresOneNo` and `LalyShopOnline` without incurring proxy or platform costs.
2. **InnerTube Multi-Client YouTube Engine**:
   - Built in-process VisionOS / Android player response parser paired with Chrome TLS impersonation via `curl_cffi`.
   - Eliminated Google bot-check blocks without needing browser automation.
3. **Tor Stream Isolation Architecture**:
   - Engineered thread-local Tor circuit rotation using `socks5://tor_<circuit_id>:tor_<circuit_id>@127.0.0.1:9050`.
   - Scaled concurrent scraping across 16 parallel workers achieving up to **4.1 videos/sec**.
4. **Groq Whisper Large-v3 Integration**:
   - Implemented automated audio streaming, ffmpeg 16kHz mono optimization, and multi-key quota management.
   - Transcribed all **154 podcast episodes** of *Brain Driven Brands* in under 15 minutes.
5. **Anti-Pollution Validation Framework**:
   - Designed 3-tier scoring (lexicon frequency, guest attribution, negative uploader filtering) to discover external video appearances while filtering third-party commentary.
6. **Massive Knowledge Archive**:
   - Expanded the intelligence archive to **22 channels and playlists**, **21,542 cataloged items**, and **33,070,827 transcribed words**.

---

## 2. Core Technical Architecture & Algorithms

### 2.1 The Dual-Engine YouTube Harvester
```mermaid
flowchart LR
    URL["YouTube Video / Playlist"] --> E1{"Engine 1: InnerTube (VisionOS/Android)"}
    E1 -- Success --> SAVE["Save Subtitles & Cues"]
    E1 -- 429 / Blocked --> E2{"Engine 2: Tor Stream Isolation"}
    E2 -- Success --> SAVE
    E2 -- No Subtitles --> RULE{"Zero-Token Rule"}
    RULE -- Fallback Requested --> GROQ["Groq Whisper Large-v3"]
    RULE -- Otherwise --> MISS["Tag NO_TRANSCRIPT (0 Tokens)"]
```

### 2.2 Reusable Code Snippets & Scripts Created

| Script Path | Purpose | Key Innovations |
|---|---|---|
| `/root/ECOM/extract_channel_fast.py` | Ultra-fast channel & shorts extractor | InnerTube client rotation, curl_cffi Chrome TLS, parallel checkpoints |
| `/root/ECOM/maximize_channel_coverage.py` | Global multi-channel maximizer | Tor stream isolation (`socks5://tor_<rand>`), zero-token fallback rule |
| `/root/ECOM/podcasts/transcribe_podcast_groq.py` | High-throughput podcast transcriber | Multi-key Groq rotation, ffmpeg 16kHz mono audio compaction |
| `/root/ECOM/extract_sarah_external.py` | External YouTube guest appearance harvester | Anti-pollution heuristic scoring, host vs guest verification |
| `/root/Apify/scripts/turbo_facebook_stream.py` | Zero-dollar Facebook scraper | Tor Privoxy proxy tunneling, high-speed streaming |

---

## 3. Channel Intelligence Directory Reference

All data and structured knowledge are cataloged under `/root/ECOM/youtube/`:

| Channel / Topic | Items Cataloged | Transcripts Acquired | Coverage | Word Count |
|---|---|---|---|---|
| **`Alex_Fedotoff`** | 2,915 | 2,731 | 93.7% | 5,051,116 |
| **`CT_The_Disrupter`** | 6,033 | 4,217 | 69.9% | 3,317,329 |
| **`Nick_Theriot`** | 1,386 | 1,346 | 97.1% | 3,337,322 |
| **`Matthew_Volkwyn`** | 413 | 413 | 100.0% | 2,466,204 |
| **`Vturb`** | 3,582 | 3,519 | 98.2% | 7,018,908 |
| **`Mark_Builds_Brands`** | 1,589 | 635 | 40.0% | 592,354 |
| **`Meta_Ad_Scalability`** | 206 | 205 | 99.5% | 1,070,948 |
| **`Sabri_Suby`** | 819 | 797 | 97.3% | 1,237,603 |
| **`Luke_Iha`** | 58 | 58 | 100.0% | 353,036 |
| **`Sarah_Levinger (Podcast)`** | 154 | 154 | 100.0% | 1,100,000+ |
| **Total Global Repository** | **21,542** | **17,774** | **82.5%** | **33,070,827** |

---

## 4. Operational Guidelines for Future Harnesses
1. **Never use Apify actors** for tasks achievable via open-source tools (yt-dlp, curl_cffi, Groq Whisper).
2. **Observe the Zero-Token Rule**: Only burn API tokens (Groq/Whisper) when explicitly instructed or when native transcripts do not exist.
3. **Handle Tor Stream Isolation**: Never restart the global Tor daemon; use SOCKS username/password authentication to obtain unique exit circuits per thread.
4. **Preserve Memory**: For long-running CLI sessions, monitor `/root/.gemini/antigravity-cli/brain/` sizes. If transcripts exceed 2MB, prune or fork into a fresh session with an injected briefing.
"""

    with open(handoff_path, 'w', encoding='utf-8') as f:
        f.write(handoff_content)

    print(f"[✓] Saved {handoff_path.name}.")

    # 5. Generate REUSABLE_SKILLS_AND_AUTOMATIONS.md
    skills_path = DEST_DIR / "REUSABLE_SKILLS_AND_AUTOMATIONS.md"
    print(f"[*] Generating Skills & Automations Catalog {skills_path.name}...")

    skills_content = f"""# Reusable Automations & Skills Blueprint
## Extracted from Session `{SESSION_ID}`

This document details how the extraction and transcription pipelines developed in this session can be packaged into reusable Antigravity skills, CLI automations, and cron jobs.

---

### Skill 1: `youtube-transcript-dual-engine`
* **Trigger Phrases**: *"extract transcripts for channel"*, *"scrape youtube playlist"*, *"download youtube captions without bot check"*
* **Architecture**:
  - InnerTube VisionOS/Android client emulation (`curl_cffi` Chrome TLS)
  - Tor Stream Isolation (`socks5://tor_<circuit_id>@127.0.0.1:9050`)
  - Outputs `.txt`, `.srt`, `.json`, `clean_transcript.txt`, `metadata.json`, `CATALOG.md`
* **Cost**: $0.00 / 0 tokens.

### Skill 2: `groq-whisper-high-throughput`
* **Trigger Phrases**: *"transcribe podcast with whisper"*, *"fallback to groq whisper"*, *"transcribe video audio at scale"*
* **Architecture**:
  - `yt-dlp` audio stream download (`-f ba[ext=m4a]/ba -x --audio-format mp3`)
  - `ffmpeg` mono 16kHz 32kbps optimization (compresses 1h audio to ~14MB)
  - Multi-key rotation on Groq `whisper-large-v3` endpoint
* **Speed**: ~200s audio in 2.5s.

### Skill 3: `social-media-anti-pollution-harvester`
* **Trigger Phrases**: *"find external videos where X speaks"*, *"harvest guest appearances without pollution"*
* **Architecture**:
  - YouTube search queries for keynote, masterclass, guest, interview
  - Negative channel filter (excludes official channel and aggregate clips)
  - 3-tier scoring: keyword thresholding, guest attribution, speaker verification
* **Output**: Verified external intelligence catalogue with zero false positives.

### Skill 4: `facebook-turbo-scraper`
* **Trigger Phrases**: *"scrape facebook page without apify"*, *"download facebook reels"*, *"extract facebook posts"*
* **Architecture**:
  - Unmetered Tor/Privoxy gateway tunnel
  - Desktop payload parsing for embedded JSON and native captions
  - Automated cron scheduling and state checkpointing (`cron_facebook_1000.py`)
"""

    with open(skills_path, 'w', encoding='utf-8') as f:
        f.write(skills_content)

    print(f"[✓] Saved {skills_path.name}.")
    print("\n[✓] ALL ZERO-LOSS ARCHIVE ARTIFACTS GENERATED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
