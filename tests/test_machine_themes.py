from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aggits_video_factory.desktop_forms import (
    DEFAULT_CTA_LABEL_BY_PROJECT,
    MACHINE_THEME_CHOICES,
    ProjectFormValues,
    project_to_form_values,
    validate_project_form,
)
from aggits_video_factory.models import MachineTheme, Project, ProjectType, ProjectValidationError
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore
from tests.test_machine_brand_hierarchy import project_for


ROOT = Path(__file__).parents[1]
STYLES = (ROOT / "static" / "video-machine.css").read_text(encoding="utf-8")
TEMPLATE = (ROOT / "templates" / "machine.html").read_text(encoding="utf-8")
DESKTOP = (ROOT / "desktop" / "video_jukebox_factory.py").read_text(encoding="utf-8")


class MachineThemeTests(unittest.TestCase):
    def test_classic_is_backward_compatible_default_and_candy_round_trips(self):
        project = project_for(ProjectType.BUSINESS)
        self.assertIs(project.machine_theme, MachineTheme.CLASSIC)

        legacy = project.to_dict()
        legacy.pop("machine_theme")
        restored_legacy = Project.from_dict(legacy)
        self.assertIs(restored_legacy.machine_theme, MachineTheme.CLASSIC)

        project.machine_theme = MachineTheme.CANDY
        restored_candy = Project.from_dict(project.to_dict())
        self.assertIs(restored_candy.machine_theme, MachineTheme.CANDY)
        self.assertEqual(restored_candy.id, project.id)
        self.assertEqual(restored_candy.slug, project.slug)
        self.assertEqual(restored_candy.project_type, project.project_type)

        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            store.save_project(project)
            stored_candy = store.load_project(project.slug)
            self.assertIs(stored_candy.machine_theme, MachineTheme.CANDY)
            self.assertEqual(stored_candy.id, project.id)

        invalid = project.to_dict()
        invalid["machine_theme"] = "unknown"
        with self.assertRaisesRegex(ProjectValidationError, "Unsupported machine theme"):
            Project.from_dict(invalid)

    def test_shared_form_choices_validate_for_every_project_type(self):
        self.assertEqual(MACHINE_THEME_CHOICES, (
            ("Classic", MachineTheme.CLASSIC),
            ("Candy", MachineTheme.CANDY),
        ))
        for project_type in ProjectType:
            with self.subTest(project_type=project_type.value):
                validated = validate_project_form(ProjectFormValues(
                    title=f"{project_type.value} candy fixture",
                    machine_theme="Candy",
                    channel_url="https://www.youtube.com/channel/UCthemefixture",
                    cta_label=DEFAULT_CTA_LABEL_BY_PROJECT[project_type],
                ), project_type)
                self.assertIs(validated.machine_theme, MachineTheme.CANDY)

                project = project_for(project_type)
                project.machine_theme = MachineTheme.CANDY
                self.assertEqual(project_to_form_values(project).machine_theme, "Candy")

    def test_desktop_exposes_one_shared_machine_theme_dropdown(self):
        self.assertIn('text="Machine Theme"', DESKTOP)
        self.assertIn("values=[label for label, _ in MACHINE_THEME_CHOICES]", DESKTOP)
        self.assertIn('state="readonly"', DESKTOP)
        self.assertIn('self.field_widgets["machine_theme"] = self.theme_combo', DESKTOP)

    def test_all_project_types_generate_the_same_candy_theme_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for project_type in ProjectType:
                with self.subTest(project_type=project_type.value):
                    project = project_for(project_type)
                    project.machine_theme = MachineTheme.CANDY
                    destination = root / project_type.value
                    build_project_site(project, destination)
                    page = (destination / "index.html").read_text(encoding="utf-8")
                    payload = json.loads((destination / "machine.json").read_text(encoding="utf-8"))

                    self.assertIn('data-machine-theme="candy"', page)
                    self.assertIn('<meta name="theme-color" content="#b20b55">', page)
                    self.assertEqual(payload["machineTheme"], "candy")
                    self.assertEqual(payload["customerConfig"]["customerTheme"], "candy")
                    self.assertEqual(page.count('class="reel-bank"'), 1)
                    self.assertEqual(page.count('class="lever"'), 1)
                    self.assertEqual(page.count('class="machine-controls"'), 1)
                    self.assertEqual(page.count('class="customer-story"'), 1)

    def test_classic_generation_remains_the_default(self):
        self.assertIn('data-machine-theme="{{MACHINE_THEME}}"', TEMPLATE)
        with tempfile.TemporaryDirectory() as temporary:
            project = project_for(ProjectType.MUSIC)
            destination = Path(temporary) / "classic"
            build_project_site(project, destination)
            page = (destination / "index.html").read_text(encoding="utf-8")
            payload = json.loads((destination / "machine.json").read_text(encoding="utf-8"))
            self.assertIn('data-machine-theme="classic"', page)
            self.assertIn('<meta name="theme-color" content="#061712">', page)
            self.assertEqual(payload["machineTheme"], "classic")

    def test_candy_skin_is_css_only_scoped_and_uses_shared_tokens(self):
        self.assertIn('.music-machine[data-machine-theme="candy"]{', STYLES)
        for token in (
            "--candy-cream:#fff4e8",
            "--candy-pink:#f02c82",
            "--candy-cyan:#18bfc7",
            "--candy-orange:#f59a16",
            "--candy-yellow:#ffd65c",
        ):
            self.assertIn(token, STYLES)
        for component in (
            ".customer-identity",
            ".reel-bank",
            ".reel",
            ".lever img",
            ".video-stage-frame",
            ".content-card",
            ".machine-controls",
            ".customer-story",
        ):
            self.assertIn(f'.music-machine[data-machine-theme="candy"] {component}', STYLES)
        self.assertNotIn("url(\"candy", STYLES)


if __name__ == "__main__":
    unittest.main()
