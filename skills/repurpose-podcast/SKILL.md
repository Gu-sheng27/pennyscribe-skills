---
name: repurpose-podcast
description: Turn a public podcast or video episode into a readable, paragraph-structured full transcript, an editable self-contained HTML feature, X posts or threads, and exportable Xiaohongshu image cards. Use for YouTube, Apple Podcasts, Xiaoyuzhou, Bilibili, RSS, direct audio URLs, and local audio when the user asks to transcribe, summarize, organize, publish, or repurpose long-form audio.
---

# Repurpose Podcast

Create a source-grounded publishing workspace from one public episode. Keep the complete readable transcript separate from summaries and promotional copy.

## Requirements

Require `python3`, `yt-dlp`, `ffmpeg`, and `curl`. Require `PENNYSCRIBE_API_KEY` for transcription. Never print, persist in project files, or ask the user to paste the key into chat.

Treat public links as user-provided sources, not as permission to bypass authentication, paywalls, DRM, geographic restrictions, or platform controls. Do not read browser cookies unless the user explicitly requests and authorizes it.

## Workflow

1. Create a fresh project directory outside this skill.
2. Acquire one episode and its metadata:

   ```bash
   python3 scripts/acquire_media.py "<url-or-local-file>" --output-dir "<project>/source"
   ```

   Use `--cookies-from-browser <browser>` only after explicit user authorization. Reject playlists by default. If an Apple Podcasts or Xiaoyuzhou page cannot expose public media, ask for its public RSS URL, direct audio URL, or a local file.

3. Transcribe the normalized audio:

   ```bash
   python3 scripts/transcribe.py "<project>/source/media.mp3" \
     --metadata "<project>/source/metadata.json" \
     --output "<project>/project.json"
   ```

   Poll until terminal. Preserve the raw PennyScribe text exactly in `transcript.raw`.

4. Read [references/content-model.md](references/content-model.md) and [references/transcript-editing.md](references/transcript-editing.md). Populate `transcript.readable`, `digest`, and provenance fields in `project.json`. Preserve all meaningful content in the readable transcript; do not turn it into a summary.
5. For X output, read [references/x-writing.md](references/x-writing.md). Generate separate `single_posts` and `threads`, always retaining the source episode URL.
6. For Xiaohongshu output, read [references/xiaohongshu-writing.md](references/xiaohongshu-writing.md). Generate the title, caption, and 4–8 cards. Keep claims traceable to transcript paragraph IDs.
7. Validate grounding and publishing invariants:

   ```bash
   python3 scripts/validate_project.py "<project>/project.json"
   ```

   Fix every reported error before rendering. Do not delete raw content or loosen provenance to make validation pass.

8. Build the self-contained editor:

   ```bash
   python3 scripts/build_workspace.py "<project>/project.json" --output "<project>/index.html"
   ```

9. Let the user review and edit the HTML. Do not silently overwrite user-edited copy when regenerating another section. The page can export edited project JSON.
10. Export Xiaohongshu cards after review:

   ```bash
   node scripts/export_cards.cjs "<project>/index.html" --output-dir "<project>/exports/xiaohongshu"
   ```

   Install Playwright when unavailable. Export one 1080×1440 PNG per card and fail on text overflow.

## Output Rules

- Deliver `index.html`, `project.json`, and exported assets requested by the user.
- Keep four distinct views: digest, readable full transcript, X, and Xiaohongshu.
- Mark uncertain names, numbers, brands, and terms with `〔疑似：…〕`; never silently repair them.
- Label quotations as `verbatim`, `lightly_edited`, or `paraphrased`. Do not use quotation marks for paraphrases.
- Do not invent speakers, timestamps, handles, endorsements, or episode facts.
- Build semantic chapters without timestamps when the transcription has no timing data.
- Prefer a few strong social posts over repetitive variants.

## Acquisition Failures

Read [references/platform-acquisition.md](references/platform-acquisition.md) when acquisition fails. Report the failed layer—native extractor, generic extractor, public page discovery, or direct media download—and offer the narrowest safe fallback.
