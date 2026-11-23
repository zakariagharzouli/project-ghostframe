/* Ghostframe Replay. GFS2 uses a shorter band for short sequences. */
const Ghostframe = (() => {
  const MODULE = 4;
  const COLS = 48;
  const MAX_ROWS = 16;
  const MIN_ROWS = 4;
  const TILE_COLS = 58;
  const BORDER_ROWS = 6;
  const BYTES_PER_ROW = COLS / 8;
  const DATA_SHARDS = 3;
  const TILE_COUNT = DATA_SHARDS + 1;
  const TILE_WIDTH = MODULE * TILE_COLS;
  const BAND_WIDTH = TILE_WIDTH * TILE_COUNT;
  const HEADER_BYTES = 15;
  const CAPACITY = (MAX_ROWS * BYTES_PER_ROW - HEADER_BYTES) * DATA_SHARDS;
  const PAYLOAD_HEADER = 5;
  const MIN_MODULE = 1.5;
  const MAX_MODULE = 12;
  const SCAN_DEPTH = 280;
  const SCAN_HEIGHT = SCAN_DEPTH + (MAX_ROWS + 4) * MAX_MODULE + 2;
  const FINDER_THRESHOLD = (0x10 + 0xff) / 2;
  const MAX_STEPS = 12;
  const MAX_NOTE_BYTES = 96;
  const MAGIC_GFS1 = 0x47465331;
  const MAGIC_GFS2 = 0x47465332;
  const utf8 = new TextEncoder();
  const fromUtf8 = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true });

  const crcTable = Uint32Array.from({ length: 256 }, (_, value) => {
    for (let bit = 0; bit < 8; bit += 1) {
      value = (value >>> 1) ^ ((value & 1) ? 0xedb88320 : 0);
    }
    return value;
  });

  function crc32(bytes) {
    let crc = 0xffffffff;
    for (const byte of bytes) crc = crcTable[(crc ^ byte) & 255] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
  }

  const validSize = (width, height) => Number.isInteger(width) && Number.isInteger(height)
    && width >= BAND_WIDTH && width <= 1600 && height >= 1 && height <= 1440;
  const viewOf = (bytes) => new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const stripLeft = (width) => Math.floor((width - BAND_WIDTH) / 2);
  const rowsFor = (length) => Math.ceil((Math.ceil(length / DATA_SHARDS) + HEADER_BYTES) / BYTES_PER_ROW);
  const bandHeight = (steps) => (Math.max(MIN_ROWS, rowsFor(metrics(steps))) + BORDER_ROWS) * MODULE;

  function serialize(width, height, steps) {
    if (!validSize(width, height) || steps.length === 0 || steps.length > MAX_STEPS) {
      throw new Error('Dimensions ou nombre d’étapes hors limites.');
    }
    const notes = steps.map(({ note }) => utf8.encode(note));
    const size = notes.reduce((length, note) => length + 6 + note.length, PAYLOAD_HEADER);
    if (size > CAPACITY || notes.some((note) => note.length > MAX_NOTE_BYTES)) {
      throw new Error('Raccourcissez les annotations pour exporter cette capture.');
    }
    const payload = new Uint8Array(size);
    const view = viewOf(payload);
    view.setUint16(0, width);
    view.setUint16(2, height);
    payload[4] = steps.length;
    let offset = PAYLOAD_HEADER;
    for (const [index, { x, y, duration }] of steps.entries()) {
      if (!Number.isInteger(x) || !Number.isInteger(y) || x < 0 || y < 0 || x >= width || y >= height
        || !Number.isInteger(duration / 100) || duration < 100 || duration > 10000) {
        throw new Error('Position ou durée d’étape hors limites.');
      }
      const note = notes[index];
      view.setUint16(offset, x);
      view.setUint16(offset + 2, y);
      payload[offset + 4] = duration / 100;
      payload[offset + 5] = note.length;
      payload.set(note, offset + 6);
      offset += 6 + note.length;
    }
    return payload;
  }

  function deserialize(payload) {
    if (payload.length < PAYLOAD_HEADER) return null;
    const view = viewOf(payload);
    const width = view.getUint16(0);
    const height = view.getUint16(2);
    const count = payload[4];
    if (!validSize(width, height) || count === 0 || count > MAX_STEPS) return null;
    const steps = [];
    let offset = PAYLOAD_HEADER;
    for (let index = 0; index < count; index += 1) {
      if (payload.length - offset < 6) return null;
      const x = view.getUint16(offset);
      const y = view.getUint16(offset + 2);
      const duration = payload[offset + 4] * 100;
      const length = payload[offset + 5];
      const end = offset + 6 + length;
      if (x >= width || y >= height || duration < 100 || duration > 10000
        || length > MAX_NOTE_BYTES || end > payload.length) return null;
      try {
        const note = fromUtf8.decode(payload.subarray(offset + 6, end));
        steps.push({ x, y, duration, note });
      } catch {
        return null;
      }
      offset = end;
    }
    return offset === payload.length ? { width, height, steps } : null;
  }

  function xorInto(target, shard) {
    for (let index = 0; index < target.length; index += 1) target[index] ^= shard[index];
  }

  function packets(payload, rows) {
    const packetBytes = rows * BYTES_PER_ROW;
    const shardBytes = packetBytes - HEADER_BYTES;
    const padded = new Uint8Array(shardBytes * DATA_SHARDS);
    padded.set(payload);
    const data = Array.from({ length: DATA_SHARDS }, (_, index) =>
      padded.subarray(index * shardBytes, (index + 1) * shardBytes));
    const parity = new Uint8Array(shardBytes);
    for (const shard of data) xorInto(parity, shard);
    const identity = crc32(payload);
    return [...data, parity].map((shard, index) => {
      const packet = new Uint8Array(packetBytes);
      const view = viewOf(packet);
      view.setUint32(0, MAGIC_GFS2);
      view.setUint32(4, identity);
      view.setUint16(8, payload.length);
      packet[10] = index;
      packet.set(shard, HEADER_BYTES);
      view.setUint32(11, crc32(packet));
      return packet;
    });
  }

  function paintBand(context, width, height, steps) {
    const payload = serialize(width, height, steps);
    const rows = rowsFor(payload.length);
    const blocks = packets(payload, rows);
    const left = stripLeft(width);
    context.fillStyle = '#fff';
    context.fillRect(0, height, width, (rows + BORDER_ROWS) * MODULE);
    context.fillStyle = '#101010';
    for (const [index, packet] of blocks.entries()) {
      const x0 = left + index * TILE_WIDTH;
      const barHeight = (rows + 4) * MODULE;
      context.fillRect(x0 + MODULE, height + MODULE, 2 * MODULE, barHeight);
      context.fillRect(x0 + 55 * MODULE, height + MODULE, 2 * MODULE, barHeight);
      for (let bit = 0; bit < COLS * rows; bit += 1) {
        if (packet[bit >>> 3] & (128 >>> (bit & 7))) {
          const x = x0 + (5 + bit % COLS) * MODULE;
          const y = height + (3 + Math.floor(bit / COLS)) * MODULE;
          context.fillRect(x, y, MODULE, MODULE);
        }
      }
    }
    return payload;
  }

  function metrics(steps) {
    return PAYLOAD_HEADER + steps.reduce((length, { note }) => length + 6 + utf8.encode(note).length, 0);
  }

  // Estimate where the black-to-white transition lies between two pixel centers.
  function crossing(coordinate, before, after) {
    return coordinate - .5 + (FINDER_THRESHOLD - before) / (after - before);
  }

  function runs(luma, width, y) {
    const row = y * width;
    const marks = [];
    for (let x = 0; x < width;) {
      if (luma[row + x] >= FINDER_THRESHOLD) {
        x += 1;
        continue;
      }
      const start = x;
      while (x < width && luma[row + x] < FINDER_THRESHOLD) x += 1;
      const left = start ? crossing(start, luma[row + start - 1], luma[row + start]) : 0;
      const right = x < width ? crossing(x, luma[row + x - 1], luma[row + x]) : width;
      marks.push({ start, end: x, width: right - left, center: (left + right) / 2 });
    }
    return marks;
  }

  function extent(luma, width, height, x, y) {
    let top = y;
    let bottom = y + 1;
    while (top > 0 && luma[(top - 1) * width + x] < FINDER_THRESHOLD) top -= 1;
    while (bottom < height && luma[bottom * width + x] < FINDER_THRESHOLD) bottom += 1;
    return {
      top: top ? crossing(top, luma[(top - 1) * width + x], luma[top * width + x]) : 0,
      bottom: bottom < height ? crossing(bottom, luma[(bottom - 1) * width + x], luma[bottom * width + x]) : height,
    };
  }

  function nearest(luma, width, x, y) {
    return luma[Math.floor(y) * width + Math.floor(x)];
  }

  function bilinear(luma, width, x, y) {
    const column = Math.floor(x - .5);
    const row = Math.floor(y - .5);
    if (column < 0 || column + 1 >= width || row < 0 || (row + 2) * width > luma.length) {
      return nearest(luma, width, x, y);
    }
    const dx = x - .5 - column;
    const dy = y - .5 - row;
    const first = row * width + column;
    const next = first + width;
    const upper = (1 - dx) * luma[first] + dx * luma[first + 1];
    const lower = (1 - dx) * luma[next] + dx * luma[next + 1];
    return (1 - dy) * upper + dy * lower;
  }

  function readTile(luma, width, height, y, a, b, sample) {
    const sx = (b.center - a.center) / 54;
    if (sx < MIN_MODULE || sx > MAX_MODULE || [a.width, b.width].some((w) => Math.abs(w - 2 * sx) > 2.2)) return null;
    const row = y * width;
    const pad = Math.max(1, Math.floor(sx / 2));
    const guard = [a.start - 1 - pad, a.end + pad, b.start - 1 - pad, b.end + pad];
    if (guard.some((x) => x < 0 || x >= width || luma[row + x] < 145)) return null;
    const left = extent(luma, width, height, Math.floor(a.center), y);
    const right = extent(luma, width, height, Math.floor(b.center), y);
    if (Math.abs(left.top - right.top) > 2 || Math.abs(left.bottom - right.bottom) > 2) return null;
    const top = (left.top + right.top) / 2;
    const bottom = (left.bottom + right.bottom) / 2;
    const x0 = a.center - 2 * sx;
    // Near-isotropic images give the row count directly. Try the remaining heights
    // when the image was stretched or the finder edge was rounded by resampling.
    const estimate = Math.round((bottom - top) / sx - 4);
    const preferred = Math.max(MIN_ROWS, Math.min(MAX_ROWS, estimate));
    const direct = sampleRows(luma, width, y, x0, top, bottom, sx, preferred, sample);
    if (direct) return direct;
    for (let rows = MIN_ROWS; rows <= MAX_ROWS; rows += 1) {
      if (rows === preferred) continue;
      const tile = sampleRows(luma, width, y, x0, top, bottom, sx, rows, sample);
      if (tile) return tile;
    }
    return null;
  }

  function sampleRows(luma, width, y, x0, top, bottom, sx, rows, sample) {
    const sy = (bottom - top) / (rows + 4);
    if (sy < MIN_MODULE || sy > MAX_MODULE || sx / sy < .66 || sx / sy > 1.5) return null;
    // The footer is the only empty scanline crossed by both bars.
    if (y + .5 < bottom - 2.6 * sy) return null;
    const y0 = top - sy;
    const packet = new Uint8Array(rows * BYTES_PER_ROW);
    const header = viewOf(packet);
    for (let yy = 0; yy < rows; yy += 1) {
      const line = y0 + (yy + 3.5) * sy;
      for (let xx = 0; xx < COLS; xx += 1) {
        const column = x0 + (xx + 5.5) * sx;
        const bit = yy * COLS + xx;
        if (sample(luma, width, column, line) < 128) packet[bit >>> 3] |= 128 >>> (bit & 7);
      }
      if (yy === 0) {
        const magic = header.getUint32(0);
        if (magic !== MAGIC_GFS2 && (magic !== MAGIC_GFS1 || rows !== MAX_ROWS)) return null;
      }
    }
    const magic = header.getUint32(0);
    const length = header.getUint16(8);
    const index = packet[10];
    if (length < PAYLOAD_HEADER || length > CAPACITY || index >= TILE_COUNT
      || (magic === MAGIC_GFS2 && rows !== rowsFor(length))) return null;
    const crc = header.getUint32(11);
    header.setUint32(11, 0);
    if (crc32(packet) !== crc) return null;
    return { length, index, magic, rows, identity: header.getUint32(4), x0, y0, sx: sx / MODULE, sy: sy / MODULE,
      shard: packet.subarray(HEADER_BYTES) };
  }

  function restore(group, width, height) {
    if (group.size < DATA_SHARDS) return null;
    const tiles = Array.from(group.values());
    const { length, identity } = tiles[0];
    const shardBytes = tiles[0].shard.length;
    const payload = new Uint8Array(shardBytes * DATA_SHARDS);
    const repair = group.size === DATA_SHARDS && group.has(DATA_SHARDS)
      ? group.get(DATA_SHARDS).shard.slice() : null;
    let missing = null;
    for (let index = 0; index < DATA_SHARDS; index += 1) {
      if (!group.has(index)) {
        if (!repair) return null;
        missing = index;
        continue;
      }
      const { shard } = group.get(index);
      payload.set(shard, index * shardBytes);
      if (repair) xorInto(repair, shard);
    }
    if (missing !== null) payload.set(repair, missing * shardBytes);
    const data = payload.subarray(0, length);
    if (crc32(data) !== identity) return null;
    const decoded = deserialize(data);
    if (!decoded) return null;

    const ordered = tiles.slice().sort((a, b) => a.index - b.index);
    const first = ordered[0];
    const last = ordered.at(-1);
    const sx = (last.x0 - first.x0) / ((last.index - first.index) * TILE_WIDTH);
    if (sx < MIN_MODULE / MODULE || sx > MAX_MODULE / MODULE
      || tiles.some((tile) => Math.abs(tile.sx - sx) > .04)) return null;
    // The bar heights are quantized to pixels. Prefer the wider horizontal baseline
    // when the measured heights agree with uniform scaling to within one pixel.
    const barHeight = (first.rows + 4) * MODULE;
    const uniform = tiles.every((tile) => Math.abs(tile.sy - sx) * barHeight <= 1.1);
    const sy = uniform ? sx : tiles.reduce((sum, tile) => sum + tile.sy, 0) / tiles.length;
    const left = first.x0 - (stripLeft(decoded.width) + first.index * TILE_WIDTH) * sx;
    const bandTop = tiles.reduce((sum, tile) => sum + tile.y0, 0) / tiles.length;
    const top = bandTop - decoded.height * sy;
    const close = (a, b) => Math.abs(a - b) <= 3;
    if (tiles.some((tile) => !close(tile.y0, bandTop)
      || !close(tile.x0, left + (stripLeft(decoded.width) + tile.index * TILE_WIDTH) * sx))) return null;

    const crop = {
      x: Math.max(0, Math.round(left)), y: Math.max(0, Math.round(top)),
      right: Math.min(width, Math.round(left + decoded.width * sx)),
      bottom: Math.min(height, Math.round(bandTop)),
    };
    if (crop.right <= crop.x || crop.bottom <= crop.y) return null;
    return { ...decoded, crop, left, top, sx, sy, recoveredTile: missing, validTiles: group.size };
  }

  function scan({ data, width, height }, top = 0, { interpolate = false } = {}) {
    const luma = new Uint8Array(width * height);
    for (let i = 0, pixel = 0; pixel < luma.length; i += 4, pixel += 1) {
      luma[pixel] = (54 * data[i] + 183 * data[i + 1] + 19 * data[i + 2]) >>> 8;
    }
    const groups = new Map();
    const sample = interpolate ? bilinear : nearest;
    for (let y = height - 1; y >= Math.max(0, height - SCAN_DEPTH); y -= 2) {
      const marks = runs(luma, width, y);
      for (let index = 1; index < marks.length; index += 1) {
        const tile = readTile(luma, width, height, y, marks[index - 1], marks[index], sample);
        if (!tile) continue;
        tile.y0 += top;
        const key = `${tile.magic}/${tile.identity}/${tile.length}`;
        if (!groups.has(key)) groups.set(key, new Map());
        const group = groups.get(key);
        if (!group.has(tile.index)) group.set(tile.index, tile);
      }
      // All of the tile footers are on one scanline, except for rounding after resizing.
      if (Array.from(groups.values()).some((group) => group.size === TILE_COUNT)) break;
    }
    const matches = Array.from(groups.values(), (group) => restore(group, width, height + top)).filter(Boolean);
    return matches.length === 1 ? matches[0] : null;
  }

  return Object.freeze({ BAND_WIDTH, CAPACITY, MAX_STEPS, MAX_NOTE_BYTES, SCAN_HEIGHT,
    serialize, deserialize, metrics, bandHeight, paintBand, scan });
})();

if (typeof module !== 'undefined') module.exports = Ghostframe;
