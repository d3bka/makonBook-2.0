import re
js_path = "static/assets/js/makon-test-config.js"
with open(js_path, "r") as f:
    js = f.read()

# Replace modes
old_modes_block = """    this.modes = [
      { id: "full_test", title: "Full Test", desc: "All modules (RW + Math)", baseMin: 134, isDefault: true, icon: "bi-bullseye" },
      { id: "rw_only", title: "Reading & Writing Only", desc: "Both RW modules", baseMin: 64, icon: "bi-book" },
      { id: "math_only", title: "Math Only", desc: "Both Math modules", baseMin: 70, icon: "bi-calculator" },
      { id: "single_module", title: "Single Module", desc: "Practice one module", baseMin: 32, icon: "bi-lightning-charge" }
    ];
    this.subModes = [
      { id: "single_english", title: "Single RW", baseMin: 32 },
      { id: "single_math", title: "Single Math", baseMin: 35 }
    ];
    this.state = { multiplier: 1.0, mode: "full_test", testName: null, classroomId: null };"""
new_modes_block = """    this.modes = [
      { id: "m1_ebrw", title: "m1 ebrw", desc: "Module 1", baseMin: 32, isDefault: true, icon: "bi-book" },
      { id: "m2_ebrw", title: "m2 ebrw", desc: "Module 2", baseMin: 32, icon: "bi-book" },
      { id: "m1_math", title: "m1 math", desc: "Module 1", baseMin: 35, icon: "bi-calculator" },
      { id: "m2_math", title: "m2 math", desc: "Module 2", baseMin: 35, icon: "bi-calculator" }
    ];
    this.state = { multiplier: 1.0, mode: "m1_ebrw", testName: null, classroomId: null };"""
js = js.replace(old_modes_block, new_modes_block)

# Replace "What to Practice" with "Choose module"
# and remove the submode container
js = js.replace('<div class="ptc-section-title">What to Practice</div>', '<div class="ptc-section-title">Choose module</div>')
js = re.sub(r'<div class="ptc-submode-container" id="ptc-submode-container".*?</div>\s*</div>', '', js, flags=re.DOTALL)

# Update _updateUI to remove submode logic
old_update_ui = """  _updateUI() {
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
    
    const totalMin = Math.round(currentModeObj.baseMin * this.state.multiplier);
"""
new_update_ui = """  _updateUI() {
    this.el.querySelectorAll('.ptc-mode-card').forEach(c => c.classList.remove('is-active'));
    let activeMainCard = this.el.querySelector(`.ptc-mode-card[data-id="${this.state.mode}"]`);
    if (activeMainCard) activeMainCard.classList.add('is-active');

    let currentModeObj = this.modes.find(m => m.id === this.state.mode);
    this.modes.forEach(m => {
      const el = document.getElementById(`ptc-badge-${m.id}`);
      if (el) el.textContent = this._fmt(Math.round(m.baseMin * this.state.multiplier));
    });
    
    const totalMin = Math.round(currentModeObj.baseMin * this.state.multiplier);
"""
js = js.replace(old_update_ui, new_update_ui)

# Update _bindEvents for modes
old_bind_events_modes = """    this.el.querySelectorAll('.ptc-mode-card').forEach(card => {
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
new_bind_events_modes = """    this.el.querySelectorAll('.ptc-mode-card').forEach(card => {
      card.addEventListener('click', () => {
        this.el.querySelectorAll('.ptc-mode-card').forEach(c => c.classList.remove('is-active'));
        card.classList.add('is-active');
        this.state.mode = card.getAttribute('data-id');
        this._updateUI();
      });
    });"""
js = js.replace(old_bind_events_modes, new_bind_events_modes)

# Fix open/close state reset (Step 3)
js = js.replace("""  open(testName, classroomId = null) {
    this.state.testName = testName;
    this.state.classroomId = classroomId;
    this.el.classList.add('is-open');
  }""", """  open(testName, classroomId = null) {
    this.state.testName = testName;
    this.state.classroomId = classroomId;
    const btn = this.el.querySelector('#ptc-btn-start');
    if (btn) {
        btn.classList.remove('is-loading');
        btn.disabled = false;
    }
    this.el.classList.add('is-open');
  }""")

js = js.replace("""  close() {
    this.el.classList.remove('is-open');
  }""", """  close() {
    this.el.classList.remove('is-open');
    const btn = this.el.querySelector('#ptc-btn-start');
    if (btn) {
        btn.classList.remove('is-loading');
        btn.disabled = false;
    }
  }""")

with open(js_path, "w") as f:
    f.write(js)
