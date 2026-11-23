const assert = require('node:assert/strict');
const { spawn, spawnSync } = require('node:child_process');
const { once } = require('node:events');
const { mkdtempSync, readFileSync, rmSync, rmdirSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { createInterface } = require('node:readline');
const { test } = require('node:test');
const { renderPage } = require('./build.cjs');

const cli = join(__dirname, 'cli.cjs');

test('build writes the same self-contained page as the library', (context) => {
  const tmp = mkdtempSync(join(tmpdir(), 'ghostframe-cli-'));
  const destination = join(tmp, 'replay.html');
  context.after(() => {
    rmSync(destination, { force: true });
    rmdirSync(tmp);
  });
  const built = spawnSync(process.execPath, [cli, 'build', destination], { encoding: 'utf8' });
  assert.equal(built.status, 0, built.stderr);
  assert.equal(built.stdout.trim(), destination);
  assert.equal(readFileSync(destination, 'utf8'), renderPage());

  const invalid = spawnSync(process.execPath, [cli, 'serve', '--port', '65536'], { encoding: 'utf8' });
  assert.equal(invalid.status, 1);
  assert.match(invalid.stderr, /Port must be an integer/);
});

test('serve exposes the app over loopback and no arbitrary files', { timeout: 8000 }, async (context) => {
  const child = spawn(process.execPath, [cli, 'serve']);
  const lines = createInterface({ input: child.stdout });
  context.after(() => {
    lines.close();
    child.kill();
  });
  const [url] = await once(lines, 'line', { signal: AbortSignal.timeout(6000) });
  assert.match(url, /^http:\/\/127\.0\.0\.1:\d+\/$/);

  const root = await fetch(url);
  assert.equal(root.status, 200);
  assert.equal(root.headers.get('content-type'), 'text/html; charset=utf-8');
  assert.equal(await root.text(), renderPage());
  const head = await fetch(url, { method: 'HEAD' });
  assert.equal(head.status, 200);
  assert.equal(await head.text(), '');
  assert.equal((await fetch(new URL('package.json', url))).status, 404);
  assert.equal((await fetch(url, { method: 'POST' })).status, 405);
});
