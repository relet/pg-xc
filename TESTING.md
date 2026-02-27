# Testing Guide for pg-xc

This repository now includes a comprehensive regression test suite for safely refactoring `import/parse.py`.

## Quick Start

```bash
# One-time setup
./tests/setup_tests.sh

# Refactoring workflow
vim import/parse.py    # Make changes
make test             # Verify output unchanged
```

## What Was Added

### Test Suite Components

| File | Purpose |
|------|---------|
| `tests/test_parse_regression.py` | Main test runner (353 lines) |
| `tests/setup_tests.sh` | One-time setup script |
| `tests/README.md` | Full documentation |
| `tests/QUICKREF.md` | Quick reference card |
| `tests/EXAMPLE.md` | Complete walkthrough |
| `tests/SUMMARY.md` | High-level overview |
| `tests/baseline/` | Reference output files |

### Helper Commands (Makefile)

```bash
make test              # Run regression tests
make test-update       # Update baseline
make run-parse         # Just run parse.py
make compare           # Compare with previous version
make clean             # Remove generated files
make help              # Show all commands
```

## How It Works

The test suite ensures refactoring doesn't break parse.py by:

1. **Running parse.py** to generate fresh output
2. **Comparing 7 output files** against a known-good baseline:
   - `luftrom.geojson` - Main airspace (feature-level comparison)
   - `luftrom.fl.txt`, `luftrom.ft.txt`, `luftrom.m.txt` - Text formats
   - `luftrom.openaip` - OpenAIP XML
   - `accsectors.geojson` - ACC sectors
   - `xcontest.json` - XContest format
3. **Reporting differences** with detailed diagnostics

### For GeoJSON Files

Detailed comparison checks:
- Feature count
- Feature names (detects missing/new)
- Coordinate counts
- Properties (class, ceiling, floor)

### For Other Files

- Fast SHA256 hash comparison
- Line-by-line diff if hashes differ

## Typical Workflow

### Before Starting Refactoring

```bash
# Ensure you have good output
cd import && python3 parse.py

# Lock it in as baseline
make test-update
```

### While Refactoring

```bash
# Make a change
vim import/parse.py

# Test it
make test

# If pass: commit
# If fail: investigate and fix OR update baseline if intentional
```

### Example Session

```bash
$ make test
INFO: Running parse.py...
INFO: parse.py completed successfully
INFO: ✓ luftrom.geojson: PASS (identical)
INFO: ✓ luftrom.fl.txt: PASS (identical)
...
======================================================================
Total files: 7
Passed: 7
Failed: 0
======================================================================

$ git commit -m "Refactor: Extract coordinate parsing"
```

## When Tests Fail

### Unintended Change (Regression)
```
ERROR: ✗ luftrom.geojson: Files differ
ERROR:   Missing features (2): oslo-tma-1, bergen-ctr
```
**Action:** Fix your code to restore original behavior

### Intended Change (Bug Fix)
```
ERROR: ✗ luftrom.geojson: Files differ
ERROR:   flesland-tma: coordinate count differs (64 vs 96)
```
**Action:** Verify the fix is correct, then `make test-update`

## Benefits

1. ✅ **Refactor Confidently** - Immediate feedback on regressions
2. ✅ **Fast Iteration** - 2-5 minute test cycle
3. ✅ **Detailed Diagnostics** - See exactly what changed
4. ✅ **Version Controlled** - Baseline in git ensures consistency
5. ✅ **Simple** - Just `make test` after every change

## Files Modified

- `.github/copilot-instructions.md` - Added testing section
- `.gitignore` - Documented test file handling
- `Makefile` - Added test commands

## Documentation

- **Quick Start**: `tests/QUICKREF.md`
- **Full Guide**: `tests/README.md`
- **Example Walkthrough**: `tests/EXAMPLE.md`
- **Implementation Details**: `tests/SUMMARY.md`

## Command Reference

| Goal | Command |
|------|---------|
| Set up tests | `./tests/setup_tests.sh` |
| Run tests | `make test` |
| Update baseline | `make test-update` |
| Verbose output | `make test-verbose` |
| Run parser only | `make run-parse` |
| Compare versions | `make compare` |
| Clean output | `make clean` |
| Show all commands | `make help` |

## Notes

- Baseline represents **current behavior**, not necessarily correct behavior
- Tests are **deterministic** - same input = same output
- No mock data needed - uses real AIP sources
- Tests run in ~2-5 minutes (limited by parse.py runtime)

## Next Steps

1. Run `./tests/setup_tests.sh` to create baseline
2. Start refactoring `import/parse.py`
3. Run `make test` after each change
4. Read `tests/README.md` for details

---

**Happy refactoring! The tests have your back.** 🎯
