# BBQr in Go, with the type M Shamir extension

Go module `github.com/Gangleri42/BBQr/go`, a sibling of the Python
reference in this repository.

- `bbqr`: the protocol as BBQr.md specifies it. `Split`, `Join` and an
  accumulating `Decoder` for the Hex, Base32 and Zlib encodings. Hex
  and Base32 output is byte for byte the Python reference's, pinned by
  golden vectors generated from it; Zlib output differs in the DEFLATE
  bitstream, as any compliant stream may.
- `shamir`: the proposed file type `M`. Any data is compressed, sealed
  with its file type and a digest, split k-of-n over GF(256), and each
  share travels as its own type `M` series. `SPEC.md` is the format,
  `testdata/vectors.json` the vectors, `testdata/check_vectors.py` an
  independent standard-library Python implementation that checks them.
- `internal/deflate`: a DEFLATE compressor whose back-references stay
  inside the 1 KiB window that `wbits=10` fixes. Its bitstream is part
  of the derived profile's contract (SPEC.md, Conformance).
- `cmd/bbqr`: encode, decode, split and combine on the command line,
  with optional PNG rendering of the parts.

The packages come from the SeedHammer II firmware, which depends on
this module for its descriptor plate splits; the history under `go/`
is theirs. The randomized profile gives information-theoretic privacy
below the threshold. The derived profile trades that for
reproducibility and is meant for data that cannot be guessed, such as
a wallet descriptor.

## Use

```
go get github.com/Gangleri42/BBQr/go@v0.1.0
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
python3 go/shamir/testdata/check_vectors.py
```

Releases are tagged `go/vX.Y.Z`, the form Go expects for a module in
a subdirectory; `go get` names the version without the `go/` prefix.
