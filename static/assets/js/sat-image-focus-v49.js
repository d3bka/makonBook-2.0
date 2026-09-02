(function () {
  'use strict';

  const IMAGE_SELECTOR = [
    'body.github-test-template-v20 #passage img',
    'body.github-test-template-v20 #question-text img',
    'body.github-test-template-v20 .just-div img',
    'body.github-test-template-v20 #graph-container img',
    'body.github-test-template-v20 #answers img'
  ].join(',');

  const MIN_SCALE = 0.15;
  const MAX_SCALE = 6;
  const ZOOM_STEP = 1.18;

  let modal = null;
  let stage = null;
  let paper = null;
  let focusImage = null;
  let zoomLabel = null;
  let lastTrigger = null;
  let scale = 1;
  let fitScale = 1;
  let x = 0;
  let y = 0;
  let dragStart = null;
  const pointers = new Map();
  let pinchStart = null;

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function eligibleImage(target) {
    return target && target.closest ? target.closest(IMAGE_SELECTOR) : null;
  }

  function enhanceImage(img) {
    if (!img || img.dataset.imageFocusReady === '1') return;
    img.dataset.imageFocusReady = '1';
    img.classList.add('sat-focusable-image');
    if (!img.hasAttribute('tabindex')) img.tabIndex = 0;
    if (!img.hasAttribute('role')) img.setAttribute('role', 'button');
    const existing = (img.getAttribute('aria-label') || img.getAttribute('alt') || 'Question image').trim();
    if (!/focus view/i.test(existing)) img.setAttribute('aria-label', `${existing}. Open image focus view`);
    img.setAttribute('title', 'Open image focus view');
    img.setAttribute('draggable', 'false');
  }

  function enhanceAll(root) {
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll(IMAGE_SELECTOR).forEach(enhanceImage);
  }

  function createModal() {
    if (modal) return;
    modal = document.createElement('div');
    modal.className = 'sat-image-focus';
    modal.hidden = true;
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Image focus view');
    modal.innerHTML = `
      <div class="sat-image-focus__toolbar">
        <div class="sat-image-focus__title"><i class="fa fa-search-plus" aria-hidden="true"></i><span data-image-focus-title>Question visual</span></div>
        <div class="sat-image-focus__controls" aria-label="Image zoom controls">
          <button type="button" class="sat-image-focus__button" data-image-focus-action="out" aria-label="Zoom out" title="Zoom out"><i class="fa fa-minus" aria-hidden="true"></i></button>
          <span class="sat-image-focus__zoom" data-image-focus-zoom>100%</span>
          <button type="button" class="sat-image-focus__button" data-image-focus-action="in" aria-label="Zoom in" title="Zoom in"><i class="fa fa-plus" aria-hidden="true"></i></button>
          <button type="button" class="sat-image-focus__button sat-image-focus__button--fit" data-image-focus-action="fit" aria-label="Fit image to screen" title="Fit to screen">Fit</button>
          <button type="button" class="sat-image-focus__button" data-image-focus-action="actual" aria-label="Show image at 100 percent" title="100%">1:1</button>
        </div>
        <button type="button" class="sat-image-focus__button sat-image-focus__close" data-image-focus-action="close" aria-label="Close image focus view" title="Close"><i class="fa fa-times" aria-hidden="true"></i></button>
      </div>
      <div class="sat-image-focus__stage" data-image-focus-stage>
        <div class="sat-image-focus__paper" data-image-focus-paper>
          <img class="sat-image-focus__image" data-image-focus-image alt="">
        </div>
      </div>
      <div class="sat-image-focus__hint"><span>Scroll to zoom</span><span aria-hidden="true">•</span><span>Drag to move</span><span aria-hidden="true">•</span><span>Double-click to fit / 100%</span><span aria-hidden="true">•</span><span>Esc to close</span></div>`;
    document.body.appendChild(modal);
    stage = modal.querySelector('[data-image-focus-stage]');
    paper = modal.querySelector('[data-image-focus-paper]');
    focusImage = modal.querySelector('[data-image-focus-image]');
    zoomLabel = modal.querySelector('[data-image-focus-zoom]');

    modal.addEventListener('click', function (event) {
      const action = event.target.closest('[data-image-focus-action]')?.dataset.imageFocusAction;
      if (action === 'close') close();
      if (action === 'in') zoomBy(ZOOM_STEP);
      if (action === 'out') zoomBy(1 / ZOOM_STEP);
      if (action === 'fit') fit();
      if (action === 'actual') actualSize();
    });

    stage.addEventListener('click', function (event) {
      if (event.target === stage) close();
    });

    stage.addEventListener('dblclick', function (event) {
      event.preventDefault();
      if (Math.abs(scale - fitScale) < 0.02) actualSize();
      else fit();
    });

    stage.addEventListener('wheel', function (event) {
      if (!modal.classList.contains('is-open')) return;
      event.preventDefault();
      const factor = event.deltaY < 0 ? 1.12 : (1 / 1.12);
      zoomAt(factor, event.clientX, event.clientY);
    }, { passive: false });

    stage.addEventListener('pointerdown', onPointerDown);
    stage.addEventListener('pointermove', onPointerMove);
    stage.addEventListener('pointerup', onPointerUp);
    stage.addEventListener('pointercancel', onPointerUp);
  }

  function naturalSize() {
    return {
      width: Math.max(1, Number(focusImage.naturalWidth || focusImage.width || 1)),
      height: Math.max(1, Number(focusImage.naturalHeight || focusImage.height || 1))
    };
  }

  function calculateFitScale() {
    if (!stage || !focusImage) return 1;
    const rect = stage.getBoundingClientRect();
    const size = naturalSize();
    const horizontalPadding = rect.width < 720 ? 36 : 88;
    const verticalPadding = rect.height < 600 ? 36 : 72;
    const availableW = Math.max(80, rect.width - horizontalPadding);
    const availableH = Math.max(80, rect.height - verticalPadding);
    return clamp(Math.min(availableW / size.width, availableH / size.height), MIN_SCALE, MAX_SCALE);
  }

  function renderTransform() {
    if (!paper) return;
    paper.style.transform = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px)) scale(${scale})`;
    if (zoomLabel) zoomLabel.textContent = `${Math.round(scale * 100)}%`;
  }

  function resetPosition() {
    x = 0;
    y = 0;
  }

  function fit() {
    fitScale = calculateFitScale();
    scale = fitScale;
    resetPosition();
    renderTransform();
  }

  function actualSize() {
    scale = 1;
    resetPosition();
    renderTransform();
  }

  function zoomBy(factor) {
    if (!stage) return;
    const rect = stage.getBoundingClientRect();
    zoomAt(factor, rect.left + rect.width / 2, rect.top + rect.height / 2);
  }

  function zoomAt(factor, clientX, clientY) {
    const oldScale = scale;
    const nextScale = clamp(oldScale * factor, MIN_SCALE, MAX_SCALE);
    if (Math.abs(nextScale - oldScale) < 0.0001) return;
    const rect = stage.getBoundingClientRect();
    const pointX = clientX - (rect.left + rect.width / 2) - x;
    const pointY = clientY - (rect.top + rect.height / 2) - y;
    const ratio = nextScale / oldScale;
    x -= pointX * (ratio - 1);
    y -= pointY * (ratio - 1);
    scale = nextScale;
    renderTransform();
  }

  function onPointerDown(event) {
    if (!modal.classList.contains('is-open')) return;
    stage.setPointerCapture?.(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 1) {
      dragStart = { clientX: event.clientX, clientY: event.clientY, x, y };
      stage.classList.add('is-dragging');
    } else if (pointers.size === 2) {
      const pts = Array.from(pointers.values());
      pinchStart = {
        distance: Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y),
        scale
      };
      dragStart = null;
    }
  }

  function onPointerMove(event) {
    if (!pointers.has(event.pointerId)) return;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 2 && pinchStart) {
      const pts = Array.from(pointers.values());
      const distance = Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y);
      if (pinchStart.distance > 0) {
        scale = clamp(pinchStart.scale * (distance / pinchStart.distance), MIN_SCALE, MAX_SCALE);
        renderTransform();
      }
      return;
    }
    if (pointers.size === 1 && dragStart) {
      x = dragStart.x + (event.clientX - dragStart.clientX);
      y = dragStart.y + (event.clientY - dragStart.clientY);
      renderTransform();
    }
  }

  function onPointerUp(event) {
    pointers.delete(event.pointerId);
    try { stage.releasePointerCapture?.(event.pointerId); } catch (error) {}
    if (pointers.size < 2) pinchStart = null;
    if (pointers.size === 0) {
      dragStart = null;
      stage.classList.remove('is-dragging');
    } else if (pointers.size === 1) {
      const remaining = Array.from(pointers.values())[0];
      dragStart = { clientX: remaining.x, clientY: remaining.y, x, y };
    }
  }

  function open(img) {
    createModal();
    if (!img || !img.currentSrc && !img.src) return;
    lastTrigger = img;
    const title = modal.querySelector('[data-image-focus-title]');
    const label = (img.getAttribute('alt') || 'Question visual').trim() || 'Question visual';
    title.textContent = label;
    focusImage.alt = label;
    focusImage.onload = function () {
      fit();
    };
    focusImage.src = img.currentSrc || img.src;
    modal.hidden = false;
    document.body.classList.add('sat-image-focus-open');
    requestAnimationFrame(function () {
      modal.classList.add('is-open');
      modal.querySelector('[data-image-focus-action="close"]')?.focus({ preventScroll: true });
      if (focusImage.complete && focusImage.naturalWidth) fit();
    });
  }

  function close() {
    if (!modal || modal.hidden) return;
    modal.classList.remove('is-open');
    document.body.classList.remove('sat-image-focus-open');
    pointers.clear();
    dragStart = null;
    pinchStart = null;
    stage?.classList.remove('is-dragging');
    window.setTimeout(function () {
      if (!modal.classList.contains('is-open')) modal.hidden = true;
    }, 180);
    if (lastTrigger && document.contains(lastTrigger)) {
      lastTrigger.focus({ preventScroll: true });
    }
  }

  function trapTab(event) {
    if (!modal || !modal.classList.contains('is-open') || event.key !== 'Tab') return;
    const focusable = Array.from(modal.querySelectorAll('button:not([disabled]), [tabindex]:not([tabindex="-1"])'));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  document.addEventListener('click', function (event) {
    const img = eligibleImage(event.target);
    if (!img || modal?.contains(img)) return;
    event.preventDefault();
    event.stopPropagation();
    open(img);
  }, true);

  document.addEventListener('keydown', function (event) {
    const img = eligibleImage(event.target);
    if (img && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      event.stopPropagation();
      open(img);
      return;
    }
    if (!modal || !modal.classList.contains('is-open')) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopImmediatePropagation();
      close();
      return;
    }
    if (event.key === '+' || event.key === '=') zoomBy(ZOOM_STEP);
    if (event.key === '-') zoomBy(1 / ZOOM_STEP);
    if (event.key === '0') fit();
    trapTab(event);
  }, true);

  window.addEventListener('resize', function () {
    if (modal?.classList.contains('is-open')) fit();
  });

  document.addEventListener('DOMContentLoaded', function () {
    createModal();
    enhanceAll(document);
    const observer = new MutationObserver(function (mutations) {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (node.matches?.(IMAGE_SELECTOR)) enhanceImage(node);
          enhanceAll(node);
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  });

  window.SATImageFocus = { open: open, close: close, fit: fit };
})();
