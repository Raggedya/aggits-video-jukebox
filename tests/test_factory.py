from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import UUID

from aggits_video_factory.migrations import CURRENT_PROJECT_SCHEMA_VERSION, ProjectMigrationError, migrate_project_dict
from aggits_video_factory.models import (
    BusinessConfig,
    MusicConfig,
    PrimaryCta,
    PrimaryCtaType,
    Project,
    ProjectType,
    ProjectValidationError,
    Video,
)
from aggits_video_factory.publisher import _library_path, _valid_public_machine_path
from aggits_video_factory.site_builder import _reel_short_title, build_project_site
from aggits_video_factory.store import ProjectIdentityError, ProjectStore, slugify
from aggits_video_factory.youtube_api import YouTubeClient, clean_display_title, merge_video_selections, parse_duration


def sample_video(index: int = 1) -> Video:
    return Video(
        video_id=f"video{index:06d}",
        title=f"A Long Song Title Number {index} (Official Video)",
        display_title=f"A Long Song Title Number {index}",
        url=f"https://www.youtube.com/watch?v=video{index:06d}",
        embed_url=f"https://www.youtube.com/embed/video{index:06d}?autoplay=0",
        thumbnail_url="https://i.ytimg.com/vi/example/hqdefault.jpg",
        published_at="2026-01-01T00:00:00Z",
        duration_seconds=213,
        channel_title="Example Channel",
        channel_id="UCexample",
    )


class FactoryTests(unittest.TestCase):
    @staticmethod
    def legacy_project_value(**overrides) -> dict:
        value = {
            "schemaVersion": 2,
            "slug": "legacy-business",
            "title": "Legacy Business",
            "ticker_text": "A legacy story remains unchanged.",
            "channel_url": "https://www.youtube.com/channel/UClegacy",
            "channel_id": "UClegacy",
            "channel_title": "Legacy Channel",
            "channel_thumbnail": "https://example.test/channel.jpg",
            "source_channel_url": "https://youtube.com/@legacy",
            "manual_video_urls": ["https://youtu.be/video000001"],
            "excluded_video_ids": ["video000099"],
            "videos": [sample_video(1).to_dict()],
            "status": "published",
            "created_at": "2026-01-02T03:04:05Z",
            "updated_at": "2026-02-03T04:05:06Z",
            "published_at": "2026-02-03T04:05:06Z",
            "published_url": "https://raggedya.github.io/aggits-video-jukebox/crispy-bits/legacy-business/",
            "delivery_status": "sent",
            "publication_revision": "a" * 40,
            "future_legacy_field": {"must": "survive"},
        }
        value.update(overrides)
        return value

    def test_crispy_bits_publish_namespace_is_isolated(self):
        workspace = Path("C:/temporary/workspace")
        public_root = workspace / "public" / "crispy-bits"
        self.assertEqual(_library_path(workspace), public_root / "library.json")
        self.assertEqual(_valid_public_machine_path(public_root, "Example Machine"), public_root / "example-machine")

    def test_slug_and_title_cleaning(self):
        self.assertEqual(slugify("  Piano Black & Brass! "), "piano-black-brass")
        self.assertEqual(clean_display_title("Lost in the Static (Official Music Video)", "Band"), "Lost in the Static")
        self.assertEqual(clean_display_title("GOOD PEOPLE DOING NOTHING - THE BROWN CLOUD", "Good People Doing Nothing"), "THE BROWN CLOUD")
        self.assertEqual(clean_display_title("The Brown Cloud — Good People Doing Nothing", "Good People Doing Nothing"), "The Brown Cloud")
        self.assertEqual(parse_duration("PT3M33S"), 213)
        self.assertEqual(YouTubeClient.video_id_from_url("https://youtu.be/dQw4w9WgXcQ?t=5"), "dQw4w9WgXcQ")
        self.assertEqual(YouTubeClient.video_id_from_url("https://www.youtube.com/shorts/dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(YouTubeClient.video_id_from_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(YouTubeClient.video_id_from_url("https://example.com/watch?v=dQw4w9WgXcQ"), "")

    def test_manual_videos_take_priority_and_duplicates_are_removed(self):
        manual = [sample_video(2), sample_video(1)]
        channel = [sample_video(1), sample_video(3), sample_video(4)]
        selected = merge_video_selections(manual, channel, 3)
        self.assertEqual([video.video_id for video in selected], ["video000002", "video000001", "video000003"])

    def test_project_roundtrip_and_site_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ProjectStore(root)
            project = Project(
                slug="example",
                title="Example",
                ticker_text="A short ticker",
                channel_url="https://www.youtube.com/channel/UCexample",
                channel_id="UCexample",
                channel_title="Example Channel",
                channel_thumbnail="",
                source_channel_url="https://youtube.com/@example",
                manual_video_urls=["https://youtu.be/video000001"],
                excluded_video_ids=["video000099"],
                videos=[sample_video(1), sample_video(2), sample_video(3)],
            )
            store.save_project(project)
            restored = store.load_project("example")
            self.assertEqual(restored.videos[1].video_id, "video000002")
            self.assertEqual(restored.source_channel_url, "https://youtube.com/@example")
            self.assertEqual(restored.manual_video_urls, ["https://youtu.be/video000001"])
            self.assertEqual(restored.excluded_video_ids, ["video000099"])
            destination = root / "site"
            build_project_site(project, destination)
            payload = json.loads((destination / "machine.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["videoCount"], 3)
            self.assertEqual(payload["schemaVersion"], 2)
            self.assertEqual(payload["customerConfig"]["customerName"], "Example")
            self.assertEqual(payload["customerConfig"]["customerStory"], "A short ticker")
            self.assertEqual(payload["customerConfig"]["customerTagline"], "MORE STORIES • MORE TO DISCOVER")
            self.assertEqual(payload["customerConfig"]["customerStorySections"], [])
            self.assertEqual(payload["videos"][0]["shortTitle"], "LONG SONG TITLE NUMBER")
            self.assertEqual(payload["videos"][0]["description"], "A closer look at A Long Song Title Number 1 from Example Channel.")
            self.assertIn("Press Play Video", payload["videos"][0]["storyText"])
            script = (destination / "assets" / "video-machine.js").read_text(encoding="utf-8")
            self.assertIn("player.src = playerUrl(current)", script)
            self.assertIn("reel-actual-slotmachine-freesound-261346.mp3", script)
            self.assertIn("machine.dataset.videoOpen = 'true'", script)
            self.assertIn("await closeVideo()", script)
            self.assertIn("shopDestination = String(config.customerConfig?.shopURL || '').trim()", script)
            self.assertNotIn("sub_confirmation=1", script)
            self.assertIn("function startStoryTicker(force = false)", script)
            self.assertIn("storyTrack.style.setProperty('--story-start', `${start}px`)", script)
            self.assertIn("storyTrack.style.setProperty('--story-end', `${end}px`)", script)
            self.assertIn("function updateStory(video = null)", script)
            self.assertIn("sessionStorage.setItem('crispyBitsSound'", script)
            self.assertIn("populateSingleReel,spinSingleReel", script)
            self.assertIn("await spinSingleReel({", script)
            self.assertIn("stopAfter: reducedMotion.matches ? ARTIST_SINGLE_REEL_PROFILE.reducedMotionDuration : ARTIST_SINGLE_REEL_PROFILE.duration", script)
            self.assertIn("leverResistance(leverProgress)", script)
            self.assertIn("MUSIC_MACHINE_REEL_PROFILE.leverTrigger", script)
            self.assertIn("scheduleVideoReveal(winner)", script)
            self.assertIn("machine.dataset.revealedVideoId = openingVideoId", script)
            reel_engine = (destination / "assets" / "single-reel-engine.js").read_text(encoding="utf-8")
            mechanics = (destination / "assets" / "machine-mechanics-core.js").read_text(encoding="utf-8")
            self.assertIn("duration:2350", reel_engine)
            self.assertIn("grid-template-rows", (destination / "assets" / "video-machine.css").read_text(encoding="utf-8"))
            self.assertIn("const rowHeight=Math.max(16,reel.clientHeight/3)", reel_engine)
            self.assertIn("strip.style.transform='';renderRows(finalEntry)", reel_engine)
            self.assertIn("minimumCadence:44", mechanics)
            self.assertIn("launchCadence:124", mechanics)
            self.assertIn("decelerationRange:190", mechanics)
            self.assertIn("leverTrigger:.72", mechanics)
            video_css = (destination / "assets" / "video-machine.css").read_text(encoding="utf-8")
            self.assertIn("grid-template-rows:repeat(3,1fr)", video_css)
            self.assertIn('@keyframes storyCrawl', video_css)
            self.assertIn('.story-window{', video_css)
            self.assertIn('.reel.is-locking{animation:reelLock .2s cubic-bezier(.16,.72,.24,1)}', video_css)
            self.assertIn('@keyframes reelLock', video_css)
            self.assertIn('rotateX(-5deg)', video_css)
            self.assertIn('rotateX(5deg)', video_css)
            self.assertIn('.reel-glass', video_css)
            self.assertNotIn('.destination-plate', video_css)
            self.assertNotIn('.centre-viewing-gate', video_css)
            self.assertNotIn('.reel-card', video_css)
            self.assertIn('.music-machine[data-video-open="true"] .video-stage', video_css)
            page = (destination / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("VIDEO MUSIC MACHINE", page)
            self.assertIn("SHOP NOW", page)
            self.assertIn('data-action="shop"', page)
            self.assertNotIn('data-action="subscribe"', page)
            self.assertNotIn("OPEN<br>YOUTUBE", page)
            self.assertIn("crispy-bits-logo-cutout-v2.png", page)
            self.assertIn("data-content-description", page)
            self.assertIn("data-view-youtube", page)
            self.assertIn("data-story-window", page)
            self.assertNotIn("data-aperture-media", page)
            self.assertNotIn("data-destination-title", page)
            self.assertNotIn("THE STORY SO FAR", page)
            self.assertEqual(page.count('class="reel" data-reel="0"'), 1)
            self.assertIn('<div class="reel-strip"><span></span><strong>PULL THE LEVER  ──────→</strong><span></span></div>', page)
            self.assertIn("CRISPY BITS", page)
            self.assertTrue((destination / "assets" / "music-machine" / "aggits-cabinet-emerald-v1.png").is_file())
            self.assertTrue((destination / "assets" / "music-machine" / "crispy-bits-logo-cutout-v2.png").is_file())
            self.assertTrue((destination / "assets" / "audio" / "machine" / "reel-stop-lock-mixkit-2857.mp3").is_file())
            self.assertTrue((destination / "qr-card.png").is_file())
            self.assertTrue((destination / "social-card.jpg").is_file())

    def test_legacy_v2_migration_is_deterministic_and_does_not_invent_cta_data(self):
        legacy = self.legacy_project_value(
            subscribeURL="https://www.youtube.com/channel/UClegacy?sub_confirmation=1",
        )
        legacy["videos"][0]["legacy_video_flag"] = "keep"
        first = Project.from_dict(legacy)
        second = Project.from_dict(legacy)
        self.assertEqual(first.id, second.id)
        UUID(first.id)
        self.assertEqual(first.project_type, ProjectType.BUSINESS)
        self.assertEqual(first.additional_urls, [])
        self.assertIsNotNone(first.business_config)
        self.assertIsNone(first.business_config.shop_url)
        self.assertIsNone(first.music_config)
        self.assertEqual(first.extra_fields["subscribeURL"], "https://www.youtube.com/channel/UClegacy?sub_confirmation=1")
        self.assertEqual(first.extra_fields["future_legacy_field"], {"must": "survive"})
        self.assertEqual(first.videos[0].extra_fields["legacy_video_flag"], "keep")
        self.assertNotIn("shop_url", legacy)
        self.assertNotIn("id", legacy)

        encoded = first.to_dict()
        self.assertEqual(encoded["schemaVersion"], CURRENT_PROJECT_SCHEMA_VERSION)
        self.assertEqual(encoded["project_type"], "business")
        self.assertEqual(encoded["business_config"], {"shop_url": None})
        self.assertIsNone(encoded["music_config"])
        self.assertEqual(encoded["subscribeURL"], "https://www.youtube.com/channel/UClegacy?sub_confirmation=1")
        self.assertEqual(encoded["future_legacy_field"], {"must": "survive"})
        self.assertEqual(encoded["videos"][0]["legacy_video_flag"], "keep")
        self.assertEqual(migrate_project_dict(encoded).data, encoded)

        explicit_shop = Project.from_dict(self.legacy_project_value(shop_url="https://example.com/real-shop"))
        self.assertEqual(explicit_shop.business_config.shop_url, "https://example.com/real-shop")

    def test_legacy_load_is_non_destructive_and_first_save_creates_one_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            directory = store.project_dir("legacy-business")
            directory.mkdir(parents=True)
            source = json.dumps(self.legacy_project_value(), indent=2) + "\n"
            project_path = directory / "project.json"
            project_path.write_text(source, encoding="utf-8")

            project = store.load_project("legacy-business")
            self.assertEqual(project_path.read_text(encoding="utf-8"), source)
            self.assertFalse((directory / "project.json.v2.backup").exists())

            store.save_project(project)
            backup = directory / "project.json.v2.backup"
            self.assertEqual(backup.read_text(encoding="utf-8"), source)
            saved = json.loads(project_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["schemaVersion"], CURRENT_PROJECT_SCHEMA_VERSION)
            self.assertEqual(saved["id"], project.id)

            backup_timestamp = backup.stat().st_mtime_ns
            store.save_project(project)
            self.assertEqual(backup.stat().st_mtime_ns, backup_timestamp)

    def test_business_and_music_current_schema_round_trip(self):
        business = Project(
            slug="shop-business",
            title="Shop Business",
            ticker_text="Business story",
            channel_url="https://youtube.com/channel/UCbusiness",
            channel_id="UCbusiness",
            channel_title="Business Channel",
            channel_thumbnail="",
            additional_urls=["https://example.com/about", "https://example.com/contact"],
            business_config=BusinessConfig(shop_url="https://example.com/shop"),
            videos=[sample_video(1)],
        )
        restored_business = Project.from_dict(business.to_dict())
        self.assertEqual(restored_business.id, business.id)
        self.assertEqual(restored_business.project_type, ProjectType.BUSINESS)
        self.assertEqual(restored_business.business_config.shop_url, "https://example.com/shop")
        self.assertEqual(restored_business.additional_urls, business.additional_urls)

        music = Project(
            slug="example-band",
            title="Example Band",
            ticker_text="Band story",
            channel_url="https://youtube.com/channel/UCmusic",
            channel_id="UCmusic",
            channel_title="Example Band",
            channel_thumbnail="",
            project_type=ProjectType.MUSIC,
            music_config=MusicConfig(primary_cta=PrimaryCta(
                cta_type=PrimaryCtaType.SPOTIFY,
                destination_url="https://open.spotify.com/artist/example",
            )),
            videos=[sample_video(2)],
        )
        restored_music = Project.from_dict(music.to_dict())
        self.assertEqual(restored_music.id, music.id)
        self.assertEqual(restored_music.project_type, ProjectType.MUSIC)
        self.assertIsNone(restored_music.business_config)
        self.assertEqual(restored_music.music_config.primary_cta.display_label, "LISTEN ON SPOTIFY")
        self.assertEqual(restored_music.music_config.primary_cta.cta_type, PrimaryCtaType.SPOTIFY)

    def test_project_type_cta_and_additional_url_validation(self):
        expected_labels = {
            "spotify": "LISTEN ON SPOTIFY",
            "bandcamp": "BUY ON BANDCAMP",
            "buy_music": "BUY MUSIC",
            "merch": "BUY MERCH",
            "tickets": "GET TICKETS",
            "apple_music": "APPLE MUSIC",
            "official_website": "OFFICIAL WEBSITE",
        }
        for cta_type, label in expected_labels.items():
            with self.subTest(cta_type=cta_type):
                cta = PrimaryCta(cta_type=cta_type, destination_url="https://example.com/action")
                self.assertEqual(cta.display_label, label)
                restored = PrimaryCta.from_dict(cta.to_dict())
                self.assertEqual(restored.cta_type.value, cta_type)
                self.assertEqual(restored.display_label, label)
                self.assertEqual(restored.destination_url, "https://example.com/action")
        custom = PrimaryCta(cta_type="custom", destination_url="https://example.com/custom", custom_label="JOIN THE CLUB")
        self.assertEqual(custom.display_label, "JOIN THE CLUB")
        restored_custom = PrimaryCta.from_dict(custom.to_dict())
        self.assertEqual(restored_custom.custom_label, "JOIN THE CLUB")
        self.assertEqual(restored_custom.display_label, "JOIN THE CLUB")

        for count in range(4):
            with self.subTest(additional_url_count=count):
                urls = [f"https://source-{index}.example" for index in range(count)]
                project = Project(
                    slug=f"url-count-{count}",
                    title=f"URL Count {count}",
                    ticker_text="",
                    channel_url="",
                    channel_id="",
                    channel_title="",
                    channel_thumbnail="",
                    additional_urls=urls,
                )
                self.assertEqual(Project.from_dict(project.to_dict()).additional_urls, urls)
        with self.assertRaises(ProjectValidationError):
            Project.from_dict({**self.legacy_project_value(), "schemaVersion": 3, "id": "5bfd106b-90d2-43c3-bb84-d94a7d494826", "project_type": "unknown"})
        with self.assertRaises(ProjectMigrationError):
            migrate_project_dict({"schemaVersion": 99})
        with self.assertRaises(ProjectValidationError):
            PrimaryCta(cta_type="custom", destination_url="https://example.com", custom_label="")
        with self.assertRaises(ProjectValidationError):
            PrimaryCta(cta_type="spotify", destination_url="not-a-url")
        with self.assertRaises(ProjectValidationError):
            Project(
                slug="too-many-urls",
                title="Too Many URLs",
                ticker_text="",
                channel_url="",
                channel_id="",
                channel_title="",
                channel_thumbnail="",
                additional_urls=["https://one.example", "https://two.example", "https://three.example", "https://four.example"],
            )

    def test_slug_allocation_is_collision_safe_and_existing_identity_is_stable(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            first = Project(
                slug=store.allocate_slug("Great Alpine Caravans"),
                title="Great Alpine Caravans",
                ticker_text="",
                channel_url="",
                channel_id="",
                channel_title="",
                channel_thumbnail="",
            )
            store.save_project(first)
            self.assertEqual(first.slug, "great-alpine-caravans")
            self.assertEqual(store.allocate_slug("Great Alpine Caravans"), "great-alpine-caravans-2")
            second_directory = store.project_dir("great-alpine-caravans-2")
            second_directory.mkdir(parents=True)
            self.assertEqual(store.allocate_slug("Great Alpine Caravans"), "great-alpine-caravans-3")

            original_id = first.id
            original_slug = first.slug
            first.title = "Renamed Great Alpine"
            first.status = "unpublished"
            store.save_project(first)
            restored = store.load_project(original_slug)
            self.assertEqual(restored.id, original_id)
            self.assertEqual(restored.slug, original_slug)

            with self.assertRaises(ProjectValidationError):
                restored.id = "8b566385-c09e-4ab7-899b-caffb853f5a7"
            self.assertEqual(store.load_project(original_slug).id, original_id)

            replacement = Project.from_dict(restored.to_dict())
            object.__setattr__(replacement, "id", "8b566385-c09e-4ab7-899b-caffb853f5a7")
            with self.assertRaises(ProjectIdentityError):
                store.save_project(replacement)
            self.assertEqual(store.load_project(original_slug).id, original_id)

    def test_migration_diagnostics_do_not_overwrite_invalid_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            valid = Project(
                slug="valid",
                title="Valid",
                ticker_text="",
                channel_url="",
                channel_id="",
                channel_title="",
                channel_thumbnail="",
            )
            store.save_project(valid)
            broken_dir = store.project_dir("broken")
            broken_dir.mkdir(parents=True)
            broken_path = broken_dir / "project.json"
            broken_source = json.dumps({"schemaVersion": 99, "slug": "broken"})
            broken_path.write_text(broken_source, encoding="utf-8")

            projects = store.list_projects()
            self.assertEqual([project.slug for project in projects], ["valid"])
            self.assertEqual(len(store.last_load_errors), 1)
            self.assertIn("Unsupported project schema version", store.last_load_errors[0].message)
            self.assertEqual(broken_path.read_text(encoding="utf-8"), broken_source)

    def test_legacy_business_site_output_schema_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            legacy_project = Project.from_dict(self.legacy_project_value())
            current_project = Project.from_dict(legacy_project.to_dict())
            legacy_destination = Path(temporary) / "legacy-site"
            current_destination = Path(temporary) / "current-site"
            build_project_site(legacy_project, legacy_destination)
            build_project_site(current_project, current_destination)
            payload = json.loads((legacy_destination / "machine.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["schemaVersion"], 2)
            self.assertNotIn("id", payload)
            self.assertNotIn("project_type", payload)
            self.assertNotIn("business_config", payload)
            self.assertEqual(payload["slug"], "legacy-business")
            self.assertEqual(payload["customerConfig"]["subscribeURL"], "https://www.youtube.com/channel/UClegacy?sub_confirmation=1")
            self.assertIsNone(payload["customerConfig"]["shopURL"])
            self.assertFalse(payload["customerConfig"]["shopEnabled"])

            def snapshot(root: Path) -> dict[str, bytes]:
                return {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in sorted(root.rglob("*"))
                    if path.is_file()
                }

            self.assertEqual(snapshot(legacy_destination), snapshot(current_destination))

    @unittest.skipUnless(os.environ.get("LOCALAPPDATA"), "Windows LocalAppData is unavailable")
    def test_real_great_alpine_v2_project_migrates_from_safe_copy(self):
        protected_source = Path(os.environ["LOCALAPPDATA"]) / "CRISPY BITS" / "Video Jukebox Factory" / "projects" / "great-alpine-caravans" / "project.json"
        if not protected_source.is_file():
            self.skipTest("The protected Great Alpine v2.3.0 project is not present on this machine.")
        protected_bytes = protected_source.read_bytes()
        protected_payload = json.loads(protected_bytes.decode("utf-8"))
        source = protected_source
        if int(protected_payload.get("schemaVersion", 2)) != 2:
            source = protected_source.with_name("project.json.v2.backup")
            if not source.is_file():
                self.skipTest("The protected Great Alpine v2 migration backup is not present on this machine.")
        original_bytes = source.read_bytes()
        legacy = json.loads(original_bytes.decode("utf-8"))
        self.assertEqual(int(legacy.get("schemaVersion", 2)), 2)

        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            copied_dir = store.project_dir("great-alpine-caravans")
            copied_dir.mkdir(parents=True)
            copied_path = copied_dir / "project.json"
            copied_path.write_bytes(original_bytes)
            migrated = store.load_project("great-alpine-caravans")

            self.assertEqual(migrated.title, legacy["title"])
            self.assertEqual(migrated.slug, "great-alpine-caravans")
            self.assertEqual(migrated.published_url, legacy.get("published_url"))
            self.assertEqual(len(migrated.videos), 30)
            self.assertEqual(migrated.excluded_video_ids, legacy.get("excluded_video_ids", []))
            self.assertEqual(migrated.channel_id, legacy["channel_id"])
            self.assertEqual(migrated.ticker_text, legacy["ticker_text"])
            self.assertEqual(migrated.status, legacy["status"])
            self.assertEqual(migrated.publication_revision, legacy.get("publication_revision"))
            self.assertEqual(migrated.delivery_status, legacy["delivery_status"])
            self.assertEqual(migrated.project_type, ProjectType.BUSINESS)
            self.assertEqual(migrated.additional_urls, [])
            self.assertIsNone(migrated.business_config.shop_url)
            self.assertIsNone(migrated.music_config)
            UUID(migrated.id)
            self.assertEqual(source.read_bytes(), original_bytes)
            self.assertEqual(protected_source.read_bytes(), protected_bytes)

            store.save_project(migrated)
            self.assertEqual((copied_dir / "project.json.v2.backup").read_bytes(), original_bytes)
            saved = json.loads(copied_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["schemaVersion"], CURRENT_PROJECT_SCHEMA_VERSION)
            self.assertEqual(saved["published_url"], legacy.get("published_url"))
            self.assertEqual(len(saved["videos"]), 30)

    def test_catalogue_filters_and_limits(self):
        client = YouTubeClient("test-key")
        channel = {
            "id": "UCexample",
            "snippet": {"title": "Example", "thumbnails": {}},
            "contentDetails": {"relatedPlaylists": {"uploads": "UUexample"}},
        }
        playlist = {"items": [{"contentDetails": {"videoId": f"id{index:03d}"}} for index in range(35)]}
        details = {"items": [
            {
                "id": f"id{index:03d}",
                "status": {"privacyStatus": "public", "embeddable": True},
                "snippet": {"title": f"Video {index}", "channelTitle": "Example", "liveBroadcastContent": "none", "thumbnails": {"high": {"url": "https://example.test/x.jpg", "width": 480, "height": 360}}},
                "contentDetails": {"duration": "PT3M"},
            }
            for index in range(35)
        ]}
        with patch.object(client, "resolve_channel", return_value=channel), patch.object(client, "_get", side_effect=[playlist, details]):
            catalogue = client.fetch_catalogue("https://youtube.com/@example")
        self.assertEqual(len(catalogue.videos), 30)
        self.assertTrue(all("autoplay=0" in item.embed_url for item in catalogue.videos))

    def test_reel_short_titles_are_compact_and_editorial(self):
        self.assertEqual(_reel_short_title("2024 - Build 20.6 FT Two Person"), "20.6 FT COUPLES")
        self.assertEqual(_reel_short_title("Meet the Great Alpine 19.6 FT Tripple Bunk Van"), "19.6 FT TRIPLE BUNK")
        self.assertEqual(_reel_short_title("Toy hauler with CRUISEMASTER ATX 4.5 T"), "TOY HAULER")
        self.assertEqual(_reel_short_title("20 6 ft two person"), "20.6 FT COUPLES")
        self.assertEqual(_reel_short_title("17.10 Family double bunk"), "17.10 FT DOUBLE BUNK")
        self.assertEqual(_reel_short_title("Check out the 2024 Build 23ft Club Lounge Caravan"), "23 FT CLUB LOUNGE")

    def test_individual_video_catalogue(self):
        client = YouTubeClient("test-key")
        details = {"items": [{
            "id": "dQw4w9WgXcQ",
            "status": {"privacyStatus": "public", "embeddable": True},
            "snippet": {"title": "Example Clip", "channelTitle": "Example Channel", "channelId": "UCexample", "liveBroadcastContent": "none", "thumbnails": {}},
            "contentDetails": {"duration": "PT4M"},
        }]}
        with patch.object(client, "_get", return_value=details):
            catalogue = client.fetch_videos(["https://youtu.be/dQw4w9WgXcQ"])
        self.assertEqual(catalogue.channel_title, "Example Channel")
        self.assertEqual(catalogue.channel_url, "https://www.youtube.com/channel/UCexample")
        self.assertEqual(catalogue.videos[0].video_id, "dQw4w9WgXcQ")


if __name__ == "__main__":
    unittest.main()
