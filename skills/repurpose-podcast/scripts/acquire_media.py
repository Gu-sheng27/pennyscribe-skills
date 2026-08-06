#!/usr/bin/env python3
"""Acquire one public episode and normalize it to MP3."""

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

    for dependency in ("yt-dlp", "ffmpeg", "curl"):
        if not shutil.which(dependency):
            parser.error(f"required executable not found: {dependency}")

    output = Path(args.output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    media_path = output / "media.mp3"
    source_path = Path(args.source).expanduser()

    if source_path.is_file():
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
            download_result = run(base + ["-x", "--audio-format", "mp3", "--audio-quality", "5", "-o", str(output / "media.%(ext)s"), args.source])
            acquired = download_result.returncode == 0 and media_path.exists()
            failure = download_result.stderr.strip()

        discovered: dict[str, object] = {}
        if not acquired:
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

        if not acquired:
            print("Acquisition failed after yt-dlp and public page media discovery.", file=sys.stderr)
            if failure:
                print(failure, file=sys.stderr)
            print("Provide a public RSS/direct audio URL or a local audio file. Authentication and DRM are not bypassed.", file=sys.stderr)
            return 2

        normalized = output / "media.normalized.mp3"
        normalize(acquired_path, normalized)
        if acquired_path != media_path:
            acquired_path.unlink(missing_ok=True)
        normalized.replace(media_path)

        metadata = {
            "source_url": str(info.get("webpage_url") or info.get("original_url") or args.source),
            "platform": platform_for(args.source, str(info.get("extractor_key") or "")),
            "title": str(info.get("title") or discovered.get("title") or "Untitled episode"),
            "creator": info.get("channel") or info.get("uploader") or discovered.get("creator"),
            "published_at": info.get("upload_date") or info.get("release_date") or discovered.get("published_at"),
            "duration_seconds": info.get("duration") or discovered.get("duration_seconds"),
            "cover": info.get("thumbnail") or discovered.get("cover"),
            "extractor": info.get("extractor_key"),
        }

    (output / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"audio": str(media_path), "metadata": str(output / "metadata.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
