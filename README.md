
# BBQr - Better Bitcoin QR

Encodes larger files into a series of QR codes so they can cross air gaps.

Project Status: **Deployed Widely**

Quick links:

- [Project Home on Github](https://github.com/coinkite/BBQr)
- [Web Demo: Browser-based JavaScript BBQr tool](https://bbqr.org/js-demo) - encode PSBTs and other data into the BBQr format.
- [BBQr Rust implementation](https://github.com/satoshiportal/bbqr-rust)
- [Dart language bindings for BBQr-rust](https://github.com/SatoshiPortal/bbqr-dart)
- [iOS/MacOS and Android bindings for BBQr library using uniFFI](https://github.com/bitcoinppl/bbqr-ffi)
- [Swift implementation](https://github.com/bitcoinppl/bbqr-swift)
- [Kotlin implementation](https://github.com/gorunjinian/bbqr-kotlin)
- [Go implementation](https://github.com/dmonakhov/bbqr-go)

# Specification

See full spec [BBQr.md](BBQr.md).

This fork adds file type `M`, Shamir shares of a k-of-n split, specified in [SHAMIR.md](SHAMIR.md). Reference implementations: the Go module in [`go/`](go/) (package `shamir`) and [`python/bbqr/shamir.py`](python/bbqr/shamir.py); cross-implementation test vectors are in [`test_data/shamir_vectors.json`](test_data/shamir_vectors.json).

# Summary

This protocol enables files larger than can fit into a single QR
to be sent as a series of QR codes (sometimes called an "animated
QR"). The target file types are PSBT (BIP-174) and signed Bitcoin
transactions, but it also supports CBOR, JSON and Text options for
general purpose use.

We carefully consider the data inside QR codes, and apply a
deep knowledge of how QR codes work, so that no pixel nor byte
is ever wasted! Internally it supports HEX and Base32 serializations
and a constrained ZLIB option for data compression. This is all
done with an eye to embedded implementations on very contrained
devices (ie. hardware wallets), which may not have enough memory
to keep more than a single QR code around.

Here are some compression numbers, using the ZLIB encoding option.
Even though Bitcoin files have relatively high entropy (with hashes
and UTXO's being non-compressable) we still see 30% typical size
reduction.

File (see testing/data) | Before | After | Compression Ratio
------------------------|--------|-------|------------------
1in1000out.psbt         |  35644 | 22095 |  38.0%
1in100out.psbt          |   4142 | 2654  |  35.9%
1in10out.psbt           |    992 | 670   |  32.5%
1in20out.psbt           |   1342 | 897   |  33.2%
1in2out.psbt            |    675 | 458   |  32.1%
devils-txn.txn          |    666 | 356   |  46.5%
finalized-by-ckcc.txn   |   1932 | 807   |  58.2%
signed.txn              | 100757 | 77090 |  23.5%

By using Base32 character encoding inside a QR code with the unique
"alphanumeric" encoding (where each character takes 5.5 bits of
space, and encodes 5 bits of binary), we can acheive the smallest
possible QR codes.

The largest possible (uncompressed) data payload in 3,470,600 bytes
spread across in 1,295 version 40 QR codes.

# Example Image

![Example of BBQr Image](example.png)

The above BBQr encodes the entire specification itself (so meta). 

```
% bbqr make BBQr.md -v 21 -o example.png --scale 3
Detected file type: U -> Unicode Text
Need 8 QR's each of version 20.
Building QR images... done!
Created 'example.png' with 8 frames.
```

# Supporting Projects

Verified against released public code on July 27, 2026. **Display** means the
project can produce BBQr; **Scan** means it can decode BBQr. Products that share
a library or inherit an implementation are still listed as products, not
counted as independent protocol implementations.

| Name               | Display | Scan | Notes | Link |
|--------------------|:-------:|:----:|-------|------|
| COLDCARD Q         | Y | Y | Hardware signer | [COLDCARD Q](https://coldcard.com/q) |
| Sparrow Wallet     | Y | Y | Desktop wallet | [Sparrow Wallet](https://sparrowwallet.com) |
| Nunchuk Desktop    | Y | Y | Desktop wallet | [Nunchuk Wallet](https://nunchuk.app) |
| BTCPay Server      | Y | Y | Payment server and wallet coordinator | [BTCPay Server](https://btcpayserver.org) |
| Krux               | Y | Y | Hardware signer firmware | [Krux Firmware](https://github.com/krux-wallet) |
| Fully Noded        | Y | Y | iOS wallet | [Fully Noded](https://fullynoded.app) |
| Cove Wallet        | Y | Y | iOS wallet | [Cove Wallet](https://github.com/bitcoinppl/cove) |
| BULL Wallet        | Y | Y | Mobile wallet | [BULL Wallet](https://bullbitcoin.com/blog/bull-by-bull-bitcoin) |
| Bitcoin Safe       | Y | Y | Desktop wallet | [Bitcoin Safe](https://bitcoin-safe.org/en/features/readme/#comprehensive-feature-list) |
| BlueWallet         | Y | Y | Mobile wallet | [BlueWallet](https://github.com/BlueWallet/BlueWallet) |
| Birch Wallet       | Y | Y | iOS wallet; uses the shared Swift library | [Birch Wallet](https://github.com/Birch-Wallet/birch-wallet) |
| Cypher Box         | Y | Y | Mobile wallet derived from BlueWallet | [Cypher Box](https://github.com/CypherBoxLLC/Cypher-Box) |
| MetroVault         | Y | Y | Android signing wallet; uses the Kotlin implementation | [MetroVault](https://github.com/gorunjinian/MetroVault) |
| Ashigaru Desktop   | Y | Y | Desktop wallet derived from Sparrow | [Ashigaru Desktop](https://github.com/linkinparkrulz/ashigaru-desktop) |
| SeedSigner         | N | Y | Hardware signer; decode-only support in version 0.8.7 | [SeedSigner](https://github.com/SeedSigner/seedsigner) |
| Signing Room       | Y | Y | PSBT coordinator; not a wallet | [Signing Room](https://github.com/scarlin90/signingroom) |

LabelBase and Trident/AnchorWatch have previously reported BBQr support, but a
released public implementation was not available for this verification pass.

# Code Examples

- Splitting QRs: [Python](python/bbqr/split.py), [JS](js/src/split.ts)
- Joining QRs: [Python](python/bbqr/join.py), [JS](js/src/join.ts)
- Binary to internal encoding: [Python](python/bbqr/utils.py), [JS](js/src/utils.ts)
- Wrapper CLI: [Python](python/bbqr/cli.py)
- [Example of using the JS implementation](https://bbqr.org/js-demo)

# License

Public Domain code by [Coinkite](https://coinkite.com)


## Useful Pipelines

These will load your clipboard with example data suitable for the COLDCARD Q Simulator.

See also [`psbt_faker`](https://github.com/Coldcard/psbt_faker)

```
% psbt_faker - | bbqr make - -t P | pbcopy
A single QR version 18 will be needed.

% bbqr make - --fake-data 2048000 -t P | pbcopy
A single QR version 35 will be needed.

% psbt_faker -n 200 - | bbqr make - -t P -r | pbcopy
Need 5 QR's each of version 37.
```

These are round-trip examples, where encode and decode are performed.

```
% psbt_faker -n 10 - | bbqr make - -t P -r | bbqr decode
A single QR version 25 will be needed.
PSBT File:
cHNidP....

```

Dumping BBQr to console:
```
# needs a very low version or cinema screen
bbqr make UNLICENSE.md -o stdout -v 5
```

## Signing Transaction with COLDCARD Q

1) Using **COLDCARD Q** choose `Scan Any QR Code` from main menu and scan this Seed QR
   to temporarily import a new seed:

![simulator_seed_qr](sim_sqr.png)

```patch
- This seed is the COLDCARD simulator key and is well known!
- DO NOT send any funds to this seed.
```

2) Confirm import of temporary seed and if **Seed Vault** is enabled you may save it there
   (not required).
    
3) Navigate to `Scan Any QR Code` again, and scan either of these transactions. You'll
   be shown the details, and if accepted, the signed result will be shown as BBQr.

### PSBT: Basic 1 input 2 outputs

![tx-1in2out](small.png)

### PSBT: 10 in, 2 out with Locktimes

![tx-10in2out-locktimes](locktimes.png)

## Multisig

1) Navigate to `Scan Any QR Code` and import below 15of15 multisig.

![multisig-15of15](15of15.png)

2) Sign below multisig PSBT

![change_psbt_multisig-15of15](change_psbt_15of15.png)

3) Above should fail because of exotic sighash (NONE). Navigate to
   `Advanced/Tools -> Danger Zone -> Sighash Checks` and choose to `Warn` only.
   After this you must be able to sign and COLDCARD presents you with a warning.

```patch
Only tweak `Sighash Check` setting if you know what you're doing. This
is very dangerous and not needed for normal operation. Please, enable checks
to `Default: Block` after this exercise.
```

## Miniscript and MiniTapscript

```patch
requires EDGE firmware 6.3.3QX or later
```

1) Import CSA threshold Tapscript multisig with static provably unspendable internal key:

![tapscript_threshold](minisc.png)

2) Sign PSBT:

![tapscript_threshold_psbt](minisc_psbt.png)

1) import MiniTapScript with ranged probably unspendable internal key:

![minitapscript](minitapscript.png)

2) Sign PSBT

![minitapscript_psbt](minitapscript_psbt.png)
