from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRIVIA = ROOT / "crispy-bits" / "trivia-machine"
DATA = json.loads((TRIVIA / "data" / "trivia-data.json").read_text(encoding="utf-8"))
HTML = (TRIVIA / "index.html").read_text(encoding="utf-8")
SCRIPT = (TRIVIA / "assets" / "trivia-machine.js").read_text(encoding="utf-8")
VALIDATOR = (TRIVIA / "assets" / "trivia-data-validator.js").read_text(encoding="utf-8")
ROTATION = (TRIVIA / "assets" / "trivia-content-rotation.js").read_text(encoding="utf-8")
CSS = (TRIVIA / "assets" / "trivia-machine.css").read_text(encoding="utf-8")


def _questions() -> list[dict[str, object]]:
    return [
        question
        for pack in DATA["questionPacks"]
        for question in pack["questions"]
    ]


def test_trivia_machine_is_an_independent_static_application() -> None:
    required = {
        "index.html",
        "package.json",
        "data/trivia-data.json",
        "assets/trivia-machine.css",
        "assets/trivia-machine.js",
        "assets/trivia-data-validator.js",
        "assets/trivia-content-rotation.js",
        "assets/video-machine.css",
        "assets/single-reel-engine.js",
        "assets/machine-mechanics-core.js",
        "assets/music-machine/aggits-reel-v2.webp",
        "assets/music-machine/aggits-lever.webp",
        "tests/trivia-data-validator.test.mjs",
    }
    assert all((TRIVIA / relative).is_file() for relative in required)


def test_proven_spin_and_mechanics_modules_are_byte_identical_copies() -> None:
    for filename in ("single-reel-engine.js", "machine-mechanics-core.js"):
        assert (TRIVIA / "assets" / filename).read_bytes() == (ROOT / "static" / filename).read_bytes()


def test_schema_contains_exactly_five_temporary_questions_in_a_separate_pack() -> None:
    questions = _questions()
    assert DATA["schemaVersion"] == 3
    assert len(DATA["questionPacks"]) == 1
    pack = DATA["questionPacks"][0]
    assert DATA["activePackId"] == pack["packId"]
    assert {
        "packId",
        "packName",
        "packVersion",
        "description",
        "availableModes",
        "questions",
    } <= pack.keys()
    assert pack["temporary"] is True
    assert len(questions) == 5
    assert all(question["temporary"] is True for question in questions)
    assert all(str(question["id"]).startswith("TEMP-M3-") for question in questions)
    assert "Which planet is commonly known" not in HTML
    assert "Which planet is commonly known" not in SCRIPT


def test_all_five_approved_modes_have_one_test_question() -> None:
    expected = {
        "general": ("GENERAL", "Give me anything.", "green"),
        "nerd": ("NERD", "Make me work for it.", "blue"),
        "weird": ("WEIRD", "That’s actually true?", "purple"),
        "unhinged": ("UNHINGED", "How did this even happen?", "orange"),
        "serial-killer": ("SERIAL KILLER", "Enter the dark side.", "red"),
    }
    actual = {
        mode["id"]: (mode["label"], mode["tagline"], mode["colour"])
        for mode in DATA["modes"]
    }
    assert actual == expected
    assert {question["mode"] for question in _questions()} == set(expected)


def test_question_schema_has_every_required_game_and_source_field() -> None:
    required = {
        "id",
        "mode",
        "category",
        "reelLabel",
        "question",
        "answerA",
        "answerB",
        "answerC",
        "answerD",
        "correctAnswer",
        "explanation",
        "crispyBit1",
        "crispyBit2",
        "whoaFact",
        "sourceName",
        "sourceUrl",
        "difficulty",
        "status",
    }
    for question in _questions():
        assert required <= question.keys()
        assert all(question[f"answer{key}"] for key in "ABCD")
        assert question["correctAnswer"] in "ABCD"
        assert question["difficulty"] in {"easy", "medium", "hard"}
        assert question["status"] in {"draft", "approved", "retired"}
        assert str(question["sourceUrl"]).startswith("https://")


def test_only_one_fixture_exercises_the_optional_youtube_path() -> None:
    questions_with_video = [
        question for question in _questions() if question.get("videoId")
    ]
    assert len(questions_with_video) == 1
    assert len(questions_with_video[0]["videoId"]) == 11
    assert questions_with_video[0]["videoTitle"]
    assert questions_with_video[0]["videoChannel"]
    assert questions_with_video[0]["videoReason"]
    assert "videoId" not in next(
        question for question in _questions() if question["mode"] == "nerd"
    )


def test_controller_reuses_frozen_spin_landing_and_lever_mechanics() -> None:
    assert "spinSingleReel({" in SCRIPT
    assert "leverResistance(progress)" in SCRIPT
    assert "MUSIC_MACHINE_REEL_PROFILE.leverTrigger" in SCRIPT
    assert "showLanding(winner)" in SCRIPT
    assert "selectQuestionForTopic(topic)" in SCRIPT
    assert "scheduleQuestionReveal(question)" in SCRIPT
    assert "data/trivia-data.json" in SCRIPT
    assert "validateTriviaData(config)" in SCRIPT
    assert "validation.approvedQuestions" in SCRIPT
    assert "createRotationPicker" in SCRIPT
    assert SCRIPT.index("await spinSingleReel({") < SCRIPT.index("showLanding(winner)")


def test_validator_enforces_production_content_readiness() -> None:
    expected_diagnostics = {
        "question_id_duplicate",
        "question_mode_invalid",
        "question_answers_invalid",
        "correct_answer_invalid",
        "source_url_invalid",
        "video_id_invalid",
        "video_metadata_without_id",
        "difficulty_invalid",
        "status_invalid",
    }
    assert all(code in VALIDATOR for code in expected_diagnostics)
    assert "question.status === 'approved'" in VALIDATOR
    assert "activePackId" in VALIDATOR
    assert "availableModes" in VALIDATOR


def test_question_rotation_is_separate_from_mechanical_landing() -> None:
    assert "function selectQuestionForTopic(topic)" in SCRIPT
    landing = SCRIPT.split("function showLanding(topic, countLanding = true)", 1)[1].split("function answerQuestion", 1)[0]
    assert "selectQuestionForTopic(topic)" in landing
    assert "lastIdentity" in ROTATION
    assert "if (bag.length > 1" in ROTATION
    assert "buildReelTopics" in ROTATION
    assert DATA["activePackId"] not in SCRIPT


def test_mode_selection_and_surprise_me_are_functional_not_background_art() -> None:
    assert 'data-mode-selection' in HTML
    assert 'data-mode-grid' in HTML
    assert 'data-action="surprise-mode"' in HTML
    assert "modes[Math.floor(Math.random() * modes.length)]" in SCRIPT
    assert "enterMode(mode)" in SCRIPT
    assert "button.dataset.mode = mode.id" in SCRIPT
    assert "trivia-mode-button--green" in CSS
    assert "trivia-mode-button--red" in CSS


def test_question_chamber_has_four_answers_and_single_submission_lock() -> None:
    assert HTML.count("data-answer=\"") == 4
    assert all(f'data-answer="{key}"' in HTML for key in "ABCD")
    assert "if (answered || !currentQuestion" in SCRIPT
    assert "answered = true" in SCRIPT
    assert "button.disabled = true" in SCRIPT


def test_correct_and_incorrect_reveals_and_crispy_bits_ticker_are_present() -> None:
    assert "key === currentQuestion.correctAnswer" in SCRIPT
    assert "is-correct" in SCRIPT
    assert "is-incorrect" in SCRIPT
    assert "CORRECT!" in SCRIPT
    assert "NOT THIS TIME" in SCRIPT
    assert "CRISPY BIT ★" in SCRIPT
    assert "★ WHOA ★" in SCRIPT


def test_watch_video_is_conditional_and_uses_privacy_enhanced_youtube_embed() -> None:
    assert 'data-action="watch-video" hidden disabled' in HTML
    assert "watchVideoButton.hidden = !hasVideo" in SCRIPT
    assert "if (!answered || !currentQuestion?.videoId) return" in SCRIPT
    assert "https://www.youtube-nocookie.com/embed/" in SCRIPT
    assert "videoTitle" in SCRIPT
    assert "videoChannel" in SCRIPT
    assert "videoReason" not in SCRIPT
    assert "videoReason" not in HTML


def test_next_re_spin_and_change_mode_are_logically_separate() -> None:
    assert 'data-action="next-question"' in HTML
    assert 'data-action="spin-again"' in HTML
    assert 'data-action="change-mode"' in HTML
    assert "function nextQuestion()" in SCRIPT
    assert "function changeMode()" in SCRIPT
    assert "reSpinButton.addEventListener('click', () => void spin())" in SCRIPT
    assert "machine.dataset.appView = 'mode-select'" in SCRIPT


def test_shell_retains_milestone_one_framework_and_has_no_qr_artwork() -> None:
    assert "CRISPY BITS TRIVIA" in HTML
    assert 'data-project-type="trivia"' in HTML
    assert 'data-reel="0"' in HTML
    assert 'class="lever"' in HTML
    assert 'data-video-stage' in HTML
    assert "qr-card" not in HTML.lower()
    assert "qr-code" not in HTML.lower()


def test_mobile_layout_stacks_modes_answers_and_post_controls() -> None:
    assert "@media (max-width:560px)" in CSS
    assert '.trivia-mode-grid{grid-template-columns:1fr' in CSS
    assert '.trivia-answers{grid-template-columns:1fr' in CSS
    assert '.trivia-post-controls{grid-template-columns:repeat(2' in CSS


def test_trivia_styles_remain_explicitly_scoped() -> None:
    assert '@import url("./video-machine.css")' in CSS
    assert CSS.count('[data-project-type="trivia"]') >= 55
    assert '[data-project-type="banjo"]' not in CSS
    assert '[data-project-type="channel_master"]' not in CSS
