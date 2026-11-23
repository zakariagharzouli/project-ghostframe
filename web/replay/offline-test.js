async (page) => {
  const unexpected = [];
  page.on('pageerror', (error) => unexpected.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') unexpected.push(message.text());
  });
  page.on('request', (request) => {
    if (/^https?:/.test(request.url())) unexpected.push(request.url());
  });
  const open = async (fixture, expected) => {
    await page.locator('#file').setInputFiles(`output/playwright/ghostframe-${fixture}.jpg`);
    await page.getByText(expected, { exact: true }).waitFor({ timeout: 5000 });
    return { fixture, status: await page.getByRole('status').textContent() };
  };
  await page.context().setOffline(true);
  await page.getByRole('button', { name: 'Rejouer', exact: true }).click();
  const records = [];
  const expectedNotes = 'Choisir commandes.csv|Lancer l’import|L’erreur 42 apparaît';
  const expectedTimes = '1 s|0,9 s|1,6 s';
  for (const [fixture, status, width, height] of [
    ['example', '3 étapes récupérées.', 1120, 650],
    ['jpeg65', '3 étapes récupérées.', 1120, 650],
    ['resize50', '3 étapes récupérées.', 560, 325],
    ['resize63', '3 étapes récupérées.', 706, 410],
    ['crop50', '3 étapes récupérées. Une tuile manquante a été restaurée.', 396, 309],
    ['gray-crop50', '3 étapes récupérées. Une tuile manquante a été restaurée.', 396, 309],
  ]) {
    records.push(await open(fixture, status));
    const notes = await page.locator('#step-list .step-title').allTextContents();
    const times = await page.locator('#step-list .step-time').allTextContents();
    if (notes.join('|') !== expectedNotes || times.join('|') !== expectedTimes) {
      throw new Error(`Annotation or timing mismatch for ${fixture}`);
    }
    const marker = await page.evaluate(() => {
      const { width, height } = document.querySelector('#screen');
      const { left, top } = document.querySelector('#target').style;
      return { width, height, x: (parseFloat(left) / 100) * width, y: (parseFloat(top) / 100) * height };
    });
    if (marker.width !== width || marker.height !== height) throw new Error(`Wrong geometry for ${fixture}`);
    const scale = fixture.includes('50') ? .5 : fixture.includes('63') ? .63 : 1;
    const nominalX = (437.5 - (fixture.includes('crop') ? 328 : 0)) * scale;
    const nominalY = (278.5 - (fixture.includes('crop') ? 32 : 0)) * scale;
    if (Math.abs(marker.x - nominalX) > 1 || Math.abs(marker.y - nominalY) > 1) {
      throw new Error(`Wrong replay position for ${fixture}`);
    }
  }
  for (const fixture of ['two-tiles-lost', 'thumbnail150']) {
    records.push(await open(fixture, 'Aucune séquence Ghostframe récupérable dans cette image.'));
  }
  if (unexpected.length) throw new Error(unexpected.join('\n'));
  await page.context().setOffline(false);
  return { offline: true, httpRequests: 0, records };
}
