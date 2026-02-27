#!/bin/bash
# Quick setup script for the test suite
# Run this once before starting refactoring work

set -e

echo "==================================="
echo "pg-xc Test Suite Setup"
echo "==================================="
echo ""

# Check if parse.py can run
echo "Checking dependencies..."
if ! python3 -c "import geojson, shapely" 2>/dev/null; then
    echo "⚠️  Warning: Missing Python dependencies (geojson, shapely)"
    echo "   Install with: pip3 install geojson shapely"
    echo ""
fi

# Check if source files exist
if [ ! -d "import/sources/txt" ] || [ -z "$(ls -A import/sources/txt)" ]; then
    echo "⚠️  Warning: No source files found in import/sources/txt/"
    echo "   Run 'make fetch-sources' to download AIP data"
    echo ""
fi

# Check if result directory exists and has files
if [ -d "import/result" ] && [ -n "$(ls -A import/result 2>/dev/null)" ]; then
    echo "✓ Found existing parse.py output in import/result/"
    echo ""
    echo "Creating baseline from existing output..."
    python3 tests/test_parse_regression.py --update-baseline
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "==================================="
        echo "✓ Setup Complete!"
        echo "==================================="
        echo ""
        echo "You can now:"
        echo "  1. Make changes to import/parse.py"
        echo "  2. Run 'make test' to verify output"
        echo "  3. Repeat as you refactor"
        echo ""
        echo "See tests/README.md for full documentation"
    else
        echo "❌ Failed to create baseline"
        exit 1
    fi
else
    echo "⚠️  No existing output found."
    echo ""
    echo "Next steps:"
    echo "  1. Run 'make fetch-sources' (if needed)"
    echo "  2. Run 'make run-parse' to generate initial output"
    echo "  3. Run './tests/setup_tests.sh' again to create baseline"
    echo ""
fi
