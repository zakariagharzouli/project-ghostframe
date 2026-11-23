/* Produce the standalone file that can be used without a local server. */
const { createHash } = require('node:crypto');
const { readFileSync, writeFileSync, mkdirSync } = require('node:fs');
const { dirname, join, resolve } = require('node:path');

const readSource = (name) => readFileSync(join(__dirname, name), 'utf8').replace(/\r\n/g, '\n');
const hash = (value) => `'sha256-${createHash('sha256').update(value, 'utf8').digest('base64')}'`;
const style = `\n${readSource('style.css')}\n`;
const script = `\n${readSource('codec.js')}\n${readSource('app.js')}\n`;
const page = readSource('index.html')
  .replace("script-src 'self'; style-src 'self'", `script-src ${hash(script)}; style-src ${hash(style)}`)
  .replace('<link rel="stylesheet" href="style.css">', () => `<style>${style}</style>`)
  .replace(/  <script defer src="codec.js"><\/script>\n  <script defer src="app.js"><\/script>\n/, '')
  .replace('</body>', () => `<script>${script}</script>\n</body>`);

const out = resolve(process.argv[2] || join(__dirname, 'dist', 'index.html'));
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, page, 'utf8');
console.log(out);
