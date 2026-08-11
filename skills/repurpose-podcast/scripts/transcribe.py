#!/usr/bin/env python3
"""Create project JSON from subtitles, PennyScribe, or ElevenLabs speech-to-text."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


PENNYSCRIBE_API = "https://api.pennyscribe.com/v1/transcriptions"
ELEVENLABS_API = "https://api.elevenlabs.io/v1/speech-to-text"
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def curl_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", "")


def run_curl(config_lines: list[str]) -> dict:
    response = subprocess.run(
        ["curl", "--config", "-"], input="\n".join(config_lines) + "\n",
        text=True, capture_output=True, check=False,
    )
    if response.returncode:
        detail = response.stdout.strip() or response.stderr.strip()
        raise RuntimeError(detail or "request failed")
    return json.loads(response.stdout)


def pennyscribe_request(url: str, key: str) -> dict:
    return run_curl([
        f'url = "{curl_quote(url)}"', 'silent', 'show-error', 'fail-with-body',
        f'header = "Authorization: Bearer {curl_quote(key)}"',
    ])


def transcribe_pennyscribe(audio: Path, key: str, language_code: str | None, poll_seconds: float) -> tuple[str, dict]:
    config = [
        f'url = "{PENNYSCRIBE_API}"', 'request = "POST"', 'silent', 'show-error', 'fail-with-body',
        f'header = "Authorization: Bearer {curl_quote(key)}"',
        f'form = "file=@{curl_quote(str(audio))}"',
    ]
    if language_code:
        config.append(f'form = "language_code={curl_quote(language_code)}"')
    job = run_curl(config)
    job_id = str(job.get("id") or "")
    if not job_id:
        raise RuntimeError("PennyScribe response did not include an id")

    while True:
        job = pennyscribe_request(f"{PENNYSCRIBE_API}/{job_id}", key)
        state = str(job.get("state") or "")
        if state in TERMINAL:
            break
        time.sleep(max(1, poll_seconds))
    if state != "COMPLETED":
        raise RuntimeError(f"Transcription ended in {state}: {job.get('error_message') or 'no detail'}")
    raw = str((job.get("result") or {}).get("text") or "").strip()
    if not raw:
        raise RuntimeError("PennyScribe returned an empty transcript")
    return raw, {
        "provider": "pennyscribe", "transcription_id": job_id,
        "language_code": job.get("language_code"), "language": job.get("language"),
        "duration_seconds": job.get("duration_seconds"),
    }


def transcribe_elevenlabs(audio: Path, key: str, language_code: str | None, model_id: str, diarize: bool) -> tuple[str, dict]:
    config = [
        f'url = "{ELEVENLABS_API}"', 'request = "POST"', 'silent', 'show-error', 'fail-with-body',
        f'header = "xi-api-key: {curl_quote(key)}"',
        f'form = "file=@{curl_quote(str(audio))}"',
        f'form = "model_id={curl_quote(model_id)}"',
        f'form = "diarize={str(diarize).lower()}"',
        'form = "tag_audio_events=false"',
    ]
    if language_code:
        config.append(f'form = "language_code={curl_quote(language_code)}"')
    response = run_curl(config)
    raw = str(response.get("text") or "").strip()
    if not raw:
        raise RuntimeError("ElevenLabs returned an empty transcript")
    return raw, {
        "provider": "elevenlabs", "model_id": model_id,
        "language_code": response.get("language_code"),
        "language_probability": response.get("language_probability"),
        "diarize": diarize,
    }


def project_from_text(metadata: dict, raw: str) -> dict:
    transcript = {"raw": raw, "readable": {"title": metadata.get("title") or "阅读全文", "dek": "", "sections": []}}
    if metadata.get("transcript_source"):
        transcript["source"] = metadata["transcript_source"]
    if metadata.get("transcript_language"):
        transcript["language"] = metadata["transcript_language"]
    return {
        "schema_version": 1,
        "source": {
            "url": metadata.get("source_url"), "platform": metadata.get("platform"), "title": metadata.get("title"),
            "creator": metadata.get("creator"), "published_at": metadata.get("published_at"),
            "duration_seconds": metadata.get("duration_seconds"), "cover": metadata.get("cover"),
        },
        "transcript": transcript,
        "digest": {"recommendation": "", "summary": "", "insights": [], "quotes": [], "audience": []},
        "x": {"single_posts": [], "threads": []},
        "xiaohongshu": {"title_options": [], "caption": "", "theme": "visual-accessibility", "show_page_numbers": True, "cards": []},
    }


def write_project(project: dict, value: str) -> Path:
    output = Path(value).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", nargs="?", help="Audio file to transcribe")
    parser.add_argument("--transcript", help="Existing source-language subtitle text; bypasses speech-to-text")
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--provider", choices=("pennyscribe", "elevenlabs"), default="pennyscribe")
    parser.add_argument("--language-code")
    parser.add_argument("--poll-seconds", type=float, default=5, help="PennyScribe polling interval")
    parser.add_argument("--model-id", default="scribe_v2", help="ElevenLabs speech-to-text model")
    parser.add_argument("--diarize", action="store_true", help="Enable ElevenLabs speaker diarization")
    args = parser.parse_args()

    if bool(args.audio) == bool(args.transcript):
        parser.error("provide exactly one of audio or --transcript")
    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))

    if args.transcript:
        transcript_path = Path(args.transcript).resolve()
        if not transcript_path.is_file():
            parser.error(f"transcript not found: {transcript_path}")
        raw = transcript_path.read_text(encoding="utf-8").strip()
        if not raw:
            parser.error("transcript is empty")
        output = write_project(project_from_text(metadata, raw), args.output)
        print(json.dumps({"project": str(output), "transcript_source": metadata.get("transcript_source") or "provided-text"}, ensure_ascii=False))
        return 0

    key = os.environ.get("PENNYSCRIBE_API_KEY")
    if not key:
        parser.error("PENNYSCRIBE_API_KEY is not set; store the selected provider's key in this variable")
    audio = Path(args.audio).resolve()
    if not audio.is_file():
        parser.error(f"audio not found: {audio}")

    try:
        if args.provider == "elevenlabs":
            raw, record = transcribe_elevenlabs(audio, key, args.language_code, args.model_id, args.diarize)
        else:
            raw, record = transcribe_pennyscribe(audio, key, args.language_code, args.poll_seconds)
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"{args.provider} transcription failed: {exc}", file=sys.stderr)
        return 2

    metadata["transcript_source"] = args.provider
    metadata["duration_seconds"] = metadata.get("duration_seconds") or record.get("duration_seconds")
    project = project_from_text(metadata, raw)
    project["transcription"] = record
    if args.provider == "pennyscribe":
        project["pennyscribe"] = {key: value for key, value in record.items() if key != "provider"}
    output = write_project(project, args.output)
    print(json.dumps({"project": str(output), "provider": args.provider, "transcription_id": record.get("transcription_id")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
