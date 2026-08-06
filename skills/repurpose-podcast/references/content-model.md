# Content model

Use UTF-8 JSON. Preserve unknown optional values as `null`, not invented text.

```json
{
  "schema_version": 1,
  "source": {
    "url": "https://example.com/episode",
    "platform": "youtube",
    "title": "Episode title",
    "creator": "Show or channel",
    "published_at": null,
    "duration_seconds": 3600,
    "cover": null
  },
  "transcript": {
    "raw": "Exact PennyScribe result",
    "readable": {
      "title": "Readable feature title",
      "dek": "Optional introduction",
      "sections": [
        {
          "id": "section-01",
          "heading": "Semantic chapter heading",
          "paragraphs": [
            {
              "id": "p-001",
              "text": "Complete readable paragraph.",
              "source_start": 0,
              "source_end": 29
            }
          ]
        }
      ]
    }
  },
  "digest": {
    "recommendation": "One-sentence reason to read or listen",
    "summary": "Grounded summary",
    "insights": [{"text": "Insight", "source_paragraph_ids": ["p-001"]}],
    "quotes": [{"text": "Standalone quotable line", "fidelity": "verbatim", "source_paragraph_ids": ["p-001"]}],
    "audience": ["Intended reader"]
  },
  "x": {
    "single_posts": [{"text": "Post text", "source_paragraph_ids": ["p-001"]}],
    "threads": [[{"text": "Thread item", "source_paragraph_ids": ["p-001"]}]]
  },
  "xiaohongshu": {
    "title_options": ["Platform-native title, not the episode title"],
    "caption": "Link-free, paragraph-formatted caption",
    "theme": "editorial-red",
    "cards": [
      {"kind": "cover", "eyebrow": "PODCAST NOTES", "title": "Card title", "body": "", "source_paragraph_ids": []}
    ]
  }
}
```

Keep stable section and paragraph IDs across editing. Use source character ranges when confidently available. Social outputs may cite multiple paragraph IDs. Never cite a nonexistent ID.

Create at least three `digest.quotes` entries so the workspace can render a useful standalone quote list. Keep Xiaohongshu copy free of URLs; the source URL remains available elsewhere in the project and workspace.
