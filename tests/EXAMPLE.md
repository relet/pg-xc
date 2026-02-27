# Example: Using the Test Suite

This example shows a complete refactoring session using the test suite.

## Initial State

You have working code in `parse.py` and want to refactor the coordinate conversion logic.

## Step 1: Create Baseline

```bash
$ ./tests/setup_tests.sh
===================================
pg-xc Test Suite Setup
===================================

✓ Found existing parse.py output in import/result/
Creating baseline from existing output...
INFO: Baseline directory: tests/baseline
INFO: Updating baseline with current output...
INFO: Updated baseline: luftrom.geojson
INFO: Updated baseline: luftrom.fl.txt
INFO: Updated baseline: luftrom.ft.txt
INFO: Updated baseline: luftrom.m.txt
INFO: Updated baseline: luftrom.openaip
INFO: Updated baseline: accsectors.geojson
INFO: Updated baseline: xcontest.json
INFO: Baseline updated successfully

===================================
✓ Setup Complete!
===================================
```

Baseline is now locked in. Any changes to parse.py will be compared against this.

## Step 2: Refactor (Extract Function)

Let's extract the coordinate parsing logic into a separate function:

```python
# In parse.py, BEFORE refactoring:
# Coordinate parsing is inline, repeated in multiple places
def parse_coordinates(line):
    # ... 50 lines of regex matching ...
    lat = float(match.group('n'))
    lon = float(match.group('e'))
    # ... more processing ...
    return (lat, lon)

# AFTER refactoring: Extract into util function
def parse_coordinate_string(coord_str):
    """Parse coordinate string into lat/lon tuple"""
    # ... same logic, just extracted ...
    return (lat, lon)

def parse_coordinates(line):
    coord_str = extract_coord_from_line(line)
    return parse_coordinate_string(coord_str)
```

## Step 3: Run Tests

```bash
$ make test
INFO: Running parse.py...
INFO: parse.py completed successfully
INFO: Comparing files against baseline...
INFO: ✓ luftrom.geojson: PASS (identical)
INFO: ✓ luftrom.fl.txt: PASS (identical)
INFO: ✓ luftrom.ft.txt: PASS (identical)
INFO: ✓ luftrom.m.txt: PASS (identical)
INFO: ✓ luftrom.openaip: PASS (identical)
INFO: ✓ accsectors.geojson: PASS (identical)
INFO: ✓ xcontest.json: PASS (identical)

======================================================================
TEST SUMMARY
======================================================================
Total files: 7
Passed: 7
Failed: 0
Skipped: 0
======================================================================
```

✅ **Success!** The refactoring preserved behavior.

## Step 4: Commit

```bash
$ git add import/parse.py import/util/utils.py
$ git commit -m "Refactor: Extract coordinate parsing into utils

- Moved parse_coordinate_string() to util/utils.py
- Reduces code duplication
- No behavior change (verified with regression tests)"
```

## Example: Bug Fix Scenario

Now you discover a bug: circles with radius in meters (not NM) are incorrectly converted.

### Fix the Bug

```python
# In parse.py, FIX:
if 'rad_m' in match.groupdict():
    radius_m = float(match.group('rad_m'))
    # OLD: radius_nm = radius_m * 1852  # WRONG! This is backwards
    # NEW: radius_nm = radius_m / 1852  # Convert meters to NM
    radius_nm = radius_m / 1852
```

### Run Tests (Will Fail - This is Good!)

```bash
$ make test
INFO: Running parse.py...
INFO: parse.py completed successfully
INFO: Comparing files against baseline...
WARNING: ✗ luftrom.geojson: Files differ, analyzing...
ERROR:   en-r122-halden: coordinate count differs (64 vs 48)
        en-d210-tellenes: coordinate count differs (64 vs 96)

======================================================================
TEST SUMMARY
======================================================================
Total files: 7
Passed: 6
Failed: 1
Skipped: 0
======================================================================
```

### Verify the Fix is Correct

```bash
# Check one of the changed features
$ python3 -c "
import geojson
data = geojson.load(open('import/result/luftrom.geojson'))
for f in data.features:
    if 'halden' in f['properties']['name'].lower():
        print(f['properties']['name'])
        print('Coordinates:', len(f['geometry']['coordinates'][0]))
"
```

The circle now has the correct size. This change is **intentional**.

### Update Baseline with Fixed Behavior

```bash
$ make test-update
INFO: Running parse.py...
INFO: parse.py completed successfully
INFO: Updating baseline with current output...
INFO: Updated baseline: luftrom.geojson
INFO: Updated baseline: accsectors.geojson
INFO: Baseline updated successfully
```

### Commit the Fix

```bash
$ git add import/parse.py tests/baseline/
$ git commit -m "Fix: Correct meter-to-NM conversion for circle radii

- Fixed backwards conversion (was multiplying instead of dividing)
- Affects EN R122 Halden and EN D210 Tellenes
- Updated test baseline with corrected geometries"
```

## Summary

The test suite lets you:
1. ✅ Refactor safely (tests catch regressions)
2. ✅ Fix bugs with confidence (tests verify fixes)
3. ✅ Track intentional changes (baseline updates)
4. ✅ Maintain quality (every change is verified)

Next: Read `tests/README.md` for full documentation.
