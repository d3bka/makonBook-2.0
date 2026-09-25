import re

css_path = "static/assets/css/test-math-page.css"
with open(css_path, "r") as f:
    css = f.read()

# Remove .home-link padding
css = re.sub(r"\.home-link\s*{\s*padding-right:\s*14px;\s*}", "", css)

# Make sure icons are strictly centered
css = re.sub(
    r"\.header-tool\s+i\s*{[^}]*}",
    ".header-tool i {\n    font-size: 16px;\n    margin: 0 !important;\n    padding: 0 !important;\n    line-height: 1 !important;\n    display: flex;\n    align-items: center;\n    justify-content: center;\n}",
    css
)

# And ensure the button itself is perfectly flex-centered with no padding
css = re.sub(
    r"\.header-tool\s*{([^}]*)}",
    lambda m: ".header-tool {" + re.sub(r'padding:[^;]+;', '', m.group(1)) + " padding: 0 !important; }",
    css
)

with open(css_path, "w") as f:
    f.write(css)
