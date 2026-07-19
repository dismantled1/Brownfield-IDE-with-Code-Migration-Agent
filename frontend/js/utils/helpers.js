/**
 * helpers.js — General-purpose utility functions for the Brownfield IDE.
 */

const Helpers = (() => {

  // ---------------------------------------------------------------------------
  // DOM
  // ---------------------------------------------------------------------------

  /** Shorthand for document.getElementById */
  function $id(id) { return document.getElementById(id); }

  /** Shorthand for document.querySelector */
  function $(sel, parent = document) { return parent.querySelector(sel); }

  /** Shorthand for document.querySelectorAll (returns Array) */
  function $$(sel, parent = document) { return Array.from(parent.querySelectorAll(sel)); }

  /** Create an element with optional attributes and children. */
  function el(tag, attrs = {}, ...children) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class')        e.className = v;
      else if (k === 'style')   Object.assign(e.style, v);
      else if (k.startsWith('on')) e.addEventListener(k.slice(2).toLowerCase(), v);
      else                      e.setAttribute(k, v);
    }
    children.flat().forEach(c => {
      e.append(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return e;
  }

  /** Show a DOM element (removes 'hidden' class). */
  function show(element) {
    if (element) element.classList.remove('hidden');
  }

  /** Hide a DOM element (adds 'hidden' class). */
  function hide(element) {
    if (element) element.classList.add('hidden');
  }

  /** Toggle visibility of a DOM element. */
  function toggle(element, force) {
    if (element) element.classList.toggle('hidden', force !== undefined ? !force : undefined);
  }

  // ---------------------------------------------------------------------------
  // Strings & Paths
  // ---------------------------------------------------------------------------

  /** Get the basename of a path (last segment). */
  function basename(path) {
    return path.replace(/\\/g, '/').split('/').pop() || path;
  }

  /** Get the directory part of a path. */
  function dirname(path) {
    const p = path.replace(/\\/g, '/');
    const idx = p.lastIndexOf('/');
    return idx === -1 ? '' : p.slice(0, idx);
  }

  /** Get file extension (lowercase, without dot). */
  function extname(path) {
    const name = basename(path);
    const dot = name.lastIndexOf('.');
    return dot === -1 ? '' : name.slice(dot + 1).toLowerCase();
  }

  /** Join path segments with forward slashes. */
  function joinPath(...parts) {
    return parts
      .filter(Boolean)
      .map((p, i) => i === 0 ? p.replace(/\\+$/, '').replace(/\/+$/, '') : p.replace(/^[/\\]+/, '').replace(/[/\\]+$/, ''))
      .join('/');
  }

  /** Truncate a string in the middle: 'very-long-path/to/file.js' → 'very-l…file.js' */
  function truncateMid(str, maxLen = 40) {
    if (str.length <= maxLen) return str;
    const half = Math.floor((maxLen - 3) / 2);
    return str.slice(0, half) + '…' + str.slice(-half);
  }

  /** Escape HTML special characters. */
  function escapeHtml(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
              .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
  }

  // ---------------------------------------------------------------------------
  // Time
  // ---------------------------------------------------------------------------

  /** Format an ISO 8601 timestamp as a relative time string. */
  function timeAgo(isoString) {
    const date = new Date(isoString);
    const diff = (Date.now() - date.getTime()) / 1000;
    if (diff < 60)   return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400)return `${Math.floor(diff / 3600)}h ago`;
    if (diff < 86400 * 30) return `${Math.floor(diff / 86400)}d ago`;
    return date.toLocaleDateString();
  }

  /** Format bytes as a human-readable string. */
  function formatBytes(bytes) {
    if (bytes < 1024)              return `${bytes} B`;
    if (bytes < 1024 * 1024)       return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
  }

  // ---------------------------------------------------------------------------
  // Debounce / Throttle
  // ---------------------------------------------------------------------------

  function debounce(fn, delay) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  }

  function throttle(fn, limit) {
    let last = 0;
    return (...args) => {
      const now = Date.now();
      if (now - last >= limit) { last = now; fn(...args); }
    };
  }

  // ---------------------------------------------------------------------------
  // Modal helpers
  // ---------------------------------------------------------------------------

  /**
   * Show a simple input modal.
   * Returns a Promise that resolves with the entered value or null on cancel.
   */
  function promptModal({ title, label, placeholder = '', defaultValue = '', confirmText = 'OK' }) {
    return new Promise(resolve => {
      const overlay = el('div', { class: 'modal-overlay', id: 'prompt-modal-overlay' });
      const modal   = el('div', { class: 'modal' });

      // Title may contain an inline SVG icon — render as HTML (static/trusted).
      const titleEl  = el('div', { class: 'modal-title' });
      titleEl.innerHTML = title;
      const labelEl  = el('label', { class: 'input-label' }, label);
      const input    = el('input', { class: 'input', type: 'text', placeholder });
      input.value    = defaultValue;

      const actions  = el('div', { class: 'modal-actions' });
      const cancelBtn = el('button', { class: 'btn btn-ghost', onclick: () => { overlay.remove(); resolve(null); } }, 'Cancel');
      const confirmBtn= el('button', { class: 'btn btn-primary', onclick: () => {
        const val = input.value.trim();
        overlay.remove();
        resolve(val || null);
      }}, confirmText);

      actions.append(cancelBtn, confirmBtn);
      modal.append(titleEl, labelEl, input, actions);
      overlay.append(modal);
      document.body.append(overlay);

      input.focus();
      input.select();

      input.addEventListener('keydown', e => {
        if (e.key === 'Enter')  { e.preventDefault(); confirmBtn.click(); }
        if (e.key === 'Escape') { e.preventDefault(); cancelBtn.click(); }
      });
    });
  }

  /**
   * Show a confirmation modal.
   * Returns a Promise<boolean>.
   */
  function confirmModal({ title, message, confirmText = 'Confirm', danger = false }) {
    return new Promise(resolve => {
      const overlay = el('div', { class: 'modal-overlay', id: 'confirm-modal-overlay' });
      const modal   = el('div', { class: 'modal' });
      const titleEl = el('div', { class: 'modal-title' });
      titleEl.innerHTML = title;  // may contain an inline SVG icon (static/trusted)
      const msgEl   = el('p', { style: { color: 'var(--color-text-secondary)', fontSize: 'var(--text-sm)', lineHeight: '1.6' } }, message);
      const actions = el('div', { class: 'modal-actions' });
      const cancelBtn  = el('button', { class: 'btn btn-ghost', onclick: () => { overlay.remove(); resolve(false); } }, 'Cancel');
      const confirmBtn = el('button', { class: `btn ${danger ? 'btn-danger' : 'btn-primary'}`, onclick: () => { overlay.remove(); resolve(true); } }, confirmText);
      actions.append(cancelBtn, confirmBtn);
      modal.append(titleEl, msgEl, actions);
      overlay.append(modal);
      document.body.append(overlay);
      confirmBtn.focus();
      overlay.addEventListener('keydown', e => {
        if (e.key === 'Escape') { overlay.remove(); resolve(false); }
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Clipboard
  // ---------------------------------------------------------------------------

  async function copyToClipboard(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch { return false; }
  }

  // ---------------------------------------------------------------------------
  // Misc
  // ---------------------------------------------------------------------------

  function uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }

  function clamp(val, min, max) { return Math.max(min, Math.min(max, val)); }

  return {
    $id, $, $$, el, show, hide, toggle,
    basename, dirname, extname, joinPath, truncateMid, escapeHtml,
    timeAgo, formatBytes,
    debounce, throttle,
    promptModal, confirmModal,
    copyToClipboard,
    uuid, clamp,
  };
})();
