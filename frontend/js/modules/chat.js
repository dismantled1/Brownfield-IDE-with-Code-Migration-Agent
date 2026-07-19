/**
 * chat.js — AI Chat Panel (Phase 2).
 *
 * Implements the functional chat panel client. Connects user prompts to the
 * backend analysis engine, parses queries for context, and handles markdown rendering.
 */

const ChatPanel = (() => {
  let _messages = [];

  function init() {
    _render();
    _bindEvents();
    _addSystemWelcome();
  }

  function _render() {
    const container = document.getElementById('chat-panel');
    if (!container) return;

    container.innerHTML = `
      <div class="chat-container">
        <!-- Header -->
        <div class="chat-header">
          <div class="chat-header-left">
            ${Icons.getUI('bot')}
            <span>AI Assistant</span>
            <span class="chat-header-badge" style="font-size: 10px; background: rgba(124,58,237,0.15); color: var(--color-text-accent); padding: 1px 4px; border-radius: 2px;">Phase 7</span>
          </div>
          <div class="chat-header-actions">
            <button class="btn-icon btn-ghost" id="btn-chat-clear" title="Clear Chat History" style="padding:4px; border-radius:3px;">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- Messages stream -->
        <div class="chat-messages" id="chat-messages-container"></div>

        <!-- Input Bar -->
        <div class="chat-input-wrapper">
          <div class="chat-text-area-box">
            <textarea
              class="chat-textarea"
              id="chat-user-input"
              placeholder="Ask me to explain project, file, class..."
              rows="1"
            ></textarea>
            <button class="chat-send-btn" id="btn-chat-send" title="Send Message">
              ${Icons.getUI('send')}
            </button>
          </div>
        </div>
      </div>
    `;
  }

  function _bindEvents() {
    const textarea = document.getElementById('chat-user-input');
    const sendBtn = document.getElementById('btn-chat-send');
    const clearBtn = document.getElementById('btn-chat-clear');

    if (textarea) {
      // Auto-resize textarea row count
      textarea.addEventListener('input', () => {
        textarea.style.height = 'auto';
        textarea.style.height = textarea.scrollHeight + 'px';
      });

      // Submit on Enter (Shift+Enter for newline)
      textarea.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          _sendMessage();
        }
      });
    }

    if (sendBtn) {
      sendBtn.addEventListener('click', _sendMessage);
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        _messages = [];
        _renderMessages();
        _addSystemWelcome();
      });
    }

    // Delegated link handling for rendered bot markdown (file:///, cmd:, urls).
    const messagesContainer = document.getElementById('chat-messages-container');
    if (messagesContainer) {
      messagesContainer.addEventListener('click', e => {
        const anchor = e.target.closest('a[data-chat-link]');
        if (anchor) handleLinkClick(e, anchor.dataset.chatLink);
      });
    }
  }

  function _addSystemWelcome() {
    _addMessage('bot', `
### Hello! I am your AI Development Assistant.

All 7 phases are active — I can analyze, search, assess impact, propose changes, validate them, and (after your approval) apply them to disk.

**Supported Prompts**:
* **Explain Project**: "Explain this project"
* **Explain Module**: "Explain this module" or "Explain module [name]"
* **Explain File**: "Explain this file" or "Explain file [path]"
* **Explain Class**: "Explain this class" or "Explain class [name]"
* **Explain Function**: "Explain this function" or "Explain function [name]"

*Tip: If you ask to explain "this file", "this class" or "this function", I will read your active tab and cursor location in Monaco!*

**Development Agent (Phase 5)** — propose changes without touching your files:
* "Add forgot password functionality"
* "Fix login bug"
* "Refactor authentication module"

**Validation & Approval (Phase 6)** — after I propose changes:
* "Run validation" · "Show test results" · "Why did validation fail?"
* "Approve changes" · "Reject changes" · "Regenerate"

**Apply & Undo (Phase 7)** — after approval, write to disk safely:
* "Apply changes" · "Undo last change" · "Show change history" · "Rollback"

**Quick Commands**:
* [🔍 Explain Project](cmd:Explain this project)
* [📄 Explain Current File](cmd:Explain this file)
* [🧱 Explain Selected Class](cmd:Explain this class)
* [⚙️ Explain Selected Function](cmd:Explain this function)
    `);
  }

  function _addMessage(sender, text) {
    _messages.push({ sender, text });
    _renderMessages();
    _scrollToBottom();
  }

  function _renderMessages() {
    const container = document.getElementById('chat-messages-container');
    if (!container) return;

    container.innerHTML = _messages.map(msg => `
      <div class="chat-bubble ${msg.sender}">
        ${msg.sender === 'bot' ? _markdownToHtml(msg.text) : Helpers.escapeHtml(msg.text)}
      </div>
    `).join('');
  }

  function _scrollToBottom() {
    const container = document.getElementById('chat-messages-container');
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }

  async function _sendMessage() {
    const textarea = document.getElementById('chat-user-input');
    if (!textarea) return;

    const text = textarea.value.trim();
    if (!text) return;

    // Add user message to chat UI
    _addMessage('user', text);
    
    // Reset textarea
    textarea.value = '';
    textarea.style.height = 'auto';

    // Show loading bubble
    _showLoadingBubble();

    try {
      const lowerText = text.toLowerCase();
      // Phase 5 — Development Agent requests (feature / bug / refactor).
      const isAgentQuery =
        /^(add|implement|build|introduce)\s+/.test(lowerText) ||
        /^(refactor|optimize|improve)\b/.test(lowerText) ||
        (/\bfix\b/.test(lowerText) &&
          /\b(bug|issue|error|exception|timeout|failure|crash|broken|fail)\b/.test(lowerText));
      // Phase 6 — Validation & Approval commands.
      const vIsApprove = /\bapprove\b/.test(lowerText);
      const vIsReject  = /\breject\b/.test(lowerText);
      const vIsRegen   = lowerText.includes('regenerate');
      const vIsRunVal  = /\bvalidat/.test(lowerText);
      const vIsTests   = lowerText.includes('test result') || (lowerText.includes('show') && lowerText.includes('test'));
      const vIsWhyFail = lowerText.includes('why') && (lowerText.includes('fail') || lowerText.includes('validation'));
      const vIsShow    = lowerText.includes('generated changes') || lowerText.includes('show changes') || lowerText.includes('show diff');
      const isValidationQuery = vIsApprove || vIsReject || vIsRegen || vIsRunVal || vIsTests || vIsWhyFail || vIsShow;
      // Phase 7 — Source update commands.
      const sIsApply   = /\bapply\b/.test(lowerText) && !lowerText.includes('forgot');
      const sIsUndo    = lowerText.includes('undo');
      const sIsHistory = lowerText.includes('change history') || lowerText.includes('show history');
      const sIsRollbck = lowerText.includes('rollback') || lowerText.includes('roll back') || lowerText.includes('restore previous');
      const isSourceQuery = sIsApply || sIsUndo || sIsHistory || sIsRollbck;
      const isReferencesQuery = lowerText.includes('referenced') || lowerText.includes('usages of');
      const isImpactQuery = 
        lowerText.includes('if i modify') ||
        lowerText.includes('if i change') ||
        lowerText.includes('if i update') ||
        lowerText.includes('what depends on') ||
        lowerText.includes('what will break') ||
        lowerText.includes('what will be affected') ||
        (lowerText.includes('changes') && (lowerText.includes('what') || lowerText.includes('which')));
      const isSearchQuery = 
        lowerText.includes('where is') || 
        lowerText.startsWith('find ') || 
        lowerText.startsWith('search ') || 
        lowerText.includes('show files') || 
        lowerText.includes('show apis') || 
        lowerText.includes('show endpoints') || 
        lowerText.includes('jwt') ||
        lowerText.includes('flow');

      if (isSourceQuery) {
        const Src = typeof Source !== 'undefined' ? Source : null;
        if (!Src) {
          _removeLoadingBubble();
          _addMessage('bot', 'The source-update module is not available.');
        } else if (sIsHistory) {
          const ops = await Src.showHistory();
          _removeLoadingBubble();
          _addMessage('bot', _formatHistoryResponse(ops));
        } else if (sIsUndo) {
          const res = await Src.undo();
          _removeLoadingBubble();
          _addMessage('bot', _formatSourceResponse('undo', res));
        } else if (sIsRollbck) {
          // Roll back the most recent applied operation.
          const ops = await Src.showHistory();
          const target = (ops || []).find(o => !o.undone);
          if (!target) { _removeLoadingBubble(); _addMessage('bot', 'There is nothing to roll back.'); }
          else { const res = await Src.rollback(target.operation_id); _removeLoadingBubble(); _addMessage('bot', _formatSourceResponse('rollback', res)); }
        } else { // apply
          const st = Src.getState();
          if (!st.planId || !st.ready) {
            _removeLoadingBubble();
            _addMessage('bot', 'Nothing approved to apply yet. Ask me to make a change, then **run validation** and **approve** it first.');
          } else {
            const res = await Src.applyChanges(false);
            _removeLoadingBubble();
            _addMessage('bot', _formatSourceResponse('apply', res));
          }
        }
      } else if (isValidationQuery) {
        const V = typeof Validation !== 'undefined' ? Validation : null;
        const planId = V ? V.getPlanId() : null;
        if (!V || (!planId && !vIsRegen)) {
          _removeLoadingBubble();
          _addMessage('bot', 'There are no proposed changes yet. Ask me to **add**, **fix**, or **refactor** something first — then I can validate, show results, and approve.');
        } else if (vIsRegen) {
          _removeLoadingBubble();
          _addMessage('bot', '🔄 Regenerating proposed changes…');
          const bundle = await V.regenerate();
          if (bundle) _addMessage('bot', _formatAgentResponse(bundle));
        } else if (vIsApprove) {
          const res = await V.approve();
          _removeLoadingBubble();
          _addMessage('bot', _formatDecisionResponse('approve', res, V.getReport()));
        } else if (vIsReject) {
          const res = await V.reject();
          _removeLoadingBubble();
          _addMessage('bot', _formatDecisionResponse('reject', res));
        } else {
          const report = await V.runValidation(planId);
          _removeLoadingBubble();
          _addMessage('bot', _formatValidationResponse(report, { tests: vIsTests, whyFail: vIsWhyFail }));
        }
      } else if (isAgentQuery) {
        // Show the Development Plan panel loading state, then run the agent.
        EventBus.emit('agent:trigger', { request: text });
        try {
          const bundle = await API.agent.develop(text);
          EventBus.emit('agent:result', { bundle });
          _removeLoadingBubble();
          _addMessage('bot', _formatAgentResponse(bundle));
        } catch (err) {
          EventBus.emit('agent:error', { message: err.message });
          throw err;
        }
      } else if (isReferencesQuery) {
        const symbol = _extractReferenceSymbol(text);
        const data = await API.search.references(symbol);
        _removeLoadingBubble();
        _addMessage('bot', _formatReferencesResponse(symbol, data));
      } else if (isImpactQuery) {
        const { type, target } = _parseImpactTarget(text);
        // Emitting triggers sidebar rendering and vis.js dependency highlights
        EventBus.emit('impact:trigger', { type, target });

        const data = await API.impact.analyze(type, target);
        _removeLoadingBubble();
        _addMessage('bot', _formatImpactResponse(target, data));
      } else if (isSearchQuery) {
        // Trigger sidebar search results panel in parallel
        EventBus.emit('search:trigger', { query: text });
        
        const data = await API.search.query(text);
        _removeLoadingBubble();
        _addMessage('bot', _formatSearchResponse(text, data));
      } else {
        const { scope, target } = _parsePrompt(text);
        const activeFile = typeof Editor !== 'undefined' ? Editor.getActiveFilePath() : null;
        const cursor = typeof Editor !== 'undefined' ? Editor.getCursorPosition() : null;
        const cursorLine = cursor ? cursor.lineNumber : null;

        const response = await API.analysis.explain(
          scope,
          target,
          activeFile,
          cursorLine
        );

        _removeLoadingBubble();
        _addMessage('bot', response.explanation);
      }
    } catch (err) {
      _removeLoadingBubble();
      _addMessage('bot', `**Error**: ${err.message}`);
    }
  }

  function _showLoadingBubble() {
    const container = document.getElementById('chat-messages-container');
    if (!container) return;

    const loadingBubble = document.createElement('div');
    loadingBubble.className = 'chat-bubble bot loading-bubble';
    loadingBubble.id = 'chat-loading-bubble';
    loadingBubble.innerHTML = `
      <div class="dot-pulse"></div>
      <div class="dot-pulse"></div>
      <div class="dot-pulse"></div>
    `;
    container.appendChild(loadingBubble);
    _scrollToBottom();
  }

  function _removeLoadingBubble() {
    const bubble = document.getElementById('chat-loading-bubble');
    if (bubble) bubble.remove();
  }

  function _parsePrompt(prompt) {
    const p = prompt.toLowerCase().trim();
    
    let scope = 'project';
    let target = '';

    // Check for explicit "class"
    if (p.includes('class')) {
      scope = 'class';
      target = _extractTargetName(p, 'class');
    }
    // Check for explicit "function" or "method"
    else if (p.includes('function') || p.includes('method')) {
      scope = 'function';
      target = _extractTargetName(p, 'function') || _extractTargetName(p, 'method');
    }
    // Check for explicit "file"
    else if (p.includes('file')) {
      scope = 'file';
      target = _extractTargetName(p, 'file');
    }
    // Check for explicit "module"
    else if (p.includes('module')) {
      scope = 'module';
      target = _extractTargetName(p, 'module');
    }
    // General fallback
    else if (p.startsWith('explain ')) {
      // e.g. "explain auth" -> check if X is class/function/module
      const rest = prompt.substring(8).trim();
      const restClean = rest.toLowerCase().replace(/^this\s+/, '').replace(/^the\s+/, '').trim();
      if (restClean === 'project' || restClean === 'codebase') {
        scope = 'project';
        target = '';
      } else {
        scope = 'class'; // Default attempt, service resolves intelligently
        target = rest;
      }
    }

    return { scope, target };
  }

  function _extractTargetName(promptLower, keyword) {
    // e.g. "explain class AnalysisManager" or "explain the class AnalysisManager"
    const regex = new RegExp(`(?:${keyword})\\s+(?:the\\s+)?([a-zA-Z0-9_/\\\\.\\-]+)`, 'i');
    const match = promptLower.match(regex);
    return match ? match[1].trim() : '';
  }

  function _markdownToHtml(md) {
    if (!md) return '';
    let html = md;
    
    // Escape HTML to prevent injection
    html = html
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
      
    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
      return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
    });
    
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Headers
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
    
    // Links (file:/// absolute paths, cmd: quick-commands, or standard urls).
    // The URL is carried in a data-* attribute and handled via delegation in
    // _bindEvents — this avoids inline-onclick string-injection from URLs.
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, text, url) => {
      const safeUrl = url.replace(/"/g, '&quot;');
      return `<a href="${safeUrl}" data-chat-link="${safeUrl}" target="_blank" rel="noopener">${text}</a>`;
    });
    
    // Bullet points (replacing lines starting with - or *)
    html = html.replace(/^\s*[-*]\s+(.*$)/gim, '<li>$1</li>');
    
    // Group contiguous <li> elements into <ul>
    // A simple parser to wrap list items with ul/ol
    let inList = false;
    const lines = html.split('\n');
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].startsWith('<li>')) {
        if (!inList) {
          lines[i] = '<ul>' + lines[i];
          inList = true;
        }
      } else {
        if (inList) {
          lines[i-1] = lines[i-1] + '</ul>';
          inList = false;
        }
      }
    }
    if (inList) {
      lines[lines.length - 1] = lines[lines.length - 1] + '</ul>';
    }
    html = lines.join('\n');
    
    // Paragraphs
    html = html.replace(/\n\n/g, '<br><br>');
    
    return html;
  }

  // Exposed handles for global actions
  function handleLinkClick(event, url) {
    // Quick-command links (e.g. "cmd:Explain this project")
    if (url.startsWith('cmd:')) {
      event.preventDefault();
      runQuickCommand(url.substring(4));
      return;
    }
    if (url.startsWith('file:///')) {
      event.preventDefault();
      
      // Separate base URL from line number hash
      let parts = url.split('#');
      let baseUri = parts[0];
      let hash = parts[1] || '';
      let lineNumber = null;
      if (hash) {
        const numMatch = hash.match(/\d+/);
        if (numMatch) {
          lineNumber = parseInt(numMatch[0], 10);
        }
      }
      
      // Extract file path from URL (remove file:///)
      let filePath = decodeURIComponent(baseUri.substring(8));
      
      // Clean up Windows absolute path formatting (e.g. /C:/ -> C:/)
      if (filePath.startsWith('/') && filePath[2] === ':') {
        filePath = filePath.substring(1);
      }
      
      const projectRoot = WorkspaceState.get().projectPath;
      if (projectRoot) {
        const rootNormalized = projectRoot.replace(/\\/g, '/').toLowerCase();
        const fileNormalized = filePath.replace(/\\/g, '/').toLowerCase();
        
        if (fileNormalized.startsWith(rootNormalized)) {
          let relPath = filePath.substring(projectRoot.length).replace(/\\/g, '/');
          if (relPath.startsWith('/')) relPath = relPath.substring(1);
          
          if (typeof Editor !== 'undefined') {
            Editor.openAndHighlight(relPath, lineNumber);
          }
        }
      }
    }
  }

  function _extractReferenceSymbol(text) {
    // Check for backticks first
    const tickMatch = text.match(/`([^`]+)`/);
    if (tickMatch) return tickMatch[1].trim();

    // Check for double/single quotes
    const quoteMatch = text.match(/['"]([^'"]+)['"]/);
    if (quoteMatch) return quoteMatch[1].trim();

    const lower = text.toLowerCase();
    if (lower.includes('usages of')) {
      const idx = lower.indexOf('usages of');
      const rest = text.substring(idx + 9).trim();
      const words = rest.split(/\s+/);
      if (words.length > 0) return words[0].replace(/[.,\/#!$%\^&\*;:{}=\-_`~()]/g,"");
    }
    if (lower.includes('referenced')) {
      const idx = lower.indexOf('referenced');
      const before = text.substring(0, idx).trim();
      const words = before.split(/\s+/);
      for (let i = words.length - 1; i >= 0; i--) {
        const cleanWord = words[i].replace(/[.,\/#!$%\^&\*;:{}=\-_`~()]/g,"").trim();
        if (cleanWord && !['where', 'is', 'the', 'in', 'are', 'referenced', 'to', 'for', 'of', 'a', 'an'].includes(cleanWord.toLowerCase())) {
          return cleanWord;
        }
      }
    }
    const words = text.trim().split(/\s+/);
    return words[words.length - 1].replace(/[.,\/#!$%\^&\*;:{}=\-_`~()]/g,"");
  }

  function _formatSearchResponse(query, data) {
    const results = data.results || [];
    const stats = data.stats || {};
    
    if (results.length === 0) {
      return `No results found for search query: **"${query}"**`;
    }
    
    const projectRoot = WorkspaceState.get().projectPath || '';
    const rootNormalized = projectRoot.replace(/\\/g, '/');
    
    let responseMarkdown = `### Search Results for **"${query}"**\n\n`;
    responseMarkdown += `Found **${stats.total}** match${stats.total !== 1 ? 'es' : ''} across codebase:\n`;
    
    const statsText = [];
    if (stats.files > 0) statsText.push(`**${stats.files}** file${stats.files > 1 ? 's' : ''}`);
    if (stats.classes > 0) statsText.push(`**${stats.classes}** class${stats.classes > 1 ? 'es' : ''}`);
    if (stats.functions > 0) statsText.push(`**${stats.functions}** function${stats.functions > 1 ? 's' : ''}`);
    if (stats.apis > 0) statsText.push(`**${stats.apis}** API${stats.apis > 1 ? 's' : ''}`);
    
    if (statsText.length > 0) {
      responseMarkdown += `(${statsText.join(', ')})\n\n`;
    } else {
      responseMarkdown += `\n`;
    }
    
    const topResults = results.slice(0, 10);
    topResults.forEach((res, index) => {
      const absPath = rootNormalized + '/' + res.file;
      const linkUrl = `file:///${absPath}#L${res.line}`;
      const typeEmoji = {
        'file': '📄',
        'class': '🧱',
        'function': '⚙️',
        'api': '🌐'
      }[res.type] || '📄';
      
      responseMarkdown += `${index + 1}. ${typeEmoji} **${res.name}** (${res.type})\n`;
      responseMarkdown += `   * Location: [${res.file}:${res.line}](${linkUrl})\n`;
      if (res.reason) {
        responseMarkdown += `   * Description: ${res.reason}\n`;
      }
      responseMarkdown += `\n`;
    });
    
    if (results.length > 10) {
      responseMarkdown += `*...and ${results.length - 10} more results visible in the **SEARCH RESULTS** explorer panel.*`;
    }
    
    return responseMarkdown;
  }

  function _formatReferencesResponse(symbol, data) {
    const incoming = data.incoming || [];
    const outgoing = data.outgoing || [];
    const symbolEscaped = Helpers.escapeHtml(symbol);
    
    if (incoming.length === 0 && outgoing.length === 0) {
      return `No references or dependencies found for symbol **"${symbolEscaped}"**.`;
    }
    
    const projectRoot = WorkspaceState.get().projectPath || '';
    const rootNormalized = projectRoot.replace(/\\/g, '/');
    
    let responseMarkdown = `### References for **"${symbolEscaped}"**\n\n`;
    
    if (incoming.length > 0) {
      responseMarkdown += `#### 📥 Incoming Usages (${incoming.length}):\n`;
      incoming.forEach(inc => {
        const absPath = rootNormalized + '/' + inc.file;
        const linkUrl = `file:///${absPath}#L${inc.line}`;
        responseMarkdown += `* [${inc.file}:${inc.line}](${linkUrl}) — *${inc.reason || inc.name}*\n`;
      });
      responseMarkdown += `\n`;
    } else {
      responseMarkdown += `#### 📥 Incoming Usages: None found.\n\n`;
    }
    
    if (outgoing.length > 0) {
      responseMarkdown += `#### 📤 Outgoing Dependencies (${outgoing.length}):\n`;
      outgoing.forEach(out => {
        const absPath = rootNormalized + '/' + out.file;
        const linkUrl = `file:///${absPath}#L${out.line}`;
        responseMarkdown += `* [${out.file}:${out.line}](${linkUrl}) — *${out.reason || out.name}*\n`;
      });
    } else {
      responseMarkdown += `#### 📤 Outgoing Dependencies: None found.\n`;
    }
    return responseMarkdown;
  }

  function _parseImpactTarget(text) {
    const clean = text.replace(/[?.,()]/g, ' ').trim();
    const words = clean.split(/\s+/);
    
    let target = "";
    let type = "unknown";
    
    const lowerText = text.toLowerCase();
    
    // Check if it matches a file name with extension
    const fileRegex = /\b[a-zA-Z0-9_\-]+\.(py|js|ts|tsx|java|html|css)\b/;
    const fileMatch = text.match(fileRegex);
    if (fileMatch) {
      return { type: 'file', target: fileMatch[0] };
    }
    
    // Explicit keywords
    if (lowerText.includes('file ')) {
      const idx = words.findIndex(w => w.toLowerCase() === 'file');
      if (idx !== -1 && words[idx + 1]) return { type: 'file', target: words[idx + 1] };
    }
    if (lowerText.includes('class ')) {
      const idx = words.findIndex(w => w.toLowerCase() === 'class');
      if (idx !== -1 && words[idx + 1]) return { type: 'class', target: words[idx + 1] };
    }
    if (lowerText.includes('function ')) {
      const idx = words.findIndex(w => w.toLowerCase() === 'function');
      if (idx !== -1 && words[idx + 1]) return { type: 'function', target: words[idx + 1] };
    }
    if (lowerText.includes('module ')) {
      const idx = words.findIndex(w => w.toLowerCase() === 'module');
      if (idx !== -1 && words[idx + 1]) return { type: 'module', target: words[idx + 1] };
    }
    if (lowerText.includes('api ') || lowerText.includes('endpoint ')) {
      const idx = words.findIndex(w => w.toLowerCase() === 'api' || w.toLowerCase() === 'endpoint');
      if (idx !== -1 && words[idx + 1]) return { type: 'api', target: words[idx + 1] };
    }
    
    // API route matching
    const apiMatch = text.match(/\b\/[a-zA-Z0-9_\-\/]+/);
    if (apiMatch) {
      return { type: 'api', target: apiMatch[0] };
    }
    
    // Search words following edit actions
    const actionWords = ['modify', 'change', 'update', 'on'];
    for (const action of actionWords) {
      const idx = words.findIndex(w => w.toLowerCase() === action);
      if (idx !== -1 && words[idx + 1]) {
        target = words[idx + 1];
        break;
      }
    }
    
    // Search word preceding changes
    if (!target && lowerText.includes('changes')) {
      const idx = words.findIndex(w => w.toLowerCase() === 'changes');
      if (idx > 0 && words[idx - 1]) {
        target = words[idx - 1];
      }
    }

    if (!target) {
      const capitalized = words.find(w => w[0] === w[0].toUpperCase() && w.toLowerCase() !== 'if' && w.toLowerCase() !== 'what');
      target = capitalized || words[words.length - 1];
    }
    
    // Guess type
    if (target.includes('.') || target.includes('/')) {
      type = 'file';
    } else if (text.includes(target + '()')) {
      type = 'function';
    } else if (target[0] === target[0].toUpperCase()) {
      type = 'class';
    } else {
      type = 'module';
    }
    
    return { type, target };
  }

  function _formatImpactResponse(target, data) {
    const summary = data.summary || {};
    const risk = summary.risk || { level: 'Low', explanation: '' };
    const riskIcon = risk.level === 'High' ? '🔴' : (risk.level === 'Medium' ? '🟡' : '🟢');
    
    const formattedFiles = summary.files?.map(f => `\`${f.split('/').pop()}\``).join(', ') || 'None';
    const formattedClasses = summary.classes?.map(c => `\`${c}\``).join(', ') || 'None';
    const formattedFuncs = summary.functions?.map(f => `\`${f.split('::').pop()}\``).join(', ') || 'None';
    const formattedModules = summary.modules?.map(m => `\`${m}\``).join(', ') || 'None';
    
    return `
### 🔍 Impact Analysis for: \`${data.target}\` (${data.type})

${riskIcon} **Change Risk Level: ${risk.level}**
> ${risk.explanation}

#### 📦 Affected Components Summary:
* **Affected Files (${summary.files?.length || 0})**: ${formattedFiles}
* **Affected Classes (${summary.classes?.length || 0})**: ${formattedClasses}
* **Affected Functions (${summary.functions?.length || 0})**: ${formattedFuncs}
* **Affected Modules (${summary.modules?.length || 0})**: ${formattedModules}

${summary.chains && summary.chains.length > 0 ? `
#### ⛓️ Dependency Chains Traced:
${summary.chains.slice(0, 5).map(c => `* \`${c}\``).join('\n')}
${summary.chains.length > 5 ? `* ... and ${summary.chains.length - 5} more chains` : ''}
` : ''}

*(Tip: The **IMPACT ANALYSIS** panel in the sidebar is now updated. You can click **Visualize Graph** there to see these dependencies dynamically!)*
`;
  }

  function _formatAgentResponse(bundle) {
    const plan = bundle.plan || {};
    const risk = bundle.risk || { level: 'Low', explanation: '' };
    const riskIcon = risk.level === 'High' ? '🔴' : (risk.level === 'Medium' ? '🟡' : '🟢');
    const stats = bundle.stats || {};
    const val = (bundle.validation || {}).summary || {};

    const fileLines = (label, arr) => {
      arr = arr || [];
      if (!arr.length) return '';
      const shown = arr.slice(0, 8).map(f => `\`${(typeof f === 'string' ? f : (f.to || f.path || '')).split('/').pop()}\``).join(', ');
      const extra = arr.length > 8 ? ` …(+${arr.length - 8})` : '';
      return `* **${label} (${arr.length})**: ${shown}${extra}\n`;
    };

    const intentLabel = { feature: 'Feature Enhancement', bug: 'Bug Fix', refactor: 'Refactoring' }[bundle.intent] || bundle.intent;

    let md = `### 🤖 ${intentLabel} — Proposed Changes\n\n`;
    md += `**Provider:** \`${bundle.provider}\`  |  ${riskIcon} **Risk: ${risk.level}**\n\n`;
    if (bundle.understanding) md += `> ${bundle.understanding}\n\n`;

    md += `#### 📋 Modification Plan\n`;
    md += fileLines('Modify', plan.files_to_modify);
    md += fileLines('Create', plan.files_to_create);
    md += fileLines('Delete', plan.files_to_delete);
    md += fileLines('Tests', plan.tests_to_update);
    if (!(plan.files_to_modify || []).length && !(plan.files_to_create || []).length && !(plan.files_to_delete || []).length) {
      md += `* *No file changes were generated.*\n`;
    }

    if ((bundle.patches || []).length) {
      md += `\n#### 🩹 Generated Changes (${bundle.patches.length})\n`;
      bundle.patches.slice(0, 8).forEach(p => {
        md += `* \`${p.change_type}\` ${p.path.split('/').pop()} — +${p.additions}/−${p.removals}\n`;
      });
    }

    md += `\n#### ✅ Validation\n`;
    md += `Passed: ${val.passed || 0} · Warnings: ${val.warnings || 0} · Failed: ${val.failed || 0}\n\n`;
    md += `*(Open the **DEVELOPMENT PLAN** panel in the sidebar and click any change to preview its diff. These changes are proposals only — nothing was written to disk.)*`;
    return md;
  }

  function _formatValidationResponse(report, opts) {
    if (!report) return '**Validation Error**: could not produce a report.';
    opts = opts || {};
    const passed = report.validation_status === 'PASSED';
    const icon = passed ? '✅' : '❌';
    const risk = report.risk || { level: 'Low' };
    const riskIcon = risk.level === 'High' ? '🔴' : (risk.level === 'Medium' ? '🟡' : '🟢');
    const st = report.stages || {};
    const tests = st.tests || { status: 'SKIPPED' };

    if (opts.whyFail) {
      const errs = report.summary.errors || [];
      if (passed && !errs.length) return `✅ Validation **PASSED** — there are no errors. ${report.summary.warning_count || 0} warning(s).`;
      let md = `### ❌ Why validation flagged issues\n\n`;
      if (errs.length) md += errs.map(e => `* 🔴 ${e}`).join('\n') + '\n\n';
      if (tests.status === 'FAILED') md += `* 🔴 Tests failed: ${tests.failed} failing\n\n`;
      md += `Fix these, then ask me to **regenerate** or **run validation** again.`;
      return md;
    }

    if (opts.tests) {
      if (tests.status === 'SKIPPED') return `🧪 **Tests:** no runnable tests were detected in this project, so test execution was skipped.`;
      if (tests.status === 'TIMEOUT') return `🧪 **Tests:** the run exceeded the time limit and was aborted.`;
      return `🧪 **Test Results (${tests.framework}):** ${tests.status} — ${tests.passed} passed, ${tests.failed} failed.`;
    }

    const s = report.summary || {};
    const stageLine = ['syntax', 'static', 'dependency', 'tests', 'impact']
      .map(k => `${k}: ${(st[k] || {}).status || '—'}`).join(' · ');
    let md = `### ${icon} Validation ${report.validation_status}\n\n`;
    md += `${riskIcon} **Risk: ${risk.level}**  ·  Files: ${s.files_modified}✏️ ${s.files_created}➕ ${s.files_deleted}🗑️\n\n`;
    md += `**Stages:** ${stageLine}\n\n`;
    md += `**Errors:** ${s.error_count || 0}  ·  **Warnings:** ${s.warning_count || 0}  ·  **Tests:** ${s.tests}\n\n`;
    if ((s.errors || []).length) md += (s.errors.slice(0, 5).map(e => `* 🔴 ${e}`).join('\n')) + '\n\n';
    md += passed
      ? `Changes look safe. Say **"approve changes"** to record approval (nothing is written to disk), or **"reject changes"** / **"regenerate"**.`
      : `Validation found blocking issues — resolve them, then **regenerate**. Approval is disabled until it passes.`;
    md += `\n\n*(See the **VALIDATION & APPROVAL** sidebar panel for the full report and buttons.)*`;
    return md;
  }

  function _formatDecisionResponse(kind, res, report) {
    if (kind === 'approve') {
      const ready = res && res.ready_to_apply;
      return `### ✅ Changes Approved\n\nApproval recorded${ready ? ' — **ready for Phase 7 (apply)**' : ''}. **No source files were modified** — actual application happens in a later phase.`;
    }
    return `### 🛑 Changes Rejected\n\nThe proposal has been discarded. **No source files were modified.** Ask me to **regenerate** or describe a new change.`;
  }

  function _formatSourceResponse(kind, res) {
    if (!res) return '**Source Update Error**: no response.';
    if (kind === 'apply') {
      if (res.status === 'SUCCESS') {
        const a = res.applied || [];
        let md = `### ✅ Changes Applied\n\n${a.length} file change(s) written to disk and the workspace was refreshed.\n\n`;
        md += a.slice(0, 10).map(x => `* \`${x.change_type}\` ${x.path.split('/').pop()}`).join('\n');
        if (res.git && res.git.committed) md += `\n\n📦 Committed to git (\`${res.git.branch}\`).`;
        md += `\n\n*(Say **"undo last change"** to revert, or **"show change history"**.)*`;
        return md;
      }
      if (res.status === 'NEEDS_REGENERATE') return `### ⚠️ Project Changed\n\n${res.message}\n\n${(res.problems || []).map(p => `* ${p}`).join('\n')}\n\nSay **"regenerate"** to rebuild the changes.`;
      if (res.status === 'ROLLED_BACK') return `### ↩️ Update Failed — Rolled Back\n\n${res.message}\n\nNo partial changes remain.`;
      return `### 🛑 Not Applied\n\n${res.message || res.error || 'Apply was blocked.'}`;
    }
    if (kind === 'undo') {
      if (res.status === 'UNDONE') return `### ↩️ Undone\n\nPrevious version restored and the workspace refreshed.`;
      return `${res.message || 'Nothing to undo.'}`;
    }
    if (kind === 'rollback') {
      if (res.status === 'UNDONE') return `### ↩️ Rolled Back\n\nBackup restored and the workspace refreshed.`;
      return `${res.message || 'Could not roll back.'}`;
    }
    return JSON.stringify(res);
  }

  function _formatHistoryResponse(ops) {
    ops = ops || [];
    if (!ops.length) return 'No changes have been applied yet.';
    let md = `### 🕑 Change History (${ops.length})\n\n`;
    ops.slice(0, 10).forEach(op => {
      const s = op.summary || {};
      const icon = op.undone ? '↩️' : '✅';
      md += `* ${icon} **${op.request || '(no request)'}** — ✏️${s.modified || 0} ➕${s.created || 0} 🗑️${s.deleted || 0}${op.undone ? ' _(undone)_' : ''}\n`;
    });
    md += `\n*(Use the **CHANGE HISTORY** sidebar panel to roll back any operation, or say **"undo last change"**.)*`;
    return md;
  }

  function runQuickCommand(cmdText) {
    const textarea = document.getElementById('chat-user-input');
    if (textarea) {
      textarea.value = cmdText;
      _sendMessage();
    }
  }

  return { init, handleLinkClick, runQuickCommand };
})();

// Bind globally for inline onclick attributes
window.ChatPanel = ChatPanel;
window.Icons = Icons;
