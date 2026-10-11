const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../apps/depthead/static/depthead/js/shared_windows.js'), 'utf8');

function setup() {
  let submit, click, resolve, reject;
  let calls = 0;
  const request = new Promise((yes, no) => { resolve = yes; reject = no; });
  const button = { disabled: false, focused: false, focus() { this.focused = true; } };
  const loading = { hidden: true };
  const error = { hidden: true, textContent: '' };
  const form = { matches: selector => selector === '.shared-window-form', querySelector: () => button };
  const card = {
    tabs: [], panels: [],
    dataset: { endpoint: '/depthead/api/shared-windows/' }, innerHTML: 'Previous results',
    attributes: {},
    querySelector(selector) {
      if (selector === '.shared-window-loading') return loading;
      if (selector === '.shared-window-error') return error;
      return button;
    },
    querySelectorAll(selector) { return selector === '.shared-window-tabs button' ? this.tabs : this.panels; },
    addEventListener(event, callback) { if (event === 'submit') submit = callback; if (event === 'click') click = callback; },
    setAttribute(key, value) { this.attributes[key] = value; },
    removeAttribute(key) { delete this.attributes[key]; },
  };
  const fetch = (url, options) => {
    calls++;
    assert.equal(url.pathname, '/depthead/api/shared-windows/');
    assert.equal(url.searchParams.get('date'), '2026-10-12');
    assert.equal(options.credentials, 'same-origin');
    return request;
  };
  vm.runInNewContext(source, {
    document: { querySelector: () => card }, fetch, URL, URLSearchParams, AbortController,
    FormData: class extends Array { constructor() { super(['date', '2026-10-12'], ['duration', '120']); } },
    window: { fetch, location: { origin: 'http://localhost' }, setTimeout: () => 1, clearTimeout: () => {} },
  });
  return { card, button, loading, error, resolve, reject, calls: () => calls,
    click: target => click({ target: { closest: () => target } }),
    submit: () => submit({ target: form, preventDefault() {} }) };
}

test('loading keeps prior content, disables submit, and ignores duplicate submits', async () => {
  const ui = setup();
  const pending = ui.submit();
  assert.equal(ui.button.disabled, true);
  assert.equal(ui.loading.hidden, false);
  assert.equal(ui.card.attributes['aria-busy'], 'true');
  assert.equal(ui.card.innerHTML, 'Previous results');
  await ui.submit();
  assert.equal(ui.calls(), 1);
  ui.resolve({ ok: true, status: 200, json: async () => ({ html: 'New results' }) });
  await pending;
  assert.equal(ui.card.innerHTML, 'New results');
  assert.equal(ui.button.disabled, false);
  assert.equal(ui.loading.hidden, true);
  assert.equal(ui.card.attributes['aria-busy'], undefined);
  assert.equal(ui.button.focused, true);
});

test('time-window buttons switch the visible faculty panel without fetching', () => {
  const ui = setup();
  ui.card.tabs = [1, 2].map(index => ({
    pressed: index === 1 ? 'true' : 'false',
    setAttribute(key, value) { this.pressed = value; },
    getAttribute() { return `panel-${index}`; },
  }));
  ui.card.panels = [{ id: 'panel-1', hidden: false }, { id: 'panel-2', hidden: true }];
  ui.click(ui.card.tabs[1]);
  assert.equal(ui.card.panels[0].hidden, true);
  assert.equal(ui.card.panels[1].hidden, false);
  assert.equal(ui.card.tabs[0].pressed, 'false');
  assert.equal(ui.card.tabs[1].pressed, 'true');
  assert.equal(ui.calls(), 0);
});

test('failure retains previous results and restores usable form', async () => {
  const ui = setup();
  const pending = ui.submit();
  ui.reject(new Error('Connection failed'));
  await pending;
  assert.equal(ui.card.innerHTML, 'Previous results');
  assert.equal(ui.error.hidden, false);
  assert.equal(ui.error.textContent, 'Connection failed');
  assert.equal(ui.button.disabled, false);
  assert.equal(ui.card.attributes['aria-busy'], undefined);
});

test('validation errors update the card without navigating', async () => {
  const ui = setup();
  const pending = ui.submit();
  ui.resolve({ ok: false, status: 400, json: async () => ({ html: 'Date validation error' }) });
  await pending;
  assert.equal(ui.card.innerHTML, 'Date validation error');
  assert.equal(ui.button.disabled, false);
});
