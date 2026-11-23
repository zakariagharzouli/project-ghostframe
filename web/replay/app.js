'use strict';

const byId = (id) => document.getElementById(id);
const ui = Object.fromEntries([
  'editor-tab', 'reader-tab', 'file-name', 'file', 'example', 'choose', 'viewport', 'stage', 'screen', 'target', 'empty',
  'empty-open', 'prev', 'play', 'next', 'capture-help', 'play-caption', 'step-count', 'no-steps', 'step-list',
  'edit-step', 'note', 'duration', 'remove', 'export-area', 'export', 'capacity', 'copy-area', 'copy-steps', 'steps-text', 'status',
].map((id) => [id, byId(id)]));
const editor = { image: null, steps: [], selected: -1, name: '' };
const reader = { image: null, steps: [], selected: -1, name: '', geometry: null };
let current = editor;
let drawn = null;
let keyboardPoint = null;
let timer = null;
let playing = false;
let deadline = 0;
let pausedFor = null;
let loadVersion = 0;
let exporting = false;
const noteEncoder = new TextEncoder();

const createCanvas = (width, height) => Object.assign(document.createElement('canvas'), { width, height });
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const seconds = (value) => (value / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 1 });
const status = (message = '', error = false) => {
  ui.status.textContent = message;
  ui.status.dataset.error = String(error);
};

function demoScreenshot() {
  const image = createCanvas(1120, 650);
  const ctx = image.getContext('2d');
  const box = (x, y, w, h, color) => {
    ctx.fillStyle = color;
    ctx.fillRect(x, y, w, h);
  };
  const line = (value, x, y, size, color = '#233049', weight = 500) => {
    ctx.fillStyle = color;
    ctx.font = `${weight} ${size}px system-ui, sans-serif`;
    ctx.fillText(value, x, y);
  };

  box(0, 0, 1120, 650, '#edf0f7');
  box(0, 0, 1120, 69, '#182039');
  box(25, 23, 24, 24, '#8e9afd');
  line('Console d’import', 62, 44, 23, '#f4f6ff', 700);
  line('Projet Atlas', 929, 43, 19, '#cbd2e7');
  box(0, 69, 206, 581, '#e3e7f2');
  line('Tableau de bord', 24, 130, 18, '#495674');
  box(15, 151, 175, 42, '#cbd3fa');
  line('Imports', 24, 178, 19, '#283d8a', 690);
  line('Historique', 24, 222, 18, '#495674');

  line('Nouvel import', 254, 145, 41, '#17213c', 730);
  line('Ajoutez un fichier CSV à ce projet.', 256, 182, 20, '#52607e');
  box(255, 218, 815, 312, '#fff');
  box(278, 246, 762, 64, '#f0f3f9');
  box(299, 264, 21, 28, '#c1cbdf');
  line('commandes.csv', 338, 287, 22, '#273755', 640);
  line('24 Ko', 944, 286, 19, '#627290');
  box(278, 333, 169, 51, '#3a51c4');
  line('Lancer l’import', 296, 366, 18, '#fff', 690);
  box(278, 411, 762, 80, '#fff0e8');
  box(278, 411, 5, 80, '#ba572c');
  line('Erreur 42', 303, 445, 23, '#8f3619', 720);
  line('La colonne date_commande est introuvable.', 303, 474, 19, '#763f30');
  line('Dernier essai enregistré', 254, 578, 18, '#576480');
  return image;
}

function loadExample(showEditor = true) {
  loadVersion += 1;
  editor.image = demoScreenshot();
  editor.name = 'Exemple d’import';
  editor.steps = [
    { x: 437, y: 278, duration: 1000, note: 'Choisir commandes.csv' },
    { x: 363, y: 359, duration: 900, note: 'Lancer l’import' },
    { x: 342, y: 445, duration: 1600, note: 'L’erreur 42 apparaît' },
  ];
  editor.selected = 0;
  if (showEditor) changeMode(editor);
}

function currentStep() {
  return current.steps[current.selected];
}

function stopPlaying() {
  if (timer !== null) clearTimeout(timer);
  timer = null;
  playing = false;
  pausedFor = null;
}

function changeMode(mode) {
  stopPlaying();
  current = mode;
  keyboardPoint = null;
  ui['steps-text'].hidden = true;
  status();
  render();
}

function showImage() {
  const image = current.image;
  ui.stage.hidden = !image;
  ui.empty.hidden = Boolean(image);
  if (!image || drawn === image) return;
  ui.screen.width = image.width;
  ui.screen.height = image.height;
  ui.screen.getContext('2d').drawImage(image, 0, 0);
  drawn = image;
}

function markLocation(step) {
  if (current === editor) return { x: step.x, y: step.y };
  const { left, top, sx, sy, crop } = reader.geometry;
  return { x: left + (step.x + .5) * sx - crop.x, y: top + (step.y + .5) * sy - crop.y };
}

function showMarker() {
  const step = currentStep();
  const point = keyboardPoint || (step ? markLocation(step) : null);
  const { screen, target } = ui;
  const visible = point && point.x >= 0 && point.x < screen.width && point.y >= 0 && point.y < screen.height;
  target.hidden = !visible;
  if (visible) {
    target.style.left = `${100 * point.x / screen.width}%`;
    target.style.top = `${100 * point.y / screen.height}%`;
    target.dataset.keyboard = String(Boolean(keyboardPoint));
    target.textContent = keyboardPoint ? '+' : String(current.selected + 1);
  }
  const caption = step && (playing || current === reader);
  ui['play-caption'].hidden = !caption;
  ui['play-caption'].textContent = caption ? `${step.note || `Étape ${current.selected + 1}`}${visible ? '' : ' · repère hors cadre'}` : '';
}

function renderList() {
  const list = ui['step-list'];
  const previouslyFocused = list.contains(document.activeElement) ? document.activeElement.dataset.index : null;
  const fragment = document.createDocumentFragment();
  for (const [index, step] of current.steps.entries()) {
    const row = document.createElement('li');
    const button = document.createElement('button');
    button.className = 'step-select';
    button.type = 'button';
    button.dataset.index = String(index);
    if (index === current.selected) button.setAttribute('aria-current', 'step');
    const number = document.createElement('span');
    number.className = 'step-number';
    number.textContent = String(index + 1);
    const title = document.createElement('span');
    title.className = 'step-title';
    title.textContent = step.note || 'Sans annotation';
    const time = document.createElement('span');
    time.className = 'step-time';
    time.textContent = `${seconds(step.duration)} s`;
    button.append(number, title, time);
    row.append(button);
    fragment.append(row);
  }
  list.replaceChildren(fragment);
  if (previouslyFocused !== null) list.querySelector(`[data-index="${previouslyFocused}"]`)?.focus();
  ui['step-count'].textContent = String(current.steps.length);
  ui['no-steps'].hidden = current !== editor || current.steps.length > 0;
}

function showCapacity() {
  const used = Ghostframe.metrics(editor.steps);
  const notesFit = editor.steps.every((step) => noteEncoder.encode(step.note).length <= Ghostframe.MAX_NOTE_BYTES);
  const within = used <= Ghostframe.CAPACITY && notesFit;
  const remaining = Ghostframe.CAPACITY - used;
  const size = Ghostframe.bandHeight(editor.steps);
  ui.capacity.textContent = within ? `${remaining} octets disponibles · bande de ${size} px` : 'Raccourcissez les annotations pour exporter.';
  ui.capacity.dataset.over = String(!within);
  ui.export.disabled = !editor.steps.length || !within || exporting;
}

function render({ fields = true } = {}) {
  const editing = current === editor;
  const step = currentStep();
  ui['editor-tab'].setAttribute('aria-pressed', String(editing));
  ui['reader-tab'].setAttribute('aria-pressed', String(!editing));
  ui['file-name'].textContent = current.name || 'Lecteur';
  ui.choose.textContent = editing ? 'Importer une capture' : 'Ouvrir un JPEG';
  ui.example.hidden = !editing;
  ui.choose.hidden = !editing && !current.image;
  ui.screen.dataset.editable = String(editing);
  ui.screen.setAttribute('aria-label', editing ? 'Capture à annoter' : 'Capture du signalement');
  ui.screen.tabIndex = editing ? 0 : -1;
  ui['capture-help'].textContent = editing
    ? 'Collez ou déposez une image. Pour ajouter un repère, cliquez ou utilisez les flèches puis Entrée.'
    : reader.image ? 'La séquence est lue depuis l’image.' : '';
  ui['export-area'].hidden = !editing;
  ui['copy-area'].hidden = !current.steps.length;
  if (!ui['steps-text'].hidden) ui['steps-text'].value = formatSteps(current.steps);
  ui['edit-step'].hidden = !editing || !step || playing;
  ui.play.textContent = playing ? 'Pause' : pausedFor === null ? 'Lire la séquence' : 'Reprendre';
  ui.play.disabled = !current.steps.length;
  ui.prev.disabled = current.selected <= 0;
  ui.next.disabled = current.selected >= current.steps.length - 1;
  if (fields && editing && step) {
    ui.note.value = step.note;
    ui.duration.value = String(step.duration / 1000);
  }
  showImage();
  showMarker();
  renderList();
  showCapacity();
}

function select(index) {
  stopPlaying();
  keyboardPoint = null;
  current.selected = clamp(index, 0, current.steps.length - 1);
  render();
}

function playNext(hold = currentStep().duration) {
  render();
  deadline = performance.now() + hold;
  timer = setTimeout(() => {
    if (current.selected === current.steps.length - 1) {
      stopPlaying();
      render();
      return;
    }
    current.selected += 1;
    playNext();
  }, hold);
}

function appendStep(x, y) {
  if (editor.steps.length >= Ghostframe.MAX_STEPS) {
    status('La capture contient déjà 12 étapes.', true);
    return;
  }
  status();
  keyboardPoint = null;
  editor.steps.push({ x: Math.floor(x), y: Math.floor(y), duration: 1200, note: '' });
  editor.selected = editor.steps.length - 1;
  render();
  ui.note.focus();
}

function loadBitmap(file) {
  if (!file || file.size > 24 * 1024 * 1024) throw new Error('Choisissez un fichier image de 24 Mo maximum.');
  return createImageBitmap(file).catch(() => {
    throw new Error('Impossible de lire cette image. Choisissez un JPEG, un PNG ou un WebP.');
  });
}

function normalize(bitmap) {
  const ratio = Math.min(1, 1600 / bitmap.width, 1440 / bitmap.height);
  const width = Math.max(1, Math.round(bitmap.width * ratio));
  const height = Math.max(1, Math.round(bitmap.height * ratio));
  const image = createCanvas(Math.max(Ghostframe.BAND_WIDTH, width), height);
  const context = image.getContext('2d', { alpha: false });
  context.fillStyle = '#fff';
  context.fillRect(0, 0, image.width, image.height);
  context.drawImage(bitmap, Math.floor((image.width - width) / 2), 0, width, height);
  return image;
}

function inspectBitmap(bitmap) {
  if (bitmap.width * bitmap.height > 8_000_000 || Math.max(bitmap.width, bitmap.height) > 4000) {
    throw new Error('L’image est trop grande pour le lecteur.');
  }
  const encoded = createCanvas(bitmap.width, bitmap.height);
  const context = encoded.getContext('2d', { willReadFrequently: true });
  context.fillStyle = '#fff';
  context.fillRect(0, 0, bitmap.width, bitmap.height);
  context.drawImage(bitmap, 0, 0);
  const top = Math.max(0, bitmap.height - Ghostframe.SCAN_HEIGHT);
  const geometry = Ghostframe.scan(context.getImageData(0, top, bitmap.width, bitmap.height - top), top);
  if (!geometry) throw new Error('Aucune séquence Ghostframe récupérable dans cette image.');
  return { encoded, geometry };
}

function decodeBitmap(bitmap) {
  const { encoded, geometry } = inspectBitmap(bitmap);
  const { x, y, right, bottom } = geometry.crop;
  const image = createCanvas(right - x, bottom - y);
  image.getContext('2d').drawImage(encoded, x, y, image.width, image.height, 0, 0, image.width, image.height);
  return { image, geometry };
}

async function openFile(file, target) {
  const version = ++loadVersion;
  let bitmap;
  status('Lecture de l’image…');
  try {
    bitmap = await loadBitmap(file);
    if (version !== loadVersion) return;
    if (target === editor) {
      editor.image = normalize(bitmap);
      editor.steps = [];
      editor.selected = -1;
    } else {
      const { image, geometry } = decodeBitmap(bitmap);
      Object.assign(reader, { image, geometry, steps: geometry.steps, selected: 0 });
    }
    target.name = file.name;
    if (target !== current) return;
    stopPlaying();
    keyboardPoint = null;
    ui['steps-text'].hidden = true;
    render();
    if (target === reader) {
      const count = reader.steps.length;
      const repaired = reader.geometry.recoveredTile === null ? '' : ' Une tuile manquante a été restaurée.';
      status(`${count} étape${count === 1 ? '' : 's'} récupérée${count === 1 ? '' : 's'}.${repaired}`);
    } else {
      status('Capture importée. Placez les repères dans l’ordre des gestes.');
    }
  } catch (error) {
    if (version === loadVersion && target === current) status(error.message, true);
  } finally {
    bitmap?.close();
  }
}

async function exportImage() {
  if (exporting) return;
  exporting = true;
  showCapacity();
  status('Export et vérification du JPEG…');
  try {
    const { image, steps, name } = editor;
    const canvas = createCanvas(image.width, image.height + Ghostframe.bandHeight(steps));
    const context = canvas.getContext('2d', { alpha: false });
    context.drawImage(image, 0, 0);
    const expected = Ghostframe.paintBand(context, image.width, image.height, steps);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', .92));
    if (!blob || blob.type !== 'image/jpeg') throw new Error('Le navigateur n’a pas pu générer le JPEG.');
    const decoded = await createImageBitmap(blob);
    try {
      const { geometry } = inspectBitmap(decoded);
      const actual = Ghostframe.serialize(geometry.width, geometry.height, geometry.steps);
      if (geometry.validTiles !== 4 || actual.length !== expected.length
        || !actual.every((byte, index) => byte === expected[index])) throw new Error('Vérification des étapes impossible.');
    } finally {
      decoded.close();
    }
    const stem = name.replace(/\.[^.]+$/, '').replace(/[^\p{L}\p{N}-]+/gu, '-').replace(/^-|-$/g, '');
    const href = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.download = `${stem.slice(0, 64) || 'capture'}-ghostframe.jpg`;
    link.href = href;
    link.click();
    setTimeout(() => URL.revokeObjectURL(href), 30_000);
    if (current === editor) status('JPEG vérifié et exporté. Ouvrez-le dans Rejouer pour retrouver ses étapes.');
  } catch (error) {
    if (current === editor) status(error.message, true);
  } finally {
    exporting = false;
    showCapacity();
  }
}

function formatSteps(steps) {
  return steps.map((step, index) => {
    const label = step.note.trim() || `Cliquer au repère (${step.x}, ${step.y})`;
    return `${index + 1}. ${label}`;
  }).join('\n');
}

async function copySteps() {
  const mode = current;
  const text = formatSteps(current.steps);
  try {
    await navigator.clipboard.writeText(text);
    if (current !== mode) return;
    ui['steps-text'].hidden = true;
    status('Étapes copiées. Collez-les dans le ticket.');
  } catch {
    if (current !== mode) return;
    const field = ui['steps-text'];
    field.value = text;
    field.hidden = false;
    field.focus();
    field.select();
    status('Le texte est sélectionné. Copiez-le pour le coller dans le ticket.');
  }
}

ui['editor-tab'].addEventListener('click', () => changeMode(editor));
ui['reader-tab'].addEventListener('click', () => changeMode(reader));
ui.example.addEventListener('click', () => loadExample());
ui.choose.addEventListener('click', () => ui.file.click());
ui['empty-open'].addEventListener('click', () => ui.file.click());
ui.file.addEventListener('change', () => {
  const [file] = ui.file.files;
  ui.file.value = '';
  if (file) void openFile(file, current);
});
ui.viewport.addEventListener('dragover', (event) => {
  if (!event.dataTransfer.types.includes('Files')) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = 'copy';
  ui.viewport.dataset.dropping = 'true';
});
ui.viewport.addEventListener('dragleave', (event) => {
  if (!ui.viewport.contains(event.relatedTarget)) delete ui.viewport.dataset.dropping;
});
ui.viewport.addEventListener('drop', (event) => {
  delete ui.viewport.dataset.dropping;
  const [file] = event.dataTransfer.files;
  if (!file) return;
  event.preventDefault();
  void openFile(file, current);
});
document.addEventListener('paste', (event) => {
  if (event.target instanceof Element && event.target.closest('input, textarea, [contenteditable="true"]')) return;
  const item = Array.from(event.clipboardData?.items || []).find(({ kind, type }) =>
    kind === 'file' && type.startsWith('image/'));
  const file = item?.getAsFile();
  if (!file) return;
  event.preventDefault();
  void openFile(file, current);
});

ui.screen.addEventListener('click', (event) => {
  if (current !== editor || playing) return;
  const rect = ui.screen.getBoundingClientRect();
  const x = clamp((event.clientX - rect.left) * editor.image.width / rect.width, 0, editor.image.width - 1);
  const y = clamp((event.clientY - rect.top) * editor.image.height / rect.height, 0, editor.image.height - 1);
  appendStep(x, y);
});

ui.screen.addEventListener('keydown', (event) => {
  if (current !== editor || playing) return;
  const moves = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  if (!moves[event.key] && event.key !== 'Enter') return;
  event.preventDefault();
  const { width, height } = editor.image;
  const point = keyboardPoint || currentStep() || { x: Math.floor(width / 2), y: Math.floor(height / 2) };
  if (event.key === 'Enter') {
    appendStep(point.x, point.y);
    return;
  }
  const [dx, dy] = moves[event.key];
  const delta = event.shiftKey ? 40 : 10;
  keyboardPoint = { x: clamp(point.x + dx * delta, 0, width - 1), y: clamp(point.y + dy * delta, 0, height - 1) };
  showMarker();
});
ui.screen.addEventListener('blur', () => {
  keyboardPoint = null;
  showMarker();
});

ui.play.addEventListener('click', () => {
  keyboardPoint = null;
  if (playing) {
    const remaining = Math.max(0, deadline - performance.now());
    stopPlaying();
    pausedFor = remaining;
    render();
    return;
  }
  if (!current.steps.length) return;
  const remaining = pausedFor;
  if (remaining === null) current.selected = 0;
  pausedFor = null;
  playing = true;
  playNext(remaining ?? currentStep().duration);
});
ui.prev.addEventListener('click', () => select(current.selected - 1));
ui.next.addEventListener('click', () => select(current.selected + 1));
ui['step-list'].addEventListener('click', (event) => {
  const button = event.target.closest('button[data-index]');
  if (button) select(Number(button.dataset.index));
});
ui.note.addEventListener('input', () => {
  const step = currentStep();
  if (current !== editor || !step) return;
  step.note = ui.note.value;
  render({ fields: false });
});
ui.duration.addEventListener('change', () => {
  const step = currentStep();
  const value = ui.duration.valueAsNumber;
  if (current !== editor || !step) return;
  if (Number.isFinite(value)) step.duration = 100 * Math.round(clamp(value, .1, 10) * 10);
  render();
});
ui.remove.addEventListener('click', () => {
  editor.steps.splice(editor.selected, 1);
  editor.selected = Math.min(editor.selected, editor.steps.length - 1);
  render();
  (editor.steps.length ? ui.note : ui.screen).focus();
});
ui.export.addEventListener('click', () => void exportImage());
ui['copy-steps'].addEventListener('click', () => void copySteps());

loadExample();
