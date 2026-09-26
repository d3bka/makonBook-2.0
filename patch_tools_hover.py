import re

css_path = "static/assets/css/test-math-page.css"
with open(css_path, "r") as f:
    css = f.read()

css = re.sub(
    r"\.header-tool:hover\s*{([^}]+)}",
    r".header-tool:hover {\1 background: var(--sat-purple-2, #7c3aed) !important; color: #fff !important; border-color: var(--sat-purple-2, #7c3aed) !important; }",
    css
)

with open(css_path, "w") as f:
    f.write(css)
