#
# This file is in the public domain.
#
"""Shamir shares over BBQr, file type M, as specified in SHAMIR.md.

split_shares() compresses data when that shrinks it, seals it with its
BBQr file type and a digest, and splits the sealed bytes over GF(256)
into n share envelopes, any k of which recover it. split_qrs_shares()
carries each envelope as its own type M BBQr series. combine() recovers
(file_type, data) from a threshold of envelopes and, with spare shares
held, survives corrupt shares and names them. Standard library only.
"""
import hashlib
import hmac
import itertools
import math
import os
import zlib
from collections import namedtuple
from .split import split_qrs

# Protocol labels of SHAMIR.md section 3 and 3a; byte-exact.
HEDGE_KEY = b"seedhammer.com/shamir hedge v0"
DERIVED_KEY = b"seedhammer.com/shamir derived v1"

SHARE_TYPE = 'M'
PREFIX_LEN = 4          # tag(2) + index(1) + threshold(1)
DIGEST_LEN = 4
FLAG_DEFLATED = 0x80    # bit 7 of the sealed type byte
DEFAULT_LIMIT = 1 << 20 # cap on the recovered data size
ATTRIBUTION_CAP = 1024  # k-subsets enumerated to attribute corruption

class ShareError(ValueError):
    # A share envelope, or a set of them, that cannot be used.
    pass

class Corrupt(ShareError):
    # No combination of the held shares passes the digest. Receivers keep
    # the set and ask for another share, which lets combine() get past
    # the corrupt one and name it.
    pass

class Ambiguous(Corrupt):
    # The held shares verify under two polynomials with equally many
    # agreeing shares, so the corrupt ones cannot be told from the clean
    # ones. The remedy is the same as for Corrupt: one more clean share.
    pass

# GF(256) with the Rijndael polynomial 0x11b (SHAMIR.md section 3), as
# log and antilog tables over the generator 3.

def _gf_tables():
    exp, log = [0] * 510, [0] * 256
    x = 1
    for i in range(255):
        exp[i] = exp[i + 255] = x
        log[x] = i
        x ^= x << 1
        if x & 0x100:
            x ^= 0x11B
    return exp, log

_EXP, _LOG = _gf_tables()

def _mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]

def _div(a, b):
    # b is never 0: divisors are share indices and their differences
    if a == 0:
        return 0
    return _EXP[_LOG[a] - _LOG[b] + 255]

# Sealed content (SHAMIR.md sections 1 and 2).

def _digest(k, t, payload):
    return hashlib.sha256(bytes([k, t]) + payload).digest()[:DIGEST_LEN]

def _deflate(data):
    # raw DEFLATE inside the 1 KiB window BBQr's Z encoding fixes
    z = zlib.compressobj(wbits=-10)
    return z.compress(data) + z.flush()

def _inflate(payload, limit):
    d = zlib.decompressobj(wbits=-10)
    try:
        data = d.decompress(payload, limit + 1)
    except zlib.error as exc:
        raise ShareError(f'payload does not inflate: {exc}')
    if len(data) > limit:
        raise ShareError(f'recovered data exceeds {limit} bytes')
    if not d.eof or d.unused_data:
        raise ShareError('payload is not one complete DEFLATE stream')
    return data

# Split (SHAMIR.md section 3) under the generator profiles (section 3a).

def _prf(label, seed, length):
    # HMAC-SHA256 counter mode: prk = HMAC(label, seed), then the blocks
    # HMAC(prk, u64be(0)), HMAC(prk, u64be(1)), ... cut to length
    prk = hmac.new(label, seed, hashlib.sha256).digest()
    blocks = (hmac.new(prk, i.to_bytes(8, 'big'), hashlib.sha256).digest()
              for i in range(-(-length // 32)))
    return b''.join(blocks)[:length]

def _split_sealed(sealed, k, n, derived=False, rand=None):
    # Envelopes for x = 1..n. The profile's stream supplies the k-1
    # coefficients of every sealed byte in ascending degree, then the tag.
    # - derived: the stream is the PRF keyed by k and sealed, no hedge
    # - rand: the random source, os.urandom by default; a bytes object is
    #   consumed as the whole stream, which is how the vectors are defined
    ncoef = len(sealed) * (k - 1)
    if derived:
        if rand is not None:
            raise ValueError('the derived profile takes no random source')
        stream = _prf(DERIVED_KEY, bytes([k]) + sealed, ncoef + 2)
    else:
        if rand is None:
            rand = os.urandom
        stream = rand if isinstance(rand, bytes) else rand(ncoef + 2)
        if len(stream) != ncoef + 2:
            raise ValueError(f'random stream of {len(stream)} bytes, the split consumes {ncoef + 2}')
        # hedge the coefficients against a failed source; the tag stays raw
        hedge = _prf(HEDGE_KEY, sealed, ncoef)
        stream = bytes(r ^ h for r, h in zip(stream, hedge)) + stream[ncoef:]
    tag = stream[ncoef:]
    coefs = [stream[i * (k - 1):(i + 1) * (k - 1)] for i in range(len(sealed))]

    envelopes = []
    for x in range(1, n + 1):
        y = bytearray()
        for s, cs in zip(sealed, coefs):
            # Horner evaluation of s + c1 X + ... + c[k-1] X^(k-1) at x
            v = 0
            for c in reversed(cs):
                v = _mul(v, x) ^ c
            y.append(_mul(v, x) ^ s)
        envelopes.append(tag + bytes([x, k]) + bytes(y))
    return envelopes

def split_shares(data, file_type, k, n, derived=False, rand=None):
    # Split data of the given BBQr file type into n share envelopes, any k
    # of which recover it (SHAMIR.md, Encoding pipeline). The data is
    # compressed when that shrinks it, sealed with its type and a digest,
    # then split, so shares carry no compressible structure and show
    # neither type nor flag below the threshold.
    # - derived: the derived profile, reproducible from (k, data) with no
    #   random source; only for data whose entropy defeats guessing
    # - rand: random source for the randomized profile, os.urandom by
    #   default; a bytes object is consumed as the whole stream
    if isinstance(data, str):
        data = data.encode('utf-8')
    if len(file_type) != 1 or not 'A' <= file_type <= 'Z':
        raise ValueError(f'invalid file type {file_type!r}')
    if not data:
        raise ValueError('nothing to split')
    if not 2 <= k <= n <= 255:
        raise ValueError(f'invalid threshold {k} of {n}')

    t, payload = ord(file_type), data
    z = _deflate(data)
    if len(z) < len(data):
        t, payload = t | FLAG_DEFLATED, z
    sealed = bytes([t]) + payload + _digest(k, t, payload)
    envelopes = _split_sealed(sealed, k, n, derived, rand)

    # A generator verifies a split before committing it to its medium
    # (SHAMIR.md, Security): recover from subsets covering every share.
    for start in range(0, n, k):
        held = [envelopes[(start + i) % n] for i in range(k)]
        if combine(held, len(data)) != (file_type, data, []):
            raise ShareError('split does not recover')

    return envelopes

def split_qrs_shares(data, file_type, k, n, derived=False, rand=None, **kws):
    # As split_shares, with each envelope encoded as its own type M BBQr
    # series in base 32: shares are uniformly random, so Z could never
    # shrink them. Returns the QR version and one list of parts per share;
    # all shares have the same length, so one version serves them all.
    # - see find_best_version() for additional kw args
    series = [split_qrs(env, SHARE_TYPE, encoding='2', **kws)
              for env in split_shares(data, file_type, k, n, derived, rand)]
    return series[0][0], [parts for _, parts in series]

# Receiver (SHAMIR.md section 4 constraints, Decoding pipeline).

# One verifying combination's polynomial: the content it unseals and, by
# position among the held shares, which of them lie on it.
_Reading = namedtuple('_Reading', 'file_type data agree')

def parse_envelope(envelope):
    # Parse one share envelope, the payload of a complete type M BBQr
    # series, into (tag, index, k, y values). The envelope does not
    # self-identify: dispatch on the series file type.
    if len(envelope) < PREFIX_LEN + 1 + DIGEST_LEN + 1:
        raise ShareError('share too short')
    tag = int.from_bytes(envelope[:2], 'big')
    index, k = envelope[2], envelope[3]
    if k < 2:
        raise ShareError(f'invalid threshold {k}')
    if index < 1:
        raise ShareError('invalid share index 0')
    return tag, index, k, envelope[PREFIX_LEN:]

def _interpolate(points, x):
    # Evaluate at x, byte by byte, the polynomial through the (index, y)
    # points. Lagrange, with subtraction being XOR:
    #     w_i = prod over m != i of (x ^ x_m) / (x_i ^ x_m)
    # x = 0 is the sealed content; a held share lies off the polynomial
    # exactly when its bytes changed after the split.
    out = bytearray(len(points[0][1]))
    for xi, yi in points:
        w = 1
        for xm, _ in points:
            if xm != xi:
                w = _div(_mul(w, x ^ xm), xi ^ xm)
        if w:
            for j, b in enumerate(yi):
                out[j] ^= _mul(w, b)
    return bytes(out)

def _read(shares, k, idx, limit):
    # Combine the shares at positions idx, verify the digest and unseal
    # the content. Raises Corrupt on the digest, ShareError for content no
    # other combination cures.
    points = [shares[i] for i in idx]
    sealed = _interpolate(points, 0)
    t, payload, digest = sealed[0], sealed[1:-DIGEST_LEN], sealed[-DIGEST_LEN:]
    if digest != _digest(k, t, payload):
        raise Corrupt('digest mismatch')
    file_type = chr(t & 0x7F)
    if not 'A' <= file_type <= 'Z':
        raise ShareError(f'invalid recovered file type {file_type!r}')
    # the digest covers the compressed payload: only verified content is inflated
    data = _inflate(payload, limit) if t & FLAG_DEFLATED else payload
    agree = [i in idx or _interpolate(points, x) == y for i, (x, y) in enumerate(shares)]
    return _Reading(file_type, data, agree)

def _recovered(shares, r):
    # the reading's content with every held share off its polynomial named
    return r.file_type, r.data, sorted(x for (x, _), ok in zip(shares, r.agree) if not ok)

def _attribute(shares, k, readings, limit):
    # Enumerate the k-subsets after the first, whose reading (if it
    # verified) is in readings. A subset inside a known reading's
    # agreement set reads the same polynomial, since k points fix a
    # polynomial of degree below k, and is skipped. The reading most held
    # shares agree with wins; a tie for the most is Ambiguous.
    subsets = itertools.combinations(range(len(shares)), k)
    for idx in itertools.islice(subsets, 1, None):
        if any(all(r.agree[i] for i in idx) for r in readings):
            continue
        try:
            readings.append(_read(shares, k, idx, limit))
        except Corrupt:
            continue
    if not readings:
        raise Corrupt('no combination of the held shares verifies')
    counts = sorted((sum(r.agree) for r in readings), reverse=True)
    if len(counts) > 1 and counts[0] == counts[1]:
        raise Ambiguous('verifying combinations tie on agreement')
    return _recovered(shares, max(readings, key=lambda r: sum(r.agree)))

def _outvote(shares, k, r, limit):
    # A reading found past the enumeration cap that at most half the held
    # shares agree with may be a cancelling pair of corrupt members
    # outvoting the clean shares: read one combination of its dissenters
    # and let the larger agreement win.
    count = sum(r.agree)
    dissent = [i for i, ok in enumerate(r.agree) if not ok]
    if 2 * count > len(shares) or len(dissent) < k:
        return _recovered(shares, r)
    try:
        alt = _read(shares, k, dissent[:k], limit)
    except Corrupt:
        return _recovered(shares, r)
    if sum(alt.agree) == count:
        raise Ambiguous('verifying combinations tie on agreement')
    return _recovered(shares, alt if sum(alt.agree) > count else r)

def combine(envelopes, limit=DEFAULT_LIMIT):
    # Recover (file_type, data, corrupt) from the share envelopes of one
    # split, in any order (SHAMIR.md, Decoding pipeline). corrupt lists
    # the index of every held share whose bytes lie off the recovered
    # polynomial, ascending; [] when every held share agrees.
    #
    # The first k shares are combined and their digest verified; when
    # every other held share lies on that polynomial the set is clean.
    # Otherwise attribution is by maximal agreement: while C(held, k) is
    # at most 1024 every k-subset is combined, the verifying ones are
    # grouped by polynomial, and the polynomial most held shares agree
    # with wins. Above that, one verifying combination is read (the first
    # k, then the first k with each member swapped for each spare, then
    # disjoint windows of k) and, when at most half the held shares agree
    # with it, checked against a combination of its dissenters.
    #
    # Raises Corrupt when no combination verifies, Ambiguous on a tie,
    # and ShareError for a malformed set or for content no other
    # combination cures (over limit, bad DEFLATE stream, bad file type).
    if not envelopes:
        raise ShareError('no shares')
    tag, _, k, y = parse_envelope(envelopes[0])
    shares = []         # (index, y values), in collection order
    for env in envelopes:
        t, x, kk, yy = parse_envelope(env)
        if (t, kk, len(yy)) != (tag, k, len(y)):
            raise ShareError('shares disagree on tag, threshold or length')
        for xi, yi in shares:
            if xi == x:
                if yi != yy:
                    raise ShareError(f'conflicting copies of share {x}')
                break
        else:
            shares.append((x, yy))
    held = len(shares)
    if held < k:
        raise ShareError(f'{held} of {k} shares')

    first = tuple(range(k))
    try:
        r = _read(shares, k, first, limit)
    except Corrupt:
        r = None
    if r and all(r.agree):
        return _recovered(shares, r)
    if math.comb(held, k) <= ATTRIBUTION_CAP:
        return _attribute(shares, k, [r] if r else [], limit)
    if r:
        return _outvote(shares, k, r, limit)
    # With c corrupt shares among the first k, a single swap finds a clean
    # combination when c == 1, and one of the first c+1 windows is clean
    # whenever held >= (c+1)*k.
    swaps = (first[:j] + (spare,) + first[j + 1:]
             for j in range(k) for spare in range(k, held))
    windows = (range(start, start + k) for start in range(k, held - k + 1, k))
    for idx in itertools.chain(swaps, windows):
        try:
            r = _read(shares, k, idx, limit)
        except Corrupt:
            continue
        return _outvote(shares, k, r, limit)
    raise Corrupt('no combination of the held shares verifies')

# EOF
