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
- An optional sponsor logo may be PNG, JPG/JPEG, or WebP and no larger than 2 MB.
- Sponsor creatives are copied under the project's `assets/` directory. Original operator paths are never serialized into public configuration.

Banjo's Choice is post-landing presentation metadata and does not alter selection probability. Sponsor insertion is a separate orchestration layer: five completed normal discoveries are required, active creatives rotate deterministically, and a sponsor can never immediately follow another sponsor.

## Public header and sponsor placement

The Banjo public page omits the generic Home/Sound row. Its existing bordered plaque shows `BANJO'S WORLD OF CARS` for 10 seconds and then, when configured, changes once into a continuously mounted right-to-left editorial ticker. The ticker accepts up to 1,500 plain-text characters; line breaks become ` • ` separators. Spins, media changes, Banjo's Choice, sponsor playback, and the Show Banjo modal do not restart it. An empty ticker leaves the title visible.

Sponsor identity does not rotate through or link from the header. An active sponsor with a valid URL instead receives a separate `VISIT OUR SPONSOR` link beneath the four main buttons and, when configured, a proportionally contained sponsor logo pointing to the same URL. When no sponsor is active, that area displays `BANJO IS LOOKING FOR SPONSORS`, a short invitation to contact Andy, and an `EMAIL ANDY` mail link with the fixed subject `Banjo Sponsorship Enquiry`. The four Banjo buttons remain `SHARE`, `PLAY/REPLAY VIDEO`, `SHOW BANJO`, and `RE-SPIN` for every content state.

## Show Banjo submissions

`SHOW BANJO` opens the Banjo-only `SHOW BANJO YOUR CAR` dialog. The browser sends only first name, email address, normalized YouTube URL, fixed Banjo machine identity, and a hidden honeypot value to `POST /api/banjo/submissions`. Localhost preview simulates success and never sends email.

The Worker validates a maximum 2 KB JSON request, accepts only the narrow field allowlist, fixes the recipient through server-side `OWNER_EMAIL`, fixes the subject to `NEW CAR FOR BANJO`, and builds the message body itself. It sends through the existing Resend identity with the validated submitter as Reply-To. It allows five attempts per Cloudflare network address per UTC-hour window and suppresses the same normalized email/video pair for 24 hours using hashed D1 guard keys. It does not expose or require the desktop HMAC credential in the public client, and it cannot accept an arbitrary recipient, subject, body, From, or HTML payload.

Submissions are email candidates only. They do not alter the project, add videos, assign Banjo's Choice, publish, republish, subscribe the submitter, or send an automatic acknowledgement.

## Sponsor media and analytics readiness

Sponsor media uses the HTML5 video element with conservative `metadata` preload. Standard media events expose structured in-page hooks through the `crispy-bits:banjo` custom event for impression, playback milestones, completion, replay, dedicated sponsor-button/logo placement, Banjo's Choice, Show Banjo submission outcomes, and share actions. Submission events contain no form values or other PII. No analytics persistence or personal tracking is implemented in this milestone.

GitHub Pages is suitable for the initial bounded experiment, but sustained high-volume sponsor-video traffic should later use dedicated object storage/CDN. No transcoding, HLS, DASH, FFmpeg, or external video platform is included.

## Audio

The Banjo's Choice visual award works without an audio file. The runtime provides a Sound-aware optional `awardAudioUrl` hook and emits an availability event. An approved TA-DAAA asset can be added separately without changing the reel, lever, or landing mechanics.
