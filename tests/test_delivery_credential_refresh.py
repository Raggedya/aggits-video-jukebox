from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
DESKTOP_PATH = ROOT / "desktop" / "video_jukebox_factory.py"


def load_desktop_module():
    spec = importlib.util.spec_from_file_location("delivery_refresh_desktop", DESKTOP_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the desktop module for testing.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeliveryCredentialRefreshTests(unittest.TestCase):
    def test_delivery_credentials_are_reloaded_instead_of_using_startup_snapshot(self):
        module = load_desktop_module()

        class Store:
            calls = 0

            def load_settings(self):
                self.calls += 1
                return {
                    "deliveryEmail": "current@example.com",
                    "deliverySecret": "freshly-provisioned-secret",
                }

        factory = object.__new__(module.Factory)
        factory.store = Store()
        factory.settings = {"deliveryEmail": "stale@example.com", "deliverySecret": ""}

        recipient, secret = module.Factory._current_delivery_credentials(factory)

        self.assertEqual(factory.store.calls, 1)
        self.assertEqual(recipient, "current@example.com")
        self.assertEqual(secret, "freshly-provisioned-secret")
        self.assertEqual(factory.settings["deliveryEmail"], "current@example.com")

    def test_every_delivery_path_uses_the_fresh_credential_helper(self):
        source = DESKTOP_PATH.read_text(encoding="utf-8")

        self.assertEqual(source.count("recipient, delivery_secret = self._current_delivery_credentials()"), 3)
        self.assertEqual(source.count("secret=delivery_secret"), 3)
        self.assertNotIn('secret=str(self.settings.get("deliverySecret") or "")', source)


if __name__ == "__main__":
    unittest.main()
