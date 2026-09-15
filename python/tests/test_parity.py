#
# (c) Copyright 2026 by Coinkite Inc. This file is in the public domain.
#
# - parity parts: any N of the series recover the data
#
from context import bbqr
from bbqr import gf256
from bbqr.split import parity_parts
from bbqr.utils import int2base36, encode_bytes, decode_bytes
from bbqr.consts import ENCODING_SPLIT_MOD
import pytest, os, sys, json, random, itertools, subprocess, pyqrcode

def test_gf256_tables():
    # 2 generates the field: every nonzero byte appears exactly once
    assert sorted(gf256.EXP[:255]) == list(range(1, 256))
    assert gf256.EXP[255:510] == gf256.EXP[:255]

    for a in range(1, 256):
        assert gf256.mul(a, gf256.div(1, a)) == 1
        assert gf256.div(gf256.mul(a, 77), 77) == a
        assert gf256.mul(a, 0) == 0

    # x^8 = x^4 + x^3 + x^2 + 1, ie. 0x11D
    assert gf256.mul(0x80, 2) == 0x1D

def test_lagrange():
    # weights rebuild a known polynomial: f(x) = 7x^2 + 3x + 9
    f = lambda x: gf256.mul(7, gf256.mul(x, x)) ^ gf256.mul(3, x) ^ 9
    xs = [5, 17, 200]
    acc = 0
    for w, x in zip(gf256.lagrange_weights(xs, 42), xs):
        acc ^= gf256.mul(w, f(x))
    assert acc == f(42)

    # values used in the spec's worked example
    assert gf256.lagrange_weights([0, 1, 2], 3) == [1, 1, 1]
    assert gf256.lagrange_weights([0, 1, 2], 4) == [15, 8, 6]

# worked example from the spec: 5 bytes as 3 data parts of 2 bytes, plus 2 parity parts
SPEC_DATA = bytes([1, 2, 3, 4, 5])
SPEC_EXAMPLE = ['B$HB03000102', 'B$HB03010304', 'B$HB030205',
                'B$HB0303078600', 'B$HB03040919A7']

def test_spec_example():
    par = parity_parts(SPEC_DATA, 3, 4, 2, 'H')
    assert ['B$HB030%d' % (3+i) + p for i, p in enumerate(par)] == SPEC_EXAMPLE[3:]

    for r in (3, 4, 5):
        for sub in itertools.combinations(SPEC_EXAMPLE, r):
            assert bbqr.join_qrs(list(sub)) == ('B', SPEC_DATA)

    for sub in (SPEC_EXAMPLE[:2], SPEC_EXAMPLE[3:], SPEC_EXAMPLE[1:2] + SPEC_EXAMPLE[4:]):
        with pytest.raises(ValueError, match='parts missing'):
            bbqr.join_qrs(sub)

def test_join_error_type():
    # JoinError is both, so code catching either keeps working
    for exc in (AssertionError, ValueError, bbqr.JoinError):
        with pytest.raises(exc, match='parts missing'):
            bbqr.join_qrs(SPEC_EXAMPLE[:2])

def test_optimized_mode():
    # the checks survive python -O, where assert statements vanish
    code = '\n'.join([
        "from context import bbqr",
        "for bad in (['B$HB03010304', 'B$HB0303078600'], ['B$HB03000102', 'B$HB03010304', 'B$HB0303078601']):",
        "    try:",
        "        bbqr.join_qrs(bad)",
        "    except bbqr.JoinError:",
        "        continue",
        "    raise SystemExit('accepted %r' % (bad,))",
        "print('ok')",
    ])
    out = subprocess.run([sys.executable, '-O', '-c', code], cwd=os.path.dirname(os.path.abspath(__file__)),
                            capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.strip() == 'ok', out.stderr

def test_bad_padding():
    # runt is lost, and the parity byte covering its padding is wrong
    with pytest.raises(ValueError, match='bad padding'):
        bbqr.join_qrs(SPEC_EXAMPLE[:2] + ['B$HB0303078601'])

def test_rebuilt_length():
    # first part is lost, and a parity byte is wrong: rebuilt block unpads too short
    with pytest.raises(ValueError, match='rebuilt part 0 has wrong length'):
        bbqr.join_qrs(['B$HB03010304', 'B$HB030205', 'B$HB0303010480'])

def test_surplus_parity_ignored():
    # a damaged parity part we don't need must not block the join
    assert bbqr.join_qrs(SPEC_EXAMPLE[:2] + [SPEC_EXAMPLE[3], 'B$HB03040919']) == ('B', SPEC_DATA)
    assert bbqr.join_qrs(SPEC_EXAMPLE[:2] + [SPEC_EXAMPLE[3], 'B$HB0304ZZZZZZ']) == ('B', SPEC_DATA)

def test_bad_input():
    with pytest.raises(ValueError, match='no parts'):
        bbqr.join_qrs([])
    with pytest.raises(ValueError, match='too short'):
        bbqr.join_qrs(['B$HB0100'])
    # int('-1', 36) would be -1; '$' is legal in a QR but not a digit
    for idx in ('-1', '+1', ' 1', '$$', 'a1'):
        with pytest.raises(ValueError, match='bad header digits'):
            bbqr.join_qrs([SPEC_EXAMPLE[0], 'B$HB03' + idx + '0304', SPEC_EXAMPLE[3]])
    with pytest.raises(ValueError, match='bad header digits'):
        bbqr.join_qrs(['B$HB0-000102'])
    with pytest.raises(ValueError):
        bbqr.join_qrs([SPEC_EXAMPLE[0], SPEC_EXAMPLE[1], 'B$HB0303078G00'])    # not hex

def test_bad_zlib():
    enc, z = encode_bytes(b'hello world ' * 50, 'Z')
    assert enc == 'Z'
    assert decode_bytes(z, 'Z') == b'hello world ' * 50
    for bad in (z[:-3], z + b'\x00', b''):
        with pytest.raises(ValueError, match='bad zlib'):
            decode_bytes(bad, 'Z')

def test_single_qr_unchanged():
    # when everything fits one QR, asking for parity changes nothing
    data = os.urandom(230)          # 460 hex chars: exactly version 11
    for enc in 'H2':
        assert bbqr.split_qrs(data, 'B', encoding=enc, parity=2) == bbqr.split_qrs(data, 'B', encoding=enc)

def test_parity_option():
    for bad in (1.5, '2', True, -1, 255):
        with pytest.raises(AssertionError, match='invalid parity'):
            bbqr.split_qrs(os.urandom(100), 'B', parity=bad)

def test_parity_index_limits():
    # a single-QR series cannot have parity parts
    with pytest.raises(ValueError, match='expecting 1'):
        bbqr.join_qrs(['B$HB0100AA', 'B$HB0101BB'])

    # index 256 (74 in base 36) is past the field
    with pytest.raises(ValueError, match='expecting 2'):
        bbqr.join_qrs(['B$HB0200AA', 'B$HB0201BB', 'B$HB0274CC'])

@pytest.mark.parametrize('encoding', [None]+list('H2Z'))
@pytest.mark.parametrize('size', [100, 2000, 10_000, 50_000])
@pytest.mark.parametrize('parity', [1, 2, 5])
@pytest.mark.parametrize('max_version', [11, 29, 40])
@pytest.mark.parametrize('low_ent', [True, False])
def test_loopback(encoding, size, parity, max_version, low_ent, filetype='P'):
    data = b'A'*size if low_ent else os.urandom(size)

    vers, parts = bbqr.split_qrs(data, filetype, encoding=encoding, parity=parity,
                                    max_version=max_version)
    assert vers <= max_version

    k = int(parts[0][4:6], 36)
    if k == 1:
        # everything fit into one QR: nothing to protect
        assert len(parts) == 1
        assert bbqr.join_qrs(parts) == (filetype, data)
        return

    assert len(parts) == k + parity
    assert set(p[:6] for p in parts) == {parts[0][:6]}
    assert [int(p[6:8], 36) for p in parts] == list(range(k + parity))

    # parity parts are one symbol group longer than a full data part
    split_mod = ENCODING_SPLIT_MOD[parts[0][2]]
    assert len(parts[k]) == len(parts[0]) + split_mod
    assert len(set(len(p) for p in parts[k:])) == 1

    # all data parts: classic path
    assert bbqr.join_qrs(parts[:k]) == (filetype, data)

    # lose up to `parity` parts, any order
    keep = random.sample(parts, len(parts) - random.randint(1, parity))
    assert bbqr.join_qrs(keep) == (filetype, data)

    # only parity plus the tail of the data
    assert bbqr.join_qrs(parts[-k:]) == (filetype, data)

    # one short is not enough
    with pytest.raises(ValueError, match='parts missing'):
        bbqr.join_qrs(random.sample(parts, k - 1))

def test_max_parity():
    data = os.urandom(20_000)
    vers, parts = bbqr.split_qrs(data, 'P', encoding='2', parity=200, max_version=15)
    k = int(parts[0][4:6], 36)
    assert len(parts) == k + 200
    assert parts[-1][6:8] == int2base36(k + 199)
    assert bbqr.join_qrs(parts[-k:]) == ('P', data)

def test_too_many_parts():
    with pytest.raises(AssertionError, match='too many parts'):
        bbqr.split_qrs(os.urandom(60_000), 'P', encoding='H', parity=10, max_version=11)

@pytest.mark.parametrize('encoding', 'H2')
def test_parity_fits_qr(encoding, version=12):
    # parity parts must fit the same QR version as the data parts
    data = os.urandom(4000)
    vers, parts = bbqr.split_qrs(data, 'P', encoding=encoding, parity=2,
                                    min_version=version, max_version=version)
    assert vers == version
    k = int(parts[0][4:6], 36)
    for p in (parts[0], parts[k-1], parts[k], parts[-1]):
        pyqrcode.create(p, error='L', version=vers, mode='alphanumeric')

def test_vectors():
    vectors = json.load(open('../test_data/parity-vectors.json'))
    assert vectors

    for v in vectors:
        data = bytes.fromhex(v['data_hex'])
        vers, parts = bbqr.split_qrs(data, v['file_type'], encoding=v['encoding'],
                                        parity=v['parity'], **v['opts'])
        assert vers == v['version'], v['name']
        assert parts == v['parts'], v['name']

        k = int(parts[0][4:6], 36)
        for _ in range(20):
            keep = random.sample(parts, k)
            assert bbqr.join_qrs(keep) == (v['file_type'], data), v['name']

# EOF
