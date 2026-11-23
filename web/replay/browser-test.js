async (page) => {
  const problems = [];
  const externalRequests = [];
  page.on('pageerror', (error) => problems.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') problems.push(message.text());
  });
  page.on('request', (request) => {
    if (/^https?:/.test(request.url()) && !request.url().startsWith('http://127.0.0.1:8764/')) {
      externalRequests.push(request.url());
    }
  });
  const ensure = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  const get = (name) => page.getByRole('button', { name, exact: true });
  await page.reload();
  await page.locator('#step-list li').first().waitFor();
  ensure(await page.locator('#step-list li').count() === 3, 'Example should have three steps.');
  await page.screenshot({ path: 'output/playwright/ghostframe-desktop.png', fullPage: true });

  const [sample] = await Promise.all([page.waitForEvent('download'), get('Exporter le JPEG').click()]);
  await sample.saveAs('output/playwright/ghostframe-example.jpg');
  await page.getByText('JPEG vérifié et exporté.', { exact: false }).waitFor();
  await page.evaluate(async () => {
    const canvas = document.querySelector('#screen');
    const png = await new Promise((resolve) => canvas.toBlob(resolve));
    const clipboardData = new DataTransfer();
    clipboardData.items.add(new File([png], 'presse-papiers.png', { type: 'image/png' }));
    document.body.dispatchEvent(new ClipboardEvent('paste', { clipboardData, bubbles: true, cancelable: true }));
  });
  await page.getByText('presse-papiers.png', { exact: true }).waitFor();
  ensure(await page.locator('#step-list li').count() === 0, 'Pasting an image should start a fresh capture.');
  await get('Exemple').click();

  await page.evaluate(() => {
    const { prototype } = HTMLCanvasElement;
    const original = prototype.toBlob;
    prototype.toBlob = function (callback, type, quality) {
      prototype.toBlob = original;
      return original.call(document.querySelector('#screen'), callback, type, quality);
    };
  });
  let invalidDownloads = 0;
  const countDownload = () => { invalidDownloads += 1; };
  page.on('download', countDownload);
  await get('Exporter le JPEG').click();
  await page.getByText('Aucune séquence Ghostframe récupérable dans cette image.').waitFor();
  ensure(invalidDownloads === 0, 'An export that fails verification must not download.');
  page.off('download', countDownload);

  await page.locator('#screen').screenshot({ path: 'output/playwright/ghostframe-input.png' });
  await page.locator('#file').setInputFiles('output/playwright/ghostframe-input.png');
  await page.getByText('Capture importée.', { exact: false }).waitFor();
  ensure(await page.locator('#step-list li').count() === 0, 'Import should have no steps.');
  await page.locator('#screen').click({ position: { x: 90, y: 80 } });
  await page.getByLabel('Annotation', { exact: true }).fill('Ouvrir <capture>');
  await page.getByLabel('Durée d’affichage', { exact: true }).fill('0.4');
  await page.getByLabel('Durée d’affichage', { exact: true }).press('Tab');
  await page.locator('#screen').focus();
  await page.locator('#screen').press('Shift+ArrowRight');
  await page.locator('#screen').press('Enter');
  await page.getByLabel('Annotation', { exact: true }).fill('Échec de l’import');
  const [download] = await Promise.all([page.waitForEvent('download'), get('Exporter le JPEG').click()]);
  await download.saveAs('output/playwright/ghostframe-edited.jpg');

  await page.reload();
  await get('Rejouer').click();
  await page.locator('#file').setInputFiles('output/playwright/ghostframe-input.png');
  await page.getByText('Aucune séquence Ghostframe récupérable dans cette image.').waitFor();
  await page.evaluate(() => {
    const fixture = document.createElement('input');
    Object.assign(fixture, { type: 'file', id: 'test-fixture', hidden: true });
    document.body.append(fixture);
  });
  await page.locator('#test-fixture').setInputFiles('output/playwright/ghostframe-edited.jpg');
  await page.evaluate(() => {
    const fixture = document.querySelector('#test-fixture');
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(fixture.files[0]);
    document.querySelector('#viewport').dispatchEvent(new DragEvent('drop', { dataTransfer, cancelable: true }));
    fixture.remove();
  });
  await page.getByText('2 étapes récupérées.').waitFor();
  ensure(await page.locator('#step-list .step-title').allTextContents().then((items) =>
    items.join('|') === 'Ouvrir <capture>|Échec de l’import'), 'Edited UTF-8 notes did not round-trip.');
  ensure(await page.locator('#step-list .step-time').allTextContents().then((items) =>
    items.join('|') === '0,4 s|1,2 s'), 'Edited durations did not round-trip.');

  // Use an isolated clipboard double to avoid reading or replacing the system clipboard during tests.
  const copied = '1. Ouvrir <capture>\n2. Échec de l’import';
  await page.evaluate(() => {
    const writeText = async (value) => { document.documentElement.dataset.testClipboard = value; };
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  });
  await get('Copier les étapes').click();
  await page.getByText('Étapes copiées.', { exact: false }).waitFor();
  ensure(await page.locator('html').getAttribute('data-test-clipboard') === copied, 'Clipboard text differs.');
  await page.evaluate(() => {
    navigator.clipboard.writeText = async () => { throw new Error('Clipboard unavailable'); };
  });
  await get('Copier les étapes').click();
  const textBox = page.getByRole('textbox', { name: 'Étapes en texte brut' });
  await textBox.waitFor();
  ensure(await textBox.inputValue() === copied, 'Fallback text differs.');
  ensure(await textBox.evaluate((field) => field.selectionStart === 0 && field.selectionEnd === field.value.length),
    'Fallback text should be selected.');
  await get('Lire la séquence').click();
  await page.waitForFunction(() => document.getElementById('target').textContent === '2');
  await get('Pause').click();
  await get('Reprendre').click();
  await get('Lire la séquence').waitFor();
  ensure(await page.locator('#target').textContent() === '2', 'Playback may not end at the last marker.');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'output/playwright/ghostframe-mobile.png', fullPage: true });
  ensure(await page.evaluate(() => document.documentElement.scrollWidth === window.innerWidth),
    'Mobile page has horizontal overflow.');
  await page.setViewportSize({ width: 1440, height: 980 });
  ensure(problems.length === 0, `Browser errors: ${problems.join(', ')}`);
  ensure(externalRequests.length === 0, `Unexpected external calls: ${externalRequests.join(', ')}`);
  return { exported: 2, recovered: 2, rejectedInvalidExport: true, pasted: true, dropped: true, copied: true,
    mobile: 'no overflow', externalRequests: externalRequests.length };
}
