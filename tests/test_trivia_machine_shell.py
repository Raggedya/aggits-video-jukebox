from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRIVIA = ROOT / "crispy-bits" / "trivia-machine"


def test_trivia_machine_is_an_independent_static_application() -> None:
    required = {
        "index.html",
        "data/trivia-data.json",
        "assets/trivia-machine.css",
        "assets/trivia-machine.js",
        "assets/video-machine.css",
        "assets/single-reel-engine.js",
        "assets/machine-mechanics-core.js",
        "assets/music-machine/aggits-reel-v2.webp",
        "assets/music-machine/aggits-lever.webp",
    }
    assert all((TRIVIA / relative).is_file() for relative in required)


def test_proven_spin_and_mechanics_modules_are_byte_identical_copies() -> None:
    for filename in ("single-reel-engine.js", "machine-mechanics-core.js"):
        assert (TRIVIA / "assets" / filename).read_bytes() == (ROOT / "static" / filename).read_bytes()


def test_trivia_content_is_external_and_contains_no_question_system() -> None:
    data = json.loads((TRIVIA / "data" / "trivia-data.json").read_text(encoding="utf-8"))
    assert data["machine"]["title"] == "CRISPY BITS TRIVIA"
    assert len(data["reelEntries"]) >= 3
    assert all({"id", "label", "stageTitle", "stageCopy"} <= entry.keys() for entry in data["reelEntries"])
    assert "questions" not in data


def test_controller_reuses_spin_engine_landing_and_lever_mechanics() -> None:
    script = (TRIVIA / "assets" / "trivia-machine.js").read_text(encoding="utf-8")
    assert "spinSingleReel({" in script
    assert "leverResistance(progress)" in script
    assert "MUSIC_MACHINE_REEL_PROFILE.leverTrigger" in script
    assert "showLanding(winner)" in script
    assert "scheduleStageReveal(entry)" in script
    assert "data/trivia-data.json" in script
    assert "[data-action=\"spin-again\"]" in script


def test_shell_has_expected_framework_without_trivia_questions() -> None:
    html = (TRIVIA / "index.html").read_text(encoding="utf-8")
    assert "CRISPY BITS TRIVIA" in html
    assert 'data-project-type="trivia"' in html
    assert 'data-reel="0"' in html
    assert 'class="lever"' in html
    assert 'data-video-stage' in html
    assert 'data-action="spin-again"' in html
    assert "TRIVIA SOON" in html
    assert "question-card" not in html


def test_trivia_styles_are_explicitly_scoped() -> None:
    css = (TRIVIA / "assets" / "trivia-machine.css").read_text(encoding="utf-8")
    assert '@import url("./video-machine.css")' in css
    assert css.count('[data-project-type="trivia"]') >= 20
    assert '[data-project-type="banjo"]' not in css
    assert '[data-project-type="channel_master"]' not in css
