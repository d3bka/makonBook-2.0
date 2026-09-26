import re

js_path = "static/assets/js/makon-test-config.js"
with open(js_path, "r") as f:
    js = f.read()

old_submodes = """    this.subModes = [
      { id: "single_english", title: "Single RW", baseMin: 32 },
      { id: "single_math", title: "Single Math", baseMin: 35 }
    ];"""

new_submodes = """    this.subModes = [
      { id: "single_english_m1", title: "Eng M1", baseMin: 32 },
      { id: "single_english_m2", title: "Eng M2", baseMin: 32 },
      { id: "single_math_m1", title: "Math M1", baseMin: 35 },
      { id: "single_math_m2", title: "Math M2", baseMin: 35 }
    ];"""

js = js.replace(old_submodes, new_submodes)

with open(js_path, "w") as f:
    f.write(js)
