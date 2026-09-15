#!/usr/bin/env python3
#
# (c) Copyright 2026 by Coinkite Inc. This file is in the public domain.
#
# Generate ../../test_data/parity-vectors.json from the Python reference implementation.
# The Python and JS test suites both check their output against this file.
#
#   ENV/bin/python tests/gen_parity_vectors.py
#
# Zlib output can differ between zlib builds, so only H and 2 encodings are used here.
#
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from bbqr import split_qrs

OUT = os.path.join(HERE, '..', '..', 'test_data', 'parity-vectors.json')

def chain(n):
    # deterministic, incompressible bytes
    out, blk = b'', b'BBQr'
    while len(out) < n:
        blk = hashlib.sha256(blk).digest()
        out += blk
    return out[:n]

# version 11 holds 229 bytes of hex or 280 bytes of base32 per part once room
# for the parity group is reserved; some cases land exactly on those boundaries
CASES = [
    # name, data, file type, encoding, parity, opts
    ('counting-hex-p2', bytes(range(256)) * 3, 'B', 'H', 2, dict(min_version=11, max_version=11)),
    ('counting-b32-p3', bytes(range(256)) * 3, 'B', '2', 3, dict(min_version=11, max_version=11)),
    ('full-runt-hex-p2', chain(4 * 229), 'B', 'H', 2, dict(min_version=11, max_version=11)),
    ('full-runt-b32-p2', chain(3 * 280), 'B', '2', 2, dict(min_version=11, max_version=11)),
    ('one-byte-runt-b32-p2', chain(3 * 280 + 1), 'B', '2', 2, dict(min_version=11, max_version=11)),
    ('chain-1000-hex-p1', chain(1000), 'T', 'H', 1, dict(min_version=15, max_version=15)),
    ('chain-1000-b32-p2', chain(1000), 'B', '2', 2, dict(min_version=15, max_version=15)),
    ('chain-5000-hex-min-split', chain(5000), 'P', 'H', 3, dict(min_split=12)),
    ('chain-10000-b32-p5', chain(10000), 'P', '2', 5, dict(min_version=20, max_version=20)),
]

vectors = []
for name, data, file_type, encoding, parity, opts in CASES:
    ver, parts = split_qrs(data, file_type, encoding=encoding, parity=parity, **opts)
    vectors.append(dict(name=name, data_hex=data.hex(), file_type=file_type,
                        encoding=encoding, parity=parity, opts=opts,
                        version=ver, parts=parts))

with open(OUT, 'w') as f:
    json.dump(vectors, f, indent=1)
    f.write('\n')

print(f"wrote {len(vectors)} vectors to {os.path.relpath(OUT)}")
