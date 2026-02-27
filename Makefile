# Makefile for pg-xc development and testing

.PHONY: help test test-update baseline clean run-parse compare

help:
	@echo "pg-xc Development Commands"
	@echo "=========================="
	@echo ""
	@echo "Testing:"
	@echo "  make test              Run regression tests for parse.py"
	@echo "  make test-update       Update test baseline with current output"
	@echo "  make test-verbose      Run tests with verbose output"
	@echo ""
	@echo "Parsing:"
	@echo "  make run-parse         Run parse.py to generate all output formats"
	@echo "  make fetch-sources     Download latest AIP source files"
	@echo ""
	@echo "Comparison:"
	@echo "  make compare           Compare current luftrom.geojson with previous version"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean             Remove generated files (result/*)"
	@echo ""

# Regression testing
test:
	python3 tests/test_parse_regression.py

test-update baseline:
	python3 tests/test_parse_regression.py --update-baseline

test-verbose:
	python3 tests/test_parse_regression.py -v

test-strict:
	python3 tests/test_parse_regression.py -x

# Run parse.py
run-parse:
	cd import && python3 parse.py

# Fetch source files
fetch-sources:
	cd import/sources && ./sources.sh

# Compare with reference
compare:
	@if [ ! -f geojson/luftrom.geojson ]; then \
		echo "Error: geojson/luftrom.geojson not found"; \
		exit 1; \
	fi
	@if [ ! -f import/result/luftrom.geojson ]; then \
		echo "Error: import/result/luftrom.geojson not found (run 'make run-parse' first)"; \
		exit 1; \
	fi
	cd import && python3 compare.py ../geojson/luftrom.geojson result/luftrom.geojson

# Clean generated files
clean:
	rm -f import/result/*
	@echo "Cleaned import/result/"

# Development workflow helpers
.PHONY: dev-setup dev-test

dev-setup:
	@echo "Setting up development environment..."
	@mkdir -p tests/baseline
	@mkdir -p import/result
	@echo "Run 'make test-update' to create initial baseline"

dev-test: run-parse test
