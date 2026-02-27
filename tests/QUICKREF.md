# Quick Reference: Refactoring parse.py

## Setup (Once)
```bash
./tests/setup_tests.sh           # Automatic setup
# OR manually:
make run-parse && make test-update
```

## Refactoring Loop
```bash
# Edit parse.py
vim import/parse.py

# Test
make test                        # Quick: just "make test"

# If failed and change is intentional:
make test-update                 # Update baseline
```

## Commands

| Command | Purpose |
|---------|---------|
| `make test` | Run regression tests |
| `make test-update` | Update baseline |
| `make test-verbose` | Show parse.py output |
| `make run-parse` | Just run parse.py |
| `make compare` | Compare with geojson/luftrom.geojson |
| `make clean` | Remove generated files |

## Test Output

✓ **PASS**: Output identical to baseline  
⚠️ **Files differ**: Analyzing differences...  
❌ **FAIL**: Features changed (see details)

## Common Scenarios

### Scenario 1: Pure Refactoring
```bash
# Goal: Extract function, no behavior change
vim import/parse.py       # Extract gen_circle() into separate function
make test                 # Should PASS (output identical)
```

### Scenario 2: Bug Fix
```bash
# Goal: Fix coordinate parsing bug
vim import/parse.py       # Fix regex in re_coord
make test                 # Will FAIL (output changed - this is good!)
# Review changes, ensure they're correct
make test-update          # Lock in the fixed behavior
```

### Scenario 3: Accidental Breakage
```bash
vim import/parse.py       # Refactor coordinate conversion
make test                 # FAIL: "Missing features (3): ..."
# Oops! Revert or fix the bug
```

## Tips

- Run `make test` after every meaningful change
- Small changes = easier debugging when tests fail
- Commit after tests pass: `git commit -m "Refactor: extract circle generation"`
- Update baseline only when changes are **intentional**
- If unsure about failure, check `import/result/` vs `tests/baseline/`

## Troubleshooting

**"No baseline for X - skipping"**  
→ Run `make test-update` first

**"parse.py failed"**  
→ Fix syntax/import errors in parse.py first

**"Files differ" but output looks the same**  
→ Might be floating point precision or ordering - check with `diff`

**Tests are slow**  
→ Normal - parse.py takes 2-5 minutes. Consider caching in future.

## More Info

- Full docs: `tests/README.md`
- Test internals: `tests/test_parse_regression.py`
- Make targets: `make help`
