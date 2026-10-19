import json
from pathlib import Path
import tempfile
import unittest
from tools.inject_arcade_shares import inject,BASE,ASSETS

class SharePublishTests(unittest.TestCase):
    def fixture(self,root):
        (root/'static').mkdir();(root/'static/arcade-presentation.js').write_text('// approved JS')
        gallery=root/'public/crispy-bits/comedy-arcade';gallery.mkdir(parents=True)
        records=[{'status':'active','primaryMachineId':'test-id','destinationUrl':BASE+'test-artist/'}]
        self.manifest(gallery,records)
        folder=gallery.parent/'test-artist';folder.mkdir()
        for name in ASSETS:
            asset=folder/'assets'/name;asset.parent.mkdir(parents=True,exist_ok=True);asset.write_bytes(b'EXACT APPROVED ART')
        (folder/'assets/arcade-presentation.js').write_text('// older JS')
        (folder/'machine.json').write_text(json.dumps({'slug':'test-artist','projectType':'channel_master','videos':[{'videoId':'test-only'}]}))
        self.original(folder)
        return gallery,folder,records
    def original(self,folder):
        (folder/'index.html').write_text(f'<html><head><link rel="canonical" href="{BASE}test-artist/"><meta property="og:title" content="TEST ARTIST"></head><body><main data-project-type="channel_master">UNCHANGED CABINET</main></body></html>')
    def manifest(self,gallery,records):
        (gallery/'index.html').write_text('<script id="arcade-data" type="application/json">'+json.dumps({'schemaVersion':1,'comedians':records})+'</script>')
    def test_normal_republish_recreates_alias_and_is_idempotent_without_changing_catalogue(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);gallery,folder,_=self.fixture(root);before=(folder/'machine.json').read_bytes()
            inject(root);alias=(folder/'theatre.html').read_bytes();inject(root)
            self.assertEqual((folder/'theatre.html').read_bytes(),alias)
            (folder/'theatre.html').unlink();self.original(folder);inject(root)
            self.assertEqual((folder/'theatre.html').read_bytes(),alias)
            self.assertEqual((folder/'machine.json').read_bytes(),before)
            self.assertIn('data-arcade-share-page="true"',alias.decode())
            self.assertNotIn('data-arcade-presentation="theatre"',(folder/'index.html').read_text())
    def test_hidden_soon_and_removed_records_receive_no_alias_and_only_marked_stale_alias_is_removed(self):
        for status in ('hidden','coming_soon','removed'):
            with self.subTest(status=status),tempfile.TemporaryDirectory() as d:
                root=Path(d);gallery,folder,records=self.fixture(root);inject(root)
                self.manifest(gallery,[] if status=='removed' else [{**records[0],'status':status}])
                unrelated=gallery.parent/'other';unrelated.mkdir();(unrelated/'theatre.html').write_text('UNRELATED HTML')
                original=(folder/'index.html').read_bytes();inject(root)
                self.assertFalse((folder/'theatre.html').exists());self.assertEqual((folder/'index.html').read_bytes(),original)
                self.assertTrue((unrelated/'theatre.html').exists())
    def test_unsafe_duplicate_and_missing_primary_block_without_writes(self):
        for change in ({'destinationUrl':'https://evil.test/a/'},{'primaryMachineId':''},{'duplicate':True}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                root=Path(d);gallery,folder,records=self.fixture(root)
                bad=[records[0],records[0]] if change.get('duplicate') else [{**records[0],**change}]
                self.manifest(gallery,bad);before=(folder/'index.html').read_bytes()
                with self.assertRaises(ValueError):inject(root)
                self.assertEqual((folder/'index.html').read_bytes(),before);self.assertFalse((folder/'theatre.html').exists())
    def test_missing_art_blocks_and_deleted_machine_is_not_resurrected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);gallery,folder,_=self.fixture(root)
            (folder/'assets'/ASSETS[0]).unlink()
            with self.assertRaises(ValueError):inject(root)
            self.assertFalse((folder/'theatre.html').exists())
            self.manifest(gallery,[{'status':'active','primaryMachineId':'gone','destinationUrl':BASE+'gone/'}])
            inject(root);self.assertFalse((gallery.parent/'gone').exists())
    def test_identity_and_canonical_mismatch_fail(self):
        for field in ('identity','canonical'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
                root=Path(d);_,folder,_=self.fixture(root)
                if field=='identity':(folder/'machine.json').write_text('{"slug":"another","projectType":"channel_master"}')
                else:(folder/'index.html').write_text((folder/'index.html').read_text().replace(BASE, 'https://evil.test/'))
                with self.assertRaises(ValueError):inject(root)
