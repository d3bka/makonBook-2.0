import re

html_path = "templates/test/shared/attempt_math.html"
with open(html_path, "r") as f:
    html = f.read()

# Replace Special Right Triangles container
old_container_start = "<!-- Special Right Triangles container -->"
old_container_end = "<!-- Rectangular Prism -->"

# Find boundaries
start_idx = html.find(old_container_start)
end_idx = html.find(old_container_end)

if start_idx == -1 or end_idx == -1:
    print("Could not find Special Right Triangles block.")
    exit(1)

new_special_html = """<!-- Special Right Triangles container -->
                    <div class="ref-special-container" style="display: flex; flex-direction: column; align-items: center; margin-top: 10px;">
                        <div style="display: flex; gap: 15px; align-items: flex-end;">
                            <!-- 30-60-90 -->
                            <div class="ref-item ref-special" style="width: auto;">
                                <svg viewBox="0 0 240 170" class="ref-svg" style="width: 130px; height: auto;">
                                    <polygon points="20,130 193,130 193,30" fill="none" stroke="currentColor" stroke-width="2"/>
                                    <polyline points="183,130 183,120 193,120" fill="none" stroke="currentColor" stroke-width="2"/>
                                    
                                    <!-- Base text -->
                                    <text x="106" y="160" fill="currentColor" class="ref-svg-text" style="font-size: 22px;">x√3</text>
                                    <!-- Height text -->
                                    <text x="205" y="85" fill="currentColor" class="ref-svg-text" style="font-size: 22px;">x</text>
                                    <!-- Hypotenuse text -->
                                    <text x="80" y="65" fill="currentColor" class="ref-svg-text" style="font-size: 22px;">2x</text>
                                    
                                    <!-- Angles -->
                                    <text x="160" y="60" fill="currentColor" style="font-size: 16px; font-family: sans-serif;">60°</text>
                                    <text x="55" y="122" fill="currentColor" style="font-size: 16px; font-family: sans-serif;">30°</text>
                                </svg>
                            </div>
                            <!-- 45-45-90 -->
                            <div class="ref-item ref-special" style="width: auto;">
                                <svg viewBox="0 0 180 170" class="ref-svg" style="width: 95px; height: auto;">
                                    <polygon points="30,130 130,130 30,30" fill="none" stroke="currentColor" stroke-width="2.5"/>
                                    <polyline points="30,118 42,118 42,130" fill="none" stroke="currentColor" stroke-width="2.5"/>
                                    
                                    <!-- Base text -->
                                    <text x="75" y="160" fill="currentColor" class="ref-svg-text" style="font-size: 26px;">s</text>
                                    <!-- Height text -->
                                    <text x="5" y="85" fill="currentColor" class="ref-svg-text" style="font-size: 26px;">s</text>
                                    <!-- Hypotenuse text -->
                                    <text x="95" y="65" fill="currentColor" class="ref-svg-text" style="font-size: 26px;">s√2</text>
                                    
                                    <!-- Angles -->
                                    <text x="85" y="122" fill="currentColor" style="font-size: 18px; font-family: sans-serif;">45°</text>
                                    <text x="38" y="75" fill="currentColor" style="font-size: 18px; font-family: sans-serif;">45°</text>
                                </svg>
                            </div>
                        </div>
                        <div style="font-weight: 700; font-family: 'Times New Roman', Times, serif; font-size: 17px; margin-top: 8px; color: var(--mk-text, #111827);">Special Right Triangles</div>
                    </div>

                    """

html = html[:start_idx] + new_special_html + html[end_idx:]

with open(html_path, "w") as f:
    f.write(html)
