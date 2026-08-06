#!/usr/bin/env python3
"""Build a self-contained editable HTML workspace from project JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def fallback_sections(raw: str) -> list[dict]:
    chunks = [part.strip() for part in raw.replace("\r", "").split("\n") if part.strip()]
    if len(chunks) < 2 and raw.strip():
        chunks = [part.strip() for part in raw.replace("。", "。\n").replace("？", "？\n").replace("！", "！\n").splitlines() if part.strip()]
        chunks = ["".join(chunks[i:i + 5]) for i in range(0, len(chunks), 5)]
    return [{"id": "section-01", "heading": "阅读全文", "paragraphs": [
        {"id": f"p-{index:03d}", "text": text, "source_start": None, "source_end": None}
        for index, text in enumerate(chunks, 1)
    ]}]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    project_path = Path(args.project).resolve()
    project = json.loads(project_path.read_text(encoding="utf-8"))
    readable = project.setdefault("transcript", {}).setdefault("readable", {})
    if not readable.get("sections"):
        readable["sections"] = fallback_sections(str(project["transcript"].get("raw") or ""))
    project.setdefault("xiaohongshu", {}).setdefault("theme", "editorial-red")
    template = (Path(__file__).resolve().parent.parent / "assets" / "workspace.html").read_text(encoding="utf-8")
    payload = json.dumps(project, ensure_ascii=False).replace("</", "<\\/")
    if "__PROJECT_DATA__" not in template:
        raise RuntimeError("workspace template marker is missing")
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(template.replace("__PROJECT_DATA__", payload), encoding="utf-8")
    print(json.dumps({"html": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
