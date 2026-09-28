const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/js/admin_navigation_loading.js', 'utf8');

function setup() {
  const listeners = {};
  const microtasks = [];
  let timeout;
  function node() {
    return {children: [], style: {}, attributes: {}, inert: false,
      classes: new Set(),
      append(child) { this.children.push(child); child.parent = this; },
      remove() { this.parent.children = this.parent.children.filter(child => child !== this); },
      setAttribute(key, value) { this.attributes[key] = value; },
      getBoundingClientRect() { return {left: 250, top: 0, width: 750}; },
      get classList() { return {add: value => this.classes.add(value), remove: value => this.classes.delete(value)}; },
    };
  }
  const main = node(), body = node();
  const document = {
    body, createElement: node,
    getElementById: () => ({textContent: JSON.stringify({'/depthead/faculty-monitoring/': ['Faculty Monitoring', 'cards']})}),
    querySelector: () => main,
    addEventListener: (type, handler) => { listeners[type] = handler; },
  };
  const window = {
    location: {href: 'https://example.com/depthead/adminFaculty', origin: 'https://example.com'},
    innerHeight: 800,
    addEventListener: (type, handler) => { listeners[type] = handler; },
  };
  vm.runInNewContext(source, {document, window, URL, queueMicrotask: fn => microtasks.push(fn),
    setTimeout: fn => { timeout = fn; return 1; }, clearTimeout: () => {},
  });
  function click(overrides = {}, linkOverrides = {}) {
    const link = {href: 'https://example.com/depthead/faculty-monitoring/', target: '',
      closest: () => true, hasAttribute: () => false, ...linkOverrides};
    const event = {button: 0, defaultPrevented: false, target: {closest: () => link}, ...overrides};
    listeners.click(event);
    return event;
  }
  return {main, body, listeners, click, microtasks, expire: () => timeout()};
}

test('sidebar navigation shows destination placeholders without replacing existing content', () => {
  const app = setup();
  const event = app.click();
  assert.equal(event.defaultPrevented, false);
  assert.equal(app.main.inert, true);
  const overlay = app.body.children[0];
  assert.equal(overlay.children[0].textContent, 'Loading Faculty Monitoring…');
  assert.equal(overlay.children[1].children[0].children.length, 6);
  assert.equal(overlay.style.left, '250px');
});

test('modified, cancelled, download, external, logout and non-sidebar clicks remain untouched', () => {
  const cases = [
    [{ctrlKey: true}, {}], [{metaKey: true}, {}], [{shiftKey: true}, {}], [{altKey: true}, {}],
    [{button: 1}, {}], [{defaultPrevented: true}, {}], [{}, {target: '_blank'}],
    [{}, {hasAttribute: () => true}], [{}, {closest: () => false}],
    [{}, {href: 'https://elsewhere.com/depthead/faculty-monitoring/'}],
    [{}, {href: 'https://example.com/accounts/logout/'}],
  ];
  for (const [event, link] of cases) {
    const app = setup(); app.click(event, link);
    assert.equal(app.body.children.length, 0);
    assert.equal(app.main.inert, false);
  }
});

test('back-forward restore, departure, escape and stalled navigation restore content', () => {
  for (const action of ['pageshow', 'pagehide', 'escape', 'timeout']) {
    const app = setup(); app.click();
    if (action === 'timeout') app.expire();
    else if (action === 'escape') app.listeners.keydown({key: 'Escape'});
    else app.listeners[action]();
    assert.equal(app.body.children.length, 0);
    assert.equal(app.main.inert, false);
    assert.equal(app.main.classes.size, 0);
  }
});

test('a later handler cancelling navigation removes the skeleton', () => {
  const app = setup();
  const event = app.click();
  event.defaultPrevented = true;
  app.microtasks.forEach(fn => fn());
  assert.equal(app.body.children.length, 0);
});
