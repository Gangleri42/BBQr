/**
 * (c) Copyright 2026 by Coinkite Inc. This file is in the public domain.
 *
 * GF(2^8) arithmetic and a systematic Reed-Solomon erasure code.
 *
 * - field uses reduction polynomial 0x11D (the one QR codes use), generator 2
 * - for each byte position, block i holds the value at x=i of a polynomial
 *   of degree < K. Any K blocks with distinct indices determine the polynomial.
 */

export const EXP = new Uint8Array(512);
export const LOG = new Uint8Array(256);

(function buildTables() {
  let x = 1;

  for (let i = 0; i < 255; i++) {
    EXP[i] = x;
    LOG[x] = i;
    x <<= 1;
    if (x & 0x100) {
      x ^= 0x11d;
    }
  }

  for (let i = 255; i < 512; i++) {
    EXP[i] = EXP[i - 255];
  }
})();

export function mul(a: number, b: number) {
  if (a === 0 || b === 0) {
    return 0;
  }

  return EXP[LOG[a] + LOG[b]];
}

export function div(a: number, b: number) {
  if (b === 0) {
    throw new Error('divide by zero');
  }

  if (a === 0) {
    return 0;
  }

  return EXP[LOG[a] - LOG[b] + 255];
}

export function lagrangeBasis(xs: number[]) {
  // For the points xs, return a function m -> weights w_i such that
  // f(m) = XOR of w_i * f(x_i) for any f of degree < xs.length.
  // - the parts that don't depend on m are computed once here

  const invDen = xs.map((xi, i) => {
    let den = 1;

    xs.forEach((xj, j) => {
      if (j !== i) {
        den = mul(den, xi ^ xj);
      }
    });

    return div(1, den);
  });

  return (m: number) => {
    let full = 1;

    for (const xj of xs) {
      full = mul(full, m ^ xj);
    }

    if (full === 0) {
      // m is one of the points
      return xs.map((xi) => (xi === m ? 1 : 0));
    }

    return xs.map((xi, i) => mul(div(full, m ^ xi), invDen[i]));
  };
}

export function lagrangeWeights(xs: number[], m: number) {
  return lagrangeBasis(xs)(m);
}

export function combine(blocks: Uint8Array[], weights: number[]) {
  // XOR of weight_i * block_i; all blocks the same length

  const n = blocks[0].length;

  if (blocks.some((b) => b.length !== n)) {
    throw new Error('blocks have differing lengths');
  }

  const rv = new Uint8Array(n);

  blocks.forEach((blk, i) => {
    const w = weights[i];

    if (w === 0) {
      return;
    }

    const logW = LOG[w];

    for (let p = 0; p < n; p++) {
      const b = blk[p];

      if (b !== 0) {
        rv[p] ^= EXP[logW + LOG[b]];
      }
    }
  });

  return rv;
}

export function encodeParity(dataBlocks: Uint8Array[], total: number) {
  // given K equal-length data blocks (indices 0..K-1), return blocks K..total-1

  const k = dataBlocks.length;
  const weights = lagrangeBasis(Array.from({ length: k }, (_, i) => i));
  const rv: Uint8Array[] = [];

  for (let m = k; m < total; m++) {
    rv.push(combine(dataBlocks, weights(m)));
  }

  return rv;
}

function mustGet(blocks: Map<number, Uint8Array>, idx: number) {
  const b = blocks.get(idx);

  if (!b) {
    throw new Error(`missing block ${idx}`);
  }

  return b;
}

export function recover(received: Map<number, Uint8Array>, k: number) {
  // received: index -> block, with at least k distinct indices
  // returns the k data blocks, in order

  if (received.size < k) {
    throw new Error(`need ${k} blocks, have ${received.size}`);
  }

  const missing: number[] = [];

  for (let i = 0; i < k; i++) {
    if (!received.has(i)) {
      missing.push(i);
    }
  }

  if (!missing.length) {
    return Array.from({ length: k }, (_, i) => mustGet(received, i));
  }

  // data blocks first (their indices are the smallest), then lowest parity indices
  const xs = [...received.keys()].sort((a, b) => a - b).slice(0, k);
  const ys = xs.map((x) => mustGet(received, x));

  const weights = lagrangeBasis(xs);
  const out = new Map<number, Uint8Array>();

  for (const x of xs) {
    if (x < k) {
      out.set(x, mustGet(received, x));
    }
  }

  for (const m of missing) {
    out.set(m, combine(ys, weights(m)));
  }

  return Array.from({ length: k }, (_, i) => mustGet(out, i));
}

// EOF
