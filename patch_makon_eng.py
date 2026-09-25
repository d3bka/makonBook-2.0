import re

css_path = "static/assets/css/makon-eng.css"
with open(css_path, "r") as f:
    css = f.read()

# Remove the weird background pill from question-title
old_block = """body.scroll-hide.mk-test-window .question-title {
    min-height: 56px;
    height: auto;
    padding: 0 12px;
    gap: 12px;
    background: rgba(124, 58, 237, .11) !important;
    border-bottom: 1px solid rgba(196, 181, 253, .18);
    border-radius: 18px;
}"""

new_block = """body.scroll-hide.mk-test-window .question-title {
    min-height: 56px;
    height: auto;
    padding: 0 12px;
    gap: 12px;
    background: transparent !important;
    border: none;
    border-radius: 0;
}"""

css = css.replace(old_block, new_block)

with open(css_path, "w") as f:
    f.write(css)
