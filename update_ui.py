import re

js_path = "static/assets/js/makon-test-config.js"
with open(js_path, "r") as f:
    content = f.read()

# 1. Update modes array back to 4 main cards
old_modes = """    this.modes = [
      { id: "full_test", title: "Full Test", desc: "All modules (RW + Math)", baseMin: 134, isDefault: true, icon: "bi-bullseye" },
      { id: "rw_only", title: "Reading & Writing Only", desc: "Both RW modules", baseMin: 64, icon: "bi-book" },
      { id: "math_only", title: "Math Only", desc: "Both Math modules", baseMin: 70, icon: "bi-calculator" },
      { id: "single_english", title: "Single RW Module", desc: "Practice one English module", baseMin: 32, icon: "bi-book-half" },
      { id: "single_math", title: "Single Math Module", desc: "Practice one Math module", baseMin: 35, icon: "bi-calculator-fill" }
    ];"""
new_modes = """    this.modes = [
      { id: "full_test", title: "Full Test", desc: "All modules (RW + Math)", baseMin: 134, isDefault: true, icon: "bi-bullseye" },
      { id: "rw_only", title: "Reading & Writing Only", desc: "Both RW modules", baseMin: 64, icon: "bi-book" },
      { id: "math_only", title: "Math Only", desc: "Both Math modules", baseMin: 70, icon: "bi-calculator" },
      { id: "single_module", title: "Single Module", desc: "Practice one module", baseMin: 32, icon: "bi-lightning-charge" }
    ];
    this.subModes = [
      { id: "single_english", title: "Single RW", baseMin: 32 },
      { id: "single_math", title: "Single Math", baseMin: 35 }
    ];"""
content = content.replace(old_modes, new_modes)

# 2. Add the sub-mode HTML logic to _buildDOM
old_dom = """    let modeHtml = this.modes.map(m => `
      <div class="ptc-mode-card ${m.isDefault ? 'is-active' : ''}" data-id="${m.id}">"""
new_dom = """    let modeHtml = this.modes.map(m => `
      <div class="ptc-mode-card ${m.isDefault ? 'is-active' : ''}" data-id="${m.id}">"""
content = content.replace(old_dom, new_dom) # just verifying we can match

old_html_insert = """        <div class="ptc-section-title">What to Practice</div>
        <div class="ptc-mode-grid">${modeHtml}</div>
        <div class="ptc-summary">"""
new_html_insert = """        <div class="ptc-section-title">What to Practice</div>
        <div class="ptc-mode-grid">${modeHtml}</div>
        
        <div class="ptc-submode-container" id="ptc-submode-container" style="display: none; margin-bottom: 24px; animation: ptcFadeIn 0.2s ease-out;">
            <div class="ptc-section-title" style="font-size: 0.95rem; margin-bottom: 12px; margin-top: 4px;">Choose Subject</div>
            <div style="display: flex; gap: 12px;">
                ${this.subModes.map(sm => `
                <div class="ptc-submode-card" data-sub="${sm.id}" style="flex: 1; padding: 12px 16px; border: 2px solid var(--mk-border); border-radius: 12px; cursor: pointer; text-align: center; font-weight: 500; font-size: 0.95rem; color: var(--mk-gray); transition: all 0.2s ease;">
                    ${sm.title}
                </div>
                `).join('')}
            </div>
        </div>

        <div class="ptc-summary">"""
content = content.replace(old_html_insert, new_html_insert)

# 3. Update bindings in _bindEvents
old_bind_mode = """    this.el.querySelectorAll('.ptc-mode-card').forEach(card => {
      card.addEventListener('click', () => {
        this.el.querySelectorAll('.ptc-mode-card').forEach(c => c.classList.remove('is-active'));
        card.classList.add('is-active');
        this.state.mode = card.getAttribute('data-id');
        this._updateUI();
      });
    });"""
new_bind_mode = """    this.el.querySelectorAll('.ptc-mode-card').forEach(card => {
      card.addEventListener('click', () => {
        this.el.querySelectorAll('.ptc-mode-card').forEach(c => c.classList.remove('is-active'));
        card.classList.add('is-active');
        const clickedMode = card.getAttribute('data-id');
        if (clickedMode === 'single_module') {
            this.state.mode = 'single_english'; // default submode
        } else {
            this.state.mode = clickedMode;
        }
        this._updateUI();
      });
    });
    
    this.el.querySelectorAll('.ptc-submode-card').forEach(card => {
        card.addEventListener('click', () => {
            if (!this.state.mode.startsWith('single_')) return;
            this.state.mode = card.getAttribute('data-sub');
            this._updateUI();
        });
    });"""
content = content.replace(old_bind_mode, new_bind_mode)

# 4. Update _updateUI
old_update = """  _updateUI() {
    let currentModeObj = this.modes.find(m => m.id === this.state.mode);
    this.modes.forEach(m => {
      const el = document.getElementById(`ptc-badge-${m.id}`);
      if (el) el.textContent = this._fmt(Math.round(m.baseMin * this.state.multiplier));
    });
    
    const totalMin = Math.round(currentModeObj.baseMin * this.state.multiplier);"""
new_update = """  _updateUI() {
    let isSingle = this.state.mode.startsWith('single_');
    let parentModeId = isSingle ? 'single_module' : this.state.mode;
    
    // Sync main cards
    this.el.querySelectorAll('.ptc-mode-card').forEach(c => c.classList.remove('is-active'));
    let activeMainCard = this.el.querySelector(`.ptc-mode-card[data-id="${parentModeId}"]`);
    if (activeMainCard) activeMainCard.classList.add('is-active');
    
    // Handle submode UI visibility and active states
    const subContainer = document.getElementById('ptc-submode-container');
    if (isSingle) {
        subContainer.style.display = 'block';
        this.el.querySelectorAll('.ptc-submode-card').forEach(c => {
            if (c.getAttribute('data-sub') === this.state.mode) {
                c.style.borderColor = 'var(--mk-text)';
                c.style.color = 'var(--mk-text)';
                c.style.backgroundColor = 'var(--mk-border)';
            } else {
                c.style.borderColor = 'var(--mk-border)';
                c.style.color = 'var(--mk-gray)';
                c.style.backgroundColor = 'transparent';
            }
        });
    } else {
        subContainer.style.display = 'none';
    }

    let currentModeObj = this.modes.find(m => m.id === this.state.mode) || this.subModes.find(m => m.id === this.state.mode);
    this.modes.forEach(m => {
      const el = document.getElementById(`ptc-badge-${m.id}`);
      if (el) el.textContent = this._fmt(Math.round(m.baseMin * this.state.multiplier));
    });
    
    // Special handling to update the badge text on the main 'single_module' card to match the submode
    if (isSingle) {
        const smObj = this.subModes.find(m => m.id === this.state.mode);
        const el = document.getElementById('ptc-badge-single_module');
        if (el) el.textContent = this._fmt(Math.round(smObj.baseMin * this.state.multiplier));
    }
    
    const totalMin = Math.round(currentModeObj.baseMin * this.state.multiplier);"""
content = content.replace(old_update, new_update)

with open(js_path, "w") as f:
    f.write(content)
print("Updated JS UI successfully.")
