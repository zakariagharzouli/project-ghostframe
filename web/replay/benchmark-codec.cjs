/* Expose the production raster codec to the Python benchmark over JSON lines. */
const readline = require('node:readline');
const Ghostframe = require('./codec.js');

function render({ width, height, steps }) {
  const rows = Ghostframe.bandHeight(steps);
  const raster = Buffer.alloc(width * rows, 255);
  const context = {
    fillStyle: '',
    fillRect(x, y, w, h) {
      const shade = this.fillStyle === '#fff' ? 255 : 16;
      for (let row = y - height; row < y - height + h; row += 1) {
        raster.fill(shade, row * width + x, row * width + x + w);
      }
    },
  };
  const payload = Ghostframe.paintBand(context, width, height, steps);
  return { rows, stripWidth: Ghostframe.BAND_WIDTH, band: raster.toString('base64'),
    payload: Buffer.from(payload).toString('base64') };
}

function read({ width, height, top, raster }) {
  const gray = Buffer.from(raster, 'base64');
  const data = new Uint8ClampedArray(gray.length * 4);
  for (let i = 0; i < gray.length; i += 1) {
    const position = i * 4;
    data[position] = data[position + 1] = data[position + 2] = gray[i];
    data[position + 3] = 255;
  }
  const result = Ghostframe.scan({ data, width, height }, top);
  if (!result) return null;
  const payload = Ghostframe.serialize(result.width, result.height, result.steps);
  return { ...result, payload: Buffer.from(payload).toString('base64') };
}

const operations = { render, read };
const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on('line', (line) => {
  try {
    const { operation, ...request } = JSON.parse(line);
    process.stdout.write(`${JSON.stringify({ result: operations[operation](request) })}\n`);
  } catch (error) {
    process.stdout.write(`${JSON.stringify({ error: error.message })}\n`);
  }
});
