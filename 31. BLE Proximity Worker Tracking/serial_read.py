"""Read ESP32 serial output on COM3 for 10 seconds."""
import serial
import time

try:
    ser = serial.Serial("COM3", 115200, timeout=1)
    print(f"Listening on COM3 at 115200 baud (10 seconds)...\n")
    end = time.time() + 10
    while time.time() < end:
        line = ser.readline()
        if line:
            try:
                print(line.decode("utf-8", errors="replace").rstrip())
            except Exception:
                print(line)
    ser.close()
except serial.SerialException as e:
    print(f"Error: {e}")
