const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
function setup() {
  class Node {
    constructor() { this.children = []; this.events = {}; this.attrs = {}; this.hidden = true; this.dataset = {}; this.textContent = ''; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; }
    setAttribute(k,v) { this.attrs[k] = v; }
    addEventListener(k,v) { this.events[k] = v; }
    focus() { this.focused = true; }
  }
  const ids = Object.fromEntries(['analytics-browser','analytics-chat-toggle','analytics-chat-panel','analytics-chat-close','analytics-chat-messages'].map(id => [id,new Node()]));
  const button = new Node(); button.dataset.metric = 'capacity'; button.textContent = 'Capacity?';
  ids['analytics-browser'].dataset.endpoint = '/api/analytics-browser/';
  ids['analytics-browser'].querySelectorAll = () => [button];
  const requests = [], windowEvents = {};
  vm.runInNewContext(fs.readFileSync('apps/depthead/static/depthead/js/analytics_browser.js','utf8'), {
    document: {getElementById: id => ids[id], createElement: () => new Node()},
    window: {location:{origin:'https://example.test'}, addEventListener:(k,v)=>windowEvents[k]=v},
    URL, AbortController, setTimeout, clearTimeout,
    fetch: (url, options) => new Promise((resolve,reject) => requests.push({url,options,resolve,reject})),
  });
  return {ids,button,requests,windowEvents};
}
const answer = label => ({ok:true,json:async()=>({period:label,lines:['<script>literal</script>'],note:'note',source_url:'/source/'})});
test('repeated clicks fetch fresh data and out-of-order replies stay with their question', async()=>{
  const {ids,button,requests}=setup();
  const first=button.events.click(), second=button.events.click();
  const messages=ids['analytics-chat-messages'];
  assert.equal(requests.length,2); assert.equal(button.disabled,undefined);
  assert.equal(messages.children[1].attrs['aria-busy'],'true');
  assert.equal(requests[0].options.cache,'no-store');
  requests[1].resolve(answer('second')); await second;
  requests[0].resolve(answer('first')); await first;
  assert.equal(messages.children[1].children[0].textContent,'first');
  assert.equal(messages.children[3].children[0].textContent,'second');
  assert.equal(messages.children[1].children[1].children[0].textContent,'<script>literal</script>');
});
test('fetch failures become friendly replies and buttons remain usable',async()=>{
  const {ids,button,requests}=setup();
  const pending=button.events.click(); requests[0].reject(Error('offline')); await pending;
  assert.match(ids['analytics-chat-messages'].children[1].children[0].textContent,/couldn't load/);
  assert.equal(ids['analytics-chat-messages'].children[1].attrs['aria-busy'],'false');
  assert.equal(button.disabled,undefined);
});
test('toggle, Escape, focus return and page reset',()=>{
  const {ids,windowEvents}=setup();
  const toggle=ids['analytics-chat-toggle'],panel=ids['analytics-chat-panel'];
  assert.equal(panel.hidden,true);
  toggle.events.click(); assert.equal(panel.hidden,false); assert.ok(ids['analytics-chat-close'].focused);
  ids['analytics-browser'].events.keydown({key:'Escape',preventDefault(){}});
  assert.equal(panel.hidden,true); assert.ok(toggle.focused);
  ids['analytics-chat-messages'].append({textContent:'old'});
  windowEvents.pageshow(); assert.equal(ids['analytics-chat-messages'].children.length,0);
});
