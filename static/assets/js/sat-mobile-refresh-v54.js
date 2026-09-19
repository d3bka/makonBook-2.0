/* Place the existing report button in the mobile exam toolbar without
   cloning it or disrupting its click listener. Restore its original position
   when the viewport becomes desktop or landscape. */
(function () {
  'use strict';

  function init() {
    const toolbar = document.querySelector('body.mk-test-window.github-test-template-v20 header .header-tools');
    const button = document.querySelector('body.mk-test-window.github-test-template-v20 .issue-report-fab');
    if (!toolbar || !button || !button.parentNode) return;

    const originalParent = button.parentNode;
    const anchor = document.createComment('issue-report-original-location');
    originalParent.insertBefore(anchor, button);
    const media = window.matchMedia('(max-width: 700px) and (orientation: portrait)');

    const place = () => {
      if (media.matches && button.parentNode !== toolbar) {
        toolbar.appendChild(button);
      } else if (!media.matches && button.parentNode !== originalParent) {
        originalParent.insertBefore(button, anchor.nextSibling);
      }
    };

    place();
    if (media.addEventListener) media.addEventListener('change', place);
    else if (media.addListener) media.addListener(place);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
