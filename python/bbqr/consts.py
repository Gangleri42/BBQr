#
# (c) Copyright 2023 by Coinkite Inc. This file is in the public domain.
#
#
# Constants and fixed values
#

# Standard defines a fixed-length header
HEADER_LEN = 8

# Parity parts use the indexes after the data parts, up to this one (GF(2^8) limit)
MAX_PARITY_INDEX = 255

# Symbol groups: each part must hold whole groups to decode on its own.
# One group is this many characters, and this many bytes.
ENCODING_SPLIT_MOD = {'H': 2, '2': 8, 'Z': 8}
ENCODING_BYTE_MOD = {'H': 1, '2': 5, 'Z': 5}

# Human names
FILETYPE_NAMES = dict(P='PSBT', T='Transaction', J='JSON', C='CBOR', U='Unicode Text',
                        X='Executable', B='Binary',
                        R='KT Rx', S='KT Tx', E='KT PSBT')

# Codes for PSBT vs. TXN and so on
KNOWN_FILETYPES = set(FILETYPE_NAMES.keys())

# EOF
