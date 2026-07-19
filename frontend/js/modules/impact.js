/**
 * impact.js — Phase 4 Impact Analysis UI & Dependency Graph Module.
 *
 * Manages the IMPACT ANALYSIS sidebar panel, parses dependency changes,
 * computes risk meters, and renders interactive vis.js graph networks in the editor container.
 */

const Impact = (() => {
  let _activeProject = null;
  let _network = null;
  let _nodesDataset = null;
  let _edgesDataset = null;
  let _currentGraphData = null; // cached nodes and edges from API

  function init() {
    _bindAccordion();
    _bindGraphControls();
    _clearUI();

    // Listen for project lifecycle events
    EventBus.on('project:opened', ({ projectPath }) => {
      _activeProject = projectPath;
      _clearUI();
      // Pre-fetch graph data on load so visualizer is fast
      setTimeout(_fetchGraphData, 1000);
    });

    EventBus.on('project:closed', () => {
      _activeProject = null;
      _clearUI();
      _destroyNetwork();
    });

    EventBus.on('analysis:completed', () => {
      if (_activeProject) {
        _fetchGraphData(); // refresh graph data cache after scan
      }
    });

    // Listen for impact triggers from AI Chat or code context menu
    EventBus.on('impact:trigger', async ({ type, target }) => {
      if (!_activeProject) return;

      // Expand impact panel accordion
      const panel = document.getElementById('section-impact');
      if (panel) panel.classList.remove('collapsed');

      _showLoading();

      try {
        const data = await API.impact.analyze(type, target);
        _renderImpactPanel(data);
        // NOTE: We intentionally do NOT build the vis.js network here
        // because the #dependency-graph-container is display:none.
        // vis.js needs a visible container to render properly.
        // The graph is built only when the Visualize button is clicked.
      } catch (err) {
        console.error('[Impact] Analysis failed:', err);
        _renderError(err.message);
      }
    });
  }

  function _bindAccordion() {
    const header = document.getElementById('header-impact');
    const panel = document.getElementById('section-impact');
    if (header && panel) {
      header.addEventListener('click', () => {
        panel.classList.toggle('collapsed');
      });
    }
  }

  function _bindGraphControls() {
    document.getElementById('btn-graph-zoom-in')?.addEventListener('click', () => {
      if (_network) {
        const scale = _network.getScale();
        _network.moveTo({ scale: scale * 1.2, animation: true });
      }
    });

    document.getElementById('btn-graph-zoom-out')?.addEventListener('click', () => {
      if (_network) {
        const scale = _network.getScale();
        _network.moveTo({ scale: scale * 0.8, animation: true });
      }
    });

    document.getElementById('btn-graph-fit')?.addEventListener('click', () => {
      if (_network) _network.fit({ animation: true });
    });

    document.getElementById('btn-graph-close-view')?.addEventListener('click', () => {
      _closeGraphView();
    });
  }

  function _showLoading() {
    const container = document.getElementById('impact-panel-content');
    if (container) {
      container.innerHTML = `
        <div class="analysis-progress-wrapper" style="background:rgba(124,58,237,0.05); border:1px solid rgba(124,58,237,0.15)">
          <div class="progress-label" style="color:var(--color-text-accent)">
            <span>Analyzing Impact...</span>
          </div>
          <div class="progress-track">
            <div class="progress-bar" style="width: 60%"></div>
          </div>
          <div class="progress-status-text">Tracing imports, call hierarchy and API routes...</div>
        </div>
      `;
    }
  }

  function _renderError(msg) {
    const container = document.getElementById('impact-panel-content');
    if (container) {
      container.innerHTML = `<div style="color:var(--color-error); padding: 5px 0;">Analysis failed: ${msg}</div>`;
    }
  }

  function _clearUI() {
    const container = document.getElementById('impact-panel-content');
    if (container) {
      container.innerHTML = `<div style="font-style:italic; color:var(--color-text-muted);">No component analyzed yet</div>`;
    }
  }

  async function _fetchGraphData() {
    try {
      _currentGraphData = await API.impact.graph();
    } catch (err) {
      console.warn('[Impact] Failed to pre-fetch graph nodes:', err);
    }
  }

  // Swap center view to show graph canvas
  function _showGraphView() {
    const graphContainer = document.getElementById('dependency-graph-container');
    const monacoContainer = document.getElementById('monaco-container');
    const welcomeEl = document.getElementById('editor-welcome');

    if (welcomeEl) welcomeEl.style.display = 'none';
    if (monacoContainer) monacoContainer.style.display = 'none';
    if (graphContainer) graphContainer.style.display = 'block';
  }

  // Restore editor view
  function _closeGraphView() {
    const graphContainer = document.getElementById('dependency-graph-container');
    const monacoContainer = document.getElementById('monaco-container');
    const welcomeEl = document.getElementById('editor-welcome');

    if (graphContainer) graphContainer.style.display = 'none';
    const activeTab = typeof TabBar !== 'undefined' ? TabBar.getActive() : null;
    if (activeTab) {
      if (monacoContainer) monacoContainer.style.display = 'block';
    } else {
      if (welcomeEl) welcomeEl.style.display = 'flex';
    }
    if (typeof Editor !== 'undefined') Editor.layout();
  }

  // Group colors in dark theme
  const GROUP_STYLES = {
    module:   { border: '#f59e0b', background: '#381e05', highlight: '#f59e0b' },
    file:     { border: '#3b82f6', background: '#0e265c', highlight: '#3b82f6' },
    class:    { border: '#10b981', background: '#033b24', highlight: '#10b981' },
    function: { border: '#8b5cf6', background: '#311054', highlight: '#8b5cf6' },
    api:      { border: '#06b6d4', background: '#05313d', highlight: '#06b6d4' }
  };

  function _renderImpactPanel(data) {
    const container = document.getElementById('impact-panel-content');
    if (!container) return;

    const esc = Helpers.escapeHtml;
    const summary = data.summary || {};
    const risk = summary.risk || { level: 'Low', explanation: 'No risk recorded.' };

    // Escape code-derived values used below.
    const targetFull = esc(data.target || '');
    const targetShort = esc((data.target || '').split('/').pop());
    const typeEsc = esc(data.type || '');
    const riskLevel = esc(risk.level || 'Low');
    const riskExplanation = esc(risk.explanation || '');

    // Risk classes
    const riskClass = (risk.level || 'low').toLowerCase();
    const riskPill = `<span class="risk-badge ${riskClass}">● ${riskLevel} Risk</span>`;

    // Generate lists
    const filesList = _renderItemsList(summary.files, 'file');
    const classesList = _renderItemsList(summary.classes, 'class');
    const funcsList = _renderItemsList(summary.functions, 'function');
    const modulesList = _renderItemsList(summary.modules, 'module');

    container.innerHTML = `
      <div class="impact-summary-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div style="font-weight:var(--font-weight-semibold); color:var(--color-text-primary); font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:140px;" title="${targetFull}">
            ${targetShort}
          </div>
          ${riskPill}
        </div>
        <div style="font-size:10px; color:var(--color-text-muted); margin-top:2px;">
          Type: <span style="text-transform:uppercase; font-weight:bold; color:var(--color-text-accent);">${typeEsc}</span>
        </div>
        <div style="font-size:11px; color:var(--color-text-secondary); margin-top:4px; line-height:1.4; border-top:1px dashed var(--color-border); padding-top:6px;">
          ${riskExplanation}
        </div>
        
        <button class="btn btn-primary" id="btn-show-graph-canvas" style="font-size:11px; padding:6px; margin-top: var(--space-2); width:100%; display:flex; align-items:center; justify-content:center; gap:6px;">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
            <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
          </svg>
          Visualize Graph
        </button>
      </div>

      <div>
        <div class="impact-group-header">
          <span>Affected Files</span>
          <span class="impact-group-count">${summary.files?.length || 0}</span>
        </div>
        <div class="impact-item-list">${filesList}</div>

        <div class="impact-group-header">
          <span>Affected Classes</span>
          <span class="impact-group-count">${summary.classes?.length || 0}</span>
        </div>
        <div class="impact-item-list">${classesList}</div>

        <div class="impact-group-header">
          <span>Affected Functions</span>
          <span class="impact-group-count">${summary.functions?.length || 0}</span>
        </div>
        <div class="impact-item-list">${funcsList}</div>

        <div class="impact-group-header">
          <span>Affected Modules</span>
          <span class="impact-group-count">${summary.modules?.length || 0}</span>
        </div>
        <div class="impact-item-list">${modulesList}</div>
      </div>
    `;

    // Bind affected-item navigation (data-nav-file → open + highlight)
    container.querySelectorAll('.impact-item-link[data-nav-file]').forEach(link => {
      link.addEventListener('click', () => {
        if (typeof Search !== 'undefined') Search.navigateToResult(link.dataset.navFile, 1);
      });
    });

    // Bind visualize button
    document.getElementById('btn-show-graph-canvas')?.addEventListener('click', async () => {
      // Show container FIRST so vis.js has a visible element to render into
      _showGraphView();
      // Always destroy and rebuild so vis.js gets the correct canvas dimensions
      _destroyNetwork();
      setTimeout(async () => {
        await _visualizeDependencyGraph(data);
      }, 50);
    });
  }

  function _renderItemsList(items, type) {
    if (!items || items.length === 0) {
      return `<div style="font-style:italic; color:var(--color-text-muted); font-size:10px; padding: 4px;">None affected</div>`;
    }
    const esc = Helpers.escapeHtml;
    return items.map(item => {
      const cleanName = esc(item.split('::').pop().split('/').pop());
      const tooltip = esc(item);

      // Resolve a navigable file path (data-* attribute, bound after render).
      let navFile = '';
      if (type === 'file') {
        navFile = item;
      } else if (type === 'function') {
        // signature holds path: e.g. "path/to/file.py::ClassName::func_name"
        navFile = item.split('::')[0];
      }
      const navAttr = navFile ? ` data-nav-file="${esc(navFile)}"` : '';

      return `
        <a class="impact-item-link"${navAttr} title="${tooltip}">
          <span style="font-size:10px;">${Icons.getUI('chevronRight')}</span>
          <span style="text-overflow:ellipsis; overflow:hidden; white-space:nowrap;">${cleanName}</span>
        </a>
      `;
    }).join('');
  }

  function _destroyNetwork() {
    if (_network) {
      _network.destroy();
      _network = null;
    }
  }

  async function _visualizeDependencyGraph(impactData) {
    // 1. Ensure we have graph data (if prefetch failed)
    if (!_currentGraphData) {
      await _fetchGraphData();
    }
    
    const canvasContainer = document.getElementById('dependency-graph-canvas');
    if (!canvasContainer || !_currentGraphData) {
      console.warn('[Impact] Cannot render graph: no canvas or graph data');
      return;
    }

    // impactData may be null when opening graph without a specific analysis
    const targetId = impactData?.target || '';

    _destroyNetwork();

    // Map styles to nodes
    const styledNodes = _currentGraphData.nodes.map(node => {
      const style = GROUP_STYLES[node.group] || { border: '#e2e8f0', background: '#1e1e2f', highlight: '#7c3aed' };
      const isTarget = targetId && node.id.includes(targetId);
      return {
        ...node,
        shape: 'dot',
        size: isTarget ? 22 : 14,
        font: { color: '#e2e8f0', size: 11, face: 'Inter, system-ui, sans-serif' },
        color: {
          border: style.border,
          background: style.background,
          highlight: {
            border: style.highlight,
            background: style.background
          }
        },
        borderWidth: isTarget ? 3 : 1
      };
    });

    const styledEdges = _currentGraphData.edges.map(edge => ({
      ...edge,
      color: {
        color: 'rgba(56, 56, 96, 0.4)',
        highlight: '#7c3aed',
        hover: '#7c3aed'
      },
      width: 1.2
    }));

    _nodesDataset = new vis.DataSet(styledNodes);
    _edgesDataset = new vis.DataSet(styledEdges);

    const data = {
      nodes: _nodesDataset,
      edges: _edgesDataset
    };

    const options = {
      nodes: {
        scaling: { min: 8, max: 24 }
      },
      edges: {
        smooth: { type: 'continuous', forceDirection: 'none', roundness: 0.5 }
      },
      physics: {
        solver: 'forceAtlas2Based',
        forceAtlas2Based: {
          gravitationalConstant: -18,
          centralGravity: 0.015,
          springLength: 90,
          springConstant: 0.12
        },
        stabilization: { iterations: 60, updateInterval: 15, fit: true }
      },
      interaction: {
        hover: true,
        tooltipDelay: 100,
        selectable: true,
        selectConnectedEdges: false
      }
    };

    _network = new vis.Network(canvasContainer, data, options);

    // Node selection / click highlights path
    _network.on('selectNode', params => {
      const selectedId = params.nodes[0];
      _highlightPathForNodeId(selectedId);
    });

    // Reset highlights on background click
    _network.on('click', params => {
      if (params.nodes.length === 0) {
        _resetGraphOpacities();
      }
    });

    // Double-click to jump to editor
    _network.on('doubleClick', params => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        _handleNodeDoubleClick(nodeId);
      }
    });

    // Fit layout on stabilization end — also disables physics for better perf
    _network.once('stabilizationFinished', () => {
      _network.setOptions({ physics: { enabled: false } });
      _network.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
      if (impactData) _highlightImpactPath(impactData);
    });

    // Fallback: force-fit after 3s in case stabilizationFinished fires late or not at all
    setTimeout(() => {
      if (_network) {
        _network.fit({ animation: false });
      }
    }, 3000);
  }

  function _highlightImpactPath(impactData) {
    if (!impactData || !impactData.summary) return;

    // Find the matching node ID in the graph
    // A target could be a file path, class name, function name, etc.
    const target = impactData.target;
    let targetNodeId = null;

    if (impactData.type === 'file') {
      targetNodeId = target;
    } else if (impactData.type === 'class') {
      targetNodeId = `class::${target}`;
    } else if (impactData.type === 'function') {
      targetNodeId = `func::${target}`;
    } else if (impactData.type === 'module') {
      targetNodeId = `module::${target}`;
    } else if (impactData.type === 'api') {
      targetNodeId = `api::${target}`;
    }

    if (targetNodeId && _nodesDataset.get(targetNodeId)) {
      _network.selectNodes([targetNodeId]);
      _highlightPathForNodeId(targetNodeId);
      // Focus on selected target node
      _network.focus(targetNodeId, { scale: 1.1, animation: { duration: 500 } });
    }
  }

  function _highlightPathForNodeId(selectedId) {
    if (!_nodesDataset || !_edgesDataset || !_network) return;

    // Traces all connected edges in both directions
    const visitedNodes = new Set([selectedId]);
    const visitedEdges = new Set();

    // 1. Gather outbound dependencies (edges pointing FROM selectId)
    // 2. Gather inbound dependents (edges pointing TO selectId)
    const allEdges = _edgesDataset.get();
    
    // Find direct and transitive paths
    let changed = true;
    while (changed) {
      changed = false;
      for (const edge of allEdges) {
        const fromNode = edge.from;
        const toNode = edge.to;

        if (visitedNodes.has(fromNode) && !visitedNodes.has(toNode)) {
          visitedNodes.add(toNode);
          visitedEdges.add(edge.id);
          changed = true;
        }
        if (visitedNodes.has(toNode) && !visitedNodes.has(fromNode)) {
          visitedNodes.add(fromNode);
          visitedEdges.add(edge.id);
          changed = true;
        }
      }
    }

    // Update opacities in DataSet
    const allNodes = _nodesDataset.get();
    const updatedNodes = allNodes.map(node => {
      const isPath = visitedNodes.has(node.id);
      return {
        id: node.id,
        color: {
          opacity: isPath ? 1.0 : 0.15
        },
        font: {
          color: isPath ? '#e2e8f0' : 'rgba(226,232,240,0.15)'
        }
      };
    });

    const updatedEdges = allEdges.map(edge => {
      const isPath = visitedEdges.has(edge.id);
      return {
        id: edge.id,
        color: {
          color: isPath ? '#7c3aed' : 'rgba(56,56,96,0.08)'
        },
        width: isPath ? 2.5 : 0.8
      };
    });

    _nodesDataset.update(updatedNodes);
    _edgesDataset.update(updatedEdges);
  }

  function _resetGraphOpacities() {
    if (!_nodesDataset || !_edgesDataset) return;
    
    const allNodes = _nodesDataset.get();
    const updatedNodes = allNodes.map(node => ({
      id: node.id,
      color: { opacity: 1.0 },
      font: { color: '#e2e8f0' }
    }));

    const allEdges = _edgesDataset.get();
    const updatedEdges = allEdges.map(edge => ({
      id: edge.id,
      color: { color: 'rgba(56, 56, 96, 0.4)' },
      width: 1.2
    }));

    _nodesDataset.update(updatedNodes);
    _edgesDataset.update(updatedEdges);
  }

  function _handleNodeDoubleClick(nodeId) {
    _closeGraphView();

    if (!_currentGraphData || !_currentGraphData.nodes) return;
    
    const nodeData = _currentGraphData.nodes.find(n => n.id === nodeId);
    if (nodeData && nodeData.file) {
      if (typeof Editor !== 'undefined') {
        Editor.openAndHighlight(nodeData.file, nodeData.line || 1);
      }
    }
  }

  return { init };
})();

// Bind globally for direct index clicks
window.Impact = Impact;
