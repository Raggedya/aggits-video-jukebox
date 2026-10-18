import copy
import tempfile
import unittest
from pathlib import Path
from urllib.request import urlopen

from aggits_video_factory.football import valid_player_video
from aggits_video_factory.preview import PreviewServer
from aggits_video_factory.youtube_api import YouTubeClient


class FootballPlaybackTests(unittest.TestCase):
    def test_stored_identifiers_and_urls(self):
        record = {'videoId': '6waA8RXdDB8', 'url': 'https://www.youtube.com/watch?v=6waA8RXdDB8'}
        self.assertTrue(valid_player_video(record))
        for url in ('https://youtu.be/6waA8RXdDB8', 'https://www.youtube.com/shorts/6waA8RXdDB8', 'https://www.youtube.com/embed/6waA8RXdDB8'):
            self.assertTrue(valid_player_video({**record, 'url': url}))
        for identifier in ('', 'short', 'abc/defghij', '<script>123'):
            self.assertFalse(valid_player_video({**record, 'videoId': identifier}))
        for url in ('https://example.com/watch?v=6waA8RXdDB8', 'javascript:alert(1)', 'https://youtube.com@evil.example/watch?v=6waA8RXdDB8', 'https://youtube.com/watch?v=M7lc1UVf-VE'):
            self.assertFalse(valid_player_video({**record, 'url': url}))

    def test_existing_review_filters(self):
        client = YouTubeClient('TEST-NOT-A-REAL-KEY')
        item = {'id': '6waA8RXdDB8', 'status': {'privacyStatus': 'public', 'embeddable': True},
                'snippet': {'title': 'TEST ONLY', 'liveBroadcastContent': 'none'}, 'contentDetails': {}}
        self.assertIsNotNone(client._video_record(item))
        for changes in ({'privacyStatus': 'private'}, {'embeddable': False}, {'privacyStatus': None}):
            restricted = copy.deepcopy(item)
            restricted['status'].update(changes)
            self.assertIsNone(client._video_record(restricted))
        self.assertIsNone(client._video_record({}))

    def test_preview_uses_localhost_and_remains_loopback_only(self):
        with tempfile.TemporaryDirectory() as directory:
            server = PreviewServer()
            try:
                url = server.start(Path(directory))
                self.assertTrue(url.startswith('http://localhost:'))
                self.assertEqual(server.server.server_address[0], '127.0.0.1')
                with urlopen(url, timeout=3) as response:
                    self.assertEqual(response.status, 200)
                # Old numeric preview URLs must not reintroduce embed failure.
                with urlopen(url.replace('localhost', '127.0.0.1') + '?qa=redirect', timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.url, url + '?qa=redirect')
            finally:
                server.stop()
