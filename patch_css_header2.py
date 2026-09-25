import re

css_path = "static/assets/css/test-math-page.css"
with open(css_path, "r") as f:
    css = f.read()

# Add !important to .reference-header
css = re.sub(
    r"\.reference-header\s*{[^}]*}",
    ".reference-header {\n    padding: 16px 18px;\n    display: flex;\n    align-items: center;\n    font-size: 20px;\n    font-weight: 700;\n    background: var(--sat-shell, var(--mk-surface-soft, #f7f7fb)) !important;\n    color: var(--sat-text, var(--mk-text, #161323)) !important;\n    border-bottom: 1px solid var(--sat-border, var(--mk-card-border, #e5e7eb)) !important;\n}",
    css
)

# Also fix .reference-close-btn
css = re.sub(
    r"\.reference-close-btn\s*{[^}]*}",
    ".reference-close-btn {\n    border: 1px solid var(--sat-border, var(--mk-card-border, #d1d5db)) !important;\n    background: var(--sat-panel, var(--mk-surface, #fff)) !important;\n    color: var(--sat-text, var(--mk-text, #161323)) !important;\n    width: 36px;\n    height: 36px;\n    border-radius: 10px;\n    font-size: 20px;\n    cursor: pointer;\n}",
    css
)

with open(css_path, "w") as f:
    f.write(css)
