import re

css_path = "static/assets/css/test-math-page.css"
with open(css_path, "r") as f:
    css = f.read()

rule = """
/* Force correct styles on math tools by overriding ID specificity */
body.scroll-hide.mk-test-window #open-reference,
body.scroll-hide.mk-test-window #open-calculator,
body.scroll-hide.mk-test-window header > a[data-test-exit] {
    border-radius: 50% !important;
    background: var(--sat-panel, rgba(124, 58, 237, 0.1)) !important;
    border: 1px solid var(--sat-border, rgba(255, 255, 255, 0.1)) !important;
    color: var(--sat-text, #ffffff) !important;
    cursor: pointer !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
}

body.scroll-hide.mk-test-window #open-reference:hover,
body.scroll-hide.mk-test-window #open-calculator:hover,
body.scroll-hide.mk-test-window header > a[data-test-exit]:hover {
    background: var(--sat-purple-2, #7c3aed) !important;
    color: #ffffff !important;
    border-color: var(--sat-purple-2, #7c3aed) !important;
}

body.scroll-hide.mk-test-window #open-reference i,
body.scroll-hide.mk-test-window #open-calculator i,
body.scroll-hide.mk-test-window header > a[data-test-exit] i {
    color: inherit !important;
}
"""

if "body.scroll-hide.mk-test-window #open-reference" not in css:
    css += rule
    with open(css_path, "w") as f:
        f.write(css)
