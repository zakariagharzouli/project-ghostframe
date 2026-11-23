/* Produce the standalone file that can be used without a local server. */
const { createHash } = require('node:crypto');
const { readFileSync, writeFileSync, mkdirSync } = require('node:fs');
const { dirname, join, resolve } = require('node:path');

const readSource = (name) => readFileSync(join(__dirname, name), 'utf8').replace(/\r\n/g, '\n');
const hash = (value) => `'sha256-${createHash('sha256').update(value, 'utf8').digest('base64')}'`;

function renderPage() {
  const style = `\n${readSource('style.css')}\n`;
  const script = `\n${readSource('codec.js')}\n${readSource('app.js')}\n`;
  return readSource('index.html')
    .replace("script-src 'self'; style-src 'self'", `script-src ${hash(script)}; style-src ${hash(style)}`)
    .replace('<link rel="stylesheet" href="style.css">', () => `<style>${style}</style>`)
    .replace(/  <script defer src="codec.js"><\/script>\n  <script defer src="app.js"><\/script>\n/, '')
    .replace('</body>', () => `<script>${script}</script>\n</body>`);
}

function writePage(target = join(__dirname, 'dist', 'index.html')) {
  const out = resolve(target);
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, renderPage(), 'utf8');
  return out;
}

if (require.main === module) console.log(writePage(process.argv[2]));

module.exports = { renderPage, writePage };
