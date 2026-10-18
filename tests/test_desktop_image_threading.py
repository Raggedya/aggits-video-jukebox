"""Run the image/worker deadlock regression in a time-bounded child process."""
import subprocess
import sys
import textwrap
import unittest


class ImageThreadingTests(unittest.TestCase):
    def test_thumbnail_cycles_save_worker_and_ui_cleanup(self):
        code = textwrap.dedent('''
            import gc, tempfile, threading, time, weakref
            from pathlib import Path
            from unittest.mock import patch
            from PIL import Image, ImageTk
            from desktop.video_jukebox_factory import Factory
            from aggits_video_factory.store import ProjectStore
            from aggits_video_factory.models import ProjectType
            from aggits_video_factory.diagnostics import close_logging

            previous = gc.isenabled()
            main_id = threading.get_ident()
            finalized = []
            class TrackedPhoto(ImageTk.PhotoImage):
                def __del__(self):
                    finalized.append(threading.get_ident())
                    super().__del__()

            with tempfile.TemporaryDirectory() as directory:
                store = ProjectStore(Path(directory))
                with patch('desktop.video_jukebox_factory.ProjectStore', return_value=store):
                    app = Factory()
                app.withdraw()
                try:
                    assert not gc.isenabled()
                    form = app.forms[ProjectType.FOOTBALL]
                    logo = Path(directory) / 'test-logo.png'
                    Image.new('RGBA', (100, 50), '#123456').save(logo)
                    form.football_vars['logo_asset'].set(str(logo))
                    for attempt in range(3):
                        photo = TrackedPhoto(Image.new('RGB', (2, 2)), master=app)
                        photo.cycle = photo
                        reference = weakref.ref(photo)
                        del photo
                        completed = []
                        def worker():
                            assert threading.get_ident() != main_id
                            assert not gc.isenabled()
                            cycles = []
                            for i in range(5000):
                                cycle = []
                                cycle.append(cycle)
                                cycles.append(cycle)
                            return 'saved'
                        app._run_async('TEST SAVE', worker, completed.append)
                        deadline = time.monotonic() + 5
                        while not completed and time.monotonic() < deadline:
                            app.update()
                            time.sleep(.01)
                        assert completed == ['saved']
                        # Exercise the scheduled collector with its normal timer lifecycle.
                        deadline = time.monotonic() + 3
                        while reference() is not None and time.monotonic() < deadline:
                            app.update()
                            time.sleep(.01)
                        assert reference() is None
                    assert finalized == [main_id] * 3, finalized
                    with patch.object(app, '_open_project_preview'), patch('desktop.video_jukebox_factory.messagebox.showinfo'):
                        assert app._save_football()
                    saved = next(iter(app.projects.values()))
                    restored = store.load_project(saved.slug)
                    form.load_project(restored)
                    assert form._football_logo_image.width() == 100
                finally:
                    app.preview_server.stop()
                    if app._async_poll_id:
                        app.after_cancel(app._async_poll_id)
                    app.destroy()
                    close_logging(store.root)
                assert gc.isenabled() == previous
        ''')
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
