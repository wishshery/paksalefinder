"""Offline regression checks: never fetch brands or rewrite the live catalogue."""
import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("updater", ROOT / "scraper/update.py")
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class DailyUpdateCompatibility(unittest.TestCase):
    def test_legacy_patches_leave_new_interface_untouched(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        patched, changes = updater.patch_index_structure(html)
        self.assertEqual(patched, html)
        self.assertEqual(changes, [])

    def test_daily_data_targets_remain_replaceable(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        for pattern, replacement in [
            (r"window\.LIVE_PRODUCTS\s*=\s*\[.*?\];", "window.LIVE_PRODUCTS = [];"),
            (r"window\.LIVE_META\s*=\s*\{.*?\};", 'window.LIVE_META = {"last_updated":"2026-09-20"};'),
        ]:
            html, matches = re.subn(pattern, lambda _: replacement, html, flags=re.DOTALL)
            self.assertEqual(matches, 1)
        self.assertIn('data-ui="sale-finder-v2"', html)
        self.assertIn('src="./assets/app.mjs"', html)
        self.assertIn('id="brandFilter"', html)


if __name__ == "__main__":
    unittest.main()
