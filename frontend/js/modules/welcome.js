/**
 * welcome.js — Welcome screen with Open Folder / Open ZIP and recent projects.
 */

const WelcomeScreen = (() => {
  let _recentProjects = [];

  function init() {
    _bindButtons();
    _loadRecents();
  }

  function _bindButtons() {
    document.getElementById('btn-open-folder').addEventListener('click', showOpenFolderDialog);
    document.getElementById('btn-open-zip').addEventListener('click', showOpenZipDialog);
  }

  async function _loadRecents() {
    try {
      _recentProjects = await API.workspace.recent();
    } catch {
      _recentProjects = [];
    }
    _renderRecents();
  }

  function _renderRecents() {
    const list = document.getElementById('recent-projects-list');
    if (!list) return;

    if (!_recentProjects.length) {
      list.innerHTML = '<div class="welcome-no-recents">No recent projects yet</div>';
      return;
    }

    list.innerHTML = _recentProjects.map(p => `
      <div class="recent-project-item" data-path="${Helpers.escapeHtml(p.path)}" id="recent-${btoa(p.path).replace(/=/g,'')}">
        <div class="recent-icon">${Icons.getUI('folder')}</div>
        <div class="recent-info">
          <div class="recent-name">${Helpers.escapeHtml(p.name)}</div>
          <div class="recent-path" title="${Helpers.escapeHtml(p.path)}">${Helpers.escapeHtml(Helpers.truncateMid(p.path, 45))}</div>
        </div>
        <span class="recent-time">${Helpers.timeAgo(p.opened_at)}</span>
        <button class="recent-remove" title="Remove from recents" data-path="${Helpers.escapeHtml(p.path)}">
          ${Icons.getUI('x')}
        </button>
      </div>
    `).join('');

    // Click to open
    list.querySelectorAll('.recent-project-item').forEach(el => {
      el.addEventListener('click', e => {
        if (e.target.closest('.recent-remove')) return;
        const path = el.dataset.path;
        _openProject(path);
      });
    });

    // Remove button
    list.querySelectorAll('.recent-remove').forEach(btn => {
      btn.addEventListener('click', async e => {
        e.stopPropagation();
        const path = btn.dataset.path;
        try {
          await API.workspace.removeRecent(path);
          _recentProjects = _recentProjects.filter(p => p.path !== path);
          _renderRecents();
        } catch (err) {
          Toast.show(`Could not remove: ${err.message}`, 'error');
        }
      });
    });
  }

  async function showOpenFolderDialog() {
    const path = await Helpers.promptModal({
      title: `${Icons.getUI('folder')} Open Folder`,
      label: 'Enter the absolute path to your project folder:',
      placeholder: 'C:\\Users\\you\\my-project   or   /home/you/my-project',
      confirmText: 'Open',
    });
    if (path) await _openProject(path.trim());
  }

  function showOpenZipDialog() {
    // Trigger hidden file input
    let input = document.getElementById('zip-file-input');
    if (!input) {
      input = document.createElement('input');
      input.type = 'file';
      input.id   = 'zip-file-input';
      input.accept = '.zip';
      input.style.display = 'none';
      document.body.appendChild(input);
    }
    input.onchange = () => {
      if (input.files[0]) _uploadZip(input.files[0]);
      input.value = '';
    };
    input.click();
  }

  async function _openProject(path) {
    _setLoading(true, 'Opening project…');
    try {
      const result = await API.workspace.open(path);
      EventBus.emit('project:opened', {
        projectName: result.project_name,
        projectPath: result.project_path,
        tree: result.tree,
      });
    } catch (err) {
      Toast.show(`Could not open project: ${err.message}`, 'error');
      _setLoading(false);
    }
  }

  async function _uploadZip(file) {
    _setLoading(true, `Uploading ${file.name}…`);
    try {
      const result = await API.fs.uploadZip(file);
      EventBus.emit('project:opened', {
        projectName: result.project_name,
        projectPath: result.project_path,
        tree: result.tree,
      });
    } catch (err) {
      Toast.show(`ZIP upload failed: ${err.message}`, 'error');
      _setLoading(false);
    }
  }

  function _setLoading(on, message = '') {
    let overlay = document.getElementById('welcome-loading');
    if (on) {
      if (!overlay) {
        overlay = Helpers.el('div', { id: 'welcome-loading', class: 'welcome-loading' },
          Helpers.el('div', { class: 'spinner spinner-lg' }),
          Helpers.el('div', { class: 'welcome-loading-text' }, message),
        );
        document.getElementById('welcome-screen').appendChild(overlay);
      } else {
        overlay.querySelector('.welcome-loading-text').textContent = message;
      }
    } else {
      if (overlay) overlay.remove();
    }
  }

  function show() {
    Helpers.show(document.getElementById('welcome-screen'));
    _loadRecents();
  }

  function hide() {
    Helpers.hide(document.getElementById('welcome-screen'));
  }

  return { init, show, hide, showOpenFolderDialog, showOpenZipDialog };
})();
