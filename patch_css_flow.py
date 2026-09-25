import re

css_path = "static/assets/css/sat-test-flow-v13.css"
with open(css_path, "r") as f:
    css = f.read()

# Fix bookmark stretching
old_bookmark_rule = ".sat-flow-page .bookmark,.sat-flow-page .crossing-options{position:static!important;height:42px!important;border:1px solid var(--sat-border)!important;border-radius:12px!important;background:var(--sat-panel)!important;color:var(--sat-text)!important;display:inline-flex!important;align-items:center;gap:8px;padding:0 13px!important;cursor:pointer;font-size:13px;font-weight:800}"
new_bookmark_rule = ".sat-flow-page .bookmark-container { flex: 0 0 auto; margin-right: auto; } .sat-flow-page .bookmark,.sat-flow-page .crossing-options{position:static!important;height:42px!important;width:auto!important;max-width:max-content!important;flex:0 0 auto!important;border:1px solid var(--sat-border)!important;border-radius:12px!important;background:var(--sat-panel)!important;color:var(--sat-text)!important;display:inline-flex!important;align-items:center;justify-content:center;gap:8px;padding:0 13px!important;cursor:pointer;font-size:13px;font-weight:800}"

if old_bookmark_rule in css:
    css = css.replace(old_bookmark_rule, new_bookmark_rule)
else:
    # If already modified or slightly different, use regex
    css = re.sub(
        r"\.sat-flow-page \.bookmark,\.sat-flow-page \.crossing-options\s*{[^}]*}",
        ".sat-flow-page .bookmark,.sat-flow-page .crossing-options{position:static!important;height:42px!important;width:auto!important;max-width:max-content!important;flex:0 0 auto!important;border:1px solid var(--sat-border)!important;border-radius:12px!important;background:var(--sat-panel)!important;color:var(--sat-text)!important;display:inline-flex!important;align-items:center;justify-content:center;gap:8px;padding:0 13px!important;cursor:pointer;font-size:13px;font-weight:800}",
        css
    )
    css += "\n.sat-flow-page .bookmark-container { flex: 0 0 auto; margin-right: auto; }\n"

with open(css_path, "w") as f:
    f.write(css)
