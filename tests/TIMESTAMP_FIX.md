# Fix Applied: xcontest.json Timestamp Handling

## Problem

The `xcontest.json` file includes timestamps that change on every run:

```python
# In import/targets/xcontest.py, line 214:
now = str(datetime.datetime.utcnow().isoformat())
fc = {'airspaces': airspaces,
      'oadescription': 'Automated export from luftrom.info - '+ now,
      'oaname': 'Norway airspace - '+now}
```

This caused the test suite to report failures even when nothing changed:
- Run 1: `Norway airspace - 2026-02-27T13:05:30.123456`
- Run 2: `Norway airspace - 2026-02-27T13:08:15.987654`
- Result: Tests fail due to different timestamps

## Solution

Updated `test_parse_regression.py` to normalize timestamps before comparison:

1. Added `normalize_timestamps()` method that replaces ISO timestamps with placeholder
2. Added `compare_json_files()` method for JSON-specific comparison
3. Updated `compare_files()` to use JSON comparison for `xcontest.json`

Now the test:
- Loads both JSON files
- Replaces all ISO timestamps (YYYY-MM-DDTHH:MM:SS.mmmmmm) with "TIMESTAMP"
- Compares the normalized data structures
- Only reports differences in actual airspace data

## Changes Made

**File: `tests/test_parse_regression.py`**
- Added `normalize_timestamps()` method (18 lines)
- Added `compare_json_files()` method (17 lines)  
- Updated comparison logic to handle xcontest.json specially

**File: `tests/README.md`**
- Added "Known Issues" section documenting the timestamp behavior
- Updated comparison strategy section

## Testing

Verified with a test script that:
```python
data1 = {'oaname': 'Norway airspace - 2026-02-27T13:05:30.123456', ...}
data2 = {'oaname': 'Norway airspace - 2026-02-27T13:08:15.987654', ...}
# After normalization: both become 'Norway airspace - TIMESTAMP'
# Result: Files match ✓
```

## Result

The test suite now correctly handles `xcontest.json`:
- ✓ Detects actual changes to airspace data
- ✓ Ignores timestamp differences (which are expected)
- ✓ Consistent test results across runs

You can now run:
```bash
python3 tests/test_parse_regression.py --update-baseline
python3 tests/test_parse_regression.py  # Should pass immediately
```

Both commands should succeed without reporting xcontest.json failures.
