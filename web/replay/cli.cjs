#!/usr/bin/env node
'use strict';

const { createServer } = require('node:http');
const { parseArgs } = require('node:util');
const { version } = require('../../package.json');
const { renderPage, writePage } = require('./build.cjs');

const help = `Ghostframe Replay

Usage
  ghostframe-replay [serve] [--port PORT]
  ghostframe-replay build OUTPUT.html
  ghostframe-replay --help
  ghostframe-replay --version

serve  Print a loopback URL and serve the editor until you press Ctrl+C.
       By default, the operating system assigns a free port.
build  Write a single HTML file that can be opened offline.
`;

function serve(port) {
  const html = Buffer.from(renderPage(), 'utf8');
  const server = createServer((request, response) => {
    if (request.url !== '/' && request.url !== '/index.html') {
      response.writeHead(404).end();
      return;
    }
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      response.writeHead(405, { Allow: 'GET, HEAD' }).end();
      return;
    }
    response.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Content-Length': html.byteLength,
      'X-Content-Type-Options': 'nosniff',
    });
    response.end(request.method === 'HEAD' ? undefined : html);
  });
  server.once('error', (error) => {
    console.error(`ghostframe-replay: ${error.message}`);
    process.exitCode = 1;
  });
  server.listen(port, '127.0.0.1', () => {
    console.log(`http://127.0.0.1:${server.address().port}/`);
  });
}

function run(args) {
  const { values, positionals } = parseArgs({
    args, allowPositionals: true,
    options: { help: { type: 'boolean', short: 'h' }, version: { type: 'boolean', short: 'v' }, port: { type: 'string' } },
  });
  if (values.help) return console.log(help);
  if (values.version) return console.log(version);
  const [command = 'serve', output, extra] = positionals;
  if (command === 'build' && output && !extra && values.port === undefined) {
    console.log(writePage(output));
    return;
  }
  if (command === 'serve' && !output) {
    const port = values.port ?? '0';
    if (!/^\d+$/.test(port) || Number(port) > 65535) throw new Error('Port must be an integer from 0 to 65535.');
    serve(Number(port));
    return;
  }
  throw new Error('Invalid command. Run ghostframe-replay --help for usage.');
}

try {
  run(process.argv.slice(2));
} catch (error) {
  console.error(`ghostframe-replay: ${error.message}`);
  process.exitCode = 1;
}
