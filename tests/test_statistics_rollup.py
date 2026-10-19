import json
import unittest
from tools.report_machine_statistics import arcade_slugs,summarize

class StatisticsRollupTests(unittest.TestCase):
    def test_public_manifest_scope_uses_only_active_real_machine_urls(self):
        records=[{'status':'active','destinationUrl':'https://raggedya.github.io/aggits-video-jukebox/crispy-bits/daas/'},
                 {'status':'coming_soon','destinationUrl':'not-a-machine'}]
        html='<script id="arcade-data" type="application/json">'+json.dumps({'comedians':records})+'</script>'
        self.assertEqual(arcade_slugs(html),['comedy-arcade','daas'])

    def test_unsafe_destination_is_rejected(self):
        data={'comedians':[{'status':'active','destinationUrl':"https://example.com/unsafe'"}]}
        with self.assertRaises(ValueError):arcade_slugs('<script id="arcade-data">'+json.dumps(data)+'</script>')

    def test_rollup_separates_landing_and_machine_visits_and_never_sums_uniques(self):
        rows=[{'slug':s,'event_name':e,'events':n,'tab_sessions':99} for s,e,n in
              [('comedy-arcade','page_view',8),('a','page_view',10),('b','page_view',12),
               ('a','spin',25),('a','spotify_click',3),('b','cta_click',4),('b','cta2_click',2),
               ('unrelated','page_view',1000)]]
        report=summarize(rows,['comedy-arcade','a','b'])
        self.assertEqual(report['gallery_page_views'],8)
        self.assertEqual(report['machine_page_views'],22)
        self.assertEqual(report['combined_page_views'],30)
        self.assertEqual(report['primary_cta_clicks'],7)
        self.assertEqual(report['recorded_action_clicks'],9)
        self.assertEqual(report['machine_totals']['cta2_click'],2)
        self.assertNotIn('unique_visitors',report)
        self.assertNotIn('tab_sessions',report)

    def test_missing_metrics_have_explicit_coverage_caveat(self):
        report=summarize([],['comedy-arcade','a'])
        self.assertEqual(report['combined_page_views'],0)
        self.assertTrue(any('Missing historical coverage' in n for n in report['notes']))
