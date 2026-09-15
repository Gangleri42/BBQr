#
# (c) Copyright 2026 by Coinkite Inc. This file is in the public domain.
#
# - GF(2^8) arithmetic and a systematic Reed-Solomon erasure code
# - field uses reduction polynomial 0x11D (the one QR codes use), generator 2
# - for each byte position, block i holds the value at x=i of a polynomial
#   of degree < K. Any K blocks with distinct indices determine the polynomial.
#

EXP = [0] * 512
LOG = [0] * 256

def _build_tables():
    x = 1
    for i in range(255):
        EXP[i] = x
        LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        EXP[i] = EXP[i - 255]

_build_tables()

def mul(a, b):
    if a == 0 or b == 0:
        return 0
    return EXP[LOG[a] + LOG[b]]

def div(a, b):
    assert b != 0, 'divide by zero'
    if a == 0:
        return 0
    return EXP[LOG[a] - LOG[b] + 255]

def lagrange_basis(xs):
    # For the points xs, return a function m -> weights w_i such that
    # f(m) = XOR of w_i * f(x_i) for any f of degree < len(xs).
    # - the parts that don't depend on m are computed once here
    inv_den = []
    for i, xi in enumerate(xs):
        den = 1
        for j, xj in enumerate(xs):
            if j != i:
                den = mul(den, xi ^ xj)
        inv_den.append(div(1, den))

    def weights(m):
        full = 1
        for xj in xs:
            full = mul(full, m ^ xj)

        if full == 0:
            # m is one of the points
            return [1 if xi == m else 0 for xi in xs]

        return [mul(div(full, m ^ xi), inv_den[i]) for i, xi in enumerate(xs)]

    return weights

def lagrange_weights(xs, m):
    return lagrange_basis(xs)(m)

# whole-block multiply by a constant: one 256-byte translation table per constant
_MUL_TABLES = {}

def mul_block(block, c):
    if c == 1:
        return block
    if c == 0:
        return bytes(len(block))
    table = _MUL_TABLES.get(c)
    if table is None:
        table = _MUL_TABLES[c] = bytes(mul(c, b) for b in range(256))
    return block.translate(table)

def combine(blocks, weights):
    # XOR of weight_i * block_i; all blocks the same length
    n = len(blocks[0])
    if any(len(b) != n for b in blocks):
        raise ValueError('blocks have differing lengths')

    acc = 0
    for blk, w in zip(blocks, weights):
        if w:
            acc ^= int.from_bytes(mul_block(blk, w), 'big')
    return acc.to_bytes(n, 'big')

def encode_parity(data_blocks, total):
    # given K equal-length data blocks (indices 0..K-1), return blocks K..total-1
    k = len(data_blocks)
    weights = lagrange_basis(list(range(k)))
    return [combine(data_blocks, weights(m)) for m in range(k, total)]

def recover(received, k):
    # received: {index: block} with at least k distinct indices
    # returns the k data blocks, in order
    if len(received) < k:
        raise ValueError(f'need {k} blocks, have {len(received)}')

    missing = [i for i in range(k) if i not in received]
    if not missing:
        return [received[i] for i in range(k)]

    # data blocks first (their indices are the smallest), then lowest parity indices
    xs = sorted(received)[:k]
    ys = [received[x] for x in xs]

    weights = lagrange_basis(xs)

    out = {x: received[x] for x in xs if x < k}
    for m in missing:
        out[m] = combine(ys, weights(m))

    return [out[i] for i in range(k)]

# EOF
