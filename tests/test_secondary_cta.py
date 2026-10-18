import json
import tempfile
import unittest
from pathlib import Path
from test_channel_master_workflow import master_project
from aggits_video_factory.models import Project, ProjectValidationError
from aggits_video_factory.secondary_cta import normalize_cta2
from aggits_video_factory.site_builder import build_project_site
from aggits_video_factory.store import ProjectStore
from aggits_video_factory.desktop_forms import project_to_form_values, validate_project_form, FormValidationError


class SecondaryCtaTests(unittest.TestCase):
    def test_urls_and_default(self):
        self.assertIsNone(normalize_cta2({'url':' ', 'label':'Not enabled'}))
        self.assertEqual(normalize_cta2({'url':'https://example.com'}),{'url':'https://example.com','label':'FIND OUT MORE'})
        for url in ('javascript:alert(1)','data:text/html,hi','file:///C:/private','//example.com','https://','https://user:pass@example.com','https://example.com\\@evil.test','https://example.com\nx','https://example.com:invalid'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_cta2({'url':url})

    def test_legacy_roundtrip_identity_and_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ProjectStore(Path(folder))
            a=master_project(); original=a.to_dict(); original.pop('cta_2',None)
            self.assertIsNone(Project.from_dict(original).cta_2)
            b=Project.from_dict(original);b.slug='second-machine'
            for value in ({'url':'https://example.com/a','label':'BUY'}, {'url':'https://example.com/c','label':'SHOP'},None):
                a.cta_2=value;store.save_project(a);a=store.load_project(a.slug)
                self.assertEqual(a.cta_2,value)
                self.assertEqual(a.id,original['id']);self.assertEqual(a.slug,original['slug'])
                self.assertEqual(a.channel_master_config.to_dict(),original['channel_master_config'])
                self.assertEqual(a.videos[0].to_dict(),original['videos'][0])
                self.assertIsNone(b.cta_2)

    def test_editor_validation_roundtrip(self):
        p=master_project();p.cta_2={'url':'https://example.com/second','label':'Second link'}
        values=project_to_form_values(p)
        self.assertEqual(validate_project_form(values,p.project_type).cta_2,p.cta_2)
        values.cta2_url='javascript:alert(1)'
        with self.assertRaises(FormValidationError):validate_project_form(values,p.project_type)

    def test_published_edit_keeps_identity_and_requires_republish(self):
        from types import SimpleNamespace
        from aggits_video_factory.business_workflow import assemble_reviewed_project
        p=master_project();p.published_url='https://example.com/stable/';p.status='published'
        original=p.to_dict()
        values=project_to_form_values(p);values.cta2_url='https://example.com/second'
        revised=assemble_reviewed_project(project_type=p.project_type, values=validate_project_form(values,p.project_type),
            catalogue=SimpleNamespace(channel_url=p.channel_url,channel_id=p.channel_id,channel_title=p.channel_title,channel_thumbnail=p.channel_thumbnail),
            selected_videos=p.videos,reviewed_videos=p.videos,source_results=[],slug='ignored',existing=p)
        self.assertEqual(revised.status,'changes_pending')
        self.assertEqual((revised.id,revised.slug,revised.published_url),(p.id,p.slug,p.published_url))
        self.assertEqual(p.to_dict(),original)
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a';b=Path(folder)/'b';build_project_site(p,a);build_project_site(revised,b)
            self.assertEqual((a/'qr-card.png').read_bytes(),(b/'qr-card.png').read_bytes())

    def test_generated_markup_payload_removal_and_safe_escaping(self):
        with tempfile.TemporaryDirectory() as folder:
            p=master_project();out=Path(folder)/'site'
            build_project_site(p,out);before=(out/'index.html').read_text(encoding='utf-8')
            self.assertNotIn('secondary-cta',before)
            p.cta_2={'url':'https://example.com/?a=1&b=2','label':'<img src=x onerror=alert(1)>'}
            build_project_site(p,out);html=(out/'index.html').read_text(encoding='utf-8')
            self.assertIn('&lt;img src=x onerror=alert(1)&gt;',html)
            self.assertIn('href="https://example.com/?a=1&amp;b=2" target="_blank" rel="noopener noreferrer"',html)
            self.assertLess(html.index('class="secondary-cta"'),html.index('class="machine-controls"'))
            self.assertEqual(json.loads((out/'machine.json').read_text())['cta2'],p.cta_2)
            p.cta_2=None;build_project_site(p,out)
            self.assertEqual(before,(out/'index.html').read_text(encoding='utf-8'))
            self.assertNotIn('cta2',json.loads((out/'machine.json').read_text()))

    def test_invalid_mutated_config_cannot_build_link(self):
        with tempfile.TemporaryDirectory() as folder:
            p=master_project();p.cta_2={'url':'javascript:alert(1)'}
            with self.assertRaises(ValueError):build_project_site(p,Path(folder)/'site')

    def test_desktop_fields_across_tabs(self):
        import tkinter as tk
        from desktop.video_jukebox_factory import ProjectForm, LoveMyLocalsForm
        from aggits_video_factory.models import ProjectType
        root=tk.Tk();root.withdraw()
        try:
            for kind in ProjectType:
                if kind is ProjectType.LOVE_MY_LOCALS:continue
                form=ProjectForm(root,kind,lambda:None,lambda:None)
                form.cta2_url_var.set('https://example.com');form.cta2_label_var.set('TEST')
                self.assertEqual(form.values().cta2_url,'https://example.com')
                form.mark_clean()
                form.clear_new();self.assertEqual(form.values().cta2_url,'')
                form.destroy()
        finally:root.destroy()
