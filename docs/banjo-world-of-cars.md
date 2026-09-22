# Banjo's World of Cars

`banjo` is the fourth Crispy Bits Desktop project type. It reuses the shared ProjectStore, YouTube resolver/editor, SiteBuilder, Publisher, QR, delivery, and reel/lever engine while keeping all public Banjo presentation and orchestration explicitly type-scoped.

## Canonical character

`static/banjo/banjo-approved-header.png` is the approved Banjo character asset. It was derived from the operator-supplied reference by removing only the green background into an alpha channel. The foreground artwork was not redrawn, regenerated, recoloured, reshaped, or enhanced.

The asset is immutable without explicit operator approval. Its SHA-256 is protected in `aggits_video_factory.banjo.BANJO_CHARACTER_SHA256`, and Banjo builds fail if the file changes or loses its RGBA transparency.

## Capacity and programming

- Up to 40 included YouTube videos.
- Up to four active Banjo's Choice records attached to existing YouTube video IDs.
- One optional sponsor identity with up to four project-controlled MP4 creatives.
- Sponsor MP4 files must be `.mp4` and no larger than 10 MB each.
- Sponsor creatives are copied under the project's `assets/` directory. Original operator paths are never serialized into public configuration.

Banjo's Choice is post-landing presentation metadata and does not alter selection probability. Sponsor insertion is a separate orchestration layer: five completed normal discoveries are required, active creatives rotate deterministically, and a sponsor can never immediately follow another sponsor.

## Sponsor media and analytics readiness

Sponsor media uses the HTML5 video element with conservative `metadata` preload. Standard media events expose structured in-page hooks through the `crispy-bits:banjo` custom event for impression, playback milestones, completion, replay, sponsor CTA placement, sponsor-header visibility, Banjo's Choice, and share actions. No analytics persistence or personal tracking is implemented in this milestone.

GitHub Pages is suitable for the initial bounded experiment, but sustained high-volume sponsor-video traffic should later use dedicated object storage/CDN. No transcoding, HLS, DASH, FFmpeg, or external video platform is included.

## Audio

The Banjo's Choice visual award works without an audio file. The runtime provides a Sound-aware optional `awardAudioUrl` hook and emits an availability event. An approved TA-DAAA asset can be added separately without changing the reel, lever, or landing mechanics.
