---
name: repurpose-podcast
description: Turn public podcast or video episodes into readable full transcripts, quote lists, editable HTML publishing workspaces, X posts or threads, native Xiaohongshu copy and exportable image cards, plus a switchable local podcast library. Prefer source-language human or automatic YouTube captions before audio transcription. Use for YouTube, Apple Podcasts, Xiaoyuzhou, Bilibili, RSS, direct audio URLs, and local audio when the user asks to transcribe, summarize, organize, publish, or repurpose long-form audio.
---

# Repurpose Podcast

Create a source-grounded publishing workspace from one public episode. Keep the complete readable transcript separate from summaries and promotional copy.

## Requirements

Require `python3`, `yt-dlp`, and `curl`. Require `ffmpeg` and `PENNYSCRIBE_API_KEY` only when audio transcription is necessary. `PENNYSCRIBE_API_KEY` stores the key for the selected transcription provider, either PennyScribe or ElevenLabs; never print it, persist it in project files, or ask the user to paste it into chat.

Treat public links as user-provided sources, not as permission to bypass authentication, paywalls, DRM, geographic restrictions, or platform controls. Do not read browser cookies unless the user explicitly requests and authorizes it.

## Workflow

1. Create a fresh project directory outside this skill.
2. Acquire one episode and its metadata:

   ```bash
   python3 scripts/acquire_media.py "<url-or-local-file>" --output-dir "<project>/source"
   ```

   Use `--cookies-from-browser <browser>` only after explicit user authorization. Reject playlists by default. If an Apple Podcasts or Xiaoyuzhou page cannot expose public media, ask for its public RSS URL, direct audio URL, or a local file.

3. Inspect the acquisition result. If `<project>/source/transcript.txt` exists, initialize the project directly from the extracted YouTube subtitles:

   ```bash
   python3 scripts/transcribe.py \
     --transcript "<project>/source/transcript.txt" \
     --metadata "<project>/source/metadata.json" \
     --output "<project>/project.json"
   ```

   Do not call PennyScribe in this branch. The acquisition script selects source-language YouTube captions in this order: human-authored subtitles, then automatic captions. It rejects translated caption tracks.

   Otherwise, when `<project>/source/media.mp3` exists, transcribe the normalized audio:

   ```bash
   python3 scripts/transcribe.py "<project>/source/media.mp3" \
     --metadata "<project>/source/metadata.json" \
     --output "<project>/project.json"
   ```

   PennyScribe is the default provider. To use ElevenLabs instead, keep the ElevenLabs key in the same `PENNYSCRIBE_API_KEY` variable and add:

   ```bash
   --provider elevenlabs --language-code zh --diarize
   ```

   ElevenLabs uses `scribe_v2` by default; override it only with a supported `--model-id`. Poll PennyScribe until terminal; ElevenLabs returns synchronously. Preserve the selected subtitle text or raw provider result exactly in `transcript.raw`.

4. Read [references/content-model.md](references/content-model.md) and [references/transcript-editing.md](references/transcript-editing.md). Populate `transcript.readable`, `digest`, including a useful quote list, and provenance fields in `project.json`. Preserve all meaningful content in the readable transcript; do not turn it into a summary.
5. For X output, read [references/x-writing.md](references/x-writing.md). Generate separate `single_posts` and `threads`, always retaining the source episode URL.
6. For Xiaohongshu output, read [references/xiaohongshu-writing.md](references/xiaohongshu-writing.md). Generate platform-native title options, a link-free caption, and 4–8 cards. Do not reuse the episode title as the primary Xiaohongshu title. Keep claims traceable to transcript paragraph IDs.
7. Validate grounding and publishing invariants:

   ```bash
   python3 scripts/validate_project.py "<project>/project.json"
   ```

   Fix every reported error before rendering. Do not delete raw content or loosen provenance to make validation pass.

8. Build the self-contained editor:

   ```bash
   python3 scripts/build_workspace.py "<project>/project.json" --output "<project>/index.html"
   ```

9. Let the user review and edit the HTML. Do not silently overwrite user-edited copy when regenerating another section. Open Xiaohongshu card editing by default. “自由排版” lets the user drag the eyebrow, title, individual body paragraphs, page number, and eligible small theme decorations. It also reveals a toolbar above each card. The cursor position selects either the title or body block; the toolbar range slider and color picker update only that selected block. Users may hide page numbers. These choices persist in exported project JSON and card images. The page can export edited project JSON, copy an individual card PNG to the clipboard, download one PNG, or package every card into one ZIP.
10. Export Xiaohongshu cards after review:

   ```bash
   node scripts/export_cards.cjs "<project>/index.html" --output-dir "<project>/exports/xiaohongshu"
   ```

   Install Playwright when unavailable. Export one 1080×1440 PNG per card and fail on text overflow.

11. To collect one or more episodes into a switchable local website, build a library:

   ```bash
   python3 scripts/build_site.py "<project-a>/project.json" "<project-b>/project.json" \
     --output-dir "<podcast-library>"
   ```

   Rebuild with all project JSON files whenever adding an episode. Start the bundled local preview server:

   ```bash
   python3 scripts/serve_site.py "<podcast-library>" --port 8000
   ```

   Open the printed loopback URL. Use `--open` when opening the user's default browser is appropriate.

## Output Rules

- Deliver `index.html`, `project.json`, and exported assets requested by the user.
- Keep five distinct views: digest, quote list, readable full transcript, X, and Xiaohongshu.
- Mark uncertain names, numbers, brands, and terms with `〔疑似：…〕`; never silently repair them.
- Label quotations as `verbatim`, `lightly_edited`, or `paraphrased`. Do not use quotation marks for paraphrases.
- Do not invent speakers, timestamps, handles, endorsements, or episode facts.
- Build semantic chapters without timestamps when the transcription has no timing data.
- Prefer a few strong social posts over repetitive variants.
- Never put the show or channel name in Xiaohongshu card artwork. Keep source attribution in metadata and the digest view.

## Acquisition Failures

Read [references/platform-acquisition.md](references/platform-acquisition.md) when acquisition fails. Report the failed layer—native extractor, generic extractor, public page discovery, or direct media download—and offer the narrowest safe fallback.
