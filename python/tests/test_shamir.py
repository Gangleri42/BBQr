#
# This file is in the public domain.
#

from context import bbqr
from bbqr import shamir
from bbqr.shamir import split_shares, split_qrs_shares, combine, parse_envelope
from bbqr.shamir import ShareError, Corrupt, Ambiguous
import pytest, os, json, random, itertools

with open('../test_data/shamir_vectors.json') as f:
    VECTORS = json.load(f)['vectors']
NAMES = [v['name'] for v in VECTORS]

DATA = b'correct horse battery staple'

def sealed_of(v):
    # The generator class starts from the recorded sealed payload: DEFLATE
    # output is not unique, so the module's compressor is checked by the
    # receiver round trip alone.
    t = bytes.fromhex(v['type_byte'])
    payload = bytes.fromhex(v['payload_hex'])
    return t + payload + shamir._digest(v['k'], t[0], payload)

@pytest.mark.parametrize('v', VECTORS, ids=NAMES)
def test_generator(v):
    # randomized: the recorded stream through the module's own hedge;
    # derived: from (k, sealed) alone
    if v['profile'] == 'derived':
        assert 'rand_hex' not in v
        envelopes = shamir._split_sealed(sealed_of(v), v['k'], v['n'], derived=True)
    else:
        envelopes = shamir._split_sealed(sealed_of(v), v['k'], v['n'],
                                         rand=bytes.fromhex(v['rand_hex']))

    assert [e.hex() for e in envelopes] == [s['envelope_hex'] for s in v['shares']]

    for env, share in zip(envelopes, v['shares']):
        vers, parts = bbqr.split_qrs(env, 'M', encoding='2')
        assert parts == share['parts']

@pytest.mark.parametrize('v', VECTORS, ids=NAMES)
def test_receiver(v):
    # every k-subset, shares and parts in shuffled order, through join_qrs;
    # one share fewer is rejected as incomplete, never combined
    data, k, n = bytes.fromhex(v['data_hex']), v['k'], v['n']
    rng = random.Random(v['name'])

    for subset in itertools.combinations(range(n), k):
        order = list(subset)
        rng.shuffle(order)
        envelopes = []
        for i in order:
            parts = list(v['shares'][i]['parts'])
            rng.shuffle(parts)
            file_type, env = bbqr.join_qrs(parts)
            assert file_type == 'M'
            envelopes.append(env)

        assert combine(envelopes) == (v['file_type'], data, [])

        with pytest.raises(ShareError) as exc:
            combine(envelopes[:-1])
        assert type(exc.value) is ShareError

@pytest.mark.parametrize('v', VECTORS, ids=NAMES)
def test_digest(v):
    # a receiver that skipped the digest would pass every vector above
    envelopes = [bytes.fromhex(s['envelope_hex']) for s in v['shares'][:v['k']]]
    bad = bytearray(envelopes[0])
    bad[-1] ^= 0xFF

    with pytest.raises(Corrupt):
        combine([bytes(bad)] + envelopes[1:])

def test_parse_envelope():
    v = VECTORS[0]
    env = bytes.fromhex(v['shares'][1]['envelope_hex'])

    tag, index, k, y = parse_envelope(env)
    assert (index, k) == (2, v['k'])
    assert env == tag.to_bytes(2, 'big') + bytes([index, k]) + y

    for bad in (env[:9], env[:3] + b'\x01' + env[4:], env[:2] + b'\x00' + env[3:]):
        with pytest.raises(ShareError):
            parse_envelope(bad)

@pytest.mark.parametrize('low_ent', [True, False])
def test_loopback(low_ent):
    # the randomized profile with its default source, through QR series
    data = b'A' * 500 if low_ent else os.urandom(500)

    vers, shares = split_qrs_shares(data, 'B', 2, 3)
    assert len(shares) == 3
    for parts in shares:
        assert all(p[:4] == 'B$2M' for p in parts)

    envelopes = [bbqr.join_qrs(parts)[1] for parts in shares]
    assert combine(envelopes[1:]) == ('B', data, [])

def test_generator_refuses(monkeypatch):
    # the derived profile has no randomness to take; a split whose shares
    # do not recover the data never reaches the medium
    with pytest.raises(ValueError, match='no random source'):
        split_shares(DATA, 'U', 2, 3, derived=True, rand=os.urandom)

    monkeypatch.setattr(shamir, 'combine', lambda *args: ('U', b'', []))
    with pytest.raises(ShareError, match='split does not recover'):
        split_shares(DATA, 'U', 2, 3)

def corrupt(envelopes, bad):
    # Flip one byte of the 1-based shares in bad, at a different position
    # per share: identical errors on two shares cancel in any combination
    # that weighs them equally, the ambiguity test_tie pins.
    out = [bytearray(e) for e in envelopes]
    for j, x in enumerate(bad):
        out[x - 1][-1 - j] ^= 0xFF
    return [bytes(e) for e in out]

def test_corrupt_spare_named():
    # a corrupt share is named wherever it sits, member or spare
    envelopes = split_shares(DATA, 'U', 3, 5, derived=True)
    for bad in ([4], [1, 4]):
        assert combine(corrupt(envelopes, bad)) == ('U', DATA, bad)

    # the threshold alone with one share corrupt: never a wrong secret
    with pytest.raises(Corrupt):
        combine(corrupt(envelopes[:3], [2]))

def test_above_enumeration_cap():
    # C(13, 6) = 1716 exceeds the cap: one verifying combination is read,
    # by a member swap for one corrupt member and by the second window
    # for two, and the agreement of the other shares stands
    envelopes = split_shares(DATA, 'U', 6, 13, derived=True)
    assert combine(corrupt(envelopes, [1])) == ('U', DATA, [1])
    assert combine(corrupt(envelopes, [1, 2])) == ('U', DATA, [1, 2])

def lambda0(xs, i):
    # Lagrange weight of xs[i] at x=0 over the points xs
    w = 1
    for m, xm in enumerate(xs):
        if m != i:
            w = shamir._div(shamir._mul(w, xm), xs[i] ^ xm)
    return w

def cancelling_pair(envelopes, k):
    # Corrupt shares 1 and 2 in one payload byte with errors that cancel
    # in the combination of the first k shares (w1*e1 ^ w2*e2 == 0 at
    # x=0), so that combination verifies with a wrong polynomial.
    xs = list(range(1, k + 1))
    e1 = 0x5A
    e2 = shamir._div(shamir._mul(lambda0(xs, 0), e1), lambda0(xs, 1))
    out = [bytearray(e) for e in envelopes]
    out[0][4 + 3] ^= e1
    out[1][4 + 3] ^= e2
    return [bytes(e) for e in out]

def test_cancelling_pair_outvoted():
    for k, n in ((2, 5), (3, 6)):
        pair = cancelling_pair(split_shares(DATA, 'U', k, n, derived=True), k)

        # the first k alone verify: the wrong polynomial reads the right data
        assert combine(pair[:k]) == ('U', DATA, [])

        # with every share held the clean shares outnumber its k members
        assert combine(pair) == ('U', DATA, [1, 2])

def test_tie():
    pair = cancelling_pair(split_shares(DATA, 'U', 3, 6, derived=True), 3)

    # one clean spare cannot outvote the wrong polynomial's three members:
    # the data is right, since the errors cancel at x=0, and the spare is
    # the share named
    assert combine(pair[:4]) == ('U', DATA, [4])

    # two clean spares tie it, {1, 2, 3} against {3, 4, 5}: no data
    assert issubclass(Ambiguous, Corrupt)
    with pytest.raises(Ambiguous):
        combine(pair[:5])

    # one more clean share breaks the tie
    assert combine(pair) == ('U', DATA, [1, 2])

    # identical errors on shares 1 and 4 of a 3-of-5: {1, 4, 5} weighs its
    # members equally (1 ^ 4 == 5) and the two errors cancel there
    envelopes = [bytearray(e) for e in split_shares(DATA, 'U', 3, 5, derived=True)]
    envelopes[0][-1] ^= 0xFF
    envelopes[3][-1] ^= 0xFF
    with pytest.raises(Ambiguous):
        combine([bytes(e) for e in envelopes])

# EOF
