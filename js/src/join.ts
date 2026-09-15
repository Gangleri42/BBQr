/**
 * (c) Copyright 2024 by Coinkite Inc. This file is in the public domain.
 *
 * QR code decoding/joining.
 */

import { ENCODINGS, ENCODING_BYTE_MOD, HEADER_LEN, MAX_PARITY_INDEX } from './consts';
import { recover } from './gf256';
import { Encoding, JoinResult } from './types';
import {
  decodeBytes,
  decodeData,
  joinByteParts,
  padBlock,
  textToBytes,
  unpadBlock,
} from './utils';

function parseBase36(s: string) {
  // two capital base 36 digits: parseInt alone would also take '-1' or ' 1' (or give NaN)
  if (!/^[0-9A-Z]{2}$/.test(s)) {
    throw new Error(`bad header digits: ${JSON.stringify(s)}`);
  }

  return parseInt(s, 36);
}

function recoverMissing(
  data: Map<number, string>,
  parity: Map<number, string>,
  numParts: number,
  encoding: Encoding
) {
  // Rebuild the data parts we didn't see from parity parts.
  // - data: idx -> text for idx < numParts, parity: idx -> text for the rest
  // - returns bytes of all numParts data parts, in order

  const mod = ENCODING_BYTE_MOD[encoding];

  const missing: number[] = [];

  for (let i = 0; i < numParts; i++) {
    if (!data.has(i)) {
      missing.push(i);
    }
  }

  // only the lowest parity indexes are needed; the rest are ignored, damaged or not
  const needed = [...parity.keys()].sort((a, b) => a - b).slice(0, missing.length);

  if (needed.length < missing.length) {
    throw new Error(`parts missing: ${missing.join(', ')}`);
  }

  const pblocks = new Map<number, Uint8Array>();

  for (const i of needed) {
    pblocks.set(i, textToBytes(parity.get(i)!, encoding));
  }

  const lengths = new Set([...pblocks.values()].map((b) => b.length));

  if (lengths.size !== 1) {
    throw new Error('parity parts have differing lengths');
  }

  const [bRs] = lengths;
  const bData = bRs - mod;

  if (bData < 1) {
    throw new Error('parity parts too short');
  }

  // all data parts are full, except the last one which may be shorter
  const rightLength = (i: number, b: Uint8Array) =>
    i < numParts - 1 ? b.length === bData : b.length >= 1 && b.length <= bData;

  const dblocks = new Map<number, Uint8Array>();

  for (const [i, p] of data) {
    const b = textToBytes(p, encoding);

    if (!rightLength(i, b)) {
      throw new Error(`part ${i} has wrong length`);
    }

    dblocks.set(i, b);
  }

  const points = new Map<number, Uint8Array>();

  for (const [i, b] of dblocks) {
    points.set(i, padBlock(b, bRs));
  }

  for (const [i, b] of pblocks) {
    points.set(i, b);
  }

  const rebuilt = recover(points, numParts);

  return rebuilt.map((b, i) => {
    const have = dblocks.get(i);

    if (have) {
      return have;
    }

    const block = unpadBlock(b);

    if (!rightLength(i, block)) {
      throw new Error(`rebuilt part ${i} has wrong length`);
    }

    return block;
  });
}

/**
 * Decodes and joins QR code parts back to binary data.
 *
 * Series with parity parts (indexes at or past the part count) need only as many
 * distinct parts as the count says; the rest may be missing.
 *
 * Scanned data is untrusted: anything malformed throws.
 *
 * @param parts Array of QR code parts
 * @returns Object containing the file type, encoding, and raw binary data.
 */
export function joinQRs(parts: string[]): JoinResult {
  if (!parts.length) {
    throw new Error('no parts');
  }

  if (parts.some((p) => p.length <= HEADER_LEN)) {
    throw new Error('part is too short');
  }

  const headers = new Set(parts.map((p) => p.slice(0, 6)));

  if (headers.size !== 1) {
    throw new Error('conflicting/variable filetype/encodings/sizes');
  }

  const header = [...headers][0];

  if (header.slice(0, 2) !== 'B$') {
    throw new Error('fixed header not found, expected B$');
  }

  if (!ENCODINGS.has(header[2])) {
    throw new Error(`bad encoding: ${header[2]}`);
  }

  const encoding = header[2] as Encoding;
  const fileType = header[3];

  if (!/^[A-Z]$/.test(fileType)) {
    throw new Error('fileType must be a single uppercase letter');
  }

  const numParts = parseBase36(header.slice(4, 6));

  if (numParts < 1) {
    throw new Error('zero parts?');
  }

  const data = new Map<number, string>();
  const parity = new Map<number, string>();

  for (const p of parts) {
    const idx = parseBase36(p.slice(6, 8));

    let dest = data;

    if (idx >= numParts) {
      // parity part: only possible for series of 2 or more, indexes up to 255
      if (numParts < 2 || idx > MAX_PARITY_INDEX) {
        throw new Error(`got part ${idx} but only expecting ${numParts}`);
      }

      dest = parity;
    }

    if (dest.has(idx) && dest.get(idx) !== p.slice(8)) {
      throw new Error(`Duplicate part 0x${idx.toString(16)} has wrong content`);
    }

    dest.set(idx, p.slice(8));
  }

  let raw: Uint8Array;

  if (data.size === numParts) {
    raw = decodeData(
      Array.from({ length: numParts }, (_, i) => data.get(i)!),
      encoding
    );
  } else {
    raw = decodeBytes(joinByteParts(recoverMissing(data, parity, numParts, encoding)), encoding);
  }

  return { fileType, encoding, raw };
}

// EOF
