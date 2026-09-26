import re

css_path = "static/assets/css/test-math-page.css"
with open(css_path, "r") as f:
    css = f.read()

# Replace all background and color for .header-tool with theme variables
css = re.sub(
    r"background:\s*rgba\(124,\s*58,\s*237,\s*0\.1\);",
    "background: var(--sat-panel, rgba(124, 58, 237, 0.1)) !important; border: 1px solid var(--sat-border, rgba(124, 58, 237, 0.2)) !important;",
    css
)

css = re.sub(
    r"color:\s*var\(--sat-purple-2,\s*#7c3aed\);",
    "color: var(--sat-text, var(--sat-purple-2, #7c3aed)) !important;",
    css
)

with open(css_path, "w") as f:
    f.write(css)
