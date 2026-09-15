import fs from 'fs';
import path from 'path';
import QRCode from 'qrcode';
import { expect, test } from 'vitest';
import { ENCODING_SPLIT_MOD } from '../src/consts';
import { joinQRs } from '../src/join';
import { parityParts, splitQRs } from '../src/split';
import { Encoding, Version } from '../src/types';
import { decodeBytes, encodeBytes, hexToBytes, intToBase36, shuffled } from '../src/utils';

// helper to create cartesian product of arrays akin to @pytest.mark.parametrize over multiple parameters
function cartesian(...a: any[][]) {
  return a.reduce((a, b) => a.flatMap((d) => b.map((e) => [d, e].flat())));
}

function combinations<T>(arr: T[], r: number): T[][] {
  if (r === 0) return [[]];
  if (arr.length < r) return [];
  const [head, ...rest] = arr;
  return [...combinations(rest, r - 1).map((c) => [head, ...c]), ...combinations(rest, r)];
}

function randomData(size: number, lowEntropy: boolean) {
  const data = new Uint8Array(size);
  if (lowEntropy) {
    data.fill(0x41);
  } else {
    crypto.getRandomValues(data);
  }
  return data;
}

// element-wise toEqual on large Uint8Arrays is very slow in vitest
function same(a: Uint8Array, b: Uint8Array) {
  return Buffer.from(a).equals(Buffer.from(b));
}

function numData(parts: string[]) {
  return parseInt(parts[0].slice(4, 6), 36);
}

// worked example from the spec: 5 bytes as 3 data parts of 2 bytes, plus 2 parity parts
const SPEC_DATA = new Uint8Array([1, 2, 3, 4, 5]);
const SPEC_EXAMPLE = [
  'B$HB03000102',
  'B$HB03010304',
  'B$HB030205',
  'B$HB0303078600',
  'B$HB03040919A7',
];

test('Spec worked example', () => {
  const par = parityParts(SPEC_DATA, 3, 4, 2, 'H');
  expect(par.map((p, i) => `B$HB030${3 + i}` + p)).toEqual(SPEC_EXAMPLE.slice(3));

  for (const r of [3, 4, 5]) {
    for (const sub of combinations(SPEC_EXAMPLE, r)) {
      const { fileType, raw } = joinQRs(sub);
      expect(fileType).toBe('B');
      expect(raw).toEqual(SPEC_DATA);
    }
  }

  for (const sub of [
    SPEC_EXAMPLE.slice(0, 2),
    SPEC_EXAMPLE.slice(3),
    [SPEC_EXAMPLE[1], SPEC_EXAMPLE[4]],
  ]) {
    expect(() => joinQRs(sub)).toThrowError(/missing/);
  }
});

test('Bad padding', () => {
  // runt is lost, and the parity byte covering its padding is wrong
  expect(() => joinQRs([...SPEC_EXAMPLE.slice(0, 2), 'B$HB0303078601'])).toThrowError(
    'bad padding'
  );
});

test('Rebuilt part length', () => {
  // first part is lost, and a parity byte is wrong: rebuilt block unpads too short
  expect(() => joinQRs(['B$HB03010304', 'B$HB030205', 'B$HB0303010480'])).toThrowError(
    'rebuilt part 0 has wrong length'
  );
});

test('Surplus damaged parity is ignored', () => {
  for (const junk of ['B$HB03040919', 'B$HB0304ZZZZZZ']) {
    const { raw } = joinQRs([...SPEC_EXAMPLE.slice(0, 2), SPEC_EXAMPLE[3], junk]);
    expect(raw).toEqual(SPEC_DATA);
  }
});

test('Bad input', () => {
  expect(() => joinQRs([])).toThrowError('no parts');
  expect(() => joinQRs(['B$HB0100'])).toThrowError('too short');
  expect(() => joinQRs(['B$ZB0100'])).toThrowError('too short');

  // parseInt would give NaN or -1 for these
  for (const idx of ['-1', '+1', ' 1', '$$', 'a1']) {
    expect(() => joinQRs([SPEC_EXAMPLE[0], 'B$HB03' + idx + '0304', SPEC_EXAMPLE[3]])).toThrowError(
      'bad header digits'
    );
  }
  expect(() => joinQRs(['B$HB0-000102'])).toThrowError('bad header digits');

  // not hex, or half a byte
  expect(() => joinQRs([SPEC_EXAMPLE[0], SPEC_EXAMPLE[1], 'B$HB0303078G00'])).toThrowError('bad hex');
  expect(() => joinQRs([SPEC_EXAMPLE[0], SPEC_EXAMPLE[1], 'B$HB030307860'])).toThrowError('bad hex');
});

test('Bad zlib data', () => {
  const text = new TextEncoder().encode('hello world '.repeat(50));
  const { encoding, raw: z } = encodeBytes(text, 'Z');
  expect(encoding).toBe('Z');
  expect(decodeBytes(z, 'Z')).toEqual(text);

  for (const bad of [z.slice(0, -3), new Uint8Array([...z, 0]), new Uint8Array(0)]) {
    expect(() => decodeBytes(bad, 'Z')).toThrowError('bad zlib data');
  }
});

test('Single QR unchanged by parity', () => {
  // 230 bytes is 460 hex chars: exactly version 11
  const data = randomData(230, false);
  for (const encoding of ['H', '2'] as const) {
    expect(splitQRs(data, 'B', { encoding, parity: 2 })).toEqual(splitQRs(data, 'B', { encoding }));
  }
});

test('Parity index limits', () => {
  // a single-QR series cannot have parity parts
  expect(() => joinQRs(['B$HB0100AA', 'B$HB0101BB'])).toThrowError(/expecting 1/);

  // index 256 (74 in base 36) is past the field
  expect(() => joinQRs(['B$HB0200AA', 'B$HB0201BB', 'B$HB0274CC'])).toThrowError(/expecting 2/);

  // split rejects a bad parity option
  const data = randomData(100, false);
  expect(() => splitQRs(data, 'B', { parity: -1 })).toThrowError('parity out of range');
  expect(() => splitQRs(data, 'B', { parity: 255 })).toThrowError('parity out of range');
  expect(() => splitQRs(data, 'B', { parity: 1.5 })).toThrowError('parity out of range');
});

// a smaller matrix than the Python tests, to stay inside the test timeout
const LOOPBACK_CASES: [Encoding, number, number, Version, boolean][] = cartesian(
  ['H', '2', 'Z'], // encoding
  [100, 2000, 10_000, 50_000], // size
  [1, 5], // parity
  [11, 40], // maxVersion
  [true, false] // lowEntropy
);

test('Parity loopback', () => {
  const fileType = 'P';

  for (const [encoding, size, parity, maxVersion, lowEntropy] of LOOPBACK_CASES) {
    const data = randomData(size, lowEntropy);

    const { version, parts } = splitQRs(data, fileType, { encoding, parity, maxVersion });
    expect(version).toBeLessThanOrEqual(maxVersion);

    const k = numData(parts);

    if (k === 1) {
      // everything fit into one QR: nothing to protect
      expect(parts.length).toBe(1);
      expect(same(joinQRs(parts).raw, data)).toBe(true);
      continue;
    }

    expect(parts.length).toBe(k + parity);
    expect(new Set(parts.map((p) => p.slice(0, 6))).size).toBe(1);
    expect(parts.map((p) => parseInt(p.slice(6, 8), 36))).toEqual(
      Array.from({ length: k + parity }, (_, i) => i)
    );

    // parity parts are one symbol group longer than a full data part
    const splitMod = ENCODING_SPLIT_MOD[parts[0][2] as Encoding];
    expect(parts[k].length).toBe(parts[0].length + splitMod);
    expect(new Set(parts.slice(k).map((p) => p.length)).size).toBe(1);

    // all data parts: classic path
    expect(same(joinQRs(parts.slice(0, k)).raw, data)).toBe(true);

    // lose up to `parity` parts, any order
    const lose = 1 + Math.floor(Math.random() * parity);
    const keep = shuffled(parts).slice(0, parts.length - lose);
    const decoded = joinQRs(keep);
    expect(decoded.fileType).toBe(fileType);
    expect(same(decoded.raw, data)).toBe(true);

    // only parity plus the tail of the data
    expect(same(joinQRs(parts.slice(-k)).raw, data)).toBe(true);

    // one short is not enough
    expect(() => joinQRs(shuffled(parts).slice(0, k - 1))).toThrowError(/missing/);
  }
}, 30_000);

test('Maximum parity', () => {
  const data = randomData(20_000, false);
  const { parts } = splitQRs(data, 'P', { encoding: '2', parity: 200, maxVersion: 15 });
  const k = numData(parts);

  expect(parts.length).toBe(k + 200);
  expect(parts[parts.length - 1].slice(6, 8)).toBe(intToBase36(k + 199));
  expect(same(joinQRs(parts.slice(-k)).raw, data)).toBe(true);
});

test('Too many parts for parity', () => {
  expect(() =>
    splitQRs(randomData(60_000, false), 'P', { encoding: 'H', parity: 10, maxVersion: 11 })
  ).toThrowError('too many parts');
});

test.each(['H', '2'] as const)('Parity parts fit the QR version, encoding %s', (encoding) => {
  const needVersion = 12;
  const data = randomData(4000, false);

  const { version, parts } = splitQRs(data, 'P', {
    encoding,
    parity: 2,
    minVersion: needVersion,
    maxVersion: needVersion,
  });
  expect(version).toBe(needVersion);

  const k = numData(parts);

  for (const p of [parts[0], parts[k - 1], parts[k], parts[parts.length - 1]]) {
    QRCode.create([{ data: p, mode: 'alphanumeric' }], {
      version,
      errorCorrectionLevel: 'L',
    });
  }
});

type Vector = {
  name: string;
  data_hex: string;
  file_type: string;
  encoding: Encoding;
  parity: number;
  opts: { min_version?: Version; max_version?: Version; min_split?: number; max_split?: number };
  version: number;
  parts: string[];
};

test('Cross-language vectors', async () => {
  const vectors: Vector[] = JSON.parse(
    await fs.promises.readFile(path.join(__dirname, '../../test_data/parity-vectors.json'), 'utf-8')
  );
  expect(vectors.length).toBeGreaterThan(0);

  for (const v of vectors) {
    const data = hexToBytes(v.data_hex);

    const { version, parts } = splitQRs(data, v.file_type, {
      encoding: v.encoding,
      parity: v.parity,
      minVersion: v.opts.min_version,
      maxVersion: v.opts.max_version,
      minSplit: v.opts.min_split,
      maxSplit: v.opts.max_split,
    });

    expect(version, v.name).toBe(v.version);
    expect(parts, v.name).toEqual(v.parts);

    const k = numData(parts);

    for (let i = 0; i < 20; i++) {
      const decoded = joinQRs(shuffled(parts).slice(0, k));
      expect(decoded.fileType, v.name).toBe(v.file_type);
      expect(same(decoded.raw, data), v.name).toBe(true);
    }
  }
});
