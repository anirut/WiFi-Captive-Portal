#!/bin/bash
# Build script for WiFi Portal Installer
# Creates a single executable using PyInstaller

set -e

echo "Building WiFi Portal Installer..."

# Install dependencies
pip install -r requirements.txt

# Build with PyInstaller
pyinstaller wifi-portal-installer.spec --clean

echo "Build complete: dist/wifi-portal-installer"
echo "Size: $(du -h dist/wifi-portal-installer | cut -f1)"
