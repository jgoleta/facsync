const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const code = name => fs.readFileSync(path.join(__dirname, '../static/js/', name), 'utf8');

test('failed images reveal existing placeholders, including dynamically rendered images', () => {
  const alreadyBroken = { complete: true, naturalWidth: 0, hidden: false };
  const good = { complete: true, naturalWidth: 32, hidden: false };
  let errorHandler;
  vm.runInNewContext(code('avatars.js'), { document: {
    addEventListener(type, handler, capture) { assert.equal(capture, true); errorHandler = handler; },
    querySelectorAll() { return [alreadyBroken, good]; },
  }});
  assert.equal(alreadyBroken.hidden, true);
  assert.equal(good.hidden, false);
  const dynamic = { matches: selector => selector === '[data-avatar-image]', hidden: false };
  errorHandler({ target: dynamic });
  assert.equal(dynamic.hidden, true);
});

function editor(file, result = { avatar_url: '', has_upload: false }, ok = true) {
  const feedback = { textContent: '' };
  const input = { files: file ? [file] : [], value: 'photo', disabled: false };
  const remove = { hidden: false, disabled: false, addEventListener(_, fn) { this.click = fn; } };
  const submit = { disabled: false };
  const calls = [];
  const avatar = { removed: false, image: null, querySelector() { return { remove: () => { this.removed = true; } }; }, append(image) { this.image = image; } };
  const form = {
    action: '/account/photo/',
    querySelector(selector) { return ({ 'input[type=file]': input, '[data-photo-feedback]': feedback, '[data-remove-photo]': remove })[selector]; },
    querySelectorAll() { return [input, remove, submit]; },
    addEventListener(_, fn) { this.submit = fn; },
  };
  class FakeFormData {
    constructor() { this.data = new Map([['photo', file]]); }
    set(key, value) { this.data.set(key, value); }
    delete(key) { this.data.delete(key); }
  }
  vm.runInNewContext(code('profile_photo.js'), {
    document: {
      querySelector() { return form; },
      querySelectorAll() { return [avatar]; },
      createElement() { return { dataset: {}, addEventListener() {} }; },
    },
    fetch: async (url, options) => { calls.push({ url, options }); return { ok, json: async () => result }; },
    FormData: FakeFormData, URL, window: { location: { origin: 'https://facsync.example' } },
  });
  return { form, feedback, calls, remove, input, avatar };
}

const flush = () => new Promise(resolve => setImmediate(resolve));

test('invalid and oversized browser files never send an upload', async () => {
  for (const file of [null, { name: 'a.svg', type: 'image/svg+xml', size: 40 },
    { name: 'a.png', type: 'text/html', size: 40 },
    { name: 'a.png', type: 'image/png', size: 2 * 1024 * 1024 + 1 }]) {
    const app = editor(file);
    app.form.submit({ preventDefault() {} });
    await flush();
    assert.equal(app.calls.length, 0);
    assert.ok(app.feedback.textContent);
  }
});

test('successful upload updates own pictures and enables removal', async () => {
  const app = editor({ name: 'a.png', type: 'image/png', size: 400 }, { avatar_url: '/account/photo/7/', has_upload: true });
  app.form.submit({ preventDefault() {} });
  await flush();
  assert.equal(app.calls.length, 1);
  assert.equal(app.calls[0].options.body.data.get('action'), 'upload');
  assert.equal(app.avatar.removed, true);
  assert.ok(app.avatar.image.src.startsWith('https://facsync.example/account/photo/7/?v='));
  assert.equal(app.remove.hidden, false);
  assert.equal(app.input.disabled, false);
});

test('removal sends no file and restores the Google photo', async () => {
  const app = editor(null, { avatar_url: 'https://lh3.googleusercontent.com/photo', has_upload: false });
  app.remove.click();
  await flush();
  assert.equal(app.calls[0].options.body.data.get('action'), 'remove');
  assert.equal(app.calls[0].options.body.data.has('photo'), false);
  assert.equal(app.avatar.image.src, 'https://lh3.googleusercontent.com/photo');
  assert.equal(app.remove.hidden, true);
});

test('storage errors preserve the visible photo and re-enable controls', async () => {
  const app = editor({ name: 'a.jpg', type: 'image/jpeg', size: 400 }, { error: 'Storage unavailable' }, false);
  app.form.submit({ preventDefault() {} });
  await flush();
  assert.equal(app.feedback.textContent, 'Storage unavailable');
  assert.equal(app.avatar.removed, false);
  assert.equal(app.input.disabled, false);
});
