class PreTestConfigModal {
  constructor() {
    this.multipliers = [
      { val: 0.5, label: "0.5× Time", sub: "Half time", icon: "bi-lightning" },
      { val: 0.75, label: "0.75× Time", sub: "75% of standard", icon: "bi-stopwatch" },
      { val: 1.0, label: "Standard", sub: "Official SAT timing", icon: "bi-stopwatch-fill", isDefault: true },
      { val: 1.5, label: "1.5× Time", sub: "50% extended", icon: "bi-person-wheelchair" },
      { val: 2.0, label: "Double Time", sub: "100% extended", icon: "bi-clock" }
    ];
    this.modes = [
      { id: "full_test", title: "Full Test", desc: "All modules (RW + Math)", baseMin: 134, isDefault: true, icon: "bi-bullseye" },
      { id: "rw_only", title: "English Only", desc: "Both RW modules", baseMin: 64, icon: "bi-book" },
      { id: "math_only", title: "Math Only", desc: "Both Math modules", baseMin: 70, icon: "bi-calculator" },
      { id: "single_module", title: "Single Module", desc: "Practice one module", baseMin: 32, icon: "bi-lightning-charge" }
    ];
    this.subModes = [
      { id: "single_english", title: "Single RW", baseMin: 32 },
      { id: "single_math", title: "Single Math", baseMin: 35 }
    ];
    this.state = { multiplier: 1.0, mode: "full_test", testName: null, classroomId: null };
    this._buildDOM();
    this._bindEvents();
  }

  _buildDOM() {
    if (document.getElementById('ptc-overlay')) return;
    const overlay = document.createElement('div');
    overlay.id = 'ptc-overlay';
    overlay.className = 'ptc-overlay';
    
    let speedHtml = this.multipliers.map(m => `
      <div class="ptc-speed-card ${m.isDefault ? 'is-active' : ''}" data-val="${m.val}">
        <i class="bi ${m.icon}"></i>
        <div class="ptc-speed-val">${m.label}</div>
        <div class="ptc-speed-sub">${m.sub}</div>
      </div>
    `).join('');

    let modeHtml = this.modes.map(m => `
      <div class="ptc-mode-card ${m.isDefault ? 'is-active' : ''}" data-id="${m.id}">
        <div class="ptc-radio-wrapper">
          <div class="ptc-radio"></div>
        </div>
        <div class="ptc-mode-info">
          <div class="ptc-mode-title-wrapper">
            <i class="bi ${m.icon} ptc-mode-icon"></i>
            <div class="ptc-mode-title">${m.title}</div>
          </div>
          <div class="ptc-mode-desc">${m.desc}</div>
          <div class="ptc-badge" id="ptc-badge-${m.id}">-- min</div>
        </div>
      </div>
    `).join('');

    overlay.innerHTML = `
      <div class="ptc-dialog" role="dialog" aria-modal="true">
        <div class="ptc-section-title">Time Accommodation</div>
        <div class="ptc-speed-row">${speedHtml}</div>
        <div class="ptc-section-title">Choose module</div>
        <div class="ptc-mode-grid">${modeHtml}</div>
        
        


        <div class="ptc-submode-container" id="ptc-submode-container" style="display: none; margin-top: 12px; animation: ptcFadeIn 0.2s ease-out;">
            <div style="display: flex; gap: 12px;">
                ${this.subModes.map(sm => `
                <div class="ptc-submode-card" data-sub="${sm.id}" style="flex: 1; padding: 10px; border: 1.5px solid var(--mk-border); border-radius: 10px; cursor: pointer; text-align: center; font-weight: 600; font-size: 0.9rem; transition: all 0.2s ease;">
                    ${sm.title}
                </div>
                `).join('')}
            </div>
        </div>
        <div class="ptc-summary">
          <div>
            <div class="ptc-summary-label">Estimated Duration</div>
            <div class="ptc-summary-val" id="ptc-total-time">--</div>
          </div>
          <div style="text-align:right;">
            <div class="ptc-summary-label">Time Setting</div>
            <div class="ptc-summary-val" id="ptc-time-setting" style="font-size:1.1rem; font-weight: 500;">1x</div>
          </div>
        </div>
        <div class="ptc-footer">
          <button class="ptc-btn ptc-btn-cancel" id="ptc-btn-cancel">Cancel</button>
          <button class="ptc-btn ptc-btn-start" id="ptc-btn-start">
            <i class="bi bi-play-fill" style="font-size: 1.2rem; line-height: 1;"></i>
            <span>Start Test</span>
            <div class="ptc-spinner"></div>
          </button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    this.el = overlay;
    this._updateUI();
  }

  _bindEvents() {
    this.el.addEventListener('click', (e) => {
      if (e.target === this.el) this.close();
    });
    this.el.querySelector('#ptc-btn-cancel').addEventListener('click', () => this.close());
    
    this.el.querySelectorAll('.ptc-speed-card').forEach(card => {
      card.addEventListener('click', () => {
        this.el.querySelectorAll('.ptc-speed-card').forEach(c => c.classList.remove('is-active'));
        card.classList.add('is-active');
        this.state.multiplier = parseFloat(card.getAttribute('data-val'));
        this._updateUI();
      });
    });

    this.el.querySelectorAll('.ptc-mode-card').forEach(card => {
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
    });

    this.el.querySelector('#ptc-btn-start').addEventListener('click', () => this._submit());
  }

  _fmt(min) {
    if (min < 60) return `${min} min`;
    const h = Math.floor(min / 60);
    const m = min % 60;
    if (this.state.mode.startsWith('single_') && min < 60) return `~${min} min`;
    return m > 0 ? `${h}h ${m}min` : `${h}h`;
  }

  _updateUI() {
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
                c.classList.add('is-active');
            } else {
                c.classList.remove('is-active');
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
    
    if (isSingle) {
        const smObj = this.subModes.find(m => m.id === this.state.mode);
        const el = document.getElementById('ptc-badge-single_module');
        if (el) el.textContent = this._fmt(Math.round(smObj.baseMin * this.state.multiplier));
    }
    
    const totalMin = Math.round(currentModeObj.baseMin * this.state.multiplier);
    document.getElementById('ptc-total-time').textContent = this._fmt(totalMin);
    
    const multObj = this.multipliers.find(m => m.val === this.state.multiplier);
    document.getElementById('ptc-time-setting').textContent = multObj.label.replace(' Time', '').replace('Standard', '1x');
  }

  _getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    const match = document.cookie.match(/(?:^|; )makonbook_csrftoken_v35=([^;]+)/);
    return match ? match[1] : '';
  }

  _submit() {
    const btn = this.el.querySelector('#ptc-btn-start');
    if (btn.classList.contains('is-loading')) return; // Prevent double submit
    
    btn.classList.add('is-loading');
    btn.disabled = true;

    fetch('/sat/api/test/initialize/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': this._getCsrfToken()
      },
      body: JSON.stringify({
        test_name: this.state.testName,
        mode: this.state.mode,
        multiplier: this.state.multiplier,
        classroom_id: this.state.classroomId
      })
    })
    .then(async res => {
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP error! status: ${res.status} - ${text}`);
      }
      return res.json();
    })
    .then(data => {
      if (data.status === 'success' && data.redirect_url) {
        window.location.href = data.redirect_url;
      } else {
        throw new Error(data.error || 'Unknown error');
      }
    })
    .catch(err => {
      console.error(err);
      alert("Failed to initialize test: " + err.message);
      btn.classList.remove('is-loading');
      btn.disabled = false;
    });
  }

  open(testName, classroomId = null) {
    this.state.testName = testName;
    this.state.classroomId = classroomId;
    const btn = this.el.querySelector('#ptc-btn-start');
    if (btn) {
        btn.classList.remove('is-loading');
        btn.disabled = false;
    }
    this.el.classList.add('is-open');
  }

  close() {
    this.el.classList.remove('is-open');
    const btn = this.el.querySelector('#ptc-btn-start');
    if (btn) {
        btn.classList.remove('is-loading');
        btn.disabled = false;
    }
    // Fire pageshow event to reset the dashboard "Opening..." button and unlock navigation
    window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }));
  }
}

window.PreTestConfig = new PreTestConfigModal();

// Intercept practice action clicks
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('a.practice-action[data-practice-navigate]').forEach(link => {
    link.addEventListener('click', function(e) {
      e.preventDefault();
      const href = this.getAttribute('href');
      
      // Extract test name and classroom from URL
      let testName = null, classroomId = null;
      const mClassroom = href.match(/\/classroom\/(\d+)\/practice\/([^/?#]+)/);
      if (mClassroom) {
        classroomId = mClassroom[1];
        testName = decodeURIComponent(mClassroom[2]);
      } else {
        const m = href.match(/\/practise\/([^/?#]+)/);
        if (m) testName = decodeURIComponent(m[1]);
      }
      
      if (testName) {
        window.PreTestConfig.open(testName, classroomId);
      } else {
        window.location.href = href;
      }
    });
  });
});
