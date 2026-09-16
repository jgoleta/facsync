const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function setup() {
  let ready, submit, poll;
  const badge = {};
  const button = {disabled: false};
  const form = {dataset: {statusUrl: '/status/', college: 'CCS'}, action: '/settings/',
    querySelector: () => button, addEventListener: (name, fn) => { submit = fn; }};
  const overlay = {classList: {add() {}, remove() {}}};
  const calls = [], confirmations = [], toasts = [];
  let state = false, approve = false, fail = false;
  const context = {
    document: {hidden: false, addEventListener: (name, fn) => { ready = fn; },
      getElementById: id => ({'closure-form': form, 'closure-status': badge, loadingOverlay: overlay})[id]},
    FormData: class extends Map { constructor() { super([['is_closed', 'on'], ['csrfmiddlewaretoken', 'token']]); } },
    fetch: async (url, options = {}) => {
      calls.push({url, options});
      if (fail) throw Error('offline');
      return {ok: true, json: async () => options.method === 'POST' ? {success: true, is_closed: true} : {is_closed: state}};
    },
    showToast: (...args) => toasts.push(args),
    setInterval: (fn, interval) => { assert.equal(interval, 10000); poll = fn; },
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('apps/depthead/static/depthead/js/collegeSettings.js', 'utf8'), context);
  context.confirmCollegeAction = async (title, message) => { confirmations.push(message); return approve; };
  ready();
  return {context, badge, button, calls, confirmations, toasts, poll: () => poll(),
    submit: () => submit({preventDefault() {}}), state: value => {state = value;},
    approve: () => {approve = true;}, fail: () => {fail = true;}};
}
const tick = () => new Promise(resolve => setImmediate(resolve));

test('poll updates saved badge; confirmation reads fresh state and cancel sends no POST', async () => {
  const app = setup(); await tick();
  assert.equal(app.badge.textContent, 'Open');
  app.state(true); app.poll(); await tick();
  assert.equal(app.badge.textContent, 'Closed');
  const reads = app.calls.length;
  await app.submit();
  assert.equal(app.calls.length, reads + 1);
  assert.match(app.confirmations[0], /update your college/);
  assert.equal(app.calls.filter(c => c.options.method === 'POST').length, 0);
  assert.equal(app.button.disabled, false);
});

test('Save submits once and immediately refreshes badge from response', async () => {
  const app = setup(); await tick(); app.approve();
  await Promise.all([app.submit(), app.submit()]);
  assert.match(app.confirmations[0], /Faculty will be notified by email/);
  assert.equal(app.calls.filter(c => c.options.method === 'POST').length, 1);
  assert.equal(app.badge.textContent, 'Closed');
});

test('failed fresh read blocks confirmation and submission', async () => {
  const app = setup(); await tick(); app.fail(); await app.submit();
  assert.equal(app.confirmations.length, 0);
  assert.equal(app.calls.filter(c => c.options.method === 'POST').length, 0);
  assert.match(app.toasts[0][0], /Unable to check/);
});

test('all transition and audience messages reflect email behavior', async () => {
  const app = setup(); await tick(); const c = app.context;
  assert.match(c.closureConfirmationMessage(true, false, 'CCS'), /reopen CCS/);
  assert.doesNotMatch(c.closureConfirmationMessage(false, false, 'CCS'), /email/);
  assert.doesNotMatch(c.announcementConfirmationMessage('students', 'CCS'), /email/);
  assert.match(c.announcementConfirmationMessage('faculty', 'CCS'), /receive an email/);
  assert.match(c.announcementConfirmationMessage('both', 'CCS'), /students and faculty/);
});


test('announcement Cancel sends nothing; Save posts the confirmed audience once', async () => {
  let submit, allow = false;
  const button = {};
  const form = {dataset: {college: 'CCS'}, action: '/announce/', querySelector: () => button,
    addEventListener: (name, fn) => {submit = fn;}, reset() {}};
  const calls = [], messages = [];
  const context = {
    document: {
      addEventListener() {},
      getElementById: id => ({'announcement-form': form, 'announcements-list': {querySelector() {}, prepend() {}},
        loadingOverlay: {classList: {add() {}, remove() {}}}})[id],
      querySelector: () => ({value: 'csrf'}),
      createElement: () => ({append() {}}),
    },
    FormData: class extends Map {constructor() {super([['audience', 'faculty'], ['message', 'Notice']]);}},
    confirmCollegeAction: async (title, text) => {messages.push(text); return allow;},
    closeCollegeConfirmation() {},
    announcementConfirmationMessage: (audience, college) => `${audience}:${college}`,
    fetch: async (url, options) => {calls.push(options); return {json: async () => ({success: true, announcement: {message: 'Notice'}})};},
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('static/js/announcements.js', 'utf8'), context);
  context.showToast = () => {};
  await submit({preventDefault() {}, target: form});
  assert.equal(calls.length, 0);
  assert.equal(messages[0], 'faculty:CCS');
  allow = true;
  await Promise.all([submit({preventDefault() {}, target: form}), submit({preventDefault() {}, target: form})]);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].body.get('audience'), 'faculty');
  assert.equal(button.disabled, false);
});


function modalEnvironment() {
  const elements = {};
  const document = {activeElement: null, addEventListener() {}, getElementById: id => elements[id]};
  for (const id of ['settings-confirm', 'settings-confirm-save', 'settings-confirm-cancel', 'settings-confirm-title', 'settings-confirm-message', 'trigger']) {
    const listeners = new Map();
    const classes = new Set(id === 'settings-confirm' ? ['hidden'] : []);
    elements[id] = {
      classList: {add: name => classes.add(name), remove: name => classes.delete(name), contains: name => classes.has(name)},
      addEventListener(name, fn) { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(fn); },
      removeEventListener(name, fn) {listeners.get(name)?.delete(fn);},
      fire(name, event = {}) {for (const fn of [...(listeners.get(name) || [])]) fn({target: elements[id], preventDefault() {}, ...event});},
      focus() {document.activeElement = elements[id];},
      listenerCount() {return [...listeners.values()].reduce((sum, entries) => sum + entries.size, 0);},
    };
  }
  elements.trigger.focus();
  const context = {document}; context.window = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('apps/depthead/static/depthead/js/collegeSettings.js', 'utf8'), context);
  return {context, elements, document};
}

test('actual modal helper dismisses via Cancel, backdrop and Escape; content clicks do not dismiss', async () => {
  const {context, elements, document} = modalEnvironment();
  const overlay = elements['settings-confirm'];
  for (const action of ['cancel', 'backdrop', 'escape']) {
    const result = context.confirmCollegeAction('Save?', 'Message');
    assert.equal(overlay.classList.contains('hidden'), false);
    overlay.fire('click', {target: elements['settings-confirm-title']});
    assert.equal(overlay.classList.contains('hidden'), false);
    if (action === 'cancel') elements['settings-confirm-cancel'].fire('click');
    if (action === 'backdrop') overlay.fire('click');
    if (action === 'escape') overlay.fire('keydown', {key: 'Escape'});
    assert.equal(await result, false);
    assert.equal(overlay.classList.contains('hidden'), true);
    assert.equal(overlay.listenerCount(), 0);
    assert.equal(document.activeElement, elements.trigger);
  }
});

test('actual modal stays open during save and closes in finally for success and failure', async () => {
  for (const fail of [false, true]) {
    const {context, elements} = modalEnvironment();
    const result = context.confirmCollegeAction('Save?', 'Message');
    elements['settings-confirm-save'].fire('click');
    elements['settings-confirm-save'].fire('click');
    assert.equal(await result, true);
    assert.equal(elements['settings-confirm-save'].disabled, true);
    assert.equal(elements['settings-confirm'].classList.contains('hidden'), false);
    try {
      if (fail) throw Error('Save failed');
    } catch {} finally {context.closeCollegeConfirmation();}
    assert.equal(elements['settings-confirm'].classList.contains('hidden'), true);
    assert.equal(elements['settings-confirm-save'].listenerCount(), 0);
    const reopened = context.confirmCollegeAction('Again?', 'Message');
    assert.equal(elements['settings-confirm-save'].disabled, false);
    elements['settings-confirm-cancel'].fire('click');
    assert.equal(await reopened, false);
  }
});
