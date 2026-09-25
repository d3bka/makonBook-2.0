import re

js_path = "static/assets/js/makon-test-config.js"
with open(js_path, "r") as f:
    js = f.read()

# Replace the title
js = js.replace('title: "English R&W only"', 'title: "English Only"')

with open(js_path, "w") as f:
    f.write(js)
