#!/usr/bin/env python3
"""Validate transcript provenance and social publishing invariants."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def validate(project: dict) -> list[str]:
    errors: list[str] = []
    source = project.get("source") or {}
    source_url = str(source.get("url") or "")
    raw = str((project.get("transcript") or {}).get("raw") or "")
    sections = ((project.get("transcript") or {}).get("readable") or {}).get("sections") or []
    paragraph_ids: set[str] = set()
    for section_index, section in enumerate(sections, 1):
        for paragraph_index, paragraph in enumerate(section.get("paragraphs") or [], 1):
            label = f"section {section_index} paragraph {paragraph_index}"
            paragraph_id = str(paragraph.get("id") or "")
            if not paragraph_id:
                errors.append(f"{label} has no id")
            elif paragraph_id in paragraph_ids:
                errors.append(f"duplicate paragraph id: {paragraph_id}")
            paragraph_ids.add(paragraph_id)
            start, end = paragraph.get("source_start"), paragraph.get("source_end")
            if start is None and end is None:
                continue
            if not isinstance(start, int) or not isinstance(end, int) or start < 0 or start > end or end > len(raw):
                errors.append(f"{label} has invalid raw-text range {start}:{end} for {len(raw)} characters")

    def check_refs(items: list, label: str) -> None:
        for index, item in enumerate(items, 1):
            for paragraph_id in item.get("source_paragraph_ids") or []:
                if paragraph_id not in paragraph_ids:
                    errors.append(f"{label} {index} references missing paragraph id: {paragraph_id}")

    digest = project.get("digest") or {}
    check_refs(digest.get("insights") or [], "digest insight")
    check_refs(digest.get("quotes") or [], "digest quote")
    for index, quote in enumerate(digest.get("quotes") or [], 1):
        if quote.get("fidelity") not in {"verbatim", "lightly_edited", "paraphrased"}:
            errors.append(f"digest quote {index} has invalid fidelity")
    if len(digest.get("quotes") or []) < 3:
        errors.append("digest requires at least 3 quotes for the quote-list view")
    social_x = project.get("x") or {}
    check_refs(social_x.get("single_posts") or [], "X post")
    for index, thread in enumerate(social_x.get("threads") or [], 1):
        check_refs(thread, f"X thread {index} item")
    if source_url:
        for index, post in enumerate(social_x.get("single_posts") or [], 1):
            if source_url not in str(post.get("text") or ""):
                errors.append(f"X post {index} does not contain the source URL")
        for index, thread in enumerate(social_x.get("threads") or [], 1):
            if thread and source_url not in str(thread[-1].get("text") or ""):
                errors.append(f"X thread {index} final item does not contain the source URL")

    xhs = project.get("xiaohongshu") or {}
    cards = xhs.get("cards") or []
    titles = xhs.get("title_options") or []
    if not titles or not str(titles[0]).strip():
        errors.append("Xiaohongshu requires a primary title")
    elif re.sub(r"\W+", "", str(titles[0])).casefold() == re.sub(r"\W+", "", str(source.get("title") or "")).casefold():
        errors.append("Xiaohongshu primary title must not reuse the episode title")
    if not 4 <= len(cards) <= 8:
        errors.append(f"Xiaohongshu requires 4–8 cards; found {len(cards)}")
    elif str(cards[0].get("kind") or "") != "cover":
        errors.append("Xiaohongshu first card must be a cover")
    for index, card in enumerate(cards[1:], 2):
        if str(card.get("kind") or "") == "cover":
            errors.append(f"Xiaohongshu card {index} must use a content-card kind")
    check_refs(cards, "Xiaohongshu card")
    xhs_text = "\n".join([*(str(title) for title in titles), str(xhs.get("caption") or "")] + [f"{card.get('title', '')}\n{card.get('body', '')}" for card in cards])
    if re.search(r"(?:https?://|www\.)\S+", xhs_text, re.I):
        errors.append("Xiaohongshu titles, caption, and cards must not contain URLs")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    args = parser.parse_args()
    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    errors = validate(project)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print("Project is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
