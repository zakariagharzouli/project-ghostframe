import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve, sep } from "node:path";
import { once } from "node:events";
import { setTimeout as sleep } from "node:timers/promises";

const [url, directory, browserArgument] = process.argv.slice(2);
const output = resolve(directory);
const target = new URL(url);
if (target.protocol !== "http:" || target.hostname !== "127.0.0.1") {
  throw new Error("Le banc de capture attend une page HTTP sur 127.0.0.1.");
}
const browserSandbox = process.env.GHOSTFRAME_TEST_NO_SANDBOX !== "1";
const windowsCandidates = [
  process.env["ProgramFiles(x86)"] && join(process.env["ProgramFiles(x86)"], "Microsoft", "Edge", "Application", "msedge.exe"),
  process.env.ProgramFiles && join(process.env.ProgramFiles, "Google", "Chrome", "Application", "chrome.exe"),
];
const browser = browserArgument || process.env.BROWSER || [
  ...windowsCandidates,
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
].find(path => path && existsSync(path));
if (!browser) throw new Error("Indiquez le navigateur Chromium via --browser ou BROWSER.");

const profile = mkdtempSync(join(output, "browser-profile-"));
const child = spawn(browser, [
  "--headless=new",
  "--no-first-run",
  "--no-default-browser-check",
  "--disable-background-networking",
  "--disable-component-update",
  "--force-color-profile=srgb",
  ...(!browserSandbox ? ["--no-sandbox"] : []),
  "--remote-debugging-port=0",
  `--user-data-dir=${profile}`,
  "about:blank",
], { stdio: ["ignore", "ignore", "pipe"], windowsHide: true });

let stderr = "";
let launchError = null;
child.on("error", (error) => { launchError = error; });
child.stderr.on("data", (chunk) => { stderr = (stderr + chunk).slice(-4096); });

async function endpoint() {
  const marker = join(profile, "DevToolsActivePort");
  for (let attempt = 0; attempt < 160; attempt++) {
    if (launchError) throw launchError;
    if (child.exitCode !== null) throw new Error(`Le navigateur a quitté avec le code ${child.exitCode}. ${stderr}`);
    if (existsSync(marker)) {
      const port = readFileSync(marker, "utf8").split(/\r?\n/)[0];
      if (port) return `http://127.0.0.1:${port}`;
    }
    await sleep(100);
  }
  throw new Error(`Délai de lancement dépassé. ${stderr}`);
}

let socket;
try {
  const devtools = await endpoint();
  const version = await fetch(`${devtools}/json/version`, { signal: AbortSignal.timeout(8000) }).then(res => res.json());
  const targets = await fetch(`${devtools}/json/list`, { signal: AbortSignal.timeout(8000) }).then(res => res.json());
  const page = targets.find(target => target.type === "page");
  if (!page) throw new Error("Contexte de page Chromium absent.");
  socket = new WebSocket(page.webSocketDebuggerUrl);
  await once(socket, "open", { signal: AbortSignal.timeout(8000) });
  let sequence = 0;
  const pending = new Map();
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    const settle = pending.get(message.id);
    if (!settle) return;
    pending.delete(message.id);
    clearTimeout(settle.timeout);
    if (message.error) settle.reject(new Error(message.error.message));
    else settle.resolve(message.result);
  });
  function cdp(method, params = {}) {
    const id = ++sequence;
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        pending.delete(id);
        reject(new Error(`Délai dépassé pour ${method}`));
      }, 8000);
      pending.set(id, { resolve, reject, timeout });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async function evaluate(expression) {
    const result = await cdp("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || expression);
    return result.result.value;
  }

  await cdp("Page.enable");
  const viewport = { width: 1136, height: 600, deviceScaleFactor: 1, mobile: false };
  await cdp("Emulation.setDeviceMetricsOverride", viewport);
  const loaded = new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("Le document de mesure ne s’est pas chargé.")), 8000);
    function listener(event) {
      if (JSON.parse(event.data).method !== "Page.loadEventFired") return;
      clearTimeout(timeout);
      socket.removeEventListener("message", listener);
      resolve();
    }
    socket.addEventListener("message", listener);
  });
  await Promise.all([loaded, cdp("Page.navigate", { url })]);
  const positions = await evaluate(`(async () => {
    await window.ready;
    return Array.from(document.querySelectorAll('[data-probe]'), element => {
      const {x, y, width, height} = element.getBoundingClientRect();
      return {name: element.dataset.probe, x, y, width, height};
    });
  })()`);
  if (!positions.length || positions.some(rect => rect.width !== 96 || rect.height !== 64
    || !Number.isInteger(rect.x) || !Number.isInteger(rect.y) || rect.y + rect.height > viewport.height)) {
    throw new Error(`Géométrie des zones de mesure inattendue. ${JSON.stringify(positions)}`);
  }

  const samples = [];
  const started = performance.now();
  for (let index = 0; index < 19; index++) {
    const file = `capture-${String(index + 1).padStart(2, "0")}.png`;
    const { data } = await cdp("Page.captureScreenshot", { format: "png", fromSurface: true });
    const elapsed_ms = Math.round(performance.now() - started);
    writeFileSync(join(output, file), Buffer.from(data, "base64"));
    samples.push({ file, elapsed_ms });
    if (index < 18) await sleep(140);
  }
  writeFileSync(join(output, "capture.json"), JSON.stringify({
    browser: version.Browser, user_agent: version["User-Agent"], node: process.version, browser_sandbox: browserSandbox,
    viewport: [viewport.width, viewport.height], positions, samples,
  }, null, 2) + "\n");
} finally {
  socket?.close();
  if (child.pid && child.exitCode === null) {
    const ended = once(child, "exit", { signal: AbortSignal.timeout(4000) }).catch(() => {});
    child.kill();
    await ended;
  }
  if (!resolve(profile).startsWith(output + sep)) throw new Error("Profil hors du dossier de mesure.");
  try {
    rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  } catch (error) {
    console.warn(`Profil temporaire conservé dans ${profile}. ${error.code}`);
  }
}
