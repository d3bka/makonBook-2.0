import re

css_path = "static/assets/css/test-math-page.css"
with open(css_path, "r") as f:
    css = f.read()

# Remove explicit background/color from .reference-header
css = re.sub(
    r"\.reference-header\s*{[^}]*}",
    ".reference-header {\n    padding: 16px 18px;\n    display: flex;\n    align-items: center;\n    font-size: 20px;\n    font-weight: 700;\n    border-bottom: 1px solid var(--sat-border, var(--mk-card-border, #e5e7eb));\n}",
    css
)

# Replace .reference-close-btn styles
css = re.sub(
    r"\.reference-close-btn\s*{[^}]*}",
    ".reference-close-btn {\n    border: 1px solid var(--sat-border, var(--mk-card-border, #d1d5db));\n    background: var(--sat-shell, var(--mk-surface-soft, #fff));\n    color: var(--sat-text, var(--mk-text, #111827));\n    width: 36px;\n    height: 36px;\n    border-radius: 10px;\n    font-size: 20px;\n    cursor: pointer;\n}",
    css
)

# Remove background from .reference-body
css = re.sub(
    r"\.reference-body\s*{[^}]*}",
    ".reference-body {\n    padding: 18px;\n    overflow-y: auto;\n    height: calc(100vh - 69px);\n}",
    css
)

# Make sure SVGs and formulas use sat-text
css = css.replace("color: var(--mk-text, #111827);", "color: var(--sat-text, var(--mk-text, #111827));")
css = css.replace("border-top: 1px solid var(--mk-card-border, #e5e7eb);", "border-top: 1px solid var(--sat-border, var(--mk-card-border, #e5e7eb));")

with open(css_path, "w") as f:
    f.write(css)

