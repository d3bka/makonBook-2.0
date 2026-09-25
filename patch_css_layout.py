import re

css_path = "static/assets/css/test-math-page.css"
with open(css_path, "r") as f:
    css = f.read()

# Add a robust centering rule for math when there's no context (no passage/graph)
centering_rule = """

/* Force center alignment for math questions without a passage or graph */
body.sat-math-no-context main {
    display: flex !important;
    justify-content: center !important;
}

body.sat-math-no-context .answers-container {
    flex: none !important;
    width: 100% !important;
    max-width: 900px !important;
    margin: 0 auto !important;
    border-left: none !important;
    border-right: none !important;
    padding-left: 20px !important;
    padding-right: 20px !important;
}

body.sat-math-no-context .question-title {
    width: 100% !important;
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    flex-wrap: nowrap !important;
    gap: 12px !important;
    overflow: hidden !important;
}

body.sat-math-no-context .bookmark {
    flex: 0 1 auto !important;
    white-space: nowrap !important;
}

body.sat-math-no-context .crossing-options {
    flex: 0 0 42px !important;
    margin-left: auto !important;
}
"""

if "body.sat-math-no-context main" not in css:
    css += centering_rule

with open(css_path, "w") as f:
    f.write(css)
