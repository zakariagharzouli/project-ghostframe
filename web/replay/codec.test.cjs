const assert = require('node:assert/strict');
const { test } = require('node:test');
const Ghostframe = require('./codec.js');

const width = 1120;
const height = 650;
const steps = [
  { x: 437, y: 278, duration: 1000, note: 'Choisir commandes.csv' },
  { x: 363, y: 359, duration: 900, note: 'Lancer l’import' },
  { x: 342, y: 445, duration: 1600, note: 'L’erreur 42 apparaît' },
];

function raster(w, h, background = 255) {
  const data = new Uint8ClampedArray(w * h * 4).fill(background);
  return {
    width: w, height: h, data, fillStyle: '#fff',
    fillRect(x, y, cols, rows) {
      const shade = this.fillStyle === '#fff' ? 255 : 16;
      for (let row = y; row < y + rows; row += 1) {
        data.fill(shade, (row * w + x) * 4, (row * w + x + cols) * 4);
      }
    },
  };
}

function capture() {
  const image = raster(width, height + Ghostframe.BAND_HEIGHT);
  Ghostframe.paintBand(image, width, height, steps);
  return image;
}

function transform(image, { left = 0, top = 0, right = image.width, scale = 1 } = {}) {
  const w = Math.round((right - left) * scale);
  const h = Math.round((image.height - top) * scale);
  const result = raster(w, h);
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      const sourceX = left + Math.floor(x / scale);
      const sourceY = top + Math.floor(y / scale);
      const value = image.data[(sourceY * image.width + sourceX) * 4];
      result.data.fill(value, (y * w + x) * 4, (y * w + x + 1) * 4);
    }
  }
  return result;
}

test('preserves ordered annotations, integer positions and durations', () => {
  const packed = Ghostframe.serialize(width, height, steps);
  assert.equal(packed.length, 84);
  assert.deepEqual(Ghostframe.deserialize(packed), { width, height, steps });
  assert.equal(Ghostframe.deserialize(packed.subarray(0, packed.length - 1)), null);
  const unicode = [{ ...steps[0], note: '\uFEFFÉchec 🧪' }];
  assert.deepEqual(Ghostframe.deserialize(Ghostframe.serialize(width, height, unicode)).steps, unicode);
});

test('enforces bounds and counts UTF-8 bytes', () => {
  assert.throws(() => Ghostframe.serialize(width, height, []));
  assert.throws(() => Ghostframe.serialize(width, height, [{ ...steps[0], note: '🧪'.repeat(25) }]));
  assert.throws(() => Ghostframe.serialize(width, height, [{ ...steps[0], duration: 15 }]));
  assert.throws(() => Ghostframe.serialize(width, height, [{ ...steps[0], x: width }]));
  assert.throws(() => Ghostframe.serialize(width, height, Array(5).fill({ ...steps[0], note: 'x'.repeat(96) })));
});

test('reads the original and the half-sized raster', () => {
  const direct = Ghostframe.scan(capture());
  assert.deepEqual(direct.steps, steps);
  assert.equal(direct.validTiles, 4);
  assert.equal(direct.recoveredTile, null);
  const small = Ghostframe.scan(transform(capture(), { scale: .5 }));
  assert.deepEqual(small.steps, steps);
  assert.deepEqual(small.crop, { x: 0, y: 0, right: width / 2, bottom: height / 2 });
});

test('uses parity for a missing data tile and preserves positions after crop and scale', () => {
  const image = transform(capture(), { left: 328, top: 32, scale: .5 });
  const restored = Ghostframe.scan(image);
  assert.deepEqual(restored.steps, steps);
  assert.equal(restored.recoveredTile, 0);
  assert.equal(restored.left, -164);
  assert.equal(restored.top, -16);
  assert.deepEqual(restored.crop, { x: 0, y: 0, right: 396, bottom: 309 });
});

test('recovers each single missing tile and refuses two data losses', () => {
  const stripe = Ghostframe.BAND_WIDTH / 4;
  const origin = (width - Ghostframe.BAND_WIDTH) / 2;
  for (let index = 0; index < 4; index += 1) {
    const image = capture();
    image.fillStyle = '#fff';
    image.fillRect(origin + index * stripe, height, stripe, Ghostframe.BAND_HEIGHT);
    const restored = Ghostframe.scan(image);
    assert.deepEqual(restored.steps, steps);
    assert.equal(restored.recoveredTile, index === 3 ? null : index);
  }
  const image = capture();
  image.fillStyle = '#fff';
  image.fillRect(origin, height, stripe * 2, Ghostframe.BAND_HEIGHT);
  assert.equal(Ghostframe.scan(image), null);
});

test('rejects an ordinary flat image', () => {
  assert.equal(Ghostframe.scan(raster(width, height, 240)), null);
});
