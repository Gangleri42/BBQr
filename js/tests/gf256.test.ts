import { expect, test } from 'vitest';
import { EXP, combine, div, encodeParity, lagrangeWeights, mul, recover } from '../src/gf256';
import { shuffled } from '../src/utils';

test('GF(2^8) tables', () => {
  // 2 generates the field: every nonzero byte appears exactly once
  expect([...EXP.slice(0, 255)].sort((a, b) => a - b)).toEqual(
    Array.from({ length: 255 }, (_, i) => i + 1)
  );
  expect(EXP.slice(255, 510)).toEqual(EXP.slice(0, 255));

  for (let a = 1; a < 256; a++) {
    expect(mul(a, div(1, a))).toBe(1);
    expect(div(mul(a, 77), 77)).toBe(a);
    expect(mul(a, 0)).toBe(0);
  }

  // x^8 = x^4 + x^3 + x^2 + 1, ie. 0x11D
  expect(mul(0x80, 2)).toBe(0x1d);

  expect(() => div(1, 0)).toThrowError('divide by zero');
});

test('Lagrange weights', () => {
  // weights rebuild a known polynomial: f(x) = 7x^2 + 3x + 9
  const f = (x: number) => mul(7, mul(x, x)) ^ mul(3, x) ^ 9;
  const xs = [5, 17, 200];

  let acc = 0;
  lagrangeWeights(xs, 42).forEach((w, i) => {
    acc ^= mul(w, f(xs[i]));
  });
  expect(acc).toBe(f(42));

  // values used in the spec's worked example
  expect(lagrangeWeights([0, 1, 2], 3)).toEqual([1, 1, 1]);
  expect(lagrangeWeights([0, 1, 2], 4)).toEqual([15, 8, 6]);
});

test('Encode parity and recover', () => {
  const k = 7;
  const total = 12;
  const blockLen = 100;

  const blocks = Array.from({ length: k }, () => {
    const b = new Uint8Array(blockLen);
    crypto.getRandomValues(b);
    return b;
  });

  const all = [...blocks, ...encodeParity(blocks, total)];
  expect(all.length).toBe(total);

  // block 3 with weights (1,1,1) style check: combine with unit weights is XOR
  const xorAll = combine(blocks, Array(k).fill(1));
  for (let p = 0; p < blockLen; p++) {
    let x = 0;
    blocks.forEach((b) => (x ^= b[p]));
    expect(xorAll[p]).toBe(x);
  }

  for (let trial = 0; trial < 20; trial++) {
    // keep a random subset of k blocks
    const idx = shuffled(Array.from({ length: total }, (_, i) => i)).slice(0, k);

    const received = new Map<number, Uint8Array>();
    idx.forEach((i) => received.set(i, all[i]));

    expect(recover(received, k)).toEqual(blocks);
  }

  const tooFew = new Map<number, Uint8Array>();
  for (let i = 1; i < k; i++) {
    tooFew.set(i, all[i]);
  }
  expect(() => recover(tooFew, k)).toThrowError('need 7 blocks');
});
