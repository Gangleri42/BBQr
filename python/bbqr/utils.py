#
# (c) Copyright 2023 by Coinkite Inc. This file is in the public domain.
#
# - helpers and basics
#
import zlib
from base64 import b32encode, b32decode
from .consts import ENCODING_SPLIT_MOD

class JoinError(ValueError, AssertionError):
    # Something is wrong with the scanned parts. A ValueError that is also an
    # AssertionError, so code written against the assert-based decoder keeps
    # catching it, and one that survives "python -O", where assert does not.
    pass

def version_to_chars(v):
    # return number of **chars** that fit into indicated version QR
    # - assumes L for ECC
    # - assumes alnum encoding
    import pyqrcode

    assert 1 <= v <= 40
    ecc = "L"
    encoding = 2        # alnum

    return pyqrcode.tables.data_capacity[v][ecc][encoding]

def int2base36(n):
    # convert an integer to two digits of base 36 string. 00 thu ZZ
    # converse is just int(s, base=36)
    assert 0 <= n <= 1295

    tostr = lambda x: chr(48+x) if x < 10 else chr(65+x-10)

    a, b = divmod(n, 36)

    return tostr(a) + tostr(b)

def encode_bytes(raw, encoding=None):
    # return new encoding (if we upgraded) and the bytes to be sent
    # - default is Zlib or if compression doesn't help, base32

    if encoding == 'H':
        return encoding, raw

    if not encoding or encoding == 'Z':
        # Trial compression, but skip if it embiggens the data
        z = zlib.compressobj(wbits=-10)
        cmp = z.compress(raw)
        cmp += z.flush()
        if len(cmp) >= len(raw):
            encoding = '2'
        else:
            encoding = 'Z'
            raw = cmp

    return encoding, raw

def bytes_to_text(b, encoding):
    # text for the QR: capital hex, or base32 with no padding bytes
    if encoding == 'H':
        return b.hex().upper()

    return b32encode(b).decode('ascii').rstrip('=')

def encode_data(raw, encoding=None):
    # return new encoding (if we upgraded) and the
    # characters after encoding (a string)
    # - default is Zlib or if compression doesn't help, base32
    # - returned data can be split, but must be done modX where X provided

    encoding, raw = encode_bytes(raw, encoding)

    return encoding, bytes_to_text(raw, encoding), ENCODING_SPLIT_MOD[encoding]

def text_to_bytes(part, encoding):
    # undo bytes_to_text for a single part
    if encoding == 'H':
        return bytes.fromhex(part)

    # base32 decode, but insert padding for API
    padding = (8 - (len(part) % 8)) % 8
    return b32decode(part + (padding*'='))

def decode_bytes(raw, encoding):
    # undo the compression, if any
    if encoding == 'Z':
        z = zlib.decompressobj(wbits=-10)
        rv = z.decompress(raw)
        rv += z.flush()
        if not z.eof or z.unused_data:
            raise JoinError('bad zlib data')
        return rv

    return raw

def pad_block(block, size):
    # pad a data block for parity math: one 0x80 then zeros, up to size bytes
    assert len(block) < size, 'no room for padding'
    return block + b'\x80' + bytes(size - len(block) - 1)

def unpad_block(block):
    # undo pad_block: strip zeros, then exactly one 0x80
    block = block.rstrip(b'\x00')
    if block[-1:] != b'\x80':
        raise JoinError('bad padding')
    return block[:-1]

def decode_data(parts, encoding):
    # give back the bytes after decoding
    # - already in order
    # - keeps the parts separate here to validate correct split from encoder
    return decode_bytes(b''.join(text_to_bytes(p, encoding) for p in parts), encoding)

# EOF
