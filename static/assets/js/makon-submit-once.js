(() => {
  const forms = document.querySelectorAll('form[data-submit-once]');

  const resetForm = (form) => {
    form.dataset.submitting = 'false';
    form.removeAttribute('aria-busy');
    form.querySelectorAll('[data-submit-once-button]').forEach((button) => {
      button.disabled = false;
      if (button.tagName === 'INPUT') {
        button.value = button.dataset.originalText || button.value;
      } else if (button.dataset.originalText) {
        button.textContent = button.dataset.originalText;
      }
    });
  };

  forms.forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (form.dataset.submitting === 'true') {
        event.preventDefault();
        return;
      }
      form.dataset.submitting = 'true';
      form.setAttribute('aria-busy', 'true');
      form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach((button) => {
        const original = button.tagName === 'INPUT' ? button.value : button.textContent;
        if (!button.dataset.originalText) button.dataset.originalText = original || '';
        const busyText = button.dataset.busyText || form.dataset.busyText || 'Please wait…';
        if (button.tagName === 'INPUT') button.value = busyText;
        else button.textContent = busyText;
        button.setAttribute('data-submit-once-button', '');
        button.disabled = true;
      });
    });
  });

  window.addEventListener('pageshow', () => forms.forEach(resetForm));
})();
