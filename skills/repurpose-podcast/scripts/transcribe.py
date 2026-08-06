#!/usr/bin/env python3
"""Upload audio to PennyScribe, poll to completion, and create project JSON."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


API = "https://api.pennyscribe.com/v1/transcriptions"
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def curl_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", "")


def request_json(url: str, key: str) -> dict:
    config = "\n".join([
        f'url = "{curl_quote(url)}"',
        'silent',
        'show-error',
        'fail-with-body',
        f'header = "Authorization: Bearer {curl_quote(key)}"',
    ]) + "\n"
    response = subprocess.run(["curl", "--config", "-"], input=config, text=True, capture_output=True, check=False)
    if response.returncode:
        detail = response.stdout.strip() or response.stderr.strip()
        raise RuntimeError(detail or "request failed")
    return json.loads(response.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio")
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--language-code")
    parser.add_argument("--poll-seconds", type=float, default=5)
    args = parser.parse_args()

    key = os.environ.get("PENNYSCRIBE_API_KEY")
    if not key:
        parser.error("PENNYSCRIBE_API_KEY is not set; create a key and set it locally without pasting it into chat")
    audio = Path(args.audio).resolve()
    if not audio.is_file():
        parser.error(f"audio not found: {audio}")

    curl_config = [f'url = "{API}"', 'request = "POST"', 'silent', 'show-error', 'fail-with-body', f'header = "Authorization: Bearer {curl_quote(key)}"', f'form = "file=@{curl_quote(str(audio))}"']
    if args.language_code:
        curl_config.append(f'form = "language_code={args.language_code}"')
    submitted = subprocess.run(["curl", "--config", "-"], input="\n".join(curl_config) + "\n", text=True, capture_output=True, check=False)
    if submitted.returncode:
        print(f"PennyScribe submission failed: {submitted.stderr.strip() or submitted.stdout.strip()}", file=sys.stderr)
        return 2
    job = json.loads(submitted.stdout)
    job_id = str(job.get("id") or "")
    if not job_id:
        raise RuntimeError("PennyScribe response did not include an id")

    while True:
        try:
            job = request_json(f"{API}/{job_id}", key)
        except (RuntimeError, json.JSONDecodeError) as exc:
            print(f"PennyScribe polling failed: {exc}", file=sys.stderr)
            return 2
        state = str(job.get("state") or "")
        if state in TERMINAL:
            break
        time.sleep(max(1, args.poll_seconds))

    if state != "COMPLETED":
        print(f"Transcription ended in {state}: {job.get('error_message') or 'no detail'}", file=sys.stderr)
        return 2

    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
    raw = str((job.get("result") or {}).get("text") or "")
    project = {
        "schema_version": 1,
        "source": {
            "url": metadata.get("source_url"), "platform": metadata.get("platform"), "title": metadata.get("title"),
            "creator": metadata.get("creator"), "published_at": metadata.get("published_at"),
            "duration_seconds": metadata.get("duration_seconds") or job.get("duration_seconds"), "cover": metadata.get("cover"),
        },
        "transcript": {"raw": raw, "readable": {"title": metadata.get("title") or "阅读全文", "dek": "", "sections": []}},
        "digest": {"recommendation": "", "summary": "", "insights": [], "quotes": [], "audience": []},
        "x": {"single_posts": [], "threads": []},
        "xiaohongshu": {"title_options": [], "caption": "", "theme": "editorial-red", "cards": []},
        "pennyscribe": {"transcription_id": job_id, "language_code": job.get("language_code"), "language": job.get("language")},
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"project": str(output), "transcription_id": job_id}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
