# Universal Crispy Bits social previews

Every generated Crispy Bits jukebox receives the same Open Graph and Twitter/X preview through the shared site-generation path. Project types do not implement previews independently.

## Components

- `templates/social-preview/crispy-bits-social-preview-template.png` is the frozen title-free visual layer. It contains the Crispy Bits marquee, gold detailing, PRESS button, and HIT IT treatment. It is packaged with the desktop generator but is not copied into public jukebox assets.
- `aggits_video_factory.social_preview` renders the canonical project title into the safe title region, produces a 1200×630 JPEG, and owns fitting, fallback, and cache-version rules.
- `aggits_video_factory.site_builder.build_project_site` supplies the canonical project title and public URL and writes crawler-readable metadata directly into `index.html`.

The title renderer measures actual glyph bounds. It prefers one line, then two balanced lines, and permits a third line only when required. It uses one consistent uppercase cream/gold Crispy Bits title treatment for every project.

## Generation and cache invalidation

The image filename contains a deterministic digest of the normalised title and the preview-template version, for example `social-card-v1-0123456789ab.jpg`. A title or template-version change produces a new URL, which prompts social crawlers to fetch the updated card. Local rebuilds remove obsolete versioned social cards; publishing replaces the complete project directory, so old assets do not accumulate.

If the artwork template cannot be read, generation creates a valid generic Crispy Bits card. A missing title falls back to `CRISPY BITS`; placeholder text is never emitted.

## Inheritance

The preview is generated after the common project validation/build path, so Business, Music, Tourism, and any future project type supported by `build_project_site` inherit it automatically. There is no project-type-specific preview class or configuration field.

Existing static GitHub Pages jukeboxes continue to work unchanged. Because their HTML and image files are already deployed static assets, they receive the new preview on their next deliberate rebuild/republish; no URL or slug changes.
