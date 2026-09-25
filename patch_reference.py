import re
import os

html_path = "templates/test/shared/attempt_math.html"
with open(html_path, "r") as f:
    html = f.read()

# Locate the reference overlay section
start_tag = '<div id="reference-overlay" class="reference-overlay">'
end_tag = "{% include 'test/shared/flow_overlays.html' %}"

start_idx = html.find(start_tag)
end_idx = html.find(end_tag)

if start_idx == -1 or end_idx == -1:
    print("Could not find reference overlay block.")
    exit(1)

new_ref_html = """<div id="reference-overlay" class="reference-overlay">
    <div class="reference-sheet">
        <div class="reference-header" style="justify-content: center; position: relative;">
            <span style="text-transform: uppercase; font-family: sans-serif; letter-spacing: 1px;">Reference</span>
            <button type="button" class="reference-close-btn" onclick="closeReference()" style="position: absolute; right: 18px;">✕</button>
        </div>

        <div class="reference-body">
            <div class="sat-reference-wrapper">
                <div class="sat-ref-flex">
                    <!-- Row 1: Area -->
                    <div class="ref-item">
                        <svg viewBox="0 0 120 120" class="ref-svg">
                            <circle cx="60" cy="60" r="40" fill="none" stroke="currentColor" stroke-width="2"/>
                            <line x1="60" y1="60" x2="100" y2="60" stroke="currentColor" stroke-width="2"/>
                            <text x="80" y="55" fill="currentColor" class="ref-svg-text">r</text>
                        </svg>
                        <div class="ref-formula">A = πr²<br>C = 2πr</div>
                    </div>
                    
                    <div class="ref-item">
                        <svg viewBox="0 0 120 120" class="ref-svg">
                            <rect x="25" y="40" width="70" height="40" fill="none" stroke="currentColor" stroke-width="2"/>
                            <text x="56" y="32" fill="currentColor" class="ref-svg-text">l</text>
                            <text x="105" y="65" fill="currentColor" class="ref-svg-text">w</text>
                        </svg>
                        <div class="ref-formula">A = lw</div>
                    </div>

                    <div class="ref-item">
                        <svg viewBox="0 0 120 120" class="ref-svg">
                            <polygon points="20,90 100,90 60,30" fill="none" stroke="currentColor" stroke-width="2"/>
                            <line x1="60" y1="30" x2="60" y2="90" stroke="currentColor" stroke-dasharray="4" stroke-width="2"/>
                            <rect x="60" y="85" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                            <text x="45" y="65" fill="currentColor" class="ref-svg-text">h</text>
                            <text x="56" y="105" fill="currentColor" class="ref-svg-text">b</text>
                        </svg>
                        <div class="ref-formula">A = ½bh</div>
                    </div>

                    <div class="ref-item">
                        <svg viewBox="0 0 120 120" class="ref-svg">
                            <polygon points="20,90 90,90 90,30" fill="none" stroke="currentColor" stroke-width="2"/>
                            <rect x="85" y="85" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                            <text x="100" y="65" fill="currentColor" class="ref-svg-text">a</text>
                            <text x="55" y="105" fill="currentColor" class="ref-svg-text">b</text>
                            <text x="45" y="55" fill="currentColor" class="ref-svg-text">c</text>
                        </svg>
                        <div class="ref-formula">c² = a² + b²</div>
                    </div>
                </div>
                
                <!-- Row 2: Special Right Triangles -->
                <div class="ref-section-title">Special Right Triangles</div>
                <div class="sat-ref-flex">
                    <div class="ref-item ref-special">
                        <svg viewBox="0 0 160 120" class="ref-svg" style="width: 140px;">
                            <polygon points="40,90 110,90 110,20" fill="none" stroke="currentColor" stroke-width="2"/>
                            <rect x="105" y="85" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                            <text x="120" y="55" fill="currentColor" class="ref-svg-text">x</text>
                            <text x="75" y="105" fill="currentColor" class="ref-svg-text">x</text>
                            <text x="55" y="45" fill="currentColor" class="ref-svg-text">x√2</text>
                            <text x="90" y="85" fill="currentColor" class="ref-svg-text" font-size="10">45°</text>
                            <text x="95" y="40" fill="currentColor" class="ref-svg-text" font-size="10">45°</text>
                        </svg>
                    </div>
                    <div class="ref-item ref-special">
                        <svg viewBox="0 0 160 120" class="ref-svg" style="width: 160px;">
                            <polygon points="20,90 130,90 130,32" fill="none" stroke="currentColor" stroke-width="2"/>
                            <rect x="125" y="85" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                            <text x="140" y="65" fill="currentColor" class="ref-svg-text">x</text>
                            <text x="75" y="105" fill="currentColor" class="ref-svg-text">x√3</text>
                            <text x="65" y="55" fill="currentColor" class="ref-svg-text">2x</text>
                            <text x="105" y="85" fill="currentColor" class="ref-svg-text" font-size="10">30°</text>
                            <text x="35" y="85" fill="currentColor" class="ref-svg-text" font-size="10">60°</text>
                        </svg>
                    </div>
                </div>

                <!-- Row 3: Volume -->
                <div class="sat-ref-flex">
                    <div class="ref-item">
                        <svg viewBox="0 0 120 120" class="ref-svg">
                            <polygon points="30,80 80,80 100,60 50,60" fill="none" stroke="currentColor" stroke-width="2"/>
                            <polygon points="30,80 80,80 80,30 30,30" fill="none" stroke="currentColor" stroke-width="2"/>
                            <polygon points="80,80 100,60 100,10 80,30" fill="none" stroke="currentColor" stroke-width="2"/>
                            <polygon points="30,30 80,30 100,10 50,10" fill="none" stroke="currentColor" stroke-width="2"/>
                            <text x="15" y="60" fill="currentColor" class="ref-svg-text">h</text>
                            <text x="55" y="95" fill="currentColor" class="ref-svg-text">l</text>
                            <text x="95" y="80" fill="currentColor" class="ref-svg-text">w</text>
                        </svg>
                        <div class="ref-formula">V = lwh</div>
                    </div>

                    <div class="ref-item">
                        <svg viewBox="0 0 120 120" class="ref-svg">
                            <ellipse cx="60" cy="25" rx="30" ry="8" fill="none" stroke="currentColor" stroke-width="2"/>
                            <ellipse cx="60" cy="85" rx="30" ry="8" fill="none" stroke="currentColor" stroke-width="2"/>
                            <line x1="30" y1="25" x2="30" y2="85" stroke="currentColor" stroke-width="2"/>
                            <line x1="90" y1="25" x2="90" y2="85" stroke="currentColor" stroke-width="2"/>
                            <line x1="60" y1="85" x2="90" y2="85" stroke="currentColor" stroke-dasharray="4" stroke-width="2"/>
                            <text x="75" y="80" fill="currentColor" class="ref-svg-text">r</text>
                            <text x="20" y="60" fill="currentColor" class="ref-svg-text">h</text>
                        </svg>
                        <div class="ref-formula">V = πr²h</div>
                    </div>

                    <div class="ref-item">
                        <svg viewBox="0 0 120 120" class="ref-svg">
                            <circle cx="60" cy="60" r="35" fill="none" stroke="currentColor" stroke-width="2"/>
                            <ellipse cx="60" cy="60" rx="35" ry="10" fill="none" stroke="currentColor" stroke-dasharray="4" stroke-width="2"/>
                            <line x1="60" y1="60" x2="95" y2="60" stroke="currentColor" stroke-dasharray="4" stroke-width="2"/>
                            <text x="75" y="55" fill="currentColor" class="ref-svg-text">r</text>
                        </svg>
                        <div class="ref-formula">V = ⁴⁄₃πr³</div>
                    </div>

                    <div class="ref-item">
                        <svg viewBox="0 0 120 120" class="ref-svg">
                            <ellipse cx="60" cy="85" rx="30" ry="8" fill="none" stroke="currentColor" stroke-width="2"/>
                            <line x1="30" y1="85" x2="60" y2="20" stroke="currentColor" stroke-width="2"/>
                            <line x1="90" y1="85" x2="60" y2="20" stroke="currentColor" stroke-width="2"/>
                            <line x1="60" y1="20" x2="60" y2="85" stroke="currentColor" stroke-dasharray="4" stroke-width="2"/>
                            <line x1="60" y1="85" x2="90" y2="85" stroke="currentColor" stroke-dasharray="4" stroke-width="2"/>
                            <rect x="60" y="80" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                            <text x="75" y="80" fill="currentColor" class="ref-svg-text">r</text>
                            <text x="50" y="60" fill="currentColor" class="ref-svg-text">h</text>
                        </svg>
                        <div class="ref-formula">V = ⅓πr²h</div>
                    </div>
                    
                    <div class="ref-item">
                        <svg viewBox="0 0 120 120" class="ref-svg">
                            <polygon points="30,85 80,85 100,70 50,70" fill="none" stroke="currentColor" stroke-width="2"/>
                            <line x1="30" y1="85" x2="65" y2="20" stroke="currentColor" stroke-width="2"/>
                            <line x1="80" y1="85" x2="65" y2="20" stroke="currentColor" stroke-width="2"/>
                            <line x1="100" y1="70" x2="65" y2="20" stroke="currentColor" stroke-width="2"/>
                            <line x1="50" y1="70" x2="65" y2="20" stroke="currentColor" stroke-dasharray="4" stroke-width="2"/>
                            <line x1="65" y1="20" x2="65" y2="77" stroke="currentColor" stroke-dasharray="4" stroke-width="2"/>
                            <rect x="65" y="72" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                            <text x="55" y="60" fill="currentColor" class="ref-svg-text">h</text>
                            <text x="55" y="98" fill="currentColor" class="ref-svg-text">l</text>
                            <text x="95" y="85" fill="currentColor" class="ref-svg-text">w</text>
                        </svg>
                        <div class="ref-formula">V = ⅓lwh</div>
                    </div>
                </div>

                <!-- Footer Notes -->
                <div class="ref-footer">
                    <p>The number of degrees of arc in a circle is 360.</p>
                    <p>The number of radians of arc in a circle is 2π.</p>
                    <p>The sum of the measures in degrees of the angles of a triangle is 180.</p>
                </div>
            </div>
        </div>
    </div>
</div>

"""

new_html = html[:start_idx] + new_ref_html + html[end_idx:]
with open(html_path, "w") as f:
    f.write(new_html)

# CSS Update
css_path = "static/assets/css/test-math-page.css"
with open(css_path, "r") as f:
    css = f.read()

# Delete old CSS
old_css_rules = [
    ".reference-grid", ".reference-card", ".reference-row", ".reference-formulas", 
    ".reference-figure", ".formula", ".reference-note"
]
for rule in old_css_rules:
    pattern = r"\." + rule + r"[\s\S]*?(?=\n\.[a-z]|\n@media|\n\Z)"
    css = re.sub(pattern, "", css)

# Make reference-sheet wider since we want a grid
css = css.replace("width: min(460px, 100%);", "width: min(650px, 100%);")
css = css.replace("height: calc(100vh - 69px);", "height: calc(100vh - 65px);")

new_css = """
.sat-reference-wrapper {
    padding: 10px;
}
.sat-ref-flex {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    justify-content: center;
    align-items: flex-end;
    margin-bottom: 24px;
}
.ref-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    flex: 0 1 120px;
}
.ref-svg {
    width: 100px;
    height: 100px;
    margin-bottom: 4px;
    color: var(--mk-text, #111827);
    stroke-linecap: round;
    stroke-linejoin: round;
}
.ref-svg-text {
    font-family: 'Times New Roman', Times, serif;
    font-style: italic;
    font-size: 16px;
    stroke: none;
}
.ref-formula {
    font-family: 'Times New Roman', Times, serif;
    font-style: italic;
    font-size: 16px;
    color: var(--mk-text, #111827);
    line-height: 1.4;
    white-space: nowrap;
}
.ref-section-title {
    width: 100%;
    text-align: center;
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 8px;
    color: var(--mk-text-muted, #4b5563);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.ref-footer {
    width: 100%;
    margin-top: 30px;
    padding-top: 15px;
    border-top: 1px solid var(--mk-card-border, #e5e7eb);
    text-align: left;
    font-size: 15px;
    color: var(--mk-text, #111827);
    font-family: 'Times New Roman', Times, serif;
    line-height: 1.5;
}
.ref-footer p {
    margin: 6px 0;
}
@media (max-width: 600px) {
    .sat-ref-flex { gap: 10px; margin-bottom: 16px; }
    .ref-item { flex: 0 1 100px; }
    .ref-svg { width: 80px; height: 80px; }
    .ref-formula { font-size: 14px; }
}
"""

css += new_css
with open(css_path, "w") as f:
    f.write(css)

print("Reference Sheet updated.")
