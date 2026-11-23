# Ghostframe Replay

English · [Français](README.md) · [Installation](../../README.md#install-and-try)

Create a JPEG that shows an ordinary screenshot and also carries the steps to reproduce an issue. Replay runs in the browser. The image and annotations stay on the device.

## Use the editor and reader

1. Open the app and click **Lire la séquence** to play the built-in example.
2. Select **Créer**. Paste or drop a screenshot, or import a PNG, JPEG, or WebP. Place the markers in order. Edit each marker's note and display duration.
3. Click **Exporter le JPEG**. The editor reads back the exported JPEG and checks that all four tiles and the step data can be recovered.
4. Select **Rejouer**, open or drop the JPEG, and press **Lire la séquence**. **Copier les étapes** copies a plain-text checklist for an issue report. If clipboard access is unavailable, the app selects the generated text for manual copying.

Replay overlays markers and notes on a single screenshot. The editor records steps explicitly entered by the author. A file can contain up to 12 steps within a 243-byte payload. Each UTF-8 note can occupy up to 96 bytes, and step durations range from 0.1 to 10 seconds in 0.1-second increments.

## Build and test

Run the following from the repository root. The build creates `web/replay/dist/index.html`, which can be opened as a local file.

```sh
node web/replay/build.cjs
npm test
```

For a loopback preview of the standalone build, use `node web/replay/cli.cjs serve`. Use `python -m http.server 8764 --bind 127.0.0.1 --directory web/replay` for the browser test suite. Create `output/playwright/` first. The suite uses Playwright CLI and a compatible Chromium executable. Pillow is required to generate the transformed JPEG controls.

```sh
npx --package @playwright/cli playwright-cli -s=ghostframe open http://127.0.0.1:8764/
npx --package @playwright/cli playwright-cli -s=ghostframe run-code --filename web/replay/browser-test.js
python web/replay/transforms.py output/playwright/ghostframe-example.jpg output/playwright
npx --package @playwright/cli playwright-cli -s=ghostframe goto http://127.0.0.1:8764/dist/index.html
npx --package @playwright/cli playwright-cli -s=ghostframe run-code --filename web/replay/offline-test.js
npx --package @playwright/cli playwright-cli -s=ghostframe close
```

The first flow checks import, paste, drop, event editing, export, playback, and clipboard fallback. The second cuts off networking after loading the standalone page, then tests an original JPEG, a reduced JPEG, a crop that removes one tile, and negative controls for smaller or truncated files.

## GFS2 and GFS1 formats

`HTMLCanvasElement.toBlob` produces a JPEG. Its raster contains the screenshot and a centered grayscale strip. The viewport is normalized to at most 1,600 × 1,440 px and padded horizontally to a minimum width of 928 px when needed. The strip stays visible in a standard image viewer. Replay hides it after recovering the sequence.

The binary payload stores width and height as two network-order `uint16` values and a `uint8` step count. Each step stores its `x` and `y` positions as `uint16`, its duration in units of 100 ms as `uint8`, its `uint8` UTF-8 note length, and the note bytes. Positions refer to the untransformed export raster.

GFS2 uses data rows of six bytes. For a payload of length `L`, `r = ceil((15 + ceil(L / 3)) / 6)`. Zero padding divides the payload into three `6r − 15` byte shards. The fourth shard is their XOR. Each tile packet begins with the `GFS2` signature, payload CRC-32, payload length (`uint16`), tile index (`uint8`), and a packet CRC-32 calculated with that checksum field set to zero. The shard follows. Bits are laid out most significant first, left to right. GFS1 uses the same packet model with the `GFS1` signature and a fixed `r = 16`.

Each of the four adjacent tiles measures `58 × (r + 6)` modules of four pixels. With zero-based indices, the finder bars occupy columns 1–2 and 55–56 and rows 1 through `r + 4`. Data occupy columns 5–52 and rows 3 through `r + 2`. The reader estimates scale and offset from the bars, checks packet and payload integrity, and uses the resulting image coordinates to place each marker. One missing shard can be reconstructed. CRCs detect corruption. Authentication is outside the format's guarantees.

The JS package exports the codec for Node.js integration. `paintBand(context, width, height, steps)` draws the strip below a screenshot into a caller-provided 2D context. `scan(imageData, top)` reads decoded RGBA pixels and returns the steps and crop geometry, or `null` when the sequence cannot be verified. Here `top` is the input raster's vertical offset when supplying only its lower region. See [`codec.js`](codec.js) for the returned fields.

## Research results

The synthetic [equal-area benchmark](benchmark.md) compares GFS2 with fragmented QR and rMQR. With the same screenshots, binary payloads, and strip areas, GFS2 scored **98/132 vs 30/132** with Lanczos, and **96/132 vs 32/132** with bicubic resampling, against the best reference for each case. Success requires exact payload recovery and every visible click within two pixels.

The [ScreenSpot-Pro study](holdout.md) compares GFS2 with QR, rMQR, and rectangular Data Matrix under a local OpenCV JPEG pipeline. On the first 12 screenshots GFS2 succeeded in 226 of 252 cases, and the strongest reference combination succeeded in 195. A research-only reader retry with bilinear sampling recovered 13 more cases on a second set of 12 screenshots, yielding **240/240** cases with the strip present and rejecting all 12 stripped-band controls. The best reference recovered 190 of those same 240 cases. The reader won on nine screenshots and tied at the maximum on three. The predefined ten-win threshold was unmet. The tested evidence covers the stated corpus, central targets, and local transformations.

Reproduce the two studies from the repository root.

```sh
python -m pip install -r web/replay/requirements-benchmark.txt
python web/replay/benchmark.py --resample lanczos --out run/replay/benchmark-equal-area-lanczos.json
python web/replay/benchmark.py --resample bicubic --out run/replay/benchmark-equal-area-bicubic.json

python -m pip install -r web/replay/requirements-holdout.txt
python web/replay/holdout.py --out run/replay/holdout.json
python web/replay/holdout.py --followup-from run/replay/holdout.json --out run/replay/holdout-bilinear.json
```

Rotation, severe reduction, and removal of the strip can prevent recovery. The benchmarks use controlled pipelines. Production ticketing channels and support time savings remain unmeasured.
