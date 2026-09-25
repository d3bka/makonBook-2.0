import re

css_path = "static/assets/css/test-math-page.css"
with open(css_path, "r") as f:
    css = f.read()

# Fix header tool color
css = re.sub(
    r"\.header-tool\s*{[^}]*}",
    ".header-tool {\n    display: flex;\n    align-items: center;\n    justify-content: center;\n    width: 38px;\n    height: 38px;\n    border-radius: 50%;\n    background: rgba(124, 58, 237, 0.1);\n    color: var(--sat-purple-2, #7c3aed);\n    text-decoration: none;\n    box-sizing: border-box;\n    transition: transform .15s ease, opacity .15s ease, box-shadow .15s ease, background .15s ease;\n}",
    css
)

css = re.sub(
    r"\.header-tool:hover\s*{[^}]*}",
    ".header-tool:hover {\n    color: #fff;\n    background: var(--sat-purple-2, #7c3aed);\n    opacity: 0.96;\n    transform: translateY(-1px);\n    box-shadow: 0 10px 18px rgba(61, 0, 142, 0.18);\n}",
    css
)

with open(css_path, "w") as f:
    f.write(css)
