import re

html_path = "templates/test/shared/attempt_math.html"
with open(html_path, "r") as f:
    html = f.read()

# Replace 30-60-90
old_30_60_90 = """<svg viewBox="0 0 130 100" class="ref-svg" style="width: 100px;">
                                    <polygon points="20,70 110,70 110,30" fill="none" stroke="currentColor" stroke-width="1.5"/>
                                    <rect x="105" y="65" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                                    <text x="115" y="55" fill="currentColor" class="ref-svg-text">x</text>
                                    <text x="60" y="85" fill="currentColor" class="ref-svg-text">x√3</text>
                                    <text x="55" y="45" fill="currentColor" class="ref-svg-text">2x</text>
                                    <text x="88" y="65" fill="currentColor" class="ref-svg-text" style="font-size: 11px;">60°</text>
                                    <text x="35" y="65" fill="currentColor" class="ref-svg-text" style="font-size: 11px;">30°</text>
                                </svg>"""
new_30_60_90 = """<svg viewBox="0 0 130 100" class="ref-svg" style="width: 100px;">
                                    <polygon points="20,70 110,70 110,30" fill="none" stroke="currentColor" stroke-width="1.5"/>
                                    <rect x="105" y="65" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                                    <text x="115" y="55" fill="currentColor" class="ref-svg-text">x</text>
                                    <text x="60" y="85" fill="currentColor" class="ref-svg-text">x√3</text>
                                    <text x="55" y="45" fill="currentColor" class="ref-svg-text">2x</text>
                                    <text x="90" y="45" fill="currentColor" class="ref-svg-text" style="font-size: 12px; font-style: normal; font-family: sans-serif;">60°</text>
                                    <text x="38" y="66" fill="currentColor" class="ref-svg-text" style="font-size: 12px; font-style: normal; font-family: sans-serif;">30°</text>
                                </svg>"""
html = html.replace(old_30_60_90, new_30_60_90)

# Replace 45-45-90
old_45_45_90 = """<svg viewBox="0 0 100 100" class="ref-svg" style="width: 75px;">
                                    <polygon points="25,70 75,70 25,20" fill="none" stroke="currentColor" stroke-width="1.5"/>
                                    <rect x="25" y="65" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                                    <text x="15" y="50" fill="currentColor" class="ref-svg-text">s</text>
                                    <text x="50" y="85" fill="currentColor" class="ref-svg-text">s</text>
                                    <text x="55" y="40" fill="currentColor" class="ref-svg-text">s√2</text>
                                    <text x="32" y="65" fill="currentColor" class="ref-svg-text" style="font-size: 11px;">45°</text>
                                    <text x="32" y="40" fill="currentColor" class="ref-svg-text" style="font-size: 11px;">45°</text>
                                </svg>"""
new_45_45_90 = """<svg viewBox="0 0 100 100" class="ref-svg" style="width: 75px;">
                                    <polygon points="25,70 75,70 25,20" fill="none" stroke="currentColor" stroke-width="1.5"/>
                                    <rect x="25" y="65" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                                    <text x="15" y="50" fill="currentColor" class="ref-svg-text">s</text>
                                    <text x="50" y="85" fill="currentColor" class="ref-svg-text">s</text>
                                    <text x="55" y="40" fill="currentColor" class="ref-svg-text">s√2</text>
                                    <text x="50" y="66" fill="currentColor" class="ref-svg-text" style="font-size: 12px; font-style: normal; font-family: sans-serif;">45°</text>
                                    <text x="30" y="40" fill="currentColor" class="ref-svg-text" style="font-size: 12px; font-style: normal; font-family: sans-serif;">45°</text>
                                </svg>"""
html = html.replace(old_45_45_90, new_45_45_90)

with open(html_path, "w") as f:
    f.write(html)
