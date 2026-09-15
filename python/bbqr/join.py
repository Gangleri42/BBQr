#
# (c) Copyright 2023 by Coinkite Inc. This file is in the public domain.
#
# - joins QR codes
# - scanned data is untrusted, so problems raise JoinError: a ValueError that is
#   also an AssertionError, and that stays live under "python -O" (assert does not)
#
from .utils import decode_data, decode_bytes, text_to_bytes, pad_block, unpad_block, JoinError
from .consts import HEADER_LEN, MAX_PARITY_INDEX, ENCODING_BYTE_MOD
from . import gf256

BASE36_DIGITS = frozenset('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ')

def check(ok, msg):
    if not ok:
        raise JoinError(msg)

def parse_base36(s):
    # two capital base 36 digits: int() alone would also take '-1' or ' 1'
    check(len(s) == 2 and set(s) <= BASE36_DIGITS, f'bad header digits: {s!r}')
    return int(s, 36)

def recover_missing(data, parity, num_parts, encoding):
    # Rebuild the data parts we didn't see from parity parts.
    # - data: {idx: text} for idx < num_parts, parity: {idx: text} for the rest
    # - returns bytes of all num_parts data parts, in order
    mod = ENCODING_BYTE_MOD[encoding]
    missing = [i for i in range(num_parts) if i not in data]

    # only the lowest parity indexes are needed; the rest are ignored, damaged or not
    needed = sorted(parity)[:len(missing)]
    check(len(needed) == len(missing), f'parts missing: {missing!r}')

    pblocks = {i: text_to_bytes(parity[i], encoding) for i in needed}
    b_rs = len(pblocks[needed[0]])
    check(all(len(b) == b_rs for b in pblocks.values()), 'parity parts have differing lengths')

    b_data = b_rs - mod
    check(b_data >= 1, 'parity parts too short')

    def right_length(i, b):
        # all data parts are full, except the last one which may be shorter
        return len(b) == b_data if i < num_parts - 1 else 1 <= len(b) <= b_data

    dblocks = {i: text_to_bytes(p, encoding) for i, p in data.items()}
    for i, b in dblocks.items():
        check(right_length(i, b), f'part {i} has wrong length')

    points = {i: pad_block(b, b_rs) for i, b in dblocks.items()}
    points.update(pblocks)

    rebuilt = gf256.recover(points, num_parts)

    rv = []
    for i in range(num_parts):
        if i in dblocks:
            rv.append(dblocks[i])
        else:
            b = unpad_block(rebuilt[i])
            check(right_length(i, b), f'rebuilt part {i} has wrong length')
            rv.append(b)

    return rv

def join_qrs(parts):
    # take a bunch of scanned data. 
    # - put into order, decode, return type code and raw data bytes
    # - lazy desktop code here
    check(parts, 'no parts')
    check(all(len(p) > HEADER_LEN for p in parts), 'part is too short')

    hdr = set(p[0:6] for p in parts)
    check(len(hdr) == 1, 'conflicting/variable filetype/encodings/sizes')
    hdr = hdr.pop()

    check(hdr[0:2] == 'B$', 'fixed header not found, expected B$')
    encoding = hdr[2]
    file_type = hdr[3]
    check(encoding in 'H2Z', f'bad encoding: {encoding}')

    num_parts = parse_base36(hdr[4:6])
    check(num_parts >= 1, 'zero parts?')

    # ok to have dups here, just need them all (or enough parity parts)
    data = {}
    parity = {}
    for p in parts:
        idx = parse_base36(p[6:8])
        if idx < num_parts:
            dest = data
        else:
            # parity part: only possible for series of 2 or more, indexes up to 255
            check(num_parts >= 2 and idx <= MAX_PARITY_INDEX,
                            f'got part {idx} but only expecting {num_parts}')
            dest = parity

        if idx in dest:
            check(dest[idx] == p[8:], f'dup part 0x{idx:02x} has wrong content')
        else:
            dest[idx] = p[8:]

    if len(data) == num_parts:
        raw = decode_data([data[i] for i in range(num_parts)], encoding)
    else:
        blocks = recover_missing(data, parity, num_parts, encoding)
        raw = decode_bytes(b''.join(blocks), encoding)

    # maybe: decode objects here... U=>text, C=>obj, J=>obj

    return file_type, raw

# EOF
