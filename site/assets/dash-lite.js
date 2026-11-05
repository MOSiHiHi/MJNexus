// dash-lite: a small stand-in for the dashboard runtime, so the radar page runs as a plain static site.
// It covers what knowledge/dashboard/index.html uses: dash.draw, dash.data, dash.params, dash.setParams,
// dash.resetParams, dash.onData, dash.setLink and dash.colors.
// Datasets load on demand from data/<id>.json, only for drawings that are not inside a [hidden] element.
// The URL hash keeps the selection (e.g. #sel=r:res:claude-code), so a view can be linked.
(() => {
  'use strict';
  const BASE = (document.querySelector('meta[name="dash-data"]') || {}).content || 'data/';
  const registry = new Map();    // drawing name -> function or {mount, update, unmount}
  const mounted = new WeakMap(); // element -> what mount returned
  const datasets = new Map();    // id -> {status, data | error}
  const listeners = [];
  let params = readHash();
  let queued = false;

  function readHash() {
    const out = {};
    new URLSearchParams(location.hash.slice(1)).forEach((v, k) => { out[k] = v; });
    return out;
  }
  function writeHash() {
    const q = new URLSearchParams(params).toString();
    history.replaceState(null, '', q ? '#' + q : location.pathname + location.search);
  }
  function load(id) {
    if (datasets.has(id)) return;
    datasets.set(id, { status: 'loading' });
    fetch(BASE + encodeURIComponent(id) + '.json')
      .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then((data) => { datasets.set(id, { status: 'ok', data }); schedule(); })
      .catch((e) => { datasets.set(id, { status: 'error', error: String(e) }); console.error('dataset', id, e); schedule(); });
  }
  const sources = (el) => {
    const host = el.closest('[data-source]');
    return host ? host.dataset.source.split(/\s+/).filter(Boolean) : [];
  };
  function run(name) {
    const fn = registry.get(name);
    if (!fn) return;
    document.querySelectorAll('[data-draw="' + CSS.escape(name) + '"]').forEach((el) => {
      if (el.closest('[hidden]')) return;  // hidden blocks neither load data nor draw
      sources(el).forEach(load);
      try {
        if (typeof fn === 'function') fn(el);
        else {
          if (!mounted.has(el)) mounted.set(el, fn.mount(el));
          fn.update(el, mounted.get(el));
        }
      } catch (e) {
        console.error('drawing', name, e);
      }
    });
  }
  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      for (const cb of listeners) { try { cb(); } catch (e) { console.error(e); } }
      registry.forEach((_, name) => run(name));
    });
  }

  // categorical colours: CSS variables so light and dark themes both read well
  const colors = [1, 2, 3, 4, 5, 6, 7, 8].map((i) => 'var(--cat-' + i + ')');

  window.dash = {
    colors,
    draw(name, fn) {
      if (fn) { registry.set(name, fn); schedule(); } else run(name);
    },
    data(id) {
      if (!datasets.has(id)) load(id);
      return datasets.get(id);
    },
    params: () => ({ ...params }),
    setParams(next) {
      for (const [k, v] of Object.entries(next)) {
        if (v === null || v === undefined || v === '') delete params[k]; else params[k] = String(v);
      }
      writeHash();
      schedule();
    },
    resetParams() { params = {}; writeHash(); schedule(); },
    onData(cb) { listeners.push(cb); schedule(); },
    setLink() {},
  };
  window.addEventListener('hashchange', () => { params = readHash(); schedule(); });
})();
