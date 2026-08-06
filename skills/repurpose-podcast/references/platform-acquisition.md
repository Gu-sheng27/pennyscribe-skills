# Platform acquisition

Try acquisition in this order:

1. `yt-dlp` native extractor.
2. `yt-dlp` generic extractor.
3. Public Open Graph audio or HTML audio source discovery.
4. Direct public media download.
5. Ask for a public RSS URL, direct audio URL, or local file.

YouTube may require an external JavaScript runtime and may restrict some public formats. Bilibili may restrict quality or access by region. Apple Podcasts and Xiaoyuzhou are not guaranteed native extractors, so use their public page metadata or RSS-backed media when exposed.

Never bypass authentication, paywalls, DRM, membership restrictions, or CAPTCHAs. Never automatically export browser cookies. When cookies are explicitly authorized, pass `--cookies-from-browser` directly to `yt-dlp` and do not persist them.

Reject playlists unless the user explicitly requests batch processing. Keep the canonical episode URL and extractor metadata for attribution.
