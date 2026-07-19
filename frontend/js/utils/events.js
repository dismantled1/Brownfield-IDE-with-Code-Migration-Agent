/**
 * events.js — Lightweight event bus for inter-module communication.
 * Modules publish events here instead of directly calling each other,
 * keeping them loosely coupled and ready for future AI phase integration.
 */

const EventBus = (() => {
  const _listeners = {};

  return {
    /**
     * Subscribe to an event.
     * @param {string} event
     * @param {Function} handler
     * @returns {Function} unsubscribe function
     */
    on(event, handler) {
      if (!_listeners[event]) _listeners[event] = [];
      _listeners[event].push(handler);
      return () => this.off(event, handler);
    },

    /** One-time subscription. */
    once(event, handler) {
      const wrapper = (...args) => {
        handler(...args);
        this.off(event, wrapper);
      };
      return this.on(event, wrapper);
    },

    /** Unsubscribe a handler. */
    off(event, handler) {
      if (!_listeners[event]) return;
      _listeners[event] = _listeners[event].filter(h => h !== handler);
    },

    /** Publish an event. */
    emit(event, data) {
      if (!_listeners[event]) return;
      _listeners[event].forEach(h => {
        try { h(data); }
        catch (e) { console.error(`[EventBus] Error in handler for "${event}":`, e); }
      });
    },

    /** Remove all listeners for an event (or all events). */
    clear(event) {
      if (event) delete _listeners[event];
      else Object.keys(_listeners).forEach(k => delete _listeners[k]);
    },
  };
})();

// ---- Known Event Names (documentation) ----
// 'project:opened'        { projectName, projectPath, tree }
// 'project:closed'        {}
// 'file:open'             { path, name, language, content }
// 'file:save'             { path }
// 'file:saved'            { path }
// 'file:close'            { path }
// 'file:renamed'          { oldPath, newPath, node }
// 'file:deleted'          { path }
// 'file:created'          { path, node }
// 'folder:created'        { path, node }
// 'explorer:refresh'      { path? }
// 'editor:change'         { path, isDirty }
// 'editor:ready'          {}
// 'terminal:create'       { sessionId }
// 'terminal:close'        { sessionId }
// 'workspace:restore'     { state }
// 'statusbar:update'      { language?, line?, col?, branch?, project? }
// 'toast:show'            { message, type, duration? }
