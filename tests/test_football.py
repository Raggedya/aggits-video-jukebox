import json
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image

from aggits_video_factory.football import FootballConfig, import_logo, club_records, import_club_logos, select_club_project
from aggits_video_factory.models import Project, ProjectType
from aggits_video_factory.desktop_forms import ProjectFormValues, validate_project_form, project_to_form_values
from aggits_video_factory.business_workflow import assemble_reviewed_project
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.diagnostics import close_logging
from aggits_video_factory.youtube_api import ChannelCatalogue
from test_channel_master_workflow import video, master_project


def football_project(count=3):
    return Project(slug="football-fixture", title="North Melbourne", ticker_text="TEST FIXTURE — NOT CLUB CONTENT",
        channel_url="", channel_id="", channel_title="Test fixture", channel_thumbnail="",
        project_type=ProjectType.FOOTBALL,
        football_config=FootballConfig(cta_url="https://example.com/club", cta_label="Visit club"),
        videos=[video(index) for index in range(count)])


class FootballTests(unittest.TestCase):
    def test_logo_layout_preserves_artwork_and_packages_padding_metadata(self):
        from aggits_video_factory.football import logo_layout
        from PIL import ImageDraw
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for mode, colour in (("RGBA", (0,0,0,0)), ("RGB", (0,30,80))):
                source = root / f"{mode}.png"
                image = Image.new(mode, (512,512), colour)
                ImageDraw.Draw(image).rectangle((98,148,413,363), fill="white")
                image.save(source)
                original = source.read_bytes()
                self.assertEqual(logo_layout(source)["bounds"], [96,146,320,220])
                project = football_project()
                project.football_config.logo_asset = import_logo(str(source), root)
                build_project_site(project, root / "site")
                club = json.loads((root / "site/machine.json").read_text())["footballConfig"]["clubs"][0]
                self.assertEqual(club["logoLayout"]["bounds"], [96,146,320,220])
                self.assertEqual((root / "site" / club["logo"]).read_bytes(), original)
            ImageDraw.Draw(image).point((0,1), fill="white")
            image.save(source)
            self.assertEqual(logo_layout(source)["bounds"], [0,0,512,512])

    def test_membership_url_persistence_validation_and_editor(self):
        self.assertEqual(FootballConfig.from_dict({}).membership_url, "")
        for invalid in ("javascript:alert(1)", "//example.com", "https://user:pass@example.com", "https://bad host/", "https://example.com:bad"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                FootballConfig(membership_url=invalid)
        first, second = football_project(), football_project()
        second.football_config.club_id = "second-test"
        first.football_config.membership_url = "https://example.com/member-a"
        second.football_config.membership_url = "https://example.com/member-b"
        first.football_config.clubs = club_records(first) + club_records(second)
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            store.save_project(first)
            restored = store.load_project(first.slug)
            output = store.project_dir(first.slug) / "site"
            build_project_site(restored, output)
            clubs = json.loads((output / "machine.json").read_text())["footballConfig"]["clubs"]
            self.assertEqual([c["membershipUrl"] for c in clubs], ["https://example.com/member-a", "https://example.com/member-b"])
            self.assertEqual(restored.football_config.cta_url, first.football_config.cta_url)
            from desktop.video_jukebox_factory import Factory
            with patch("desktop.video_jukebox_factory.application_data_root", return_value=Path(temporary)):
                app = Factory()
                app.withdraw()
                try:
                    form = app.forms[ProjectType.FOOTBALL]
                    form.load_project(restored)
                    self.assertIn("membership_url", form.field_widgets)
                    self.assertEqual(form.football_vars["membership_url"].get(), "https://example.com/member-a")
                    form.football_vars["membership_url"].set("https://example.com/edited")
                    self.assertEqual(form._football_capture()["settings"]["membership_url"], "https://example.com/edited")
                finally:
                    app.destroy()
                    close_logging(app.store.root)

    def test_reviewing_second_club_does_not_replace_first_catalogue(self):
        project = football_project(3)
        other = football_project(2)
        other.title = "SECOND TEST CLUB"
        other.football_config.club_id = "second-test"
        other.videos = [video(10), video(11)]
        project.football_config.clubs = club_records(project) + club_records(other)
        selected = select_club_project(project, club_records(project)[1])
        values = validate_project_form(project_to_form_values(selected), ProjectType.FOOTBALL)
        revised = assemble_reviewed_project(project_type=ProjectType.FOOTBALL, values=values,
            catalogue=ChannelCatalogue("fixture", "Test", "", "", other.videos),
            selected_videos=other.videos[:1], reviewed_videos=other.videos,
            source_results=[], slug=project.slug, existing=selected)
        restored = Project.from_dict(revised.to_dict())
        records = club_records(restored)
        self.assertEqual(records[0]["videos"], club_records(project)[0]["videos"])
        self.assertEqual(records[0]["excluded_video_ids"], [])
        self.assertEqual(records[1]["excluded_video_ids"], [video(11).video_id])
        self.assertEqual(restored.id, project.id)

    def test_roster_assets_catalogues_and_selected_club_persist(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ProjectStore(root)
            project = football_project()
            other = football_project()
            other.title = "TEST ONLY SECOND CLUB"
            other.football_config = FootballConfig(club_id="test-second", base_colour="#112233",
                primary_colour="#445566", highlight_colour="#778899", cta_label="Test CTA", cta_url="https://example.com/second")
            other.ticker_text = "SECOND TEST TICKER"
            other.source_channel_url = "https://www.youtube.com/@test-fixture"
            other.videos = [video(10), video(11)]
            for index, club in enumerate((project, other)):
                source = root / f"test-{index}.png"
                Image.new("RGB", (4, 4), (index * 100, 20, 40)).save(source)
                club.football_config.logo_asset = str(source)
            project.football_config.clubs = club_records(project) + club_records(other)
            directory = store.project_dir(project.slug)
            import_club_logos(project, directory)
            store.save_project(project)
            restored = store.load_project(project.slug)
            records = club_records(restored)
            self.assertEqual(len(records), 2)
            self.assertNotEqual(records[0]["settings"]["logo_asset"], records[1]["settings"]["logo_asset"])
            selected = select_club_project(restored, records[1])
            self.assertEqual(selected.videos[0].video_id, video(10).video_id)
            selected.football_config.primary_colour = "#ABCDEF"
            store.save_project(selected)
            again = store.load_project(project.slug)
            self.assertEqual(again.id, project.id)
            self.assertEqual(club_records(again)[0]["settings"]["primary_colour"], "#005EB8")
            self.assertEqual(club_records(again)[1]["settings"]["primary_colour"], "#ABCDEF")
            build_project_site(again, directory / "site")
            clubs = json.loads((directory / "site/machine.json").read_text())["footballConfig"]["clubs"]
            self.assertEqual(len(clubs), 2)
            self.assertEqual(clubs[1]["primaryColour"], "#ABCDEF")
            self.assertFalse({v["videoId"] for v in clubs[0]["videos"]} & {v["videoId"] for v in clubs[1]["videos"]})
            for club in clubs:
                self.assertTrue((directory / "site" / club["logo"]).is_file())

    def test_desktop_picker_add_eighteen_remove_and_save_reload(self):
        from desktop.video_jukebox_factory import Factory
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            with patch("desktop.video_jukebox_factory.ProjectStore", return_value=store):
                app = Factory()
            app.withdraw()
            try:
                form = app.forms[ProjectType.FOOTBALL]
                with patch("desktop.video_jukebox_factory.colorchooser.askcolor", return_value=((18, 52, 86), "#123456")) as chooser:
                    form.football_swatches["base_colour"].invoke()
                    chooser.assert_called_once()
                self.assertEqual(form.football_vars["base_colour"].get(), "#123456")
                self.assertEqual(form.football_swatches["base_colour"].cget("background"), "#123456")
                for key, chosen in (("primary_colour", "#234567"), ("highlight_colour", "#ABCDEF")):
                    with patch("desktop.video_jukebox_factory.colorchooser.askcolor", return_value=((0, 0, 0), chosen)):
                        form.football_swatches[key].invoke()
                    self.assertEqual(form.football_vars[key].get(), chosen)
                    self.assertEqual(form.football_swatches[key].cget("background"), chosen)
                with patch("desktop.video_jukebox_factory.colorchooser.askcolor", return_value=(None, None)):
                    form.football_swatches["base_colour"].invoke()
                self.assertEqual(form.football_vars["base_colour"].get(), "#123456")
                for index in range(17):
                    form._football_add()
                    form.title_var.set(f"TEST ONLY CLUB {index + 2}")
                self.assertEqual(len(form.football_records), 18)
                with patch("desktop.video_jukebox_factory.messagebox.showinfo") as limit:
                    form._football_add()
                    self.assertIn("18", limit.call_args.args[1])
                self.assertEqual(len(form.football_records), 18)
                form.football_vars["base_colour"].set("#654321")
                with patch.object(app, "_open_project_preview"), patch("desktop.video_jukebox_factory.messagebox.showinfo"), patch("desktop.video_jukebox_factory.messagebox.showerror") as errors:
                    self.assertTrue(app._save_football())
                    errors.assert_not_called()
                saved = next(iter(app.projects.values()))
                restored = store.load_project(saved.slug)
                self.assertEqual(len(club_records(restored)), 18)
                self.assertEqual(club_records(restored)[0]["settings"]["base_colour"], "#123456")
                self.assertEqual(club_records(restored)[0]["settings"]["primary_colour"], "#234567")
                self.assertEqual(club_records(restored)[0]["settings"]["highlight_colour"], "#ABCDEF")
                self.assertEqual(club_records(restored)[-1]["settings"]["base_colour"], "#654321")
                data = json.loads((store.project_dir(saved.slug) / "site/machine.json").read_text())
                self.assertEqual(len(data["footballConfig"]["clubs"]), 18)
                form.load_project(restored)
                form.football_list.selection_clear(0, "end")
                form.football_list.selection_set(0)
                form._football_select()
                self.assertEqual(form.football_vars["base_colour"].get(), "#123456")
                with patch("desktop.video_jukebox_factory.messagebox.askyesno", return_value=True):
                    form._football_remove()
                self.assertEqual(len(form.football_records), 17)
                form.restore_baseline()
                self.assertEqual(len(form.football_records), 18)
            finally:
                app.preview_server.stop()
                if app._async_poll_id:
                    app.after_cancel(app._async_poll_id)
                app.destroy()
                close_logging(store.root)

    def test_roster_limit_and_duplicate_ids_rejected(self):
        project = football_project(0)
        record = club_records(project)[0]
        from copy import deepcopy
        records = []
        for index in range(19):
            item = deepcopy(record)
            item["settings"]["club_id"] = f"test-{index}"
            records.append(item)
        with self.assertRaisesRegex(ValueError, "18"):
            FootballConfig(club_id="test-0", clubs=records)
        with self.assertRaisesRegex(ValueError, "unique"):
            FootballConfig(clubs=[record, record])

    def test_separate_club_projects_round_trip_without_settings_leakage(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            first, second = football_project(), football_project()
            second.slug = "isolation-test-only"
            second.title = "ISOLATION TEST — NOT AN AFL CLUB"
            second.ticker_text = "SECOND TEST TICKER"
            second.football_config = FootballConfig(club_id="isolation-test-only",
                base_colour="#201020", primary_colour="#703050", highlight_colour="#FFD080",
                cta_label="Test destination", cta_url="https://example.com/football-test")
            second.videos = [video(index) for index in range(10, 13)]
            for project in [first, second]:
                store.save_project(project)
            for project in [first, second, first]:
                restored = ProjectStore(Path(temporary)).load_project(project.slug)
                self.assertEqual(restored.football_config.to_dict(), project.football_config.to_dict())
                self.assertEqual(restored.ticker_text, project.ticker_text)
                self.assertEqual([v.video_id for v in restored.videos], [v.video_id for v in project.videos])

    def test_two_club_fixture_is_separate_from_normal_output(self):
        from tools.create_football_preview import create_two_club_preview
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = create_two_club_preview(root / "qa")
            first, second = data["footballConfig"]["clubs"]
            self.assertTrue(data["testOnly"])
            self.assertNotEqual(first["id"], second["id"])
            self.assertFalse(set(v["videoId"] for v in first["videos"]) & set(v["videoId"] for v in second["videos"]))
            for key in ("ticker", "ctaLabel", "ctaUrl", "baseColour", "primaryColour", "highlightColour"):
                self.assertNotEqual(first[key], second[key])
            build_project_site(football_project(), root / "normal")
            normal = json.loads((root / "normal/machine.json").read_text())
            self.assertEqual(len(normal["footballConfig"]["clubs"]), 1)
            self.assertNotIn("testOnly", normal)
            self.assertFalse((root / "normal/fixture-only.js").exists())

    def test_save_reload_and_no_migration(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            project = football_project()
            store.save_project(project)
            restored = ProjectStore(Path(temporary)).load_project(project.slug)
            self.assertEqual(restored.football_config.to_dict(), project.football_config.to_dict())
            self.assertEqual(restored.id, project.id)
            self.assertEqual(restored.ticker_text, project.ticker_text)
            self.assertEqual(restored.to_dict()["schemaVersion"], 3)
            self.assertNotIn("football_config", restored.extra_fields)
            self.assertEqual(Project.from_dict(master_project().to_dict()).football_config, None)

    def test_logo_is_project_owned_and_packaged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = football_project()
            source = root / "supplied.png"
            Image.new("RGBA", (64, 64), (0, 70, 140, 255)).save(source)
            project.football_config.logo_asset = import_logo(str(source), root)
            source.unlink()
            ProjectStore(root).save_project(project)
            build_project_site(project, root / "site")
            data = json.loads((root / "site/machine.json").read_text())
            logo = data["footballConfig"]["clubs"][0]["logo"]
            self.assertTrue((root / "site" / logo).is_file())
            self.assertNotIn(str(root), json.dumps(data))

    def test_logo_validation_and_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = root / "fake.png"
            fake.write_text("not an image")
            with self.assertRaises(ValueError):
                import_logo(str(fake), root)
            with self.assertRaises(ValueError):
                import_logo("../other.png", root)

    def test_generated_club_data_and_empty_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = football_project(0)
            build_project_site(project, Path(temporary) / "site")
            data = json.loads((Path(temporary) / "site/machine.json").read_text(encoding="utf-8"))
            club = data["footballConfig"]["clubs"][0]
            self.assertEqual(club["id"], "north-melbourne")
            self.assertEqual(club["videos"], [])
            self.assertEqual(club["logo"], "")
            self.assertEqual(club["ticker"], project.ticker_text)
            self.assertEqual(club["ctaUrl"], "https://example.com/club")
            self.assertNotIn("channelMasterConfig", data)

    def test_form_roundtrip_and_review_assembly(self):
        original = football_project()
        values = validate_project_form(project_to_form_values(original), ProjectType.FOOTBALL)
        catalogue = ChannelCatalogue("fixture", "Fixture", "", "", original.videos)
        revised = assemble_reviewed_project(project_type=ProjectType.FOOTBALL, values=values, catalogue=catalogue,
            selected_videos=original.videos[:2], reviewed_videos=original.videos, source_results=[], slug=original.slug, existing=original)
        self.assertEqual(revised.id, original.id)
        self.assertEqual(revised.football_config.to_dict(), original.football_config.to_dict())
        self.assertEqual(revised.excluded_video_ids, [original.videos[2].video_id])
        values.football_config.club_id = "changed-id"
        with self.assertRaises(ValueError):
            assemble_reviewed_project(project_type=ProjectType.FOOTBALL, values=values, catalogue=catalogue,
                selected_videos=[], reviewed_videos=[], source_results=[], slug=original.slug, existing=original)

    def test_colour_and_cta_validation(self):
        with self.assertRaises(ValueError):
            FootballConfig(base_colour="red; color:black")
        with self.assertRaises(ValueError):
            FootballConfig(cta_url="javascript:alert(1)")
        self.assertIsNone(football_project().channel_master_config)

    def test_catalogue_limit_and_legacy_video_editor(self):
        from aggits_video_factory.video_editor import VideoSelectionSession
        project = football_project(50)
        with self.assertRaises(ValueError):
            football_project(51)
        session = VideoSelectionSession(project)
        self.assertEqual(len(session.videos), 50)
        self.assertEqual(session.revised_project().football_config.club_id, "north-melbourne")

    def test_empty_draft_roundtrip_preserves_label_without_url(self):
        project = football_project(0)
        project.football_config.cta_url = ""
        project.football_config.cta_label = "Shop now"
        values = validate_project_form(project_to_form_values(project), ProjectType.FOOTBALL)
        self.assertEqual(values.football_config.cta_label, "Shop now")

    def test_desktop_save_real_asset_without_network(self):
        from desktop.video_jukebox_factory import Factory
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            source = Path(temporary) / "operator.png"
            Image.new("RGB", (60, 60), "blue").save(source)
            with patch("desktop.video_jukebox_factory.ProjectStore", return_value=store):
                app = Factory()
            app.withdraw()
            try:
                form = app.forms[ProjectType.FOOTBALL]
                form.football_vars["logo_asset"].set(str(source))
                with patch.object(app, "_open_project_preview"), patch("desktop.video_jukebox_factory.messagebox.showinfo"), patch("desktop.video_jukebox_factory.messagebox.showerror") as errors:
                    self.assertTrue(app._save_football())
                    errors.assert_not_called()
                saved = store.load_project("north-melbourne")
                self.assertEqual(saved.football_config.club_id, "north-melbourne")
                self.assertTrue((store.project_dir(saved.slug) / saved.football_config.logo_asset).is_file())
                source.unlink()
                form.load_project(saved)
                self.assertEqual(form.values().football_config.logo_asset, saved.football_config.logo_asset)
                form.football_vars["logo_asset"].set("")
                with patch.object(app, "_open_project_preview"), patch("desktop.video_jukebox_factory.messagebox.showinfo"):
                    self.assertTrue(app._save_football())
                self.assertEqual(store.load_project(saved.slug).football_config.logo_asset, "")
            finally:
                app.preview_server.stop()
                if app._async_poll_id:
                    app.after_cancel(app._async_poll_id)
                app.destroy()
                close_logging(store.root)
                del form, app
                import gc
                gc.collect()

    def test_desktop_fields_and_layout(self):
        from desktop.video_jukebox_factory import ProjectForm
        root = tk.Tk()
        root.withdraw()
        try:
            form = ProjectForm(root, ProjectType.FOOTBALL, lambda: None, lambda: None)
            form.pack(fill="both", expand=True)
            form.load_project(football_project())
            self.assertEqual(form.values().football_config.club_id, "north-melbourne")
            self.assertEqual(form.field_widgets["club_id"].cget("state"), "readonly")
            for size in ("1320x820", "1120x720"):
                root.geometry(size)
                root.update()
                self.assertIn("football_logo", form.field_widgets)
            form.football_vars["base_colour"].set("bad")
            self.assertTrue(form.is_dirty())
        finally:
            root.destroy()

    def test_existing_output_not_opted_in(self):
        with tempfile.TemporaryDirectory() as temporary:
            build_project_site(master_project(), Path(temporary))
            data = json.loads((Path(temporary) / "machine.json").read_text())
            self.assertNotIn("footballConfig", data)
            self.assertNotIn("data-football-grid", (Path(temporary) / "index.html").read_text())
