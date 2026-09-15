# BBQr JavaScript / TypeScript implementation

This is an implementation of [BBQr - Better Bitcoin QR](https://bbqr.org) for the browser, written in TypeScript.

## Installation

Install with npm (or your package manager of choice):

```sh
npm install bbqr
```

## Usage

### Low-level splitting/joining

```js
import { joinQRs, splitQRs } from 'bbqr';

// Create a Uint8Array containing the raw bytes of a PSBT, transaction or other data
const input = new Uint8Array([
  112,
  115,
  98,
  116,
  255, // ... rest of PSBT bytes
]);

// ...

const fileType = 'P'; // 'P' is for PSBT

const splitResult = splitQRs(input, fileType, {
  // these are optional - default values are shown
  encoding: 'Z', // Zlib compressed base32 encoding
  minSplit: 1, // minimum number of parts to return
  maxSplit: 1295, // maximum number of parts to return
  minVersion: 5, // minimum QR code version
  maxVersion: 40, // maximum QR code version
  parity: 0, // number of extra parity QR codes to add (see below)
});

// the QR code version chosen for best efficiency
console.log(splitResult.version);

// the actual encoding used - could be '2' (uncompressed base32) if the 'Z' option didn't provide a smaller result
console.log(splitResult.encoding);

// the QR code parts
console.log(splitResult.parts);

// now we do this in reverse and get back the bytes

const reassembled = joinQRs(splitResult.parts);

console.log(reassembled.fileType === fileType); // true
console.log(reassembled.encoding === splitResult.encoding); // true
console.log(reassembled.raw.every((byte, i) => byte === input[i])); // true
```

### Parity Parts

Setting `parity` appends that many extra QR codes to the series. Their indexes follow the
data parts, so a series of 7 data parts with `parity: 2` has parts `00` to `08`, and any 7
of those 9 are enough to get the data back. The count in the header stays the number of
data parts. Decoders written before parity parts existed reject the extra indexes, so only
enable this for receivers known to support it.

Parity has no effect when everything fits into a single QR code.

`joinQRs` accepts any such subset: pass it whatever parts were scanned, in any order, and it
rebuilds the missing data parts when at least as many parts as the header's count are present.

```js
// something big enough to need several QR codes
const big = new Uint8Array(5000);
crypto.getRandomValues(big);

const { parts } = splitQRs(big, 'B', { encoding: '2', parity: 2 });

// drop any two parts and the data still comes back
const scanned = parts.slice(2);
const { raw } = joinQRs(scanned);
```

### Detecting the File Type

In the previous example, we provided the raw bytes and specified the File Type to use. You can also
detect the file type by calling `detectFileType` with a `Uint8Array`, a `File` object or a `string` (the contents of
a text file).

This is especially useful for PSBTs and Bitcoin transactions as `detectFileType` can also detect these
in HEX and Base64 format.

If a PSBT or transaction is not detected, the file type will be:

- `J` for a text file that can be successfully parsed as JSON.
- `U` for all other text files.
- `B` for all other binary files.

For other supported type codes, you should do the conersion to `Uint8Array` not rely on `detectFileType`.

```js
import { detectFileType } from 'bbqr';

// hex representation of a Bitcoin transaction
const contents =
  '01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff0704ffff001d0104ffffffff0100f2052a0100000043410496b538e853519c726a2c91e61ec11600ae1390813a627c66fb8be7947be63c52da7589379515d4e0a604f8141781e62294721166bf621e73a82cbf2342c858eeac00000000';

const detected = await detectFileType(contents);

// 'T' for transaction
console.log(detected.fileType);

// Uint8Array of the transaction bytes
console.log(detected.raw);
```

### Generating QR Code Images

The result from `splitQRs` can be passed to `renderQRImage` to generate (animated) PNG images of
the QR codes. The result is an `ArrayBuffer` which can easily be converted to a suitable format.

```js
import { renderQRImage } from 'bbqr';

// get an ArrayBuffer containing the PNG image data
const imgBuffer = await renderQRImage(splitResult.parts, splitResult.version, {
  // optional settings - values here are the defaults
  frameDelay: 250,
  randomizeOrder: false,
});

// convert to data URL for display
const base64String = btoa(String.fromCharCode(...new Uint8Array(imgBuffer)));
const dataUrl = `data:image/png;base64,${base64String}`;

document.body.innerHTML += `<img src="${dataUrl}">`;
```

## Developing

This library is built with [Vite](https://vitejs.dev).

- The `index.html` and `demo.ts` files are for local development.
- Start the Vite dev server: `npm run dev`.
- Start the Vitest tests in watch mode: `npm run test:watch`
- Building for production: `npm run build`
