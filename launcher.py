#!/usr/bin/env python3
"""Launcher for lightweight build that ensures dependencies."""

import sys
from pathlib import Path

# Add transcoder to path
sys.path.insert(0, str(Path(__file__).parent))

from transcoder.dependency_manager import check_dependencies, ensure_all_dependencies

if __name__ == "__main__":
    # Check if dependencies are available
    all_available, missing = check_dependencies()
    
    if not all_available:
        print("Missing dependencies:", ", ".join(missing))
        print("Installing missing dependencies...")
        
        if not ensure_all_dependencies():
            print("Error: Failed to install dependencies")
            print("Please install manually:")
            print("  pip install torch torchvision easyocr opencv-python")
            sys.exit(1)
    
    # Import and run main application
    from transcoder.main import main
    main()















