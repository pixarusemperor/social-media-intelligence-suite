import json
from pathlib import Path

base = Path("/root/Apify/transcripts/markbuildsbrands")
catalog_path = base / "CATALOG.md"

items = []
for folder in sorted(base.iterdir()):
    meta_path = folder / "metadata.json"
    if meta_path.exists():
        with open(meta_path) as f:
            m = json.load(f)
            m["folder_name"] = folder.name
            items.append(m)

items.sort(key=lambda x: str(x.get("upload_date", "")), reverse=True)

total_hours = sum(x.get("duration", 0) for x in items) / 3600.0
total_segments = sum(x.get("snippets_count", 0) for x in items)
total_words = sum(x.get("word_count", 0) for x in items)

lines = [
    "# YouTube Channel Transcripts: @markbuildsbrands",
    "",
    "Complete corpus of transcripts extracted with $0.00 in proxy costs and no Apify.",
    "",
    f"- **Total Videos & Streams Transcribed:** {len(items)}",
    f"- **Total Spoken Content:** {total_hours:.1f} Hours",
    f"- **Total Transcript Segments:** {total_segments:,}",
    f"- **Total Words:** {total_words:,}",
    "",
    "---",
    "",
    "| # | Video Title | Category | Duration | Words | Published | Links |",
    "|:---:|---|:---:|:---:|:---:|:---:|:---:|"
]

for idx, it in enumerate(items, 1):
    title = it.get("title", "").replace("|", "-")
    vid_id = it.get("id")
    cat = it.get("category", "video").upper()
    dur_sec = it.get("duration", 0)
    m, s = divmod(dur_sec, 60)
    h, m = divmod(m, 60)
    dur_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
    words_cnt = it.get("word_count", 0)
    words_str = f"{words_cnt:,}"
    pub = it.get("upload_date", "N/A")
    folder = it.get("folder_name")
    
    links = f"[TXT](./{folder}/transcript.txt) • [SRT](./{folder}/transcript.srt) • [JSON](./{folder}/transcript.json)"
    lines.append(f"| {idx} | **[{title}](https://www.youtube.com/watch?v={vid_id})** | `{cat}` | {dur_str} | {words_str} | {pub} | {links} |")

catalog_path.write_text("\n".join(lines), encoding="utf-8")
print(f"CATALOG.md written with {len(items)} entries! Size: {catalog_path.stat().st_size:,} bytes")
