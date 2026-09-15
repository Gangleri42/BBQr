/**
 * (c) Copyright 2024 by Coinkite Inc. This file is in the public domain.
 *
 * Helper/utility functions.
 */

import { base32 } from '@scure/base';
import pako from 'pako';
import { MAX_PARITY_INDEX, QR_DATA_CAPACITY } from './consts';
import type { Encoding, SplitOptions, Version } from './types';

export function hexToBytes(hex: string) {
  // convert a hex string to a Uint8Array

  const match = hex.match(/.{1,2}/g) ?? [];

  return Uint8Array.from(match.map((byte) => parseInt(byte, 16)));
}

export function base64ToBytes(base64: string) {
  // convert a base64 string to a Uint8Array

  const binaryString = atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);

  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }

  return bytes;
}

export function intToBase36(n: number) {
  // convert an integer 0-1295 to two digits of base 36 - 00-ZZ

  if (n < 0 || n > 1295 || !Number.isInteger(n)) {
    throw new Error('Out of range');
  }

  return n.toString(36).toUpperCase().padStart(2, '0');
}

export async function fileToBytes(file: File) {
  // read a File's contents and return as a Uint8Array

  const reader = new FileReader();

  return new Promise<Uint8Array>((resolve, reject) => {
    reader.onload = (e) => {
      const result = e.target?.result;

      if (result instanceof ArrayBuffer) {
        resolve(new Uint8Array(result));
      } else {
        reject(new Error('FileReader result is not an ArrayBuffer'));
      }
    };

    reader.readAsArrayBuffer(file);
  });
}

export function joinByteParts(parts: Uint8Array[]) {
  // perf-optimized way to join Uint8Arrays

  const length = parts.reduce((acc, bytes) => acc + bytes.length, 0);

  const rv = new Uint8Array(length);

  let offset = 0;
  for (const bytes of parts) {
    rv.set(bytes, offset);
    offset += bytes.length;
  }

  return rv;
}

export function isValidVersion(v: number): v is Version {
  // act as a TS type guard but also a runtime check

  return v in QR_DATA_CAPACITY;
}

export function isValidSplit(s: number) {
  return s >= 1 && s <= 1295;
}

export function validateSplitOptions(opts: SplitOptions) {
  // ensure all split options are valid, filling in defaults as needed

  const allOpts = {
    minVersion: opts.minVersion ?? 5,
    maxVersion: opts.maxVersion ?? 40,
    minSplit: opts.minSplit ?? 1,
    maxSplit: opts.maxSplit ?? 1295,
    encoding: opts.encoding ?? 'Z',
    parity: opts.parity ?? 0,
  } as const;

  if (
    allOpts.minVersion > allOpts.maxVersion ||
    !isValidVersion(allOpts.minVersion) ||
    !isValidVersion(allOpts.maxVersion)
  ) {
    throw new Error('min/max version out of range');
  }

  if (
    !isValidSplit(allOpts.minSplit) ||
    !isValidSplit(allOpts.maxSplit) ||
    allOpts.minSplit > allOpts.maxSplit
  ) {
    throw new Error('min/max split out of range');
  }

  // at least 2 data parts share the 256 indexes with the parity parts
  if (
    !Number.isInteger(allOpts.parity) ||
    allOpts.parity < 0 ||
    allOpts.parity >= MAX_PARITY_INDEX
  ) {
    throw new Error('parity out of range');
  }

  return allOpts;
}

export function looksLikePsbt(data: Uint8Array) {
  try {
    // 'psbt' + 0xff
    return new Uint8Array([0x70, 0x73, 0x62, 0x74, 0xff]).every((b, i) => b === data[i]);
  } catch (err) {
    return false;
  }
}

export function shuffled<T>(arr: T[]): T[] {
  // modern Fisher-Yates shuffle (https://en.wikipedia.org/wiki/Fisher–Yates_shuffle#The_modern_algorithm)

  // create a copy so we don't mutate the original
  arr = [...arr];

  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    const temp = arr[i];
    arr[i] = arr[j];
    arr[j] = temp;
  }

  return arr;
}

export function versionToChars(v: Version) {
  // return number of **chars** that fit into indicated version QR
  // - assumes L for ECC
  // - assumes alnum encoding

  if (!isValidVersion(v)) {
    throw new Error('Invalid version');
  }

  const ecc = 'L';
  const encoding = 2; // alnum

  return QR_DATA_CAPACITY[v][ecc][encoding];
}

export function encodeBytes(raw: Uint8Array, encoding?: Encoding) {
  // return new encoding (if we upgraded) and the bytes to be sent
  // - default is Zlib or if compression doesn't help, base32

  encoding = encoding ?? 'Z';

  if (encoding === 'Z') {
    // trial compression, but skip if it embiggens the data

    const compressed = pako.deflate(raw, { windowBits: -10 });

    if (compressed.length >= raw.length) {
      encoding = '2';
    } else {
      raw = compressed;
    }
  }

  return { encoding, raw };
}

export function bytesToText(bytes: Uint8Array, encoding: Encoding) {
  // text for the QR: capital hex, or base32 without padding

  if (encoding === 'H') {
    return bytes
      .reduce((acc, byte) => acc + byte.toString(16).padStart(2, '0'), '')
      .toUpperCase();
  }

  return base32.encode(bytes).replace(/=*$/, '');
}

export function encodeData(raw: Uint8Array, encoding?: Encoding) {
  // return new encoding (if we upgraded) and the
  // characters after encoding (a string)
  // - default is Zlib or if compression doesn't help, base32
  // - returned data can be split, but must be done modX where X provided

  const encoded = encodeBytes(raw, encoding);

  return {
    encoding: encoded.encoding,
    encoded: bytesToText(encoded.raw, encoded.encoding),
  };
}

export function textToBytes(part: string, encoding: Encoding) {
  // undo bytesToText for a single part

  if (encoding === 'H') {
    // hexToBytes itself is lenient; scanned parts are not to be trusted
    if (!/^(?:[0-9A-Fa-f]{2})*$/.test(part)) {
      throw new Error('bad hex');
    }

    return hexToBytes(part);
  }

  // base32 decode, but insert padding for API (decoder rejects bad chars and lengths)
  const padding = (8 - (part.length % 8)) % 8;

  return base32.decode(part + '='.repeat(padding));
}

export function decodeBytes(bytes: Uint8Array, encoding: Encoding) {
  // undo the compression, if any

  if (encoding === 'Z') {
    // one-shot pako.inflate() returns undefined or a prefix on bad input, so stream
    // it and insist on a complete deflate stream with nothing after it
    const inflator = new pako.Inflate({ windowBits: -10 });
    inflator.push(bytes, true);

    // @types/pako leaves these runtime fields undeclared
    const { ended, strm } = inflator as unknown as { ended: boolean; strm: { avail_in: number } };

    if (inflator.err || !ended || strm.avail_in !== 0) {
      throw new Error('bad zlib data');
    }

    return inflator.result as Uint8Array;
  }

  return bytes;
}

export function decodeData(parts: string[], encoding: Encoding) {
  // decode the parts back into a Uint8Array

  return decodeBytes(joinByteParts(parts.map((p) => textToBytes(p, encoding))), encoding);
}

export function padBlock(block: Uint8Array, size: number) {
  // pad a data block for parity math: one 0x80 then zeros, up to size bytes

  if (block.length >= size) {
    throw new Error('no room for padding');
  }

  const rv = new Uint8Array(size);
  rv.set(block);
  rv[block.length] = 0x80;

  return rv;
}

export function unpadBlock(block: Uint8Array) {
  // undo padBlock: strip zeros, then exactly one 0x80

  let end = block.length;

  while (end > 0 && block[end - 1] === 0) {
    end--;
  }

  if (end === 0 || block[end - 1] !== 0x80) {
    throw new Error('bad padding');
  }

  return block.slice(0, end - 1);
}

// EOF
