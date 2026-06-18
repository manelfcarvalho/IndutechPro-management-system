"""
Build script for creating standalone Windows executable using PyInstaller
"""

import os
import shutil
import sys
import PyInstaller.__main__


def main():
    """Build the standalone executable"""
    
    # Build PyInstaller arguments
    args = [
        'main.py',                          # Entry point
        '--name=Indutechpro',               # Executable name
        '--onefile',                        # Single .exe file
        '--noconsole',                      # No black terminal window
        '--clean',                          # Clean PyInstaller cache
        
        # Collect all data files for customtkinter (themes, assets)
        '--collect-all=customtkinter',
        
        # Collect all data files for tkcalendar (locale files, etc.)
        '--collect-all=tkcalendar',
        
        # Critical: babel is required by tkcalendar but PyInstaller doesn't auto-detect it
        '--hidden-import=babel',
        '--hidden-import=babel.numbers',
        '--hidden-import=babel.dates',
        '--hidden-import=babel.core',
        '--collect-all=babel',              # Collect babel locale data files
        
        # Add assets folder (Windows separator: ;)
        '--add-data=assets;assets',
    ]
    
    # Add config folder if it exists
    if os.path.exists('config'):
        args.append('--add-data=config;config')
    
    # Do not bundle the live database. The app creates/uses database/indutechpro.db
    # next to the executable, preserving each company's real data between versions.
    
    # Run PyInstaller with error handling
    print("=" * 60)
    print("Starting PyInstaller build process...")
    print("=" * 60)
    print(f"Executable name: Indutechpro")
    print(f"Mode: One-file executable (--onefile)")
    print(f"Console: Hidden (--noconsole)")
    print("\nIncluding dependencies:")
    print("  - customtkinter (with all assets)")
    print("  - tkcalendar (with all locale files)")
    print("  - babel (required by tkcalendar)")
    print(f"\nArguments: {args}")
    print("\nBuilding executable...")
    print("=" * 60)
    
    try:
        PyInstaller.__main__.run(args)
        print("\n" + "=" * 60)
        print("[OK] PyInstaller build completed successfully!")
        print("=" * 60)
    except Exception as e:
        print("\n" + "=" * 60)
        print("[ERROR] BUILD FAILED!")
        print("=" * 60)
        print(f"Error: {str(e)}")
        print("\nTroubleshooting:")
        print("  1. Ensure all app dependencies are installed: pip install -r requirements-app.txt")
        print("  2. Check that tkcalendar and babel are installed: pip install tkcalendar babel")
        print("  3. Try running with --clean flag (already included)")
        print("  4. Check PyInstaller version: pip install --upgrade pyinstaller")
        sys.exit(1)
    
    # Post-build: Copy assets folder to dist directory (if not already included)
    print("\nVerifying assets folder in dist directory...")
    
    source_path = 'assets'
    dest_path = 'dist/assets'
    
    # Check if assets folder exists
    if not os.path.exists(source_path):
        print(f"Warning: Source folder '{source_path}' does not exist. Skipping assets copy.")
        return
    
    # For onefile builds, assets are bundled inside the exe, but we may want a copy for reference
    # Only copy if dist/assets doesn't exist (onefile bundles it internally)
    if not os.path.exists(dest_path):
        try:
            shutil.copytree(source_path, dest_path)
            print(f"[OK] Assets copied to {dest_path} (for reference).")
        except Exception as e:
            print(f"Warning: Could not copy assets folder: {str(e)}")
            print("  (This is OK for onefile builds - assets are bundled in the .exe)")
    else:
        print(f"[OK] Assets folder already exists in dist directory.")
    
    print("\n" + "=" * 60)
    print("[OK] BUILD COMPLETE!")
    print("=" * 60)
    print(f"Executable location: dist/Indutechpro.exe")
    print("\nNote: For onefile builds, all assets are bundled inside the .exe")
    print("      The application will extract them to a temporary folder at runtime.")
    print("=" * 60)


if __name__ == "__main__":
    main()
