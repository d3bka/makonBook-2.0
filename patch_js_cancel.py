import re

js_path = "static/assets/js/makon-test-config.js"
with open(js_path, "r") as f:
    js = f.read()

old_close = """  close() {
    this.el.classList.remove('is-open');
    const btn = this.el.querySelector('#ptc-btn-start');
    if (btn) {
        btn.classList.remove('is-loading');
        btn.disabled = false;
    }
  }"""

new_close = """  close() {
    this.el.classList.remove('is-open');
    const btn = this.el.querySelector('#ptc-btn-start');
    if (btn) {
        btn.classList.remove('is-loading');
        btn.disabled = false;
    }
    // Fire pageshow event to reset the dashboard "Opening..." button and unlock navigation
    window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }));
  }"""

js = js.replace(old_close, new_close)

with open(js_path, "w") as f:
    f.write(js)
