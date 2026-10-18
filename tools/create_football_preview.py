"""Local-only QA output. No official club content is fabricated or published."""
from pathlib import Path
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_football import football_project
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.football import club_records, FootballConfig
from test_channel_master_workflow import video


def create_two_club_preview(destination, count=2):
    """TEST ONLY: compose an isolated preview, never a saved/publishable project."""
    project = football_project(3)
    records = club_records(project)
    for index in range(1, count):
        other = football_project(0)
        other.title = "ISOLATION TEST — NOT AN AFL CLUB" if index == 1 else f"TEST ONLY CLUB {index + 1}"
        other.ticker_text = f"CLUB {index + 1} TEST TICKER — NO REAL CLUB CONTENT"
        other.football_config = FootballConfig(club_id="isolation-test-only" if index == 1 else f"test-club-{index + 1}",
            base_colour="#201020", primary_colour="#703050", highlight_colour="#FFD080",
            cta_label="Test destination", cta_url=f"https://example.com/football-test/{index + 1}")
        other.videos = [video(index * 10 + offset) for offset in range(3)]
        records.extend(club_records(other))
    project.football_config.clubs = records
    build_project_site(project, destination)
    data_path = destination / "machine.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    for club in data["footballConfig"]["clubs"]:
        for item in club["videos"]:
            item["title"] = "TEST ONLY — " + item["title"]
            item["thumbnailUrl"] = ""
    data["testOnly"] = True
    data_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # Never contact YouTube with synthetic fixture IDs. Local stub retains the
    # existing iframe command boundary; this script exists only in QA output.
    (destination / "fixture-player.html").write_text('''<!doctype html><body style="background:#171923;color:#fff;font:18px sans-serif">TEST PLAYER — NOT REAL CLUB VIDEO<script>addEventListener('message',e=>{try{parent.postMessage({qaCommand:JSON.parse(e.data).func},'*')}catch{}})</script>''', encoding="utf-8")
    (destination / "fixture-only.js").write_text('''
if (!['127.0.0.1','localhost','::1','[::1]'].includes(location.hostname)) {
  window.fetch = async () => {throw new Error('LOCAL TEST FIXTURE ONLY');};
  addEventListener('DOMContentLoaded', () => document.body.replaceChildren(document.createTextNode('TEST FIXTURE: LOCAL PREVIEW ONLY')));
} else {
  const originalSrc = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'src');
  Object.defineProperty(HTMLIFrameElement.prototype, 'src', {get:originalSrc.get, set(value) {
    originalSrc.set.call(this, String(value).startsWith('https://www.youtube.com/embed/') ? new URL('fixture-player.html', location.href).href : value);
  }});
  window.YT = {Player: class {
    constructor(frame, options) { queueMicrotask(()=>options.events.onReady?.()); }
    playVideo() { window.postMessage({qaCommand:'playVideo'},'*'); }
    destroy() {}
  }};
}
''', encoding="utf-8")
    html = destination / "index.html"
    content = html.read_text(encoding="utf-8")
    content = content.replace('</head>', '<script src="fixture-only.js"></script></head>')
    content = content.replace('<div class="experience-frame">', '<div class="experience-frame"><p style="text-align:center;color:#fff">TEST ONLY — ALL VIDEO CATALOGUES ARE SYNTHETIC. CLUB LOGOS NOT SUPPLIED.</p>')
    html.write_text(content, encoding="utf-8")
    return data

if __name__ == "__main__":
    output = ROOT / "build" / "football-preview"
    for folder, count in (("north-melbourne", 0), ("test-fixture", 3)):
        project = football_project(count)
        if not count:
            project.ticker_text = "LOCAL PROTOTYPE — LOGO AND REVIEWED CLUB VIDEOS REQUIRED"
            project.football_config.cta_url = ""
        build_project_site(project, output / folder / "site")
        print(output / folder / "site" / "index.html")
    create_two_club_preview(output / "two-club-test" / "site")
    print(output / "two-club-test" / "site" / "index.html")
    create_two_club_preview(output / "eighteen-club-test" / "site", count=18)
    print(output / "eighteen-club-test" / "site" / "index.html")
