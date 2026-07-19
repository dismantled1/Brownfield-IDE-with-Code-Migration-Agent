/**
 * explorer.js — Project file tree with lazy loading and full file management.
 *
 * Architecture:
 *  - Root children loaded at project open (depth=1)
 *  - Subdirectory children fetched on-demand when expanded
 *  - Children cached client-side; invalidated on create/rename/delete
 *  - Context menu for all file operations
 *  - Inline rename with F2 / double-click
 */

const Explorer = (() => {
  let _projectRoot = null;
  let _projectName = null;

  // childrenCache: relative path → FileNode[]
  const _childrenCache = new Map();
  // expandedPaths: Set of relative paths currently expanded
  const _expandedPaths = new Set();

  let _searchQuery  = '';
  let _searchTimer  = null;
  let _contextTarget = null;
  let _selectedPath  = null;
  let _selectedType  = null;

  function _setSelected(path, type) {
    _selectedPath = path;
    _selectedType = type;
    EventBus.emit('explorer:select', { path, type });
  }

  function getSelectedPath() { return _selectedPath; }
  function getSelectedType() { return _selectedType; }
  function getSelectedFolder() {
    if (_selectedType === 'folder') return _selectedPath;
    if (_selectedPath) {
      const idx = _selectedPath.lastIndexOf('/');
      return idx !== -1 ? _selectedPath.substring(0, idx + 1) : _selectedPath;
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------

  function init() {
    EventBus.on('project:opened', ({ projectName, projectPath, tree }) => {
      _projectRoot = projectPath;
      _projectName = projectName;
      _childrenCache.clear();
      _expandedPaths.clear();
      _restoreExpanded();
      _renderTree(tree);
    });

    EventBus.on('project:closed',   _clearTree);
    EventBus.on('explorer:refresh', ({ path } = {}) => {
      if (path) _childrenCache.delete(path);
      else      { _childrenCache.clear(); _refresh(); }
    });

    _bindSearch();
    _bindContextMenu();
    _bindHeaderButtons();
  }

  // ---------------------------------------------------------------------------
  // Restore expanded state from WorkspaceState
  // ---------------------------------------------------------------------------

  function _restoreExpanded() {
    const saved = WorkspaceState.get().expandedFolders || [];
    saved.forEach(p => _expandedPaths.add(p));
  }

  function _saveExpanded() {
    WorkspaceState.setExpandedFolders([..._expandedPaths]);
  }

  // ---------------------------------------------------------------------------
  // Render tree
  // ---------------------------------------------------------------------------

  function _renderTree(rootNode) {
    const container = document.getElementById('explorer-tree');
    if (!container) return;

    container.innerHTML = '';

    // Cache the root children
    if (rootNode.children) {
      _childrenCache.set('', rootNode.children);
      rootNode.children.forEach(child => {
        if (child.type === 'folder' && child.children) {
          _childrenCache.set(child.path, child.children);
        }
      });
    }

    // Update explorer title
    const titleEl = document.getElementById('explorer-title');
    if (titleEl) titleEl.textContent = _projectName || 'EXPLORER';

    // Render children of root
    const children = rootNode.children || [];
    children.forEach(node => {
      container.appendChild(_buildNode(node, 0));
    });

    if (!children.length) {
      container.innerHTML = '<div class="tree-empty-folder">Empty project</div>';
    }
  }

  function _buildNode(node, depth) {
    const wrapper = document.createElement('div');
    wrapper.className = `tree-node${node.type === 'folder' ? ' folder' : ' file'}`;
    wrapper.dataset.path = node.path;
    wrapper.dataset.type = node.type;

    const isExpanded = _expandedPaths.has(node.path);

    // Row
    const row = document.createElement('div');
    row.className = 'tree-node-row';
    row.style.paddingLeft = `${8 + depth * 16}px`;
    row.title = node.path;

    // Arrow (folders only)
    const arrow = document.createElement('span');
    arrow.className = `tree-arrow${node.type === 'file' ? ' empty' : ''}${isExpanded ? ' expanded' : ''}`;
    arrow.innerHTML = Icons.getUI('chevronRight');
    row.appendChild(arrow);

    // Icon
    const icon = document.createElement('span');
    icon.className = 'tree-icon';
    if (node.type === 'folder') {
      icon.innerHTML = Icons.getFolderIcon(node.name, isExpanded);
    } else {
      icon.innerHTML = Icons.getFileIcon(node.extension);
    }
    row.appendChild(icon);

    // Name
    const nameEl = document.createElement('span');
    nameEl.className = 'tree-node-name';
    nameEl.textContent = node.name;
    row.appendChild(nameEl);

    // Hover actions
    const actions = document.createElement('span');
    actions.className = 'tree-node-actions';
    if (node.type === 'folder') {
      actions.innerHTML = `
        <button class="tree-node-action-btn" data-action="new-file" title="New File">${Icons.getUI('newFile')}</button>
        <button class="tree-node-action-btn" data-action="new-folder" title="New Folder">${Icons.getUI('newFolder')}</button>
      `;
    }
    row.appendChild(actions);

    wrapper.appendChild(row);

    // Children container (folders)
    if (node.type === 'folder') {
      const childContainer = document.createElement('div');
      childContainer.className = `tree-children${isExpanded ? '' : ' collapsed'}`;
      wrapper.appendChild(childContainer);

      if (isExpanded) {
        _loadAndRenderChildren(node.path, childContainer, depth + 1);
      }

      // Expand/collapse on click
      row.addEventListener('click', e => {
        if (e.target.closest('.tree-node-actions')) return;
        _setSelected(node.path, 'folder');
        document.querySelectorAll('.tree-node-row.active').forEach(r => r.classList.remove('active'));
        row.classList.add('active');
        _toggleFolder(node, wrapper, childContainer, arrow, icon, depth);
      });
    } else {
      // Open file on click
      row.addEventListener('click', e => {
        if (e.target.closest('.tree-node-actions')) return;
        _setSelected(node.path, 'file');
        _openFile(node);
        document.querySelectorAll('.tree-node-row.active').forEach(r => r.classList.remove('active'));
        row.classList.add('active');
      });
    }

    // Double-click to rename
    row.addEventListener('dblclick', e => {
      e.preventDefault();
      e.stopPropagation();
      _startRename(node, nameEl, wrapper);
    });

    // F2 rename on selected node
    row.addEventListener('keydown', e => {
      if (e.key === 'F2') { e.preventDefault(); _startRename(node, nameEl, wrapper); }
    });

    // Right-click context menu
    row.addEventListener('contextmenu', e => {
      e.preventDefault();
      _showContextMenu(e, node, wrapper);
    });

    // Hover action buttons
    actions.addEventListener('click', async e => {
      e.stopPropagation();
      const btn = e.target.closest('[data-action]');
      if (!btn) return;
      const action = btn.dataset.action;
      if (action === 'new-file')   await _createFileIn(node.path, wrapper);
      if (action === 'new-folder') await _createFolderIn(node.path, wrapper);
    });

    return wrapper;
  }

  // ---------------------------------------------------------------------------
  // Folder expand / collapse
  // ---------------------------------------------------------------------------

  async function _toggleFolder(node, wrapper, childContainer, arrow, icon, depth) {
    const isExpanded = _expandedPaths.has(node.path);

    if (isExpanded) {
      // Collapse
      _expandedPaths.delete(node.path);
      arrow.classList.remove('expanded');
      icon.innerHTML = Icons.getFolderIcon(node.name, false);
      childContainer.classList.add('collapsed');
      _saveExpanded();
    } else {
      // Expand
      _expandedPaths.add(node.path);
      arrow.classList.add('expanded');
      icon.innerHTML = Icons.getFolderIcon(node.name, true);
      childContainer.classList.remove('collapsed');
      await _loadAndRenderChildren(node.path, childContainer, depth + 1);
      _saveExpanded();
    }
  }

  async function _loadAndRenderChildren(folderPath, container, depth) {
    // Check cache first
    if (_childrenCache.has(folderPath)) {
      _renderChildren(_childrenCache.get(folderPath), container, depth);
      return;
    }

    // Show loading skeleton
    container.innerHTML = `
      <div class="tree-skeleton" style="padding-left: ${8 + depth * 16}px">
        <div class="tree-skeleton-line" style="width: 60%; height: 10px;"></div>
      </div>
    `;

    try {
      const children = await API.fs.children(folderPath || '');
      _childrenCache.set(folderPath, children);
      _renderChildren(children, container, depth);
    } catch (err) {
      container.innerHTML = `<div class="tree-empty-folder" style="padding-left: ${8 + depth * 16}px">Error loading: ${Helpers.escapeHtml(err.message)}</div>`;
    }
  }

  function _renderChildren(children, container, depth) {
    container.innerHTML = '';
    if (!children.length) {
      container.innerHTML = `<div class="tree-empty-folder" style="padding-left: ${8 + depth * 16}px">Empty folder</div>`;
      return;
    }
    children.forEach(child => {
      container.appendChild(_buildNode(child, depth));
    });
  }

  // ---------------------------------------------------------------------------
  // File opening
  // ---------------------------------------------------------------------------

  async function _openFile(node) {
    try {
      const data = await API.fs.readFile(node.path);
      EventBus.emit('file:open', {
        path:     data.path,
        name:     node.name,
        language: data.language,
        content:  data.content,
      });
    } catch (err) {
      Toast.show(`Cannot open "${node.name}": ${err.message}`, 'error');
    }
  }

  // ---------------------------------------------------------------------------
  // Inline rename
  // ---------------------------------------------------------------------------

  function _startRename(node, nameEl, wrapper) {
    const row = wrapper.querySelector('.tree-node-row');
    row.classList.add('rename-mode');

    const input = document.createElement('input');
    input.type      = 'text';
    input.className = 'tree-rename-input';
    input.value     = node.name;

    nameEl.replaceWith(input);
    input.focus();
    input.select();

    const finish = async (commit) => {
      input.replaceWith(nameEl);
      row.classList.remove('rename-mode');

      if (!commit) return;
      const newName = input.value.trim();
      if (!newName || newName === node.name) return;

      try {
        const updated = await API.fs.rename(node.path, newName);
        const oldPath = node.path;
        node.name     = updated.name;
        node.path     = updated.path;
        nameEl.textContent = updated.name;
        wrapper.dataset.path = updated.path;
        _invalidateParent(oldPath);
        EventBus.emit('file:renamed', { oldPath, newPath: updated.path, node: updated });
        Toast.show(`Renamed to "${updated.name}"`, 'success');
      } catch (err) {
        Toast.show(`Rename failed: ${err.message}`, 'error');
      }
    };

    input.addEventListener('blur',    () => finish(true));
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter')  { e.preventDefault(); finish(true); }
      if (e.key === 'Escape') { e.preventDefault(); finish(false); }
    });
  }

  // ---------------------------------------------------------------------------
  // Create / Delete
  // ---------------------------------------------------------------------------

  async function _createFileIn(folderPath, folderWrapper) {
    const name = await Helpers.promptModal({
      title: `${Icons.getUI('newFile')} New File`,
      label: 'File name:',
      placeholder: 'index.js',
      confirmText: 'Create',
    });
    if (!name) return;

    const newPath = folderPath ? `${folderPath}/${name}` : name;
    try {
      const node = await API.fs.createFile(newPath);
      _invalidateFolder(folderPath, folderWrapper);
      EventBus.emit('file:created', { path: newPath, node });
      EventBus.emit('file:open', { path: newPath, name: node.name, language: 'plaintext', content: '' });
      Toast.show(`Created "${name}"`, 'success');
    } catch (err) {
      Toast.show(`Create failed: ${err.message}`, 'error');
    }
  }

  async function _createFolderIn(folderPath, folderWrapper) {
    const name = await Helpers.promptModal({
      title: `${Icons.getUI('newFolder')} New Folder`,
      label: 'Folder name:',
      placeholder: 'my-folder',
      confirmText: 'Create',
    });
    if (!name) return;

    const newPath = folderPath ? `${folderPath}/${name}` : name;
    try {
      const node = await API.fs.createFolder(newPath);
      _invalidateFolder(folderPath, folderWrapper);
      EventBus.emit('folder:created', { path: newPath, node });
      Toast.show(`Created folder "${name}"`, 'success');
    } catch (err) {
      Toast.show(`Create folder failed: ${err.message}`, 'error');
    }
  }

  async function _deleteItem(node, wrapper) {
    const what = node.type === 'folder' ? `folder "${node.name}" and all its contents` : `"${node.name}"`;
    const ok = await Helpers.confirmModal({
      title: `Delete ${node.type === 'folder' ? 'Folder' : 'File'}`,
      message: `Are you sure you want to delete ${what}? This cannot be undone.`,
      confirmText: 'Delete',
      danger: true,
    });
    if (!ok) return;

    try {
      await API.fs.deleteItem(node.path);
      const parentPath = Helpers.dirname(node.path);
      _childrenCache.delete(parentPath);
      wrapper.remove();
      EventBus.emit('file:deleted', { path: node.path });
      Toast.show(`Deleted "${node.name}"`, 'success');
    } catch (err) {
      Toast.show(`Delete failed: ${err.message}`, 'error');
    }
  }

  // ---------------------------------------------------------------------------
  // Cache invalidation helpers
  // ---------------------------------------------------------------------------

  function _invalidateFolder(folderPath, folderWrapper) {
    _childrenCache.delete(folderPath);
    // Re-render if expanded
    if (_expandedPaths.has(folderPath)) {
      const childContainer = folderWrapper.querySelector('.tree-children');
      if (childContainer) {
        const depth = parseInt(folderWrapper.querySelector('.tree-node-row').style.paddingLeft) / 16;
        _loadAndRenderChildren(folderPath, childContainer, depth + 1);
      }
    }
  }

  function _invalidateParent(itemPath) {
    const parent = Helpers.dirname(itemPath);
    _childrenCache.delete(parent);
  }

  // ---------------------------------------------------------------------------
  // Context Menu
  // ---------------------------------------------------------------------------

  function _bindContextMenu() {
    document.addEventListener('click', () => _hideContextMenu());
    document.addEventListener('contextmenu', e => {
      if (!e.target.closest('.tree-node-row')) _hideContextMenu();
    });
  }

  function _showContextMenu(e, node, wrapper) {
    _hideContextMenu();
    _contextTarget = { node, wrapper };

    const menu = document.getElementById('context-menu');
    menu.innerHTML = '';

    const items = node.type === 'folder'
      ? [
          { label: 'New File',         icon: 'newFile',   action: 'new-file'   },
          { label: 'New Folder',        icon: 'newFolder', action: 'new-folder' },
          { sep: true },
          { label: 'Rename',            icon: 'pencil',    action: 'rename'     },
          { label: 'Copy Path',         icon: 'copy',      action: 'copy-path'  },
          { sep: true },
          { label: 'Refresh',           icon: 'refresh',   action: 'refresh'    },
          { sep: true },
          { label: 'Delete',            icon: 'trash',     action: 'delete',    danger: true },
        ]
      : [
          { label: 'Open',              icon: 'file',      action: 'open'       },
          { label: 'Rename',            icon: 'pencil',    action: 'rename'     },
          { label: 'Copy Path',         icon: 'copy',      action: 'copy-path'  },
          { sep: true },
          { label: 'Delete',            icon: 'trash',     action: 'delete',    danger: true },
        ];

    items.forEach(item => {
      if (item.sep) {
        menu.appendChild(Helpers.el('div', { class: 'context-separator' }));
        return;
      }
      const el = Helpers.el('div', {
        class: `context-item${item.danger ? ' danger' : ''}`,
        onclick: () => { _handleContextAction(item.action, node, wrapper); _hideContextMenu(); },
      });
      el.innerHTML = Icons.getUI(item.icon) + ` <span>${item.label}</span>`;
      menu.appendChild(el);
    });

    // Position
    const margin = 8;
    let x = e.clientX, y = e.clientY;
    menu.style.display = 'block';
    const rect = menu.getBoundingClientRect();
    if (x + rect.width  > window.innerWidth  - margin) x = window.innerWidth  - rect.width  - margin;
    if (y + rect.height > window.innerHeight - margin)  y = window.innerHeight - rect.height - margin;
    menu.style.left = x + 'px';
    menu.style.top  = y + 'px';
  }

  function _hideContextMenu() {
    const menu = document.getElementById('context-menu');
    if (menu) menu.style.display = 'none';
    _contextTarget = null;
  }

  async function _handleContextAction(action, node, wrapper) {
    const row    = wrapper.querySelector('.tree-node-row');
    const nameEl = row.querySelector('.tree-node-name');

    switch (action) {
      case 'open':       await _openFile(node); break;
      case 'rename':     _startRename(node, nameEl, wrapper); break;
      case 'copy-path':  Helpers.copyToClipboard(node.path); Toast.show('Path copied', 'success'); break;
      case 'delete':     await _deleteItem(node, wrapper); break;
      case 'new-file':   await _createFileIn(node.path, wrapper); break;
      case 'new-folder': await _createFolderIn(node.path, wrapper); break;
      case 'refresh':
        _childrenCache.delete(node.path);
        const childContainer = wrapper.querySelector('.tree-children');
        if (childContainer && _expandedPaths.has(node.path)) {
          const depth = Math.round((parseInt(row.style.paddingLeft) - 8) / 16);
          await _loadAndRenderChildren(node.path, childContainer, depth + 1);
        }
        break;
    }
  }

  // ---------------------------------------------------------------------------
  // Search
  // ---------------------------------------------------------------------------

  function _bindSearch() {
    const input  = document.getElementById('explorer-search-input');
    const clear  = document.getElementById('explorer-search-clear');
    const results= document.getElementById('explorer-search-results');

    if (!input) return;

    input.addEventListener('input', () => {
      const q = input.value.trim();
      _searchQuery = q;
      if (clear) clear.style.display = q ? 'flex' : 'none';

      clearTimeout(_searchTimer);
      if (!q) {
        if (results) Helpers.hide(results);
        return;
      }
      _searchTimer = setTimeout(() => _doSearch(q), 300);
    });

    if (clear) {
      clear.addEventListener('click', () => {
        input.value = '';
        _searchQuery = '';
        clear.style.display = 'none';
        if (results) Helpers.hide(results);
      });
    }
  }

  async function _doSearch(query) {
    const results = document.getElementById('explorer-search-results');
    if (!results) return;

    results.innerHTML = '<div class="search-results-header">Searching…</div>';
    Helpers.show(results);

    try {
      const data = await API.fs.search(query, 50);
      if (!data.nodes.length) {
        results.innerHTML = '<div class="search-results-header">No results found</div>';
        return;
      }
      results.innerHTML = `<div class="search-results-header">${data.total} result${data.total !== 1 ? 's' : ''}</div>`;
      data.nodes.forEach(node => {
        const row = Helpers.el('div', { class: 'tree-node-row', style: { paddingLeft: '12px' }, title: node.path });
        row.innerHTML = `
          <span class="tree-arrow empty"></span>
          <span class="tree-icon">${node.type === 'folder' ? Icons.getFolderIcon(node.name) : Icons.getFileIcon(node.extension)}</span>
          <span class="tree-node-name">${Helpers.escapeHtml(node.name)}</span>
        `;
        const sub = Helpers.el('div', { style: { fontSize: 'var(--text-xs)', color: 'var(--color-text-disabled)', paddingLeft: '44px', paddingBottom: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, Helpers.truncateMid(node.path, 40));
        if (node.type === 'file') {
          row.addEventListener('click', () => _openFile(node));
        }
        results.appendChild(row);
        results.appendChild(sub);
      });
    } catch (err) {
      results.innerHTML = `<div class="search-results-header">Error: ${Helpers.escapeHtml(err.message)}</div>`;
    }
  }

  // ---------------------------------------------------------------------------
  // Header buttons
  // ---------------------------------------------------------------------------

  function _bindHeaderButtons() {
    document.getElementById('btn-explorer-new-file')?.addEventListener('click', () => {
      Helpers.promptModal({ title: 'New File', label: 'Path (relative to project):', placeholder: 'src/app.js', confirmText: 'Create' })
        .then(path => { if (path) API.fs.createFile(path).then(() => _refresh()).catch(e => Toast.show(e.message, 'error')); });
    });
    document.getElementById('btn-explorer-new-folder')?.addEventListener('click', () => {
      Helpers.promptModal({ title: 'New Folder', label: 'Path (relative to project):', placeholder: 'src/components', confirmText: 'Create' })
        .then(path => { if (path) API.fs.createFolder(path).then(() => _refresh()).catch(e => Toast.show(e.message, 'error')); });
    });
    document.getElementById('btn-explorer-refresh')?.addEventListener('click', _refresh);
  }

  // ---------------------------------------------------------------------------
  // Refresh
  // ---------------------------------------------------------------------------

  async function _refresh() {
    if (!_projectRoot) return;
    _childrenCache.clear();
    try {
      const tree = await API.fs.tree(1);
      _renderTree(tree);
    } catch (err) {
      Toast.show(`Refresh failed: ${err.message}`, 'error');
    }
  }

  function _clearTree() {
    _projectRoot = null;
    _childrenCache.clear();
    _expandedPaths.clear();
    const container = document.getElementById('explorer-tree');
    if (container) container.innerHTML = '';
    const titleEl = document.getElementById('explorer-title');
    if (titleEl) titleEl.textContent = 'EXPLORER';
  }

  return { init, getSelectedPath, getSelectedType, getSelectedFolder };
})();
