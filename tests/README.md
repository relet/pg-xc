# Test Suite for parse.py

This directory contains regression tests to ensure that refactoring `parse.py` doesn't accidentally change the output.

## Quick Start

```bash
# 1. Create baseline from current output (run this ONCE before starting refactoring)
python3 tests/test_parse_regression.py --update-baseline

# 2. Make changes to parse.py

# 3. Run tests to verify output hasn't changed
python3 tests/test_parse_regression.py

# 4. Repeat steps 2-3 as you refactor
```

## How It Works

The test suite:
1. Runs `parse.py` to generate fresh output
2. Compares all output files against the baseline
3. Reports any differences with detailed analysis

### Files Compared

- `luftrom.geojson` - Main airspace file (detailed feature-by-feature comparison)
- `luftrom.fl.txt` - Flight level format
- `luftrom.ft.txt` - Feet format  
- `luftrom.m.txt` - Meters format
- `luftrom.openaip` - OpenAIP XML format
- `accsectors.geojson` - ACC sectors
- `xcontest.json` - XContest format

### Comparison Strategy

**For GeoJSON files:**
- Feature count
- Feature names (missing/new features)
- Coordinate counts per feature
- Key properties (class, ceiling, floor)

**For other files:**
- SHA256 hash (fast check)
- Line-by-line diff if hashes differ

## Usage

### Create/Update Baseline

Run this when you're satisfied with the current output and want to lock it in as the reference:

```bash
python3 tests/test_parse_regression.py --update-baseline
```

### Run Tests

```bash
# Basic run
python3 tests/test_parse_regression.py

# Verbose output (shows parse.py stdout)
python3 tests/test_parse_regression.py -v

# Exit on first difference (useful in CI)
python3 tests/test_parse_regression.py -x
```

### Custom Baseline Directory

```bash
python3 tests/test_parse_regression.py --baseline-dir=tests/my_baseline
```

## Workflow Example

```bash
# Start: Lock in current behavior
$ python3 tests/test_parse_regression.py --update-baseline
INFO: Running parse.py...
INFO: parse.py completed successfully
INFO: Updated baseline: luftrom.geojson
INFO: Updated baseline: luftrom.fl.txt
...

# Make some changes to parse.py (e.g., extract a function, rename variables)

# Run tests
$ python3 tests/test_parse_regression.py
INFO: Running parse.py...
INFO: parse.py completed successfully
INFO: Comparing files against baseline...
INFO: ✓ luftrom.geojson: PASS (identical)
INFO: ✓ luftrom.fl.txt: PASS (identical)
...
======================================================================
TEST SUMMARY
======================================================================
Total files: 7
Passed: 7
Failed: 0
Skipped: 0
======================================================================
```

## When Tests Fail

If tests fail, the output will show what changed:

```
ERROR: ✗ luftrom.geojson: Files differ, analyzing...
ERROR:   Missing features (2): oslo-tma-1, bergen-ctr
       New features (1): oslo-tma-west
       flesland-tma-2: coordinate count differs (64 vs 32)
       tromso-ctr: to (m amsl) differs (1500 vs 1524)
```

### Investigate Changes

1. Check if the changes are **intentional** (e.g., you fixed a bug in geometry generation)
2. If intentional: Update the baseline with `--update-baseline`
3. If unintentional: Fix your refactoring to preserve the original behavior

## Integration with Development

### Add to .gitignore

The baseline files are committed to git so everyone uses the same reference:

```bash
# DON'T ignore tests/baseline/ - commit it!
```

### Pre-commit Hook (Optional)

```bash
#!/bin/bash
# .git/hooks/pre-commit
python3 tests/test_parse_regression.py -x
```

## Notes

- The baseline captures the **current behavior**, not necessarily the correct behavior
- If `parse.py` has bugs, the baseline will include them
- Use this test suite to refactor safely, then fix bugs separately and update baseline
- Test runtime is dominated by `parse.py` execution (~2-5 minutes typically)
