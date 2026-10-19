import tempfile
import unittest
import sqlite3
from pathlib import Path
from test_channel_master_workflow import master_project
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.models import ProjectType

class MachineStatisticsTests(unittest.TestCase):
    def test_pages_injection_survives_old_desktop_republish(self):
        from tools.inject_daas_statistics import inject
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'static').mkdir()
            (root/'static/machine-statistics.js').write_text('// test collector')
            for slug in ('doug-anthony-allstars','other'):
                site=root/'public/crispy-bits'/slug
                site.mkdir(parents=True)
                (site/'index.html').write_text('<html><body><main class="music-machine"></main></body></html>')
            inject(root);inject(root)
            html=(root/'public/crispy-bits/doug-anthony-allstars/index.html').read_text()
            self.assertEqual(html.count('machine-statistics.js'),1)
            self.assertIn('machine-statistics',(root/'public/crispy-bits/other/index.html').read_text())
            self.assertEqual((root/'public/crispy-bits/doug-anthony-allstars/assets/machine-statistics.js').read_text(),'// test collector')

    def test_all_generated_machines_include_collector(self):
        with tempfile.TemporaryDirectory() as directory:
            project=master_project()
            for slug in ('doug-anthony-allstars','another-machine'):
                project.slug=slug
                output=Path(directory)/slug
                build_project_site(project,output)
                self.assertIn('src="assets/machine-statistics.js?', (output/'index.html').read_text(encoding='utf-8'))

    def test_every_product_and_standalone_trivia_republish_injection(self):
        from tools.inject_daas_statistics import inject
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'static').mkdir()
            (root/'static/machine-statistics.js').write_text('// collector')
            for kind in [p.value for p in ProjectType]+['trivia']:
                site=root/'public/crispy-bits'/kind.replace('_','-')
                site.mkdir(parents=True)
                (site/'index.html').write_text(f'<main class="music-machine" data-project-type="{kind}"><section class="machine-controls"></section></main></body>')
            landing=root/'public/landing/index.html'
            landing.parent.mkdir();landing.write_text('<body>Not a player</body>')
            review=root/'public/reviews/sample/index.html'
            review.parent.mkdir(parents=True);review.write_text('<main class="music-machine"></main></body>')
            inject(root);inject(root)
            for page in (root/'public/crispy-bits').glob('*/index.html'):
                self.assertEqual(page.read_text().count('machine-statistics.js'),1)
            self.assertNotIn('machine-statistics',landing.read_text())
            self.assertNotIn('machine-statistics',review.read_text())

    def test_arcade_landing_is_injected_but_unrelated_galleries_are_not(self):
        from tools.inject_daas_statistics import inject
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'static').mkdir()
            (root/'static/machine-statistics.js').write_text('// gallery and machines')
            for slug in ('comedy-arcade','unrelated-gallery'):
                page=root/'public/crispy-bits'/slug/'index.html';page.parent.mkdir(parents=True)
                page.write_text('<body><main class="machine-stack"></main></body>')
            inject(root);inject(root)
            self.assertEqual((root/'public/crispy-bits/comedy-arcade/index.html').read_text().count('machine-statistics.js'),1)
            self.assertNotIn('machine-statistics',(root/'public/crispy-bits/unrelated-gallery/index.html').read_text())

    def test_additive_schema_constraints_and_deduplication(self):
        db=sqlite3.connect(':memory:')
        db.executescript((Path(__file__).parents[1]/'worker/migrations/0004_machine_statistics.sql').read_text())
        sql="INSERT OR IGNORE INTO machine_statistics(event_id,session_id,slug,event_name) VALUES('test','session','doug-anthony-allstars','page_view')"
        db.execute(sql);db.execute(sql)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM machine_statistics').fetchone()[0],1)
        self.assertGreater(db.execute('SELECT received_at FROM machine_statistics').fetchone()[0],0)
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO machine_statistics(event_id,session_id,slug,event_name) VALUES('other','session','wrong','page_view')")
        before=db.execute('SELECT * FROM machine_statistics').fetchall()
        db.executescript((Path(__file__).parents[1]/'worker/migrations/0005_all_machine_spins.sql').read_text())
        self.assertEqual(before,db.execute('SELECT * FROM machine_statistics').fetchall())
        db.execute("INSERT INTO machine_statistics(event_id,session_id,slug,event_name) VALUES('other','session','another-machine','spin')")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM machine_statistics WHERE slug='another-machine' AND event_name='spin'").fetchone()[0],1)
        before=db.execute('SELECT * FROM machine_statistics ORDER BY event_id').fetchall()
        db.executescript((Path(__file__).parents[1]/'worker/migrations/0006_all_machine_details.sql').read_text())
        self.assertEqual(before,db.execute('SELECT * FROM machine_statistics ORDER BY event_id').fetchall())
        for event in ('page_view','play_click','share_click','spotify_click','cta_click','cta2_click','contact_click','membership_click'):
            db.execute('INSERT INTO machine_statistics(event_id,session_id,slug,event_name) VALUES(?,?,?,?)',(event,'tab','another-machine',event))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO machine_statistics(event_id,session_id,slug,event_name) VALUES('bad','tab','another-machine','fake_metric')")
        db.close()
