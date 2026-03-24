#!/bin/bash
# Quick test script for select dropdown fix

echo "Starting FIAS Emulator to test select dropdown fix..."

# Change to emulator directory
cd /home/anirut/DEV/vibe-coding/WiFi_Captive_Portal/tools/fias-emulator

# Start the emulator in the background
source .venv/bin/activate
export FIAS_TCP_PORT=9090
export FIAS_HTTP_PORT=8081
uvicorn emulator.main:app --host 0.0.0.0 --port 8081 &
EMULATOR_PID=$!

echo "Emulator started with PID: $EMULATOR_PID"
echo "Please visit http://localhost:8081 to test the select dropdowns"
echo ""
echo "Test the following pages:"
echo "- Guests page: Try selecting a scenario from the dropdown"
echo "- Failure Rules page: Test all select dropdowns (Trigger, Action, Malformed Type, Scenario)"
echo "- Activity page: Test the filter dropdowns"
echo ""
echo "Press Enter to stop the emulator..."
read

# Clean up
kill $EMULATOR_PID 2>/dev/null
echo "Emulator stopped."