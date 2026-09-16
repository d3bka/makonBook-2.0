from pathlib import Path
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]


class MobileTestRunnerV50Tests(SimpleTestCase):
    def test_written_math_answer_does_not_force_decimal_keyboard(self):
        js = (ROOT / "static/assets/js/test-math.js").read_text(encoding="utf-8")
        self.assertIn('inputmode="text"', js)
        self.assertNotIn('inputmode="decimal"', js)
        self.assertIn('data-written-symbol="/"', js)
        self.assertIn("setRangeText(symbol", js)

    def test_phone_runner_uses_single_scroll_flow(self):
        css = (ROOT / "static/assets/css/makon-exam-responsive-v2.css").read_text(encoding="utf-8")
        self.assertIn("v2.1 — phone test runner polish", css)
        self.assertIn("display: block !important;", css)
        self.assertIn("overflow-y: auto !important;", css)
        self.assertIn("sat-keyboard-open footer", css)

    def test_mobile_assets_are_cache_bumped(self):
        responsive = (ROOT / "templates/base/responsive_css.html").read_text(encoding="utf-8")
        math_template = (ROOT / "templates/test/shared/attempt_math.html").read_text(encoding="utf-8")
        self.assertIn("makon-exam-responsive-v2.css' %}?v=4", responsive)
        self.assertIn("assets/js/test-math.js' %}?v=28", math_template)
