import re
import os

html_path = "templates/test/shared/attempt_math.html"
with open(html_path, "r") as f:
    html = f.read()

start_tag = '<div id="reference-overlay" class="reference-overlay">'
end_tag = "{% include 'test/shared/flow_overlays.html' %}"

start_idx = html.find(start_tag)
end_idx = html.find(end_tag)

new_ref_html = """<div id="reference-overlay" class="reference-overlay">
    <div class="reference-sheet">
        <div class="reference-header" style="justify-content: space-between;">
            <span>Reference Sheet</span>
            <button type="button" class="reference-close-btn" onclick="closeReference()">✕</button>
        </div>

        <div class="reference-body">
            <div class="sat-reference-wrapper">
                <div class="sat-ref-flex">
                    <!-- Circle -->
                    <div class="ref-item">
                        <svg viewBox="0 0 100 100" class="ref-svg">
                            <circle cx="50" cy="50" r="35" fill="none" stroke="currentColor" stroke-width="1.5"/>
                            <circle cx="50" cy="50" r="2" fill="currentColor"/>
                            <line x1="50" y1="50" x2="85" y2="50" stroke="currentColor" stroke-width="1.5"/>
                            <text x="67" y="45" fill="currentColor" class="ref-svg-text">r</text>
                        </svg>
                        <div class="ref-formula">A = πr²<br>C = 2πr</div>
                    </div>
                    
                    <!-- Rectangle -->
                    <div class="ref-item">
                        <svg viewBox="0 0 100 100" class="ref-svg">
                            <rect x="20" y="35" width="60" height="35" fill="none" stroke="currentColor" stroke-width="1.5"/>
                            <text x="50" y="30" fill="currentColor" class="ref-svg-text">ℓ</text>
                            <text x="85" y="57" fill="currentColor" class="ref-svg-text">w</text>
                        </svg>
                        <div class="ref-formula">A = ℓw</div>
                    </div>

                    <!-- Triangle -->
                    <div class="ref-item">
                        <svg viewBox="0 0 100 100" class="ref-svg">
                            <polygon points="20,70 80,70 45,25" fill="none" stroke="currentColor" stroke-width="1.5"/>
                            <line x1="45" y1="25" x2="45" y2="70" stroke="currentColor" stroke-dasharray="3" stroke-width="1.5"/>
                            <rect x="45" y="65" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                            <text x="52" y="55" fill="currentColor" class="ref-svg-text">h</text>
                            <text x="50" y="85" fill="currentColor" class="ref-svg-text">b</text>
                        </svg>
                        <div class="ref-formula">A = <span class="math-frac"><span class="math-num">1</span><span class="math-den">2</span></span>bh</div>
                    </div>

                    <!-- Right Triangle -->
                    <div class="ref-item">
                        <svg viewBox="0 0 100 100" class="ref-svg">
                            <polygon points="25,70 85,70 25,30" fill="none" stroke="currentColor" stroke-width="1.5"/>
                            <rect x="25" y="65" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                            <text x="15" y="55" fill="currentColor" class="ref-svg-text">b</text>
                            <text x="55" y="85" fill="currentColor" class="ref-svg-text">a</text>
                            <text x="57" y="45" fill="currentColor" class="ref-svg-text">c</text>
                        </svg>
                        <div class="ref-formula">c² = a² + b²</div>
                    </div>
                    
                    <!-- Special Right Triangles container -->
                    <div class="ref-special-container" style="display: flex; flex-direction: column; align-items: center; margin-top: 10px;">
                        <div style="display: flex; gap: 15px; align-items: flex-end;">
                            <div class="ref-item ref-special" style="width: auto;">
                                <svg viewBox="0 0 130 100" class="ref-svg" style="width: 100px;">
                                    <polygon points="20,70 110,70 110,30" fill="none" stroke="currentColor" stroke-width="1.5"/>
                                    <rect x="105" y="65" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                                    <text x="115" y="55" fill="currentColor" class="ref-svg-text">x</text>
                                    <text x="60" y="85" fill="currentColor" class="ref-svg-text">x√3</text>
                                    <text x="55" y="45" fill="currentColor" class="ref-svg-text">2x</text>
                                    <text x="88" y="65" fill="currentColor" class="ref-svg-text" style="font-size: 11px;">60°</text>
                                    <text x="35" y="65" fill="currentColor" class="ref-svg-text" style="font-size: 11px;">30°</text>
                                </svg>
                            </div>
                            <div class="ref-item ref-special" style="width: auto;">
                                <svg viewBox="0 0 100 100" class="ref-svg" style="width: 75px;">
                                    <polygon points="25,70 75,70 25,20" fill="none" stroke="currentColor" stroke-width="1.5"/>
                                    <rect x="25" y="65" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                                    <text x="15" y="50" fill="currentColor" class="ref-svg-text">s</text>
                                    <text x="50" y="85" fill="currentColor" class="ref-svg-text">s</text>
                                    <text x="55" y="40" fill="currentColor" class="ref-svg-text">s√2</text>
                                    <text x="32" y="65" fill="currentColor" class="ref-svg-text" style="font-size: 11px;">45°</text>
                                    <text x="32" y="40" fill="currentColor" class="ref-svg-text" style="font-size: 11px;">45°</text>
                                </svg>
                            </div>
                        </div>
                        <div style="font-weight: 700; font-family: 'Times New Roman', Times, serif; font-size: 16px; margin-top: 5px;">Special Right Triangles</div>
                    </div>

                    <!-- Rectangular Prism -->
                    <div class="ref-item">
                        <svg viewBox="0 0 120 100" class="ref-svg">
                            <polygon points="25,65 75,65 75,40 25,40" fill="none" stroke="currentColor" stroke-width="1.5"/>
                            <polygon points="25,40 75,40 95,25 45,25" fill="none" stroke="currentColor" stroke-width="1.5"/>
                            <polygon points="75,65 95,50 95,25 75,40" fill="none" stroke="currentColor" stroke-width="1.5"/>
                            <text x="50" y="80" fill="currentColor" class="ref-svg-text">ℓ</text>
                            <text x="88" y="70" fill="currentColor" class="ref-svg-text">w</text>
                            <text x="100" y="45" fill="currentColor" class="ref-svg-text">h</text>
                        </svg>
                        <div class="ref-formula">V = ℓwh</div>
                    </div>

                    <!-- Cylinder -->
                    <div class="ref-item">
                        <svg viewBox="0 0 100 100" class="ref-svg">
                            <ellipse cx="50" cy="30" rx="30" ry="10" fill="none" stroke="currentColor" stroke-width="1.5"/>
                            <circle cx="50" cy="30" r="2" fill="currentColor"/>
                            <line x1="50" y1="30" x2="80" y2="30" stroke="currentColor" stroke-width="1.5"/>
                            <text x="65" y="25" fill="currentColor" class="ref-svg-text">r</text>
                            <path d="M 20,30 L 20,70 A 30,10 0 0,0 80,70 L 80,30" fill="none" stroke="currentColor" stroke-width="1.5"/>
                            <text x="85" y="55" fill="currentColor" class="ref-svg-text">h</text>
                        </svg>
                        <div class="ref-formula">V = πr²h</div>
                    </div>

                    <!-- Sphere -->
                    <div class="ref-item">
                        <svg viewBox="0 0 100 100" class="ref-svg">
                            <circle cx="50" cy="50" r="30" fill="none" stroke="currentColor" stroke-width="1.5"/>
                            <path d="M 20,50 A 30,10 0 0,1 80,50" fill="none" stroke="currentColor" stroke-dasharray="3" stroke-width="1.5"/>
                            <path d="M 20,50 A 30,10 0 0,0 80,50" fill="none" stroke="currentColor" stroke-width="1.5"/>
                            <circle cx="50" cy="50" r="2" fill="currentColor"/>
                            <line x1="50" y1="50" x2="80" y2="50" stroke="currentColor" stroke-dasharray="3" stroke-width="1.5"/>
                            <text x="65" y="45" fill="currentColor" class="ref-svg-text">r</text>
                        </svg>
                        <div class="ref-formula">V = <span class="math-frac"><span class="math-num">4</span><span class="math-den">3</span></span>πr³</div>
                    </div>

                    <!-- Cone -->
                    <div class="ref-item">
                        <svg viewBox="0 0 100 100" class="ref-svg">
                            <path d="M 20,70 A 30,10 0 0,1 80,70" fill="none" stroke="currentColor" stroke-dasharray="3" stroke-width="1.5"/>
                            <path d="M 20,70 A 30,10 0 0,0 80,70" fill="none" stroke="currentColor" stroke-width="1.5"/>
                            <line x1="20" y1="70" x2="50" y2="20" stroke="currentColor" stroke-width="1.5"/>
                            <line x1="80" y1="70" x2="50" y2="20" stroke="currentColor" stroke-width="1.5"/>
                            <line x1="50" y1="20" x2="50" y2="70" stroke="currentColor" stroke-dasharray="3" stroke-width="1.5"/>
                            <circle cx="50" cy="70" r="2" fill="currentColor"/>
                            <line x1="50" y1="70" x2="80" y2="70" stroke="currentColor" stroke-dasharray="3" stroke-width="1.5"/>
                            <rect x="50" y="65" width="5" height="5" fill="none" stroke="currentColor" stroke-width="1"/>
                            <text x="65" y="65" fill="currentColor" class="ref-svg-text">r</text>
                            <text x="40" y="50" fill="currentColor" class="ref-svg-text">h</text>
                        </svg>
                        <div class="ref-formula">V = <span class="math-frac"><span class="math-num">1</span><span class="math-den">3</span></span>πr²h</div>
                    </div>
                    
                    <!-- Pyramid -->
                    <div class="ref-item">
                        <svg viewBox="0 0 110 100" class="ref-svg">
                            <polygon points="20,75 70,75 90,60" fill="none" stroke="currentColor" stroke-width="1.5"/>
                            <polyline points="20,75 40,60 90,60" fill="none" stroke="currentColor" stroke-dasharray="3" stroke-width="1.5"/>
                            <line x1="20" y1="75" x2="55" y2="25" stroke="currentColor" stroke-width="1.5"/>
                            <line x1="70" y1="75" x2="55" y2="25" stroke="currentColor" stroke-width="1.5"/>
                            <line x1="90" y1="60" x2="55" y2="25" stroke="currentColor" stroke-width="1.5"/>
                            <line x1="40" y1="60" x2="55" y2="25" stroke="currentColor" stroke-dasharray="3" stroke-width="1.5"/>
                            <line x1="55" y1="25" x2="55" y2="67.5" stroke="currentColor" stroke-dasharray="3" stroke-width="1.5"/>
                            <rect x="55" y="62.5" width="4" height="4" fill="none" stroke="currentColor" stroke-width="1"/>
                            <text x="47" y="50" fill="currentColor" class="ref-svg-text">h</text>
                            <text x="45" y="88" fill="currentColor" class="ref-svg-text">ℓ</text>
                            <text x="85" y="75" fill="currentColor" class="ref-svg-text">w</text>
                        </svg>
                        <div class="ref-formula">V = <span class="math-frac"><span class="math-num">1</span><span class="math-den">3</span></span>ℓwh</div>
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

new_html_content = html[:start_idx] + new_ref_html + html[end_idx:]
with open(html_path, "w") as f:
    f.write(new_html_content)


css_path = "static/assets/css/test-math-page.css"
with open(css_path, "r") as f:
    css = f.read()

# Revert width back to original min(460px, 100%)
css = css.replace("width: min(650px, 100%);", "width: min(460px, 100%);")

# Append new math-frac styles
new_css = """
.math-frac {
    display: inline-block;
    vertical-align: middle;
    text-align: center;
    font-size: 0.8em;
    margin: 0 1px;
}
.math-num {
    display: block;
    border-bottom: 1.5px solid currentColor;
    line-height: 1.2;
    padding: 0 1px;
}
.math-den {
    display: block;
    line-height: 1.2;
    padding: 0 1px;
}
"""
if ".math-frac" not in css:
    css += new_css

with open(css_path, "w") as f:
    f.write(css)

print("Patch applied.")
