#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression test suite for parse.py

This test suite ensures that refactoring parse.py doesn't change the output.
It compares newly generated files against a known-good baseline.

Usage:
    # Run tests (compare against baseline)
    python3 tests/test_parse_regression.py

    # Update baseline with current output
    python3 tests/test_parse_regression.py --update-baseline

    # Run with verbose output
    python3 tests/test_parse_regression.py -v

    # Exit on first difference
    python3 tests/test_parse_regression.py -x
"""

import geojson
import json
import os
import sys
import subprocess
import hashlib
import logging
from pathlib import Path
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class ParseRegressionTest:
    """Test suite for parse.py regression testing"""
    
    def __init__(self, baseline_dir="tests/baseline", exit_on_error=False, verbose=False):
        self.baseline_dir = Path(baseline_dir)
        self.exit_on_error = exit_on_error
        self.verbose = verbose
        self.test_results = defaultdict(list)
        self.import_dir = Path("import")
        self.result_dir = self.import_dir / "result"
        
        # Files to compare
        self.test_files = [
            "luftrom.geojson",
            "luftrom.fl.txt",
            "luftrom.ft.txt", 
            "luftrom.m.txt",
            "luftrom.openaip",
            "accsectors.geojson",
            "xcontest.json"
        ]
    
    def setup_baseline(self):
        """Create baseline directory if it doesn't exist"""
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Baseline directory: {self.baseline_dir}")
    
    def run_parse(self):
        """Run parse.py to generate fresh output"""
        logger.info("Running parse.py...")
        try:
            result = subprocess.run(
                ["python3", "parse.py"],
                cwd=self.import_dir,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                logger.error("parse.py failed!")
                logger.error(f"STDOUT: {result.stdout}")
                logger.error(f"STDERR: {result.stderr}")
                return False
            
            if self.verbose:
                logger.info(f"parse.py output:\n{result.stdout}")
            
            logger.info("parse.py completed successfully")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("parse.py timed out after 5 minutes")
            return False
        except Exception as e:
            logger.error(f"Failed to run parse.py: {e}")
            return False
    
    def compute_file_hash(self, filepath):
        """Compute SHA256 hash of a file"""
        sha256 = hashlib.sha256()
        try:
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception as e:
            logger.error(f"Failed to hash {filepath}: {e}")
            return None
    
    def normalize_timestamps(self, data):
        """Normalize timestamps in xcontest.json for comparison"""
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                # Replace timestamp fields with a fixed value
                if key in ('oadescription', 'oaname'):
                    if isinstance(value, str):
                        # Remove timestamp portion (ISO format: YYYY-MM-DDTHH:MM:SS.mmmmmm)
                        import re
                        value = re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?', 'TIMESTAMP', value)
                result[key] = self.normalize_timestamps(value)
            return result
        elif isinstance(data, list):
            return [self.normalize_timestamps(item) for item in data]
        else:
            return data
    
    def compare_json_files(self, file1, file2):
        """Compare two JSON files, normalizing timestamps"""
        try:
            with open(file1, 'r', encoding='utf-8') as f1:
                data1 = json.load(f1)
            with open(file2, 'r', encoding='utf-8') as f2:
                data2 = json.load(f2)
            
            # Normalize timestamps for comparison
            data1_norm = self.normalize_timestamps(data1)
            data2_norm = self.normalize_timestamps(data2)
            
            if data1_norm == data2_norm:
                return True, "JSON content matches (timestamps normalized)"
            else:
                # Show what's different
                return False, "JSON content differs (excluding timestamps)"
            
        except Exception as e:
            return False, f"Error comparing JSON: {e}"
    
    def compare_text_files(self, file1, file2):
        """Compare two text files line by line"""
        try:
            with open(file1, 'r', encoding='utf-8') as f1:
                lines1 = f1.readlines()
            with open(file2, 'r', encoding='utf-8') as f2:
                lines2 = f2.readlines()
            
            if len(lines1) != len(lines2):
                return False, f"Line count differs: {len(lines1)} vs {len(lines2)}"
            
            diffs = []
            for i, (line1, line2) in enumerate(zip(lines1, lines2), 1):
                if line1 != line2:
                    diffs.append(f"Line {i}: '{line1.strip()}' != '{line2.strip()}'")
            
            if diffs:
                return False, "\n".join(diffs[:10])  # Show first 10 differences
            
            return True, "Files match"
            
        except Exception as e:
            return False, f"Error comparing files: {e}"
    
    def compare_geojson_detailed(self, file1, file2, name):
        """Detailed GeoJSON comparison with feature-by-feature analysis"""
        try:
            with open(file1, 'r', encoding='utf-8') as f1:
                data1 = geojson.load(f1)
            with open(file2, 'r', encoding='utf-8') as f2:
                data2 = geojson.load(f2)
            
            issues = []
            
            # Compare feature counts
            if len(data1.features) != len(data2.features):
                issues.append(f"Feature count differs: {len(data1.features)} vs {len(data2.features)}")
            
            # Build feature index by name
            def normalize_name(s):
                return str(s).strip().lower().replace('å','a').replace('ø','o').replace('æ','a')
            
            baseline_features = {normalize_name(f['properties']['name']): f for f in data1.features}
            current_features = {normalize_name(f['properties']['name']): f for f in data2.features}
            
            # Check for missing/new features
            baseline_names = set(baseline_features.keys())
            current_names = set(current_features.keys())
            
            missing = baseline_names - current_names
            new = current_names - baseline_names
            
            if missing:
                issues.append(f"Missing features ({len(missing)}): {', '.join(list(missing)[:5])}")
            if new:
                issues.append(f"New features ({len(new)}): {', '.join(list(new)[:5])}")
            
            # Compare common features
            common = baseline_names & current_names
            for feat_name in common:
                baseline_feat = baseline_features[feat_name]
                current_feat = current_features[feat_name]
                
                # Compare geometry (coordinate count and rough shape)
                b_coords = baseline_feat['geometry']['coordinates'][0]
                c_coords = current_feat['geometry']['coordinates'][0]
                
                if len(b_coords) != len(c_coords):
                    issues.append(f"{feat_name}: coordinate count differs ({len(b_coords)} vs {len(c_coords)})")
                
                # Compare key properties
                b_props = baseline_feat['properties']
                c_props = current_feat['properties']
                
                for key in ['class', 'from (m amsl)', 'to (m amsl)']:
                    if key in b_props and key in c_props:
                        if b_props[key] != c_props[key]:
                            issues.append(f"{feat_name}: {key} differs ({b_props[key]} vs {c_props[key]})")
            
            if issues:
                return False, "\n".join(issues[:20])  # Show first 20 issues
            
            return True, f"All {len(common)} features match"
            
        except Exception as e:
            return False, f"Error comparing GeoJSON: {e}"
    
    def compare_files(self):
        """Compare all generated files against baseline"""
        logger.info("Comparing files against baseline...")
        all_passed = True
        
        for filename in self.test_files:
            baseline_file = self.baseline_dir / filename
            current_file = self.result_dir / filename
            
            if not baseline_file.exists():
                logger.warning(f"No baseline for {filename} - skipping")
                self.test_results[filename].append(("SKIP", "No baseline"))
                continue
            
            if not current_file.exists():
                logger.error(f"Output file {filename} not generated!")
                self.test_results[filename].append(("FAIL", "File not generated"))
                all_passed = False
                if self.exit_on_error:
                    return False
                continue
            
            # Quick hash comparison first
            baseline_hash = self.compute_file_hash(baseline_file)
            current_hash = self.compute_file_hash(current_file)
            
            if baseline_hash == current_hash:
                logger.info(f"✓ {filename}: PASS (identical)")
                self.test_results[filename].append(("PASS", "Identical"))
                continue
            
            # Files differ - do detailed comparison
            logger.warning(f"✗ {filename}: Files differ, analyzing...")
            
            if filename.endswith('.geojson'):
                passed, details = self.compare_geojson_detailed(baseline_file, current_file, filename)
            elif filename == 'xcontest.json':
                # Special handling for xcontest.json (has timestamps)
                passed, details = self.compare_json_files(baseline_file, current_file)
            elif filename.endswith('.json'):
                passed, details = self.compare_text_files(baseline_file, current_file)
            else:
                passed, details = self.compare_text_files(baseline_file, current_file)
            
            if passed:
                logger.info(f"  {details}")
                self.test_results[filename].append(("PASS", details))
            else:
                logger.error(f"  {details}")
                self.test_results[filename].append(("FAIL", details))
                all_passed = False
                
                if self.exit_on_error:
                    return False
        
        return all_passed
    
    def update_baseline(self):
        """Copy current output to baseline"""
        logger.info("Updating baseline with current output...")
        self.setup_baseline()
        
        for filename in self.test_files:
            current_file = self.result_dir / filename
            baseline_file = self.baseline_dir / filename
            
            if not current_file.exists():
                logger.warning(f"Cannot update baseline: {filename} not found")
                continue
            
            try:
                import shutil
                shutil.copy2(current_file, baseline_file)
                logger.info(f"Updated baseline: {filename}")
            except Exception as e:
                logger.error(f"Failed to update {filename}: {e}")
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        
        total = len(self.test_results)
        passed = sum(1 for results in self.test_results.values() 
                    if any(r[0] == "PASS" for r in results))
        failed = sum(1 for results in self.test_results.values() 
                    if any(r[0] == "FAIL" for r in results))
        skipped = sum(1 for results in self.test_results.values() 
                     if any(r[0] == "SKIP" for r in results))
        
        print(f"Total files: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Skipped: {skipped}")
        
        if failed > 0:
            print("\nFailed files:")
            for filename, results in self.test_results.items():
                if any(r[0] == "FAIL" for r in results):
                    print(f"  - {filename}")
        
        print("="*70)
        return failed == 0
    
    def run(self, update_baseline=False):
        """Run the complete test suite"""
        if update_baseline:
            self.setup_baseline()
            if not self.run_parse():
                logger.error("Cannot update baseline: parse.py failed")
                return False
            self.update_baseline()
            logger.info("Baseline updated successfully")
            return True
        
        # Run comparison tests
        self.setup_baseline()
        
        if not self.run_parse():
            logger.error("parse.py failed - cannot run tests")
            return False
        
        all_passed = self.compare_files()
        passed = self.print_summary()
        
        return all_passed and passed


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Regression tests for parse.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--update-baseline', action='store_true',
                       help='Update baseline with current output')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')
    parser.add_argument('-x', '--exit-on-error', action='store_true',
                       help='Exit on first difference')
    parser.add_argument('--baseline-dir', default='tests/baseline',
                       help='Baseline directory (default: tests/baseline)')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    tester = ParseRegressionTest(
        baseline_dir=args.baseline_dir,
        exit_on_error=args.exit_on_error,
        verbose=args.verbose
    )
    
    success = tester.run(update_baseline=args.update_baseline)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
