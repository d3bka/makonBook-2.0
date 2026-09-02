from pathlib import Path

from unittest import TestCase


ROOT = Path(__file__).resolve().parents[2]
ENG_TEMPLATE = ROOT / "templates/test/shared/attempt_eng.html"
MATH_TEMPLATE = ROOT / "templates/test/shared/attempt_math.html"
THEME_CSS = ROOT / "static/assets/css/sat-test-theme-v49.css"
FOCUS_CSS = ROOT / "static/assets/css/sat-image-focus-v49.css"
FOCUS_JS = ROOT / "static/assets/js/sat-image-focus-v49.js"


class TestRunnerThemeImageFocusV49Tests(TestCase):
    def _template(self, path):
        return path.read_text(encoding="utf-8")

    def test_test_runner_bootstraps_saved_theme_before_styles(self):
        for path in (ENG_TEMPLATE, MATH_TEMPLATE):
            source = self._template(path)
            theme_init = source.index("{% include 'base/theme_init.html' %}")
            first_test_stylesheet = source.index("assets/css/makon-eng.css")
            self.assertLess(theme_init, first_test_stylesheet, path.name)
            self.assertIn("assets/js/makon-theme-switcher.js", source)
            self.assertIn("assets/css/sat-test-theme-v49.css", source)

    def test_both_test_sections_load_image_focus_assets(self):
        for path in (ENG_TEMPLATE, MATH_TEMPLATE):
            source = self._template(path)
            self.assertIn("assets/css/sat-image-focus-v49.css", source)
            self.assertIn("assets/js/sat-image-focus-v49.js", source)

    def test_light_theme_overrides_legacy_dark_test_shell(self):
        css = THEME_CSS.read_text(encoding="utf-8")
        self.assertIn('html[data-theme="light"] body.github-test-template-v20', css)
        self.assertIn(".question-container", css)
        self.assertIn(".choice-container", css)
        self.assertIn(".question-overview-card", css)
        self.assertIn(".test-flow-modal-card.finish-summary-card", css)

    def test_light_theme_keeps_footer_secondary_controls_visible(self):
        css = THEME_CSS.read_text(encoding="utf-8")
        for selector in ("#clear-button", "#pen-button", "#backButton"):
            self.assertIn(selector, css)
        self.assertIn('html[data-theme="light"] body.github-test-template-v20 .footer-right', css)
        self.assertIn("background: #ffffff !important", css)
        self.assertIn("color: #5b21b6 !important", css)
        self.assertIn("#pen-button.active", css)

    def test_test_runner_theme_css_cache_busts_v492(self):
        for path in (ENG_TEMPLATE, MATH_TEMPLATE):
            source = self._template(path)
            self.assertIn("assets/css/sat-test-theme-v49.css' %}?v=49.2", source)

    def test_timer_and_save_status_are_readable_in_light_theme(self):
        css = THEME_CSS.read_text(encoding="utf-8")
        self.assertIn(".github-test-timer-wrap .timer", css)
        self.assertIn("font-variant-numeric: tabular-nums !important", css)
        self.assertIn('html[data-theme="light"] body.github-test-template-v20 .github-test-timer-wrap .timer', css)
        self.assertIn("background: #ffffff !important", css)
        self.assertIn(".timer.is-warning", css)
        self.assertIn(".timer.is-critical", css)
        self.assertIn(".github-test-timer-wrap .test-save-status", css)

    def test_image_focus_covers_question_graphs_and_visual_answers(self):
        js = FOCUS_JS.read_text(encoding="utf-8")
        self.assertIn("#passage img", js)
        self.assertIn("#question-text img", js)
        self.assertIn("#graph-container img", js)
        self.assertIn("#answers img", js)
        self.assertIn("MutationObserver", js)
        self.assertIn("pointerdown", js)
        self.assertIn("wheel", js)

    def test_visual_answer_image_can_receive_click_without_selecting_choice(self):
        css = FOCUS_CSS.read_text(encoding="utf-8")
        js = FOCUS_JS.read_text(encoding="utf-8")
        self.assertIn(".choice-container .sat-focusable-image", css)
        self.assertIn("pointer-events: auto !important", css)
        self.assertIn("event.stopPropagation()", js)
        self.assertIn("event.preventDefault()", js)
