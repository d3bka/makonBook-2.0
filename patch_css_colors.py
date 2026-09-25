import re

css_path = "static/assets/css/makon-test-config.css"
with open(css_path, "r") as f:
    css = f.read()

# Replace hardcoded variables with smart fallbacks
css = css.replace("var(--sat-panel, #ffffff)", "var(--sat-panel, var(--practice-card, #ffffff))")
css = css.replace("var(--sat-text, #161323)", "var(--sat-text, var(--practice-text, #161323))")
css = css.replace("var(--sat-border, #dcd9e5)", "var(--sat-border, var(--practice-line, #dcd9e5))")
css = css.replace("var(--sat-shell, #f7f7fb)", "var(--sat-shell, var(--practice-bg, #f7f7fb))")
css = css.replace("var(--sat-text, #1e293b)", "var(--sat-text, var(--practice-text, #161323))")
css = css.replace("var(--sat-border, #e2e8f0)", "var(--sat-border, var(--practice-line, #dcd9e5))")
css = css.replace("var(--sat-muted, #6d6879)", "var(--sat-muted, var(--practice-muted, #6d6879))")
css = css.replace("var(--sat-purple, #4f46e5)", "var(--sat-purple, var(--practice-purple, #4f46e5))")
css = css.replace("var(--sat-purple-2, #7c3aed)", "var(--sat-purple, var(--practice-purple, #7c3aed))")
css = css.replace("var(--sat-muted, #475569)", "var(--sat-muted, var(--practice-muted, #6d6879))")
css = css.replace("var(--sat-muted, #94a3b8)", "var(--sat-muted, var(--practice-muted, #94a3b8))")
css = css.replace("var(--sat-text, #0f172a)", "var(--sat-text, var(--practice-text, #0f172a))")
css = css.replace("var(--sat-border, #cbd5e1)", "var(--sat-border, var(--practice-line, #cbd5e1))")
css = css.replace("var(--sat-text, #334155)", "var(--sat-text, var(--practice-text, #334155))")
css = css.replace("var(--sat-shell, #f1f5f9)", "var(--sat-shell, var(--practice-bg, #f1f5f9))")
css = css.replace("var(--sat-shell, #f8fafc)", "var(--sat-shell, var(--practice-bg, #f8fafc))")
css = css.replace("var(--sat-border, #f1f5f9)", "var(--sat-border, var(--practice-line, #f1f5f9))")
css = css.replace("var(--sat-muted, #64748b)", "var(--sat-muted, var(--practice-muted, #64748b))")

# Remove specific html[data-theme="dark"] rules since we use native variables which handle this
css = re.sub(r'html\[data-theme="dark"\].*?{[^}]*}', '', css, flags=re.DOTALL)

# Re-add specific dark mode handling only for specific backgrounds if variables are not enough
new_dark_rules = """
/* Explicit dark theme overrides where variables aren't sufficient */
html[data-theme="dark"] .ptc-speed-card.is-active,
html[data-theme="dark"] .ptc-mode-card.is-active {
    background: rgba(124, 58, 237, 0.15);
}
html[data-theme="dark"] .ptc-btn-start {
    background: var(--sat-purple, var(--practice-purple, #7c3aed));
}
"""
css += new_dark_rules

# Add styles for the newly restored submode cards
css += """
.ptc-submode-card {
    border-color: var(--sat-border, var(--practice-line, #e2e8f0));
    color: var(--sat-muted, var(--practice-muted, #6d6879));
    background: transparent;
}
.ptc-submode-card:hover {
    border-color: var(--sat-purple, var(--practice-purple, #4f46e5));
}
.ptc-submode-card.is-active {
    border-color: var(--sat-purple, var(--practice-purple, #4f46e5));
    color: var(--sat-purple, var(--practice-purple, #4f46e5));
    background: rgba(79, 70, 229, 0.05);
}
html[data-theme="dark"] .ptc-submode-card.is-active {
    background: rgba(124, 58, 237, 0.15);
}
@keyframes ptcFadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
"""

with open(css_path, "w") as f:
    f.write(css)

