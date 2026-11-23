async (page) => {
  await page.context().setOffline(true);
  await page.getByRole('button', { name: 'Rejouer', exact: true }).click();
  const result = [];
  for (const crop of ['intact', 'crop']) {
    for (const percent of [63, 50, 45, 40]) {
      for (const quality of [85, 65, 45, 30]) {
        const row = { crop, percent, quality };
        for (const version of ['v1', 'v2']) {
          const path = `output/playwright/replay-matrix/${version}-${crop}-${percent}-${quality}.jpg`;
          await page.locator('#file').setInputFiles(path);
          await page.waitForFunction(() => /récupérées|récupérable/.test(document.querySelector('#status').textContent));
          row[version] = await page.evaluate(() => {
            if (!document.querySelector('#status').textContent.startsWith('3 étapes récupérées.')) return false;
            const notes = [...document.querySelectorAll('.step-title')].map((node) => node.textContent).join('|');
            const durations = [...document.querySelectorAll('.step-time')].map((node) => node.textContent).join('|');
            if (notes !== 'Choisir commandes.csv|Lancer l’import|L’erreur 42 apparaît' || durations !== '1 s|0,9 s|1,6 s') {
              throw new Error('Unexpected successful decode');
            }
            return true;
          });
        }
        result.push(row);
      }
    }
  }
  await page.context().setOffline(false);
  return { v1: result.filter((test) => test.v1).length, v2: result.filter((test) => test.v2).length,
    total: result.length, differences: result.filter((test) => test.v1 !== test.v2),
    failedBoth: result.filter((test) => !test.v1 && !test.v2) };
}
