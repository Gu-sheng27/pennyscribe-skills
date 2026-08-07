#!/usr/bin/env python3
"""Acquire one public episode as source-language subtitles or normalized MP3."""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


MEDIA_PATTERNS = (
    r'<meta[^>]+(?:property|name)=["\'](?:og:audio|twitter:player:stream)["\'][^>]+content=["\']([^"\']+)',
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:audio|twitter:player:stream)["\']',
    r'<audio[^>]+src=["\']([^"\']+)',
    r'"(?:audioUrl|audio_url|mediaUrl|media_url|enclosureUrl)"\s*:\s*"([^"\\]+(?:\\.[^"\\]*)*)"',
)


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def fetch(url: str, limit: int | None = None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 PennyScribeSkills/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(limit or -1)
    return data


def download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 PennyScribeSkills/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as destination:
        shutil.copyfileobj(response, destination, length=1024 * 1024)


def page_media(url: str) -> tuple[str | None, dict[str, str]]:
    text = fetch(url, 8_000_000).decode("utf-8", "replace")
    metadata: dict[str, str] = {}
    for key, prop in (("title", "og:title"), ("creator", "og:site_name"), ("cover", "og:image")):
        match = re.search(
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)',
            text,
            re.I,
        )
        if match:
            metadata[key] = html.unescape(match.group(1))
    for pattern in MEDIA_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            media = bytes(match.group(1), "utf-8").decode("unicode_escape")
            return urllib.parse.urljoin(url, html.unescape(media).replace("\\/", "/")), metadata
    return None, metadata


def apple_episode(url: str) -> tuple[str | None, dict[str, object]]:
    parsed = urllib.parse.urlparse(url)
    if "podcasts.apple.com" not in parsed.netloc.lower():
        return None, {}
    show_match = re.search(r"/id(\d+)", parsed.path)
    episode_id = urllib.parse.parse_qs(parsed.query).get("i", [None])[0]
    if not show_match or not episode_id:
        return None, {}
    lookup = f"https://itunes.apple.com/lookup?id={show_match.group(1)}&entity=podcastEpisode&limit=200"
    response = subprocess.run(["curl", "-L", "-sS", "--fail", lookup], capture_output=True, check=False)
    if response.returncode:
        return None, {}
    payload = json.loads(response.stdout.decode("utf-8"))
    for item in payload.get("results", []):
        if str(item.get("trackId")) == str(episode_id) and item.get("episodeUrl"):
            return str(item["episodeUrl"]), {
                "title": item.get("trackName"),
                "creator": item.get("collectionName") or item.get("artistName"),
                "cover": item.get("artworkUrl600") or item.get("artworkUrl160"),
                "published_at": item.get("releaseDate"),
                "duration_seconds": round(float(item.get("trackTimeMillis") or 0) / 1000) or None,
            }
    return None, {}


def platform_for(url: str, extractor: str | None = None) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if "youtube" in host or "youtu.be" in host:
        return "youtube"
    if "bilibili" in host or "b23.tv" in host:
        return "bilibili"
    if "podcasts.apple" in host:
        return "apple-podcasts"
    if "xiaoyuzhoufm" in host:
        return "xiaoyuzhou"
    return (extractor or "web").lower()


def language_key(code: str) -> str:
    normalized = str(code or "").lower().replace("_", "-")
    return normalized.removesuffix("-orig")


def same_language(left: str, right: str) -> bool:
    left_key, right_key = language_key(left), language_key(right)
    return left_key == right_key or left_key.split("-", 1)[0] == right_key.split("-", 1)[0]


def original_caption_tracks(captions: object) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    if not isinstance(captions, dict):
        return result
    for code, formats in captions.items():
        if str(code).lower() == "live_chat" or not isinstance(formats, list):
            continue
        original = []
        for item in formats:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            query = urllib.parse.parse_qs(urllib.parse.urlparse(str(item["url"])).query)
            if "tlang" not in query:
                original.append(item)
        if original:
            result[str(code)] = original
    return result


def choose_youtube_caption(info: dict[str, object]) -> dict[str, object] | None:
    """Prefer source-language manual captions, then source-language automatic captions."""
    manual = original_caption_tracks(info.get("subtitles"))
    automatic = original_caption_tracks(info.get("automatic_captions"))
    if not manual and not automatic:
        return None

    available = set(manual) | set(automatic)
    declared = str(info.get("language") or "").strip()
    source_code = next((code for code in available if declared and same_language(code, declared)), None)

    if source_code is None:
        auto_languages = {language_key(code).split("-", 1)[0] for code in automatic}
        if len(auto_languages) == 1:
            source_code = next(iter(automatic))
        elif manual:
            # yt-dlp preserves YouTube's caption-track order; the default/source track is first.
            source_code = next(iter(manual))
    if source_code is None:
        return None

    for kind, tracks in (("manual", manual), ("automatic", automatic)):
        matching = [(code, formats) for code, formats in tracks.items() if same_language(code, source_code)]
        if not matching:
            continue
        matching.sort(key=lambda item: (language_key(item[0]) != language_key(source_code), item[0].endswith("-orig") is False, item[0]))
        code, formats = matching[0]
        priority = {"json3": 0, "vtt": 1, "ttml": 2, "srv3": 3, "srv2": 4, "srv1": 5}
        selected = min(formats, key=lambda item: priority.get(str(item.get("ext") or ""), 99))
        return {"kind": kind, "language": code, "format": selected}
    return None


def subtitle_text(path: Path, extension: str) -> str:
    if extension == "json3":
        payload = json.loads(path.read_text(encoding="utf-8"))
        lines = []
        for event in payload.get("events", []):
            line = "".join(str(segment.get("utf8") or "") for segment in event.get("segs", []) if isinstance(segment, dict)).strip()
            if line and (not lines or line != lines[-1]):
                lines.append(line)
        return "\n".join(lines).strip()

    raw = path.read_text(encoding="utf-8", errors="replace")
    if extension == "ttml":
        raw = "\n".join(re.findall(r"<p\b[^>]*>(.*?)</p>", raw, re.I | re.S))
    lines = []
    for value in raw.splitlines():
        line = html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
        if not line or line.isdigit() or line.upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        if "-->" in line or re.fullmatch(r"[\d:.,\s-]+", line):
            continue
        if not lines or line != lines[-1]:
            lines.append(line)
    return "\n".join(lines).strip()


def normalize(source: Path, target: Path) -> None:
    result = run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(target)])
    if result.returncode:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Public episode URL or local media file")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cookies-from-browser", help="Pass cookies to yt-dlp only with explicit user authorization")
    args = parser.parse_args()

    output = Path(args.output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    media_path = output / "media.mp3"
    transcript_path = output / "transcript.txt"
    source_path = Path(args.source).expanduser()
    transcript_path.unlink(missing_ok=True)

    if source_path.is_file():
        if not shutil.which("ffmpeg"):
            parser.error("required executable not found: ffmpeg")
        normalize(source_path.resolve(), media_path)
        metadata = {
            "source_url": source_path.resolve().as_uri(),
            "platform": "local-file",
            "title": source_path.stem,
            "creator": None,
            "published_at": None,
            "duration_seconds": None,
            "cover": None,
        }
    else:
        parsed = urllib.parse.urlparse(args.source)
        if parsed.scheme not in {"http", "https"}:
            parser.error("source must be a local file or an HTTP(S) URL")
        for dependency in ("yt-dlp", "curl"):
            if not shutil.which(dependency):
                parser.error(f"required executable not found: {dependency}")

        base = ["yt-dlp", "--no-playlist", "--no-warnings"]
        if args.cookies_from_browser:
            base.extend(["--cookies-from-browser", args.cookies_from_browser])
        probe = run(base + ["--dump-single-json", args.source])
        info: dict[str, object] = {}
        acquired = False
        acquired_path = media_path
        failure = probe.stderr.strip()
        if probe.returncode == 0:
            info = json.loads(probe.stdout)
            if platform_for(args.source, str(info.get("extractor_key") or "")) == "youtube":
                caption = choose_youtube_caption(info)
                if caption:
                    caption_format = caption["format"]
                    extension = str(caption_format.get("ext") or "vtt")
                    subtitle_path = output / f"subtitle.{extension}"
                    try:
                        download(str(caption_format["url"]), subtitle_path)
                        text = subtitle_text(subtitle_path, extension)
                        if not text:
                            raise ValueError("selected subtitle track was empty")
                        transcript_path.write_text(text + "\n", encoding="utf-8")
                        info["selected_caption"] = {"kind": caption["kind"], "language": caption["language"]}
                    except Exception as exc:
                        failure = f"subtitle extraction failed: {exc}"
                    finally:
                        subtitle_path.unlink(missing_ok=True)
            if not transcript_path.exists():
                if not shutil.which("ffmpeg"):
                    parser.error("required executable not found: ffmpeg (no usable source-language YouTube subtitles were found)")
                download_result = run(base + ["-x", "--audio-format", "mp3", "--audio-quality", "5", "-o", str(output / "media.%(ext)s"), args.source])
                acquired = download_result.returncode == 0 and media_path.exists()
                failure = download_result.stderr.strip() or failure

        if not transcript_path.exists() and probe.returncode != 0 and not shutil.which("ffmpeg"):
            parser.error("required executable not found: ffmpeg")

        discovered: dict[str, object] = {}
        if not acquired and not transcript_path.exists():
            try:
                media_url, discovered = apple_episode(args.source)
                if not media_url:
                    media_url, discovered = page_media(args.source)
            except Exception as exc:  # network and unsupported-page fallback
                media_url = None
                failure = f"{failure}\npublic page discovery failed: {exc}".strip()
            if media_url:
                suffix = Path(urllib.parse.urlparse(media_url).path).suffix or mimetypes.guess_extension("audio/mpeg") or ".bin"
                temporary = output / f"download{suffix}"
                download(media_url, temporary)
                acquired_path = temporary
                acquired = True

        if not acquired and not transcript_path.exists():
            print("Acquisition failed after yt-dlp and public page media discovery.", file=sys.stderr)
            if failure:
                print(failure, file=sys.stderr)
            print("Provide a public RSS/direct audio URL or a local audio file. Authentication and DRM are not bypassed.", file=sys.stderr)
            return 2

        if acquired:
            normalized = output / "media.normalized.mp3"
            normalize(acquired_path, normalized)
            if acquired_path != media_path:
                acquired_path.unlink(missing_ok=True)
            normalized.replace(media_path)

        selected_caption = info.get("selected_caption") if isinstance(info.get("selected_caption"), dict) else None
        metadata = {
            "source_url": str(info.get("webpage_url") or info.get("original_url") or args.source),
            "platform": platform_for(args.source, str(info.get("extractor_key") or "")),
            "title": str(info.get("title") or discovered.get("title") or "Untitled episode"),
            "creator": info.get("channel") or info.get("uploader") or discovered.get("creator"),
            "published_at": info.get("upload_date") or info.get("release_date") or discovered.get("published_at"),
            "duration_seconds": info.get("duration") or discovered.get("duration_seconds"),
            "cover": info.get("thumbnail") or discovered.get("cover"),
            "extractor": info.get("extractor_key"),
            "transcript_source": f"youtube-{selected_caption['kind']}-subtitles" if selected_caption else "pennyscribe",
            "transcript_language": selected_caption["language"] if selected_caption else None,
        }

    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {"metadata": str(output / "metadata.json")}
    if transcript_path.exists():
        result["transcript"] = str(transcript_path)
    else:
        result["audio"] = str(media_path)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
