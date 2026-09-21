# Universal project-title social previews

Every generated Crispy Bits jukebox receives the same minimal Open Graph and Twitter/X preview through the shared site-generation path. Project types do not implement previews independently.

## Components

- `aggits_video_factory.social_preview` creates a deterministic 1200×630 midnight-blue/black vignette, renders the canonical project title into its central safe region, and draws one small static touch/press icon.
- The active renderer does not load customer logos, video thumbnails, CTA data, project-type labels, Bio content, or branded artwork. Its only content input is the canonical project title.
- `aggits_video_factory.site_builder.build_project_site` supplies that title and the public URL and writes crawler-readable metadata directly into `index.html`.

The title renderer measures actual glyph bounds. It prefers one line, then two balanced lines, and never exceeds two lines. It preserves the stored title's letter case while normalising insignificant whitespace. A missing title produces a valid background and touch icon without invented placeholder or brand copy. Its Georgia-based local font stack and exact midnight/ivory palette mirror the live machine hero.

## Generation and cache invalidation

The image filename contains a deterministic digest of the normalised title and the preview-design version, for example `social-card-v2-0123456789ab.jpg`. A title or design-version change produces a new URL, which prompts social crawlers to fetch the updated card. Local rebuilds remove obsolete versioned social cards; publishing replaces the complete project directory, so old assets do not accumulate.

## Inheritance

The preview is generated after the common project validation/build path, so Business, Music, Tourism, and any future project type supported by `build_project_site` inherit it automatically. There is no project-type-specific preview class or configuration field.

Existing static GitHub Pages jukeboxes continue to work unchanged. Because their HTML and image files are already deployed static assets, they receive the redesigned preview only on their next deliberate rebuild/republish; no URL or slug changes.
