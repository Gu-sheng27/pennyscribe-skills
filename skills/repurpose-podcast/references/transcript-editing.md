# Readable transcript editing

Produce a complete reading edition, not a synopsis.

1. Preserve every meaningful claim, example, qualification, disagreement, and transition.
2. Split text into semantic chapters and readable paragraphs. Prefer 2–6 paragraphs per chapter and avoid walls of text.
3. Repair punctuation and obvious ASR sentence boundaries. Remove only empty fillers and immediately repeated fragments.
4. Preserve the speaker's tone. Do not rewrite spoken content into polished opinions the speaker did not express.
5. Keep names, numbers, brands, and technical terms unchanged unless the correction is certain from context. Mark uncertainty as `〔疑似：原文〕`.
6. Do not assign speaker names without diarization evidence.
7. Generate chapter headings without timestamps when timing data is unavailable.
8. Keep `transcript.raw` byte-for-byte unchanged. Put the reading edition only in `transcript.readable`.
9. Map paragraphs back to raw-text character offsets when practical. Verify each range before storing it.

After editing, compare the concatenated reading edition with the raw transcript. Investigate unexpectedly large reductions; a reading edition should usually retain most substantive text.
