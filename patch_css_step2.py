import re

css_path = "static/assets/css/makon-test-config.css"
with open(css_path, "r") as f:
    css = f.read()

# Replace gray colors with Satmakon purples and fix margins for compactness

new_css = """
.ptc-overlay {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(0,0,0,0.4); z-index: 1050;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; pointer-events: none; transition: opacity 0.2s;
  backdrop-filter: blur(4px);
}
.ptc-overlay.is-open { opacity: 1; pointer-events: auto; }
.ptc-dialog {
  background: var(--sat-panel, #ffffff); color: var(--sat-text, #161323);
  width: 94%; max-width: 680px; max-height: 95vh;
  border-radius: 16px; overflow-y: auto; padding: 24px 28px;
  box-shadow: 0 20px 40px rgba(0,0,0,0.25);
  font-family: inherit;
  border: 1px solid var(--sat-border, #dcd9e5);
}
.ptc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; display: none; }
.ptc-section-title { font-size: 1rem; font-weight: 700; margin-bottom: 12px; margin-top: 16px; color: var(--sat-text, #1e293b); }
.ptc-section-title:first-child { margin-top: 0; }
.ptc-speed-row { display: flex; gap: 8px; margin-bottom: 20px; }
.ptc-speed-card {
  flex: 1; padding: 12px 6px; border: 1.5px solid var(--sat-border, #e2e8f0);
  border-radius: 12px; text-align: center; cursor: pointer; transition: all 0.2s;
  background: var(--sat-shell, #f7f7fb); user-select: none;
  display: flex; flex-direction: column; align-items: center; justify-content: flex-start;
}
.ptc-speed-card i { font-size: 1.2rem; color: var(--sat-muted, #6d6879); margin-bottom: 6px; }
.ptc-speed-card.is-active i { color: var(--sat-purple, #4f46e5); }
html[data-theme="dark"] .ptc-speed-card.is-active i { color: var(--sat-purple-2, #7c3aed); }

.ptc-speed-val { font-size: 0.9rem; font-weight: 600; color: var(--sat-text, #161323); line-height: 1.2; margin-bottom: 2px; }
.ptc-speed-sub { font-size: 0.75rem; color: var(--sat-muted, #6d6879); line-height: 1.2; }

.ptc-speed-card:hover { border-color: var(--sat-purple, #4f46e5); }
html[data-theme="dark"] .ptc-speed-card:hover { border-color: var(--sat-purple-2, #7c3aed); }

.ptc-speed-card.is-active {
  border-color: var(--sat-purple, #4f46e5);
  background: rgba(79, 70, 229, 0.05);
}
html[data-theme="dark"] .ptc-speed-card.is-active {
  border-color: var(--sat-purple-2, #7c3aed); background: rgba(124, 58, 237, 0.15);
}

.ptc-mode-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 540px) { .ptc-mode-grid { grid-template-columns: 1fr; } }
.ptc-mode-card {
  display: flex; gap: 12px; padding: 14px; border: 1.5px solid var(--sat-border, #e2e8f0);
  border-radius: 12px; cursor: pointer; transition: all 0.2s; background: var(--sat-shell, #f7f7fb);
  align-items: center;
}
.ptc-mode-card:hover { border-color: var(--sat-purple, #4f46e5); }
html[data-theme="dark"] .ptc-mode-card:hover { border-color: var(--sat-purple-2, #7c3aed); }

.ptc-mode-card.is-active { border-color: var(--sat-purple, #4f46e5); background: rgba(79, 70, 229, 0.05); }
html[data-theme="dark"] .ptc-mode-card.is-active { border-color: var(--sat-purple-2, #7c3aed); background: rgba(124, 58, 237, 0.15); }

.ptc-radio-wrapper { display: flex; align-items: center; justify-content: center; height: 24px; }
.ptc-radio { width: 18px; height: 18px; border: 2px solid var(--sat-muted, #94a3b8); border-radius: 50%; position: relative; transition: all 0.2s; }
.ptc-mode-card.is-active .ptc-radio { border-color: var(--sat-purple, #4f46e5); }
html[data-theme="dark"] .ptc-mode-card.is-active .ptc-radio { border-color: var(--sat-purple-2, #7c3aed); }

.ptc-mode-card.is-active .ptc-radio::after {
  content: ""; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 8px; height: 8px;
  background: var(--sat-purple, #4f46e5); border-radius: 50%;
}
html[data-theme="dark"] .ptc-mode-card.is-active .ptc-radio::after { background: var(--sat-purple-2, #7c3aed); }

.ptc-mode-info { flex: 1; display: flex; align-items: center; justify-content: space-between; overflow: hidden; }
.ptc-mode-title-wrapper { display: flex; align-items: center; gap: 8px; overflow: hidden; }
.ptc-mode-icon { color: var(--sat-muted, #475569); font-size: 1.1rem; flex-shrink: 0; }
html[data-theme="dark"] .ptc-mode-icon { color: var(--sat-muted, #94a3b8); }
.ptc-mode-card.is-active .ptc-mode-icon { color: var(--sat-purple, #4f46e5); }
html[data-theme="dark"] .ptc-mode-card.is-active .ptc-mode-icon { color: var(--sat-purple-2, #7c3aed); }

.ptc-mode-title { font-weight: 600; font-size: 1rem; color: var(--sat-text, #161323); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-transform: uppercase; }
.ptc-mode-desc { display: none; } /* Hide description to make it compact */

.ptc-badge { display: inline-block; padding: 4px 10px; font-size: 0.8rem; background: var(--sat-amber, #f59e0b); color: #fff; border-radius: 6px; font-weight: 700; flex-shrink: 0; }

.ptc-summary { margin-top: 20px; padding: 16px 20px; background: var(--sat-shell, #f8fafc); border-radius: 12px; display: flex; justify-content: space-between; align-items: center; border: 1px solid var(--sat-border, #f1f5f9);}
.ptc-summary-label { font-size: 0.85rem; color: var(--sat-muted, #64748b); font-weight: 600; margin-bottom: 2px; }
.ptc-summary-val { font-size: 1.5rem; font-weight: 700; color: var(--sat-text, #0f172a); }

.ptc-footer { display: flex; justify-content: flex-end; gap: 12px; margin-top: 20px; }
.ptc-btn { padding: 10px 20px; border-radius: 8px; font-weight: 600; cursor: pointer; border: none; font-size: 0.95rem; transition: all 0.2s;}
.ptc-btn-cancel { background: transparent; border: 1px solid var(--sat-border, #cbd5e1); color: var(--sat-text, #334155); }
.ptc-btn-cancel:hover { background: var(--sat-shell, #f1f5f9); }

.ptc-btn-start { background: var(--sat-purple, #4f46e5); color: #fff; display: flex; align-items: center; gap: 8px; }
html[data-theme="dark"] .ptc-btn-start { background: var(--sat-purple-2, #7c3aed); color: #fff; }
.ptc-btn-start:hover { opacity: 0.9; transform: translateY(-1px); }

.ptc-btn-start:disabled { opacity: 0.7; cursor: not-allowed; transform: none; }
.ptc-spinner { display: none; width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff; border-radius: 50%; animation: ptc-spin 1s linear infinite; }
.ptc-btn-start.is-loading .ptc-spinner { display: inline-block; }
.ptc-btn-start.is-loading i.bi-play-fill { display: none; }
.ptc-btn-start.is-loading span { opacity: 0.8; }
@keyframes ptc-spin { to { transform: rotate(360deg); } }
"""

with open(css_path, "w") as f:
    f.write(new_css)
