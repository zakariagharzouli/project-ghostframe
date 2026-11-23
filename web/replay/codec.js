/* Ghostframe Replay v1. The transport is carried entirely by grayscale pixels. */
const Ghostframe = (() => {
  const MODULE = 4;
  const COLS = 48;
  const ROWS = 16;
  const TILE_COLS = 58;
  const TILE_ROWS = 22;
  const DATA_SHARDS = 3;
  const TILE_COUNT = DATA_SHARDS + 1;
  const TILE_WIDTH = MODULE * TILE_COLS;
  const BAND_WIDTH = TILE_WIDTH * TILE_COUNT;
  const BAND_HEIGHT = MODULE * TILE_ROWS;
  const PACKET_BYTES = COLS * ROWS / 8;
  const HEADER_BYTES = 15;
  const SHARD_BYTES = PACKET_BYTES - HEADER_BYTES;
  const CAPACITY = SHARD_BYTES * DATA_SHARDS;
  const PAYLOAD_HEADER = 5;
  const MAX_STEPS = 12;
  const MAX_NOTE_BYTES = 96;
  const MAGIC = 0x47465331;
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

  function packets(payload) {
    const padded = new Uint8Array(CAPACITY);
    padded.set(payload);
    const data = Array.from({ length: DATA_SHARDS }, (_, index) =>
      padded.subarray(index * SHARD_BYTES, (index + 1) * SHARD_BYTES));
    const parity = new Uint8Array(SHARD_BYTES);
    for (const shard of data) xorInto(parity, shard);
    const identity = crc32(payload);
    return [...data, parity].map((shard, index) => {
      const packet = new Uint8Array(PACKET_BYTES);
      const view = viewOf(packet);
      view.setUint32(0, MAGIC);
      view.setUint32(4, identity);
      view.setUint16(8, payload.length);
      packet[10] = index;
      packet.set(shard, HEADER_BYTES);
      view.setUint32(11, crc32(packet));
      return packet;
    });
  }

  function paintBand(context, width, height, steps) {
    const blocks = packets(serialize(width, height, steps));
    const left = stripLeft(width);
    context.fillStyle = '#fff';
    context.fillRect(0, height, width, BAND_HEIGHT);
    context.fillStyle = '#101010';
    for (const [index, packet] of blocks.entries()) {
      const x0 = left + index * TILE_WIDTH;
      context.fillRect(x0 + MODULE, height + MODULE, 2 * MODULE, 20 * MODULE);
      context.fillRect(x0 + 55 * MODULE, height + MODULE, 2 * MODULE, 20 * MODULE);
      for (let bit = 0; bit < COLS * ROWS; bit += 1) {
        if (packet[bit >>> 3] & (128 >>> (bit & 7))) {
          const x = x0 + (5 + bit % COLS) * MODULE;
          const y = height + (3 + Math.floor(bit / COLS)) * MODULE;
          context.fillRect(x, y, MODULE, MODULE);
        }
      }
    }
  }

  function metrics(steps) {
    return PAYLOAD_HEADER + steps.reduce((length, { note }) => length + 6 + utf8.encode(note).length, 0);
  }

  function runs(luma, width, y) {
    const row = y * width;
    const marks = [];
    for (let x = 0; x < width;) {
      if (luma[row + x] >= 100) {
        x += 1;
        continue;
      }
      const start = x;
      while (x < width && luma[row + x] < 100) x += 1;
      marks.push({ start, end: x, width: x - start, center: (start + x) / 2 });
    }
    return marks;
  }

  function extent(luma, width, height, x, y) {
    let top = y;
    let bottom = y + 1;
    while (top > 0 && luma[(top - 1) * width + x] < 100) top -= 1;
    while (bottom < height && luma[bottom * width + x] < 100) bottom += 1;
    return { top, bottom };
  }

  function readTile(luma, width, height, y, a, b) {
    const sx = (b.center - a.center) / 54;
    if (sx < 1.65 || sx > 12 || [a.width, b.width].some((w) => Math.abs(w - 2 * sx) > 2.2)) return null;
    if (a.start === 0 || b.end === width) return null;
    const row = y * width;
    if ([a.start - 1, a.end, b.start - 1, b.end].some((x) => luma[row + x] < 145)) return null;
    const left = extent(luma, width, height, Math.floor(a.center), y);
    const right = extent(luma, width, height, Math.floor(b.center), y);
    if (Math.abs(left.top - right.top) > 2 || Math.abs(left.bottom - right.bottom) > 2) return null;
    const top = (left.top + right.top) / 2;
    const bottom = (left.bottom + right.bottom) / 2;
    const sy = (bottom - top) / 20;
    if (sy < 1.65 || sy > 12 || sx / sy < .66 || sx / sy > 1.5) return null;
    // The scanline must cross the footer, where only the two bars are painted.
    if (y + .5 < bottom - 2.6 * sy) return null;
    const x0 = a.center - 2 * sx;
    const y0 = top - sy;
    const packet = new Uint8Array(PACKET_BYTES);
    for (let yy = 0; yy < ROWS; yy += 1) {
      const row = Math.floor(y0 + (yy + 3.5) * sy) * width;
      for (let xx = 0; xx < COLS; xx += 1) {
        const sample = Math.floor(x0 + (xx + 5.5) * sx);
        const bit = yy * COLS + xx;
        if (luma[row + sample] < 128) packet[bit >>> 3] |= 128 >>> (bit & 7);
      }
      if (yy === 0 && viewOf(packet).getUint32(0) !== MAGIC) return null;
    }
    const header = viewOf(packet);
    const crc = header.getUint32(11);
    header.setUint32(11, 0);
    if (crc32(packet) !== crc) return null;
    const length = header.getUint16(8);
    const index = packet[10];
    if (length < PAYLOAD_HEADER || length > CAPACITY || index >= TILE_COUNT) return null;
    return { length, index, identity: header.getUint32(4), x0, y0, sx: sx / MODULE, sy: sy / MODULE,
      shard: packet.subarray(HEADER_BYTES) };
  }

  function restore(group, width, height) {
    if (group.size < DATA_SHARDS) return null;
    const tiles = Array.from(group.values());
    const { length, identity } = tiles[0];
    const payload = new Uint8Array(CAPACITY);
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
      payload.set(shard, index * SHARD_BYTES);
      if (repair) xorInto(repair, shard);
    }
    if (missing !== null) payload.set(repair, missing * SHARD_BYTES);
    const data = payload.subarray(0, length);
    if (crc32(data) !== identity) return null;
    const decoded = deserialize(data);
    if (!decoded) return null;

    const ordered = tiles.slice().sort((a, b) => a.index - b.index);
    const first = ordered[0];
    const last = ordered.at(-1);
    const sx = (last.x0 - first.x0) / ((last.index - first.index) * TILE_WIDTH);
    const sy = tiles.reduce((sum, tile) => sum + tile.sy, 0) / tiles.length;
    if (sx < .40 || sx > 3 || tiles.some((tile) => Math.abs(tile.sx - sx) > .04)) return null;
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

  function scan({ data, width, height }) {
    const luma = new Uint8Array(width * height);
    for (let i = 0, pixel = 0; pixel < luma.length; i += 4, pixel += 1) {
      luma[pixel] = (54 * data[i] + 183 * data[i + 1] + 19 * data[i + 2]) >>> 8;
    }
    const groups = new Map();
    for (let y = height - 1; y >= Math.max(0, height - 280); y -= 2) {
      const marks = runs(luma, width, y);
      for (let index = 1; index < marks.length; index += 1) {
        const tile = readTile(luma, width, height, y, marks[index - 1], marks[index]);
        if (!tile) continue;
        const key = `${tile.identity}/${tile.length}`;
        if (!groups.has(key)) groups.set(key, new Map());
        const group = groups.get(key);
        if (!group.has(tile.index)) group.set(tile.index, tile);
      }
      // All of the tile footers are on one scanline, except for rounding after resizing.
      if (Array.from(groups.values()).some((group) => group.size === TILE_COUNT)) break;
    }
    const matches = Array.from(groups.values(), (group) => restore(group, width, height)).filter(Boolean);
    return matches.length === 1 ? matches[0] : null;
  }

  return Object.freeze({ BAND_WIDTH, BAND_HEIGHT, CAPACITY, MAX_STEPS, MAX_NOTE_BYTES,
    serialize, deserialize, metrics, paintBand, scan });
})();

if (typeof module !== 'undefined') module.exports = Ghostframe;
