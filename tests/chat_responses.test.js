const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor(tag = 'div') {
    this.tag = tag; this.children = []; this.events = {}; this.dataset = {};
    this.hidden = false; this.attributes = {}; this.classList = { toggle() {} };
  }
  set textContent(value) { this.text = String(value ?? ''); }
  get textContent() { return this.text || ''; }
  set innerHTML(value) { throw new Error('Replies must not interpret HTML'); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(event, callback) { this.events[event] = callback; }
  setAttribute(key, value) { this.attributes[key] = value; }
  querySelectorAll() { return []; }
  focus() {}
}

async function render(data, ok = true) {
  const ids = Object.fromEntries(['analytics-browser', 'analytics-chat-toggle', 'analytics-chat-panel',
    'analytics-chat-close', 'analytics-chat-messages'].map(id => [id, new Element()]));
  const question = new Element('button');
  question.textContent = 'Example question'; question.dataset.metric = 'available_now';
  ids['analytics-browser'].querySelectorAll = () => [question];
  ids['analytics-browser'].dataset = { endpoint: '/helper/', sourceLabel: 'View faculty directory' };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../apps/depthead/static/depthead/js/analytics_browser.js'), 'utf8'), {
    document: {
      getElementById: id => ids[id], querySelector: () => null,
      createElement: tag => new Element(tag), body: new Element('body'),
    },
    window: { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {},
      location: { origin: 'https://facsync.example' } },
    URL, AbortController, setTimeout, clearTimeout,
    fetch: async () => ({ ok, json: async () => data }),
  });
  await question.events.click();
  return ids['analytics-chat-messages'].children[1];
}

test('intro, names, note and directory link render in that order', async () => {
  const reply = await render({ period: 'Faculty available on October 3, 2026:', lines: ['John Doe', 'Mary Jane'],
    note: 'Based on their latest recorded status.', source_url: '/student/dashboard/' });
  assert.deepEqual(reply.children.map(node => node.tag), ['p', 'ul', 'p', 'a']);
  assert.deepEqual(reply.children[1].children.map(node => node.textContent), ['John Doe', 'Mary Jane']);
  assert.equal(reply.children[3].textContent, 'View faculty directory');
  assert.equal(reply.children[3].href, 'https://facsync.example/student/dashboard/');
});

test('empty and closure replies render as paragraphs, without empty headings or bullet lists', async () => {
  const reply = await render({ period: '', presentation: 'paragraphs', lines: ['No closure is recorded.'],
    note: '', source_url: '/faculty/dashboard/', source_label: 'View faculty dashboard' });
  assert.deepEqual(reply.children.map(node => node.tag), ['p', 'a']);
  assert.equal(reply.children[0].textContent, 'No closure is recorded.');
});

test('announcement messages and metadata are separate text-only blocks', async () => {
  const message = '<img src=x onerror=alert(1)>\nOriginal announcement';
  const reply = await render({ period: 'Current announcements:', lines: [message], note: '', source_url: '/depthead/college-settings/',
    announcements: [{ message, details: ['For: Students', 'Posted: October 3, 2026'] }] });
  const block = reply.children[1];
  assert.equal(block.tag, 'section');
  assert.deepEqual(block.children.map(node => node.textContent), [message, 'For: Students', 'Posted: October 3, 2026']);
});

test('faculty source links retain the consultation anchor', async () => {
  const reply = await render({ period: 'Your consultations:', lines: ['1 PM–1:59 PM — 1 completed consultation'],
    source_url: '/faculty/dashboard/#consultation-requests', source_label: 'View your consultations' });
  assert.equal(reply.children.at(-1).href, 'https://facsync.example/faculty/dashboard/#consultation-requests');
});

test('external source URLs are not rendered', async () => {
  const reply = await render({ period: 'Result:', lines: ['Example'], source_url: 'https://external.example/' });
  assert.equal(reply.children.some(node => node.tag === 'a'), false);
});

test('failed requests retain the friendly retry response', async () => {
  const reply = await render({}, false);
  assert.match(reply.children[0].textContent, /Please try again/);
  assert.equal(reply.attributes['aria-busy'], 'false');
});
