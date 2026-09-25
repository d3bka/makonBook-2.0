import re

css_path = "static/assets/css/test-math-page.css"
with open(css_path, "r") as f:
    css = f.read()

# Fix the hardcoded white icons
old_icon_block = """.math-header-tools .math-tool-btn i,
.header-tools .header-tool i,
.math-tool-btn i,
.header-tool i,
.math-tool-home i,
.fa-home {
    color: #ffffff !important;
    opacity: 1 !important;
}"""

new_icon_block = """.math-header-tools .math-tool-btn i,
.header-tools .header-tool i,
.math-tool-btn i,
.header-tool i,
.math-tool-home i,
.fa-home {
    color: inherit;
    opacity: 1 !important;
}"""

css = css.replace(old_icon_block, new_icon_block)

with open(css_path, "w") as f:
    f.write(css)
