#
# (c) Copyright 2023 by Coinkite Inc. This file is in the public domain.
#
# - uses pyqrcode for deep QR knowledge
# - text prefix on each QR:
#
#       B$                  fixed header for this protocol (2 chars)
#       2                   one char encode: Z=zlib, 2=Base32, H=Hex
#       P                   one char file type: P=PSBT, T=TXN, etc
#       05                  2-digits of base 36: number of data QR codes (all are needed)
#       00                  2-digits of base 36: which QR code this is in the sequence
#
# - optional parity QR codes use indexes 05 and up; any 5 of the series recover the data
#
from math import ceil
from .utils import version_to_chars, encode_bytes, bytes_to_text, pad_block, int2base36
from .consts import HEADER_LEN, KNOWN_FILETYPES, MAX_PARITY_INDEX
from .consts import ENCODING_BYTE_MOD, ENCODING_SPLIT_MOD
from . import gf256

def num_qr_needed(ver, ll, split_mod, reserve=0):
    # Determine number of QR's at indicated version would be
    # needed to hold ll characters. when 2 or more QR, consider
    # the exact split point cannot be between encoded symbols
    # - ok to return huge numbers for unlikely cases
    # - reserve: chars to leave free in each QR (parity parts are one group longer)
    cap = version_to_chars(ver) - HEADER_LEN - reserve
    cap2 = cap - (cap % split_mod)

    need = ceil(ll / cap2)

    if need == 1:
        # no alignment concerns
        assert ll <= cap
        return 1, ll

    # going to be 2 or more, gotta be precise
    actual = ((need - 1) * cap2) + cap

    return (need if actual >= ll else (need + 1)), cap2

def find_best_version(ll, split_mod, min_split=1, max_split=1295, min_version=5, max_version=40, reserve=0):
    # Find ideal QR version and provide # of QR and splits needed.
    # - assumes you want to pack the QR, so forcing min_split means you need to have the data
    #   at least the data to fill that # of QR at min_version
    #
    # ll = length of encoded data to be transmitted (no headers)
    # split_mod = required size of non-runt parts so that can be decoded w/o spliting symbols

    min_version = min(min_version, max_version)     # in case they spec a very low max

    assert 1 <= min_version <= max_version <= 40, "min/max version out of range"
    assert 1 <= min_split <= max_split <= 1295, "num splits out of range"

    options = []
    for ver in range(min_version, max_version+1):
        count, pe = num_qr_needed(ver, ll, split_mod, reserve)
        if not (min_split <= count <= max_split): continue
        options.append( (ver, count, pe) )

    # pick smallest number of QR, lowest version
    options.sort(key=lambda v: (v[1], v[0]))

    if not options:
        raise ValueError("Cannot make it fit")

    return options[0]

def parity_parts(stream, num_qr, per_each, parity, encoding):
    # Build `parity` extra parts (text, without headers) for a series of num_qr data parts.
    # - any num_qr parts out of the whole series recover the data
    # - each data block is padded with 0x80 then zeros to one symbol group more than a
    #   full block, so a rebuilt block always shows where its data ends
    # - Reed-Solomon over GF(2^8): block i is the value at x=i, see gf256.py
    assert num_qr >= 2, 'parity needs 2 or more data parts'
    assert num_qr + parity <= MAX_PARITY_INDEX + 1, 'too many parts for parity'

    mod = ENCODING_BYTE_MOD[encoding]
    split_mod = ENCODING_SPLIT_MOD[encoding]
    b_data = (per_each // split_mod) * mod            # bytes in a full data part
    b_rs = b_data + mod

    blocks = [pad_block(stream[off:off+b_data], b_rs) for off in range(0, len(stream), b_data)]
    assert len(blocks) == num_qr

    return [bytes_to_text(p, encoding) for p in gf256.encode_parity(blocks, num_qr + parity)]

def split_qrs(raw, type_code, encoding=None, parity=0, **kws):
    # Take some bytes and yield a series of text values that 
    # can be sent as QR code.
    # - returns text
    # - assumes and requires alnum, L error level
    # - parity: number of extra QR codes to add; any N of the whole series recover the data
    #   (no effect when everything fits into a single QR)
    # - kws: min_split, max_split, min_version, max_version (see find_best_version)

    assert type_code in KNOWN_FILETYPES, f"invalid type_code: {type_code}"
    if encoding: assert encoding in 'H2Z', f"invalid encoding: {encoding}"
    if not isinstance(raw, bytes):
        assert isinstance(raw, str), "need binary or text"
        raw = raw.encode('utf-8')
    assert isinstance(parity, int) and not isinstance(parity, bool) \
            and 0 <= parity < MAX_PARITY_INDEX, f"invalid parity: {parity!r}"

    # perhaps compress data
    encoding, stream = encode_bytes(raw, encoding)
    encoded = bytes_to_text(stream, encoding)
    split_mod = ENCODING_SPLIT_MOD[encoding]

    ll = len(encoded)

    ver, num_qr, per_each = find_best_version(ll, split_mod, **kws)

    if parity and num_qr >= 2:
        # parity parts are one symbol group longer than data parts; leave room for
        # that, now that we know the data needs more than one QR anyway
        ver, num_qr, per_each = find_best_version(ll, split_mod, reserve=split_mod, **kws)
    else:
        # a single QR has nothing to lose
        parity = 0

    assert per_each * num_qr >= ll

    hdr = f'B${encoding}{type_code}' + int2base36(num_qr)

    parts = [hdr + int2base36(n) + encoded[off:off+per_each] for
                            (n, off) in enumerate(range(0, ll, per_each))]

    if parity:
        parts += [hdr + int2base36(num_qr + n) + p for n, p in
                    enumerate(parity_parts(stream, num_qr, per_each, parity, encoding))]

    return ver, parts

# EOF
