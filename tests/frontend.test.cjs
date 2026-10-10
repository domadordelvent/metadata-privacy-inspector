const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// A minimal DOM adapter exercises the actual app code without dependencies.
class Element {
  constructor() {
    this.textContent = ''; this.hidden = false; this.disabled = false;
    this.children = []; this.listeners = {}; this.files = []; this.value = '';
    this.attributes = {};
    this.classList = { add() {}, remove() {} };
  }
  set innerHTML(value) { throw Error('Unsafe HTML insertion'); }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  get childElementCount() { return this.children.length; }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  focus() { this.focused = true; }
  async fire(name, overrides = {}) {
    return this.listeners[name]({ preventDefault() {}, ...overrides });
  }
}
function setup(fetch) {
  const elements = new Map();
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const body = [];
  const window = new Element();
  const context = vm.createContext({
    document: { getElementById: get, createElement: () => new Element() },
    window, fetch,
    atob: value => Buffer.from(value, 'base64').toString('binary'),
    Blob: class { constructor(parts) { this.parts = parts; } },
    URL: { createObjectURL: () => 'blob:local-clean-file', revokeObjectURL: () => {} },
    FormData: class { append(...args) { body.push(args); } },
  });
  vm.runInContext(fs.readFileSync('static/app.js', 'utf8'), context);
  return { get, window, body };
}
const file = (name = 'sample.png', size = 100) => ({ name, size });
async function choose(ui, files) {
  ui.get('file-input').files = files;
  await ui.get('file-input').fire('change');
}

test('selection rejects invalid files and drop supports one file', async () => {
  const ui = setup();
  for (const files of [[file('sample.png', 0)], [file('sample.png', 20 * 1024 * 1024 + 1)], [file('sample.exe')], [file(), file()]]) {
    await choose(ui, files);
    assert.equal(ui.get('analyze-button').disabled, true);
    assert.equal(ui.get('error-message').hidden, false);
  }
  await ui.get('drop-zone').fire('drop', { dataTransfer: { files: [file('safe.png')] } });
  assert.equal(ui.get('drop-title').textContent, 'safe.png');
  assert.equal(ui.get('analyze-button').disabled, false);
  assert.equal(ui.get('error-message').hidden, true);
});

test('analysis renders untrusted text, every field, GPS and resets the workspace', async () => {
  const malicious = '<img src=x onerror=alert(1)>';
  let calls = 0;
  const ui = setup(async (url, options) => {
    calls++;
    assert.equal(url, '/api/inspect');
    assert.equal(options.cache, 'no-store');
    assert.equal(options.method, 'POST');
    return { ok: true, json: async () => ({
      file: { name: malicious, extension: '.png', size_bytes: 100, mime_type: 'image/png' },
      metadata: { Author: malicious, GPS: { latitude_decimal: 41.3874, longitude_decimal: 2.1686 }, raw: { encoding: 'base64', data: 'YWJj' } },
      findings: [{ field: 'Author', value: malicious, description: 'Author identity' }],
    }) };
  });
  await choose(ui, [file()]);
  await ui.get('upload-form').fire('submit');
  assert.equal(calls, 1);
  assert.equal(ui.body[0][0], 'file');
  assert.equal(ui.get('result-name').textContent, malicious);
  assert.equal(ui.get('metadata-body').children.length, 3);
  assert.equal(ui.get('metadata-body').children[0].children[1].textContent, malicious);
  assert.equal(ui.get('findings-list').children[0].children[1].textContent, malicious);
  assert.equal(ui.get('gps-panel').hidden, false);
  assert.equal(ui.get('gps-values').children[0].children[1].textContent, '41.387400°');
  assert.equal(ui.get('results').hidden, false);
  assert.equal(ui.get('progress').hidden, true);
  assert.equal(ui.get('file-input').value, '');
  await ui.get('reset-button').fire('click');
  assert.equal(ui.get('results').hidden, true);
  assert.equal(ui.get('upload-panel').hidden, false);
  assert.equal(ui.get('metadata-body').children.length, 0);
  assert.equal(ui.get('gps-values').children.length, 0);
});

test('busy state prevents duplicate submission and server errors remain generic', async () => {
  let complete;
  let calls = 0;
  const ui = setup(() => { calls++; return new Promise(resolve => { complete = resolve; }); });
  await choose(ui, [file()]);
  const pending = ui.get('upload-form').fire('submit');
  assert.equal(ui.get('progress').hidden, false);
  assert.equal(ui.get('file-input').disabled, true);
  await ui.get('upload-form').fire('submit');
  assert.equal(calls, 1);
  complete({ ok: false, status: 500, json: async () => ({ detail: '/internal/secret' }) });
  await pending;
  assert.equal(ui.get('progress').hidden, true);
  assert.equal(ui.get('file-input').disabled, false);
  assert.equal(ui.get('error-message').hidden, false);
  assert.ok(!ui.get('error-message').textContent.includes('/internal'));
  assert.equal(ui.get('analyze-button').disabled, false);
});

test('network failure permits retry', async () => {
  const ui = setup(async () => { throw Error('connection failed'); });
  await choose(ui, [file()]);
  await ui.get('upload-form').fire('submit');
  assert.match(ui.get('error-message').textContent, /local application/);
  assert.equal(ui.get('analyze-button').disabled, false);
});

async function summaryReport(metadata, findings = []) {
  const ui = setup(async () => ({ ok: true, json: async () => ({
    file: { name: 'sample.png', extension: '.png', size_bytes: 100, mime_type: 'image/png' },
    metadata, findings,
  }) }));
  await choose(ui, [file()]);
  await ui.get('upload-form').fire('submit');
  return ui;
}

test('summary maps only detected metadata to explanations and recommendations', async () => {
  const cases = [
    [{ GPS: { latitude_decimal: 0, longitude_decimal: 0 } }, 'Location', 'Remove location tags'],
    [{ Location: '+41.0+002.0/' }, 'Location', 'Remove location tags'],
    [{ Model: 'Camera model' }, 'Device', 'Remove device tags'],
    [{ Author: 'Alice' }, 'Author and ownership', 'Review these labels'],
    [{ LastModifiedBy: 'Editor' }, 'Author and ownership', 'Review these labels'],
    [{ CreationDate: '2026-10-08' }, 'Dates', 'Review the timestamps'],
    [{ DateTimeOriginal: '2026:10:08 12:00:00' }, 'Dates', 'Review the timestamps'],
    [{ Software: 'Editor 1.0' }, 'Software', 'Review these labels'],
    [{ Encoder: 'Encoder 1.0' }, 'Software', 'Review these labels'],
    [{ Comments: 'Private note' }, 'Comments', 'Read the comments'],
  ];
  for (const [metadata, title, recommendation] of cases) {
    const ui = await summaryReport(metadata);
    const cards = ui.get('privacy-summary-items').children;
    assert.equal(cards.length, 1);
    assert.equal(cards[0].children[0].textContent, title);
    assert.ok(cards[0].children[2].textContent.includes(Object.keys(metadata)[0]));
    assert.ok(cards[0].children[3].textContent.includes(recommendation));
  }
});

test('summary does not infer sensitive data from technical metadata or empty values', async () => {
  for (const metadata of [{}, { width: 100, height: 100, format: 'PNG' },
    { Author: '', Model: null, Location: ' ', GPS: {}, Comments: [], CreationDate: undefined }]) {
    const ui = await summaryReport(metadata);
    assert.equal(ui.get('privacy-summary-items').children.length, 0);
    assert.match(ui.get('privacy-summary-intro').textContent, /does not guarantee.*completely private/);
  }
});

test('summary uses existing alerts, avoids duplicates and keeps unknown alerts factual', async () => {
  const ui = await summaryReport({ Author: 'Alice' }, [
    { field: 'Author', value: 'Alice', description: 'Author identity' },
    { field: 'GPS', value: [0, 0], description: 'Precise location' },
    { field: 'UnknownTag', value: 'value', description: 'Unrecognized signal' },
  ]);
  const cards = ui.get('privacy-summary-items').children;
  assert.deepEqual(cards.map(card => card.children[0].textContent), ['Location', 'Author and ownership', 'Other privacy signals']);
  assert.match(cards[2].children[2].textContent, /UnknownTag/);
  assert.match(cards[2].children[1].textContent, /additional metadata for review/);
});

test('summary replaces previous results and clears on Analyze Another File', async () => {
  const ui = await summaryReport({ Model: 'Device', Software: 'Editor' });
  assert.equal(ui.get('privacy-summary-items').children.length, 2);
  await ui.get('reset-button').fire('click');
  assert.equal(ui.get('privacy-summary-items').children.length, 0);
  assert.equal(ui.get('privacy-summary-intro').textContent, '');
});


test('cleaning uploads original, shows verification and creates download link', async () => {
  const calls = [];
  const ui = setup(async (url) => {
    calls.push(url);
    return { ok: true, json: async () => url === '/api/inspect' ? {
      file: { name: 'sample.png', extension: '.png', size_bytes: 100, mime_type: 'image/png' },
      metadata: { Artist: 'Alice' }, findings: [],
    } : {
      name: 'clean.png', data: 'YWJj', report: {
        removed_fields: ['Artist'], changed_fields: [], remaining_metadata: { width: 10 },
        remaining_findings: [], operations: ['Removed EXIF'], warnings: ['Technical data remains'], notice: 'Not a guarantee of complete privacy',
      },
    } };
  });
  await choose(ui, [file()]);
  await ui.get('upload-form').fire('submit');
  assert.equal(ui.get('remove-button').disabled, false);
  await ui.get('remove-button').fire('click');
  assert.deepEqual(calls, ['/api/inspect', '/api/clean']);
  assert.equal(ui.get('download-button').hidden, false);
  assert.equal(ui.get('download-button').download, 'clean.png');
  assert.match(ui.get('clean-report').children[0].textContent, /Artist/);
  assert.match(ui.get('clean-report').children[2].textContent, /width/);
  await ui.get('reset-button').fire('click');
  assert.equal(ui.get('download-button').hidden, true);
});

test('video cleaning stays disabled and does not send a cleaning request', async () => {
  let calls = 0;
  const ui = setup(async () => { calls++; return { ok: true, json: async () => ({
    file: { name: 'sample.mp4', extension: '.mp4', size_bytes: 100, mime_type: 'video/mp4' }, metadata: {}, findings: [],
  }) }; });
  await choose(ui, [file('sample.mp4')]);
  await ui.get('upload-form').fire('submit');
  assert.equal(ui.get('remove-button').disabled, true);
  await ui.get('remove-button').fire('click');
  assert.equal(calls, 1);
  assert.match(ui.get('clean-status').textContent, /disabled/);
});

test('cleaning rejection explains limitation and never exposes a download', async () => {
  const ui = setup(async url => ({ ok: url === '/api/inspect', status: 422, json: async () => url === '/api/inspect' ? {
    file: { name: 'sample.pdf', extension: '.pdf', size_bytes: 100, mime_type: 'application/pdf' }, metadata: {}, findings: [],
  } : { detail: 'Signed PDFs cannot be cleaned safely.' } }));
  await choose(ui, [file('sample.pdf')]);
  await ui.get('upload-form').fire('submit');
  await ui.get('remove-button').fire('click');
  assert.match(ui.get('clean-status').textContent, /Signed PDFs/);
  assert.equal(ui.get('download-button').hidden, true);
  assert.equal(ui.get('reset-button').disabled, false);
});
