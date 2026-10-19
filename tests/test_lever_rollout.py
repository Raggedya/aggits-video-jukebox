"""Republish upgrades retain old runtime behavior and never replace catalogues."""
import subprocess
import tempfile
from pathlib import Path
import unittest
from tools.inject_daas_statistics import instrument_runtime, inject_page

ROOT=Path(__file__).resolve().parents[1]
class LeverRolloutTests(unittest.TestCase):
    def test_every_published_video_runtime_supports_idempotent_telemetry_only_upgrade(self):
        names=subprocess.check_output(['git','ls-tree','-r','--name-only','origin/main'],cwd=ROOT,text=True).splitlines()
        paths=[p for p in names if p.startswith('public/') and p.count('/') in (3,4)
               and p.endswith('/assets/video-machine.js') and '/reviews/' not in p]
        self.assertGreaterEqual(len(paths),55)
        for p in paths:
            with self.subTest(path=p):
                original=subprocess.check_output(['git','show','origin/main:'+p],cwd=ROOT,text=True)
                patched=instrument_runtime(original)
                self.assertEqual(instrument_runtime(patched),patched)
                self.assertEqual(patched.count("dispatchEvent(new CustomEvent('crispy-bits:accepted-spin'"),1)
                self.assertEqual([s for s in original.splitlines() if s.startswith('import ')],
                                 [s for s in patched.splitlines() if s.startswith('import ')])
                # Everything outside telemetry/spin input paths remains exact.
                for start,end in [('function playerUrl(', 'function requestPlayerPlay(')]:
                    if start in original and end in original:
                        self.assertEqual(original[original.index(start):original.index(end)],patched[patched.index(start):patched.index(end)])
    def test_unknown_runtime_fails_closed(self):
        with self.assertRaises(ValueError):instrument_runtime('unknown engine')
    def test_republish_cache_busts_without_changing_catalogue_or_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'static').mkdir();(root/'static/machine-statistics.js').write_text('// collector')
            site=root/'site';(site/'assets').mkdir(parents=True)
            (site/'machine.json').write_text('{"videos":[]}')
            (site/'index.html').write_text('<body><main class="music-machine">CONTROLS</main><script type="module" src="assets/video-machine.js"></script></body>')
            old=subprocess.check_output(['git','show','origin/main:public/crispy-bits/andovia/assets/video-machine.js'],cwd=ROOT,text=True)
            (site/'assets/video-machine.js').write_text(old)
            inject_page(root,site/'index.html');first=(site/'index.html').read_bytes()
            inject_page(root,site/'index.html')
            self.assertEqual(first,(site/'index.html').read_bytes())
            self.assertIn(b'video-machine.js?v=',first)
            self.assertIn(b'CONTROLS',first)
            self.assertEqual((site/'machine.json').read_text(),'{"videos":[]}')
