#!/usr/bin/env python3
"""
Test for border following geometry generation.

This test specifically checks features that use "along border" syntax
to ensure the border following logic produces correct geometries.

The Kirkenes Centre TMA is a critical test case because it follows
the Finland-Norway border and a bug in border following logic caused
it to span the entire country instead of being a small local area.
"""

import json
import sys
import os
from shapely.geometry import Polygon

# Add import directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'import'))


def test_kirkenes_centre_tma():
    """Test that Kirkenes Centre TMA has correct location and size.
    
    This feature follows the Finland-Norway border and should be located
    near Kirkenes at approximately 69.7°N, 29°E.
    
    Previous bug: Border following logic was wrapping around the entire
    Norway border (19k+ points) instead of taking the short path (4 points),
    resulting in a polygon spanning from southern to northern Norway.
    """
    # Load generated luftrom.geojson
    result_file = os.path.join(os.path.dirname(__file__), '../import/result/luftrom.geojson')
    
    if not os.path.exists(result_file):
        print("SKIP: No result file generated yet")
        return True
    
    with open(result_file, 'r') as f:
        data = json.load(f)
    
    # Find Kirkenes Centre TMA
    feature = None
    for f in data['features']:
        if 'kirkenes centre tma' in f['properties']['name'].lower():
            feature = f
            break
    
    if not feature:
        print("FAIL: Kirkenes Centre TMA not found in output")
        return False
    
    coords = feature['geometry']['coordinates'][0]
    poly = Polygon(coords)
    bounds = poly.bounds  # (minx, miny, maxx, maxy)
    
    # Validation criteria
    tests = []
    
    # 1. Should be in northern Norway near Kirkenes
    # Kirkenes is at ~69.7°N, 30°E
    lat_ok = 69.0 < bounds[1] < 70.0 and 69.0 < bounds[3] < 70.0
    tests.append(('Latitude range (69-70°N)', lat_ok))
    
    lon_ok = 28.0 < bounds[0] < 31.0 and 28.0 < bounds[2] < 31.0
    tests.append(('Longitude range (28-31°E)', lon_ok))
    
    # 2. Should be a small local area, not spanning the whole country
    # Area should be less than 1 square degree (local TMA)
    area_ok = poly.area < 1.0
    tests.append((f'Small area (<1 sq deg): {poly.area:.6f}', area_ok))
    
    # 3. Should have reasonable number of coordinates (not thousands)
    # Border following should fill ~20-30 points, not 19k+
    coord_ok = 10 < len(coords) < 100
    tests.append((f'Reasonable coordinate count: {len(coords)}', coord_ok))
    
    # 4. Bounding box should be small (local area, not spanning 10+ degrees)
    lat_span = bounds[3] - bounds[1]
    lon_span = bounds[2] - bounds[0]
    span_ok = lat_span < 2.0 and lon_span < 2.0
    tests.append((f'Small geographic span: {lat_span:.2f}°×{lon_span:.2f}°', span_ok))
    
    # Print results
    all_passed = True
    for test_name, passed in tests:
        status = "✓" if passed else "✗"
        print(f"  {status} {test_name}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print(f"PASS: Kirkenes Centre TMA geometry correct")
        print(f"      Location: {poly.centroid.y:.2f}°N, {poly.centroid.x:.2f}°E")
        print(f"      Area: {poly.area:.6f} sq deg")
    else:
        print(f"FAIL: Kirkenes Centre TMA geometry incorrect")
        print(f"      Expected: Small area near 69.7°N, 29-30°E")
        print(f"      Got: {bounds}")
    
    return all_passed


def test_border_following_features():
    """Test all features that use border following.
    
    Ensures that features following country borders have reasonable sizes
    and don't accidentally wrap around the entire border.
    """
    result_file = os.path.join(os.path.dirname(__file__), '../import/result/luftrom.geojson')
    
    if not os.path.exists(result_file):
        print("SKIP: No result file generated yet")
        return True
    
    with open(result_file, 'r') as f:
        data = json.load(f)
    
    # Features known to use border following
    border_features = [
        'Kirkenes Centre TMA',
        'Kirkenes West TMA',
        # Add more as needed
    ]
    
    all_passed = True
    for feat_name in border_features:
        # Find feature
        feature = None
        for f in data['features']:
            if feat_name.lower() in f['properties']['name'].lower():
                feature = f
                break
        
        if not feature:
            print(f"  ⚠ {feat_name}: Not found")
            continue
        
        coords = feature['geometry']['coordinates'][0]
        poly = Polygon(coords)
        
        # Check that it's not unreasonably large
        # (indicating wrap-around bug)
        if poly.area > 10.0:  # More than 10 square degrees = likely bug
            print(f"  ✗ {feat_name}: Area too large ({poly.area:.2f} sq deg)")
            all_passed = False
        elif len(coords) > 1000:  # Too many coordinates
            print(f"  ✗ {feat_name}: Too many coordinates ({len(coords)})")
            all_passed = False
        else:
            print(f"  ✓ {feat_name}: OK (area={poly.area:.4f}, coords={len(coords)})")
    
    return all_passed


if __name__ == '__main__':
    print("Testing border following geometry...")
    print()
    
    print("Test 1: Kirkenes Centre TMA specific checks")
    test1 = test_kirkenes_centre_tma()
    print()
    
    print("Test 2: All border-following features")
    test2 = test_border_following_features()
    print()
    
    if test1 and test2:
        print("=" * 50)
        print("ALL BORDER FOLLOWING TESTS PASSED")
        print("=" * 50)
        sys.exit(0)
    else:
        print("=" * 50)
        print("SOME BORDER FOLLOWING TESTS FAILED")
        print("=" * 50)
        sys.exit(1)
