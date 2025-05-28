#!/bin/bash

# Make sure to `uv sync` before running this script

# Try to find the virtual environment directory
VENV_DIR=${VIRTUAL_ENV:-}

if [ -z "$VENV_DIR" ]; then
    echo "Error: Could not find virtual environment directory"
    echo "Please activate your virtual environment or set VIRTUAL_ENV to the path of the virtual environment"
    exit 1
fi

echo "Virtual environment directory: $VENV_DIR"

# Find the geni directory in site-packages
GENI_DIR=$(find "$VENV_DIR/lib/" -type d -path "*/site-packages/geni" 2>/dev/null)

if [ -z "$GENI_DIR" ]; then
    echo "Error: Could not find geni package directory in site-packages"
    exit 1
fi

echo "Found geni package at: $GENI_DIR"

# Convert the geni-lib library code to python 3
2to3 -w "$GENI_DIR"
2to3 -w "$VENV_DIR/bin/build-context"

# Fix encoding issues in specific files
CONTEXT_PY="$GENI_DIR/aggregate/context.py"
RSPEC_PG_PY="$GENI_DIR/rspec/pg.py"

echo "Fixing encoding in context.py and pg.py..."
sed -i 's/f\.write(cred)/f.write(cred.encode("utf-8") if isinstance(cred, str) else cred)/' "$CONTEXT_PY"
sed -i 's/f\.write(buf)/f.write(buf.decode("utf-8") if not isinstance(buf, str) else buf)/' "$RSPEC_PG_PY"