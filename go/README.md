# BBQr in Go

Go module `github.com/Gangleri42/BBQr/go`: the BBQr protocol and the
type `M` Shamir share extension specified in [SHAMIR.md](../SHAMIR.md).

- `bbqr`: the protocol as [BBQr.md](../BBQr.md) specifies it. `Split`,
  `Join` and an accumulating `Decoder` for the Hex, Base32 and Zlib
  encodings. Hex and Base32 output is byte for byte the Python
  reference's, pinned by golden vectors generated from it; Zlib output
  differs in the DEFLATE bitstream, as any compliant stream may.
- `shamir`: file type `M`. Any data is compressed, sealed with its file
  type and a digest, split k-of-n over GF(256), and each share travels
  as its own type `M` series. `testdata/vectors.json` mirrors the
  repository's `test_data/shamir_vectors.json`.
- `internal/deflate`: a DEFLATE compressor whose back-references stay
  inside the 1 KiB window that `wbits=10` fixes. Its bitstream is part
  of the derived profile's contract (SHAMIR.md, Conformance).
- `cmd/bbqr`: encode, decode, split and combine on the command line,
  with optional PNG rendering of the parts.

The packages were written for the SeedHammer II firmware, which
depends on this module. The randomized profile gives
information-theoretic privacy below the threshold. The derived profile
trades that for reproducibility and is meant for data that cannot be
guessed, such as a wallet descriptor.

## Use

```
go get github.com/Gangleri42/BBQr/go
```

```
go run github.com/Gangleri42/BBQr/go/cmd/bbqr@latest encode -type P tx.psbt
go run github.com/Gangleri42/BBQr/go/cmd/bbqr@latest split -k 2 -n 3 -type U words.txt
go run github.com/Gangleri42/BBQr/go/cmd/bbqr@latest combine shares.txt
```

Parts are one QR content per line; share series are separated by a
blank line. `split -derived` makes shares reproducible from the data
and the threshold; use it for high-entropy data only.

## Check

```
cd go && go test ./...
```

Releases are tagged `go/vX.Y.Z`, the form Go expects for a module in
a subdirectory; `go get` names the version without the `go/` prefix.
