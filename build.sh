#!/bin/bash
# Build script for macOS/Linux
# This script runs the Python build script to create a standalone executable

set -e  # Exit on error

echo "Building transcoder executable..."
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Please install Python 3.10 or higher."
    exit 1
fi

# Run the build script with all passed arguments
python3 build.py "$@"

if [ $? -eq 0 ]; then
    echo ""
    echo "Build completed successfully!"
    if [ "$(uname)" == "Darwin" ]; then
        echo "Executable location: dist/transcode"
    else
        echo "Executable location: dist/transcode"
    fi
else
    echo ""
    echo "Build failed!"
    exit 1
fi


