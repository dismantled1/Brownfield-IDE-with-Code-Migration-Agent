/**
 * icons.js — SVG file-type and UI icons for the Brownfield IDE.
 * Returns inline SVG strings keyed by file extension or icon name.
 */

const Icons = (() => {

  // Generic SVG wrapper
  const svg = (content, extra = '') =>
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ${extra}>${content}</svg>`;

  // ---------------------------------------------------------------------------
  // UI Icons (Lucide-style)
  // ---------------------------------------------------------------------------

  const UI = {
    folder:        svg('<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'),
    folderOpen:    svg('<path d="M6 14l1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.55 6a2 2 0 0 1-1.94 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2v2"/>'),
    file:          svg('<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/>'),
    chevronRight:  svg('<polyline points="9 18 15 12 9 6"/>'),
    chevronDown:   svg('<polyline points="6 9 12 15 18 9"/>'),
    x:             svg('<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>'),
    plus:          svg('<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>'),
    trash:         svg('<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>'),
    pencil:        svg('<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>'),
    refresh:       svg('<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>'),
    search:        svg('<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>'),
    terminal:      svg('<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>'),
    save:          svg('<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>'),
    upload:        svg('<polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>'),
    home:          svg('<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>'),
    bot:           svg('<rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/>'),
    send:          svg('<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>'),
    close:         svg('<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>'),
    check:         svg('<polyline points="20 6 9 17 4 12"/>'),
    warning:       svg('<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'),
    info:          svg('<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>'),
    error:         svg('<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>'),
    success:       svg('<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>'),
    more:          svg('<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>'),
    copy:          svg('<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'),
    link:          svg('<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>'),
    code:          svg('<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>'),
    gear:          svg('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'),
    newFile:       svg('<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/>'),
    newFolder:     svg('<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/><line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/>'),
    git:           svg('<circle cx="12" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><path d="M18 9v1a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V9"/><line x1="12" y1="12" x2="12" y2="15"/>'),
    layers:        svg('<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>'),
    cpu:           svg('<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>'),
    zip:           svg('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/><line x1="9" y1="12" x2="15" y2="12"/>'),
  };

  // ---------------------------------------------------------------------------
  // File-type coloured icons (inline SVG with colour)
  // ---------------------------------------------------------------------------

  const colour = (hex) => `fill="${hex}" stroke="none"`;

  const FILE_ICONS = {
    // JavaScript / TypeScript
    js:   `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#f7df1e"/><path d="M6 17.5c.4.7 1 1.2 2 1.2 1.1 0 1.7-.5 1.7-1.3 0-.9-.7-1.2-1.8-1.7l-.6-.3C5.8 14.8 5 14 5 12.6c0-1.5 1.1-2.6 2.9-2.6 1.3 0 2.2.5 2.8 1.4L9.5 12.6c-.3-.6-.7-.8-1.3-.8-.6 0-1 .4-1 .8 0 .6.4.8 1.3 1.2l.6.3c1.6.7 2.5 1.5 2.5 3 0 1.7-1.4 2.8-3.2 2.8-1.8 0-3-1-3.6-2.2L6 17.5zm6.9.1c.5.8 1.1 1.4 2.3 1.4 1 0 1.6-.5 1.6-1.1 0-.8-.6-1.1-1.7-1.5l-.6-.3C13 15.3 12.2 14.5 12.2 13c0-1.5 1.1-2.6 2.9-2.6 1.2 0 2.1.4 2.7 1.5l-1.2.7c-.3-.6-.7-.9-1.4-.9-.6 0-1 .3-1 .8 0 .5.3.8 1.2 1.2l.6.2c1.7.7 2.6 1.4 2.6 3s-1.4 2.8-3.2 2.8c-1.8 0-3-1-3.6-2.4l1.1-.7z" fill="#000"/></svg>`,
    ts:   `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#3178c6"/><path d="M3 12h4v1.5H5.5V20H4v-6.5H3V12zm5.5 0h4.5l-.1 1.5h-1.5V20H10v-6.5H9V12z" fill="white"/><path d="M14 15.5c.1-.8.7-1.4 1.7-1.4.8 0 1.3.4 1.5 1l1.3-.5c-.4-1.1-1.4-1.8-2.8-1.8-1.7 0-3 1.1-3 2.8 0 1.7 1.2 2.8 3 2.8 1.4 0 2.4-.7 2.8-1.9l-1.3-.4c-.2.6-.7 1-1.5 1-.9 0-1.7-.6-1.7-1.6z" fill="white"/></svg>`,
    jsx:  `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#61dafb"/><text x="4" y="17" font-size="9" font-family="monospace" font-weight="bold" fill="#000">JSX</text></svg>`,
    tsx:  `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#3178c6"/><text x="4" y="17" font-size="9" font-family="monospace" font-weight="bold" fill="#fff">TSX</text></svg>`,
    // Python
    py:   `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#306998"/><path d="M12 2C7 2 7.5 4.5 7.5 4.5V7h5v1H5.5S2.5 7.7 2.5 12s3.5 5 3.5 5H8v-2.5S8 12 10.5 12H14s2.5 0 2.5-2.5V5S17.5 2 12 2zm-1.5 1.5c.8 0 1.5.6 1.5 1.5s-.7 1.5-1.5 1.5c-.9 0-1.5-.7-1.5-1.5s.6-1.5 1.5-1.5z" fill="#ffd43b"/><path d="M12 22c5 0 4.5-2.5 4.5-2.5V17h-5v-1h6.5s3 .3 3-4-3.5-5-3.5-5H16v2.5S16 12 13.5 12H10s-2.5 0-2.5 2.5V19S7.5 22 12 22zm1.5-1.5c-.8 0-1.5-.6-1.5-1.5s.7-1.5 1.5-1.5c.9 0 1.5.7 1.5 1.5s-.6 1.5-1.5 1.5z" fill="#306998"/></svg>`,
    // Java
    java: `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#007396"/><text x="4" y="17" font-size="10" font-family="serif" font-weight="bold" fill="#fff">J</text><text x="10" y="17" font-size="7" font-family="serif" fill="#f89820">ava</text></svg>`,
    // Web
    html: `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#e34c26"/><text x="3" y="17" font-size="8" font-family="monospace" font-weight="bold" fill="#fff">HTML</text></svg>`,
    css:  `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#1572b6"/><text x="4" y="17" font-size="9" font-family="monospace" font-weight="bold" fill="#fff">CSS</text></svg>`,
    scss: `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#cc6699"/><text x="3" y="17" font-size="8" font-family="monospace" font-weight="bold" fill="#fff">SCSS</text></svg>`,
    // Data
    json: `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#292929"/><text x="3" y="15" font-size="7" font-family="monospace" fill="#f8c041">{  }</text></svg>`,
    xml:  `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#f16529"/><text x="3" y="16" font-size="7" font-family="monospace" fill="#fff">&lt;/&gt;</text></svg>`,
    yaml: `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#cb171e"/><text x="3" y="17" font-size="8" font-family="monospace" font-weight="bold" fill="#fff">YAML</text></svg>`,
    yml:  `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#cb171e"/><text x="4" y="17" font-size="9" font-family="monospace" font-weight="bold" fill="#fff">YML</text></svg>`,
    // Docs
    md:   `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#083fa1"/><path d="M3 8h18v8H3z" fill="none" stroke="white" stroke-width="1.5"/><path d="M6 14V10l2.5 3 2.5-3v4m3-4v4m0-4l2 2 2-2" stroke="white" stroke-width="1.2" fill="none"/></svg>`,
    // Shell
    sh:   `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#1d1d1d"/><text x="3" y="16" font-size="9" font-family="monospace" fill="#00ff00">$ _</text></svg>`,
    bat:  `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#1d1d1d"/><text x="3" y="16" font-size="8" font-family="monospace" fill="#569cd6">.bat</text></svg>`,
    ps1:  `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#012456"/><text x="3" y="16" font-size="8" font-family="monospace" fill="#00bfff">PS</text></svg>`,
    // Images
    svg:  `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#ffb13b"/><text x="3" y="17" font-size="8" font-family="monospace" font-weight="bold" fill="#000">SVG</text></svg>`,
    // Config
    env:  `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#ecd53f"/><text x="3" y="17" font-size="8" font-family="monospace" font-weight="bold" fill="#000">.env</text></svg>`,
    // Build tools
    dockerfile: `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#0db7ed"/><text x="3" y="16" font-size="6" font-family="monospace" fill="#fff">DOCK</text></svg>`,
    // SQL
    sql:  `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect width="24" height="24" rx="3" fill="#cc2927"/><text x="3" y="17" font-size="9" font-family="monospace" font-weight="bold" fill="#fff">SQL</text></svg>`,
  };

  // Folder icons (coloured)
  const FOLDER_ICONS = {
    default: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill="#c8a96e" stroke="#b8924e" stroke-width="1"/></svg>`,
    open:    `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 19 3 5h18l-2 14H5zm1-7h12M6 14l.5 3h11l.5-3" fill="#dfc080" stroke="#c8a060" stroke-width="1"/></svg>`,
    src:     `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill="#7c3aed" stroke="#6d28d9" stroke-width="1"/></svg>`,
    test:    `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill="#10b981" stroke="#059669" stroke-width="1"/></svg>`,
    config:  `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill="#6b7280" stroke="#4b5563" stroke-width="1"/></svg>`,
  };

  // Map folder names to special icons
  const FOLDER_NAME_MAP = {
    src: 'src', source: 'src', app: 'src', lib: 'src', core: 'src',
    test: 'test', tests: 'test', spec: 'test', __tests__: 'test',
    config: 'config', conf: 'config', settings: 'config',
  };

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  function getFileIcon(extension) {
    const ext = (extension || '').toLowerCase();
    if (FILE_ICONS[ext]) {
      return FILE_ICONS[ext];
    }
    // Fallback: generic file icon
    return `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" fill="#6b7280" stroke="#4b5563" stroke-width="0.5"/><polyline points="14 2 14 8 20 8" stroke="#4b5563" stroke-width="0.5"/></svg>`;
  }

  function getFolderIcon(name, isOpen = false) {
    if (isOpen) return FOLDER_ICONS.open;
    const key = FOLDER_NAME_MAP[(name || '').toLowerCase()];
    return FOLDER_ICONS[key] || FOLDER_ICONS.default;
  }

  function getUI(name) {
    return UI[name] || UI.file;
  }

  return { getFileIcon, getFolderIcon, getUI, UI };
})();
