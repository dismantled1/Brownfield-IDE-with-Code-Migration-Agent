/**
 * terminal.js — xterm.js terminal with WebSocket backend and multi-session tabs.
 *
 * FIXED BUGS:
 *  1. term.open() now called AFTER pane is made visible (display: block)
 *  2. Empty state hidden on first session creation
 *  3. FitAddon null-safe dimensions
 *  4. Robust WebSocket reconnect messaging
 *  5. Terminal pane properly sized before fit
 */

const TerminalManager = (() => {
  const _sessions = {};  // sessionId → { term, fitAddon, ws, tabEl, paneEl, alive }
  let   _active   = null;
  let   _projectCwd = null;

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------

  function init() {
    EventBus.on('project:opened', ({ projectPath }) => { _projectCwd = projectPath; });
    EventBus.on('project:closed', () => { _projectCwd = null; });

    document.getElementById('btn-terminal-new')?.addEventListener('click', createSession);
    _bindResizePanel();
  }

  // ---------------------------------------------------------------------------
  // Create a new terminal session
  // ---------------------------------------------------------------------------

  async function createSession() {
    const cwd = _projectCwd || null;

    let sessionId, sessionCwd;
    try {
      const res = await API.terminal.create(cwd, 80, 24);
      sessionId  = res.session_id;
      sessionCwd = res.cwd;
    } catch (err) {
      Toast.show(`Terminal error: ${err.message}`, 'error');
      return;
    }

    // ── 1. Create UI elements and insert into DOM ──────────────────────────
    const tabLabel = `Terminal ${Object.keys(_sessions).length + 1}`;
    const tabEl    = _createTab(sessionId, tabLabel);
    const paneEl   = _createPane(sessionId);

    document.getElementById('terminal-tabs').appendChild(tabEl);
    document.getElementById('terminal-content').appendChild(paneEl);

    // ── 2. Hide the "no terminal" placeholder ──────────────────────────────
    const emptyState = document.getElementById('terminal-empty-state');
    if (emptyState) emptyState.style.display = 'none';

    // ── 3. Deactivate previous session ────────────────────────────────────
    if (_active && _sessions[_active]) {
      _sessions[_active].tabEl.classList.remove('active');
      _sessions[_active].paneEl.classList.remove('active');
    }

    // ── 4. Make THIS pane visible BEFORE opening xterm ────────────────────
    //     xterm.js requires the container to have visible dimensions.
    tabEl.classList.add('active');
    paneEl.classList.add('active');
    _active = sessionId;

    // ── 5. Create xterm.js terminal instance ──────────────────────────────
    const term = new Terminal({
      theme: {
        background:    '#0d0d14',
        foreground:    '#e2e8f0',
        cursor:        '#7c3aed',
        cursorAccent:  '#0d0d14',
        selectionBackground: 'rgba(124,58,237,0.35)',
        black:         '#1a1a2e',
        red:           '#ef4444',
        green:         '#10b981',
        yellow:        '#f59e0b',
        blue:          '#3b82f6',
        magenta:       '#8b5cf6',
        cyan:          '#06b6d4',
        white:         '#e2e8f0',
        brightBlack:   '#475569',
        brightRed:     '#f87171',
        brightGreen:   '#34d399',
        brightYellow:  '#fcd34d',
        brightBlue:    '#60a5fa',
        brightMagenta: '#a78bfa',
        brightCyan:    '#67e8f9',
        brightWhite:   '#f8fafc',
      },
      fontFamily:     "'JetBrains Mono', 'Cascadia Code', Consolas, monospace",
      fontSize:       13,
      lineHeight:     1.35,
      cursorBlink:    true,
      cursorStyle:    'bar',
      scrollback:     5000,
      convertEol:     true,
      allowProposedApi: true,
      windowsMode:    true,   // Correct CRLF handling on Windows
    });

    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);

    // Optional: web links addon
    try {
      const webLinksAddon = new WebLinksAddon.WebLinksAddon();
      term.loadAddon(webLinksAddon);
    } catch { /* optional */ }

    // ── 6. Open terminal into the NOW-VISIBLE pane ────────────────────────
    term.open(paneEl);

    // ── 7. Fit to actual container dimensions ─────────────────────────────
    //    Use requestAnimationFrame to ensure layout has been computed.
    await new Promise(resolve => requestAnimationFrame(resolve));
    try { fitAddon.fit(); } catch { /* ignore if container too small */ }

    // ── 8. Store session BEFORE connecting WebSocket ──────────────────────
    _sessions[sessionId] = { term, fitAddon, ws: null, tabEl, paneEl, alive: true };

    // ── 9. Connect WebSocket ───────────────────────────────────────────────
    const ws = _connectWebSocket(sessionId, term, fitAddon);
    _sessions[sessionId].ws = ws;

    // ── 10. Forward user keystrokes → WebSocket ───────────────────────────
    term.onData(data => {
      const session = _sessions[sessionId];
      if (session && session.ws && session.ws.readyState === WebSocket.OPEN) {
        session.ws.send(JSON.stringify({ type: 'input', data }));
      }
    });

    // ── 11. Forward resize events → WebSocket ─────────────────────────────
    term.onResize(({ rows, cols }) => {
      const session = _sessions[sessionId];
      if (session && session.ws && session.ws.readyState === WebSocket.OPEN) {
        session.ws.send(JSON.stringify({ type: 'resize', rows, cols }));
      }
    });

    // Focus the terminal
    term.focus();

    EventBus.emit('terminal:create', { sessionId });
  }

  // ---------------------------------------------------------------------------
  // WebSocket connection
  // ---------------------------------------------------------------------------

  function _connectWebSocket(sessionId, term, fitAddon) {
    const ws = API.terminal.connect(sessionId);

    ws.onopen = () => {
      // Send current terminal dimensions immediately on connect
      let dims = null;
      try { dims = fitAddon.proposeDimensions(); } catch { /* ignore */ }
      const rows = dims?.rows ?? 24;
      const cols = dims?.cols ?? 80;
      ws.send(JSON.stringify({ type: 'resize', rows, cols }));
    };

    ws.onmessage = e => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'output') {
          term.write(msg.data);
        } else if (msg.type === 'exit') {
          term.write('\r\n\x1b[33m[Process exited]\x1b[0m\r\n');
          const session = _sessions[sessionId];
          if (session) {
            session.alive = false;
            session.tabEl.querySelector('.terminal-tab-dot').style.background = 'var(--color-error)';
          }
        } else if (msg.type === 'error') {
          term.write(`\r\n\x1b[31m[Error: ${msg.message}]\x1b[0m\r\n`);
        }
      } catch { /* ignore parse errors */ }
    };

    ws.onerror = (e) => {
      console.error('[Terminal] WebSocket error:', e);
      term.write('\r\n\x1b[31m[WebSocket connection error]\x1b[0m\r\n');
    };

    ws.onclose = (e) => {
      const session = _sessions[sessionId];
      if (session && session.alive) {
        term.write(`\r\n\x1b[33m[Disconnected — code ${e.code}]\x1b[0m\r\n`);
        session.alive = false;
        const dot = session.tabEl.querySelector('.terminal-tab-dot');
        if (dot) dot.style.background = 'var(--color-error)';
      }
    };

    return ws;
  }

  // ---------------------------------------------------------------------------
  // UI creation helpers
  // ---------------------------------------------------------------------------

  function _createTab(sessionId, label) {
    const tab = Helpers.el('div', {
      class: 'terminal-tab',
      'data-session': sessionId,
    });
    tab.innerHTML = `
      <span class="terminal-tab-dot"></span>
      <span class="terminal-tab-label">${Helpers.escapeHtml(label)}</span>
      <button class="terminal-tab-close" title="Close terminal">${Icons.getUI('x')}</button>
    `;
    tab.addEventListener('click', e => {
      if (e.target.closest('.terminal-tab-close')) {
        e.stopPropagation();
        _closeSession(sessionId);
      } else {
        _activateSession(sessionId);
      }
    });
    return tab;
  }

  function _createPane(sessionId) {
    const pane = document.createElement('div');
    pane.className  = 'terminal-pane';
    pane.id         = `terminal-pane-${sessionId}`;
    pane.dataset.session = sessionId;
    // Explicit dimensions help xterm calculate rows/cols correctly
    pane.style.width  = '100%';
    pane.style.height = '100%';
    return pane;
  }

  // ---------------------------------------------------------------------------
  // Activate a session (switch tabs)
  // ---------------------------------------------------------------------------

  function _activateSession(sessionId) {
    if (_active && _sessions[_active]) {
      _sessions[_active].tabEl.classList.remove('active');
      _sessions[_active].paneEl.classList.remove('active');
    }

    _active = sessionId;
    const session = _sessions[sessionId];
    if (!session) return;

    session.tabEl.classList.add('active');
    session.paneEl.classList.add('active');

    // Re-fit on the next frame so layout recalculates first
    requestAnimationFrame(() => {
      try {
        session.fitAddon.fit();
        session.term.focus();
      } catch { /* ignore */ }
    });
  }

  // ---------------------------------------------------------------------------
  // Close a session
  // ---------------------------------------------------------------------------

  async function _closeSession(sessionId) {
    const session = _sessions[sessionId];
    if (!session) return;

    // Close WS gracefully
    try { session.ws?.close(); } catch { /* ignore */ }

    // Tell server to kill the PTY
    try { await API.terminal.kill(sessionId); } catch { /* ignore */ }

    // Dispose xterm
    try { session.term.dispose(); } catch { /* ignore */ }

    // Remove UI elements
    session.tabEl.remove();
    session.paneEl.remove();

    delete _sessions[sessionId];
    EventBus.emit('terminal:close', { sessionId });

    // Show empty state if no more sessions
    const remaining = Object.keys(_sessions);
    if (!remaining.length) {
      const emptyState = document.getElementById('terminal-empty-state');
      if (emptyState) emptyState.style.display = '';
      _active = null;
    } else {
      // Activate the last remaining session
      if (_active === sessionId) {
        _active = null;
        _activateSession(remaining[remaining.length - 1]);
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Panel resize (drag handle)
  // ---------------------------------------------------------------------------

  function _bindResizePanel() {
    const handle = document.getElementById('terminal-resize');
    const panel  = document.getElementById('terminal-panel');
    if (!handle || !panel) return;

    let startY, startH;

    handle.addEventListener('mousedown', e => {
      e.preventDefault();
      startY = e.clientY;
      startH = panel.getBoundingClientRect().height;
      handle.classList.add('dragging');

      const onMove = e => {
        const delta  = startY - e.clientY;
        const minH   = 80;
        const maxH   = 600;
        const newH   = Math.max(minH, Math.min(maxH, startH + delta));
        panel.style.height = newH + 'px';
        document.documentElement.style.setProperty('--terminal-height', newH + 'px');
        WorkspaceState.setTerminalHeight(newH);

        // Refit active terminal
        if (_active && _sessions[_active]) {
          try { _sessions[_active].fitAddon.fit(); } catch { /* ignore */ }
        }
      };

      const onUp = () => {
        handle.classList.remove('dragging');
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup',   onUp);
      };

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup',   onUp);
    });
  }

  return { init, createSession };
})();
