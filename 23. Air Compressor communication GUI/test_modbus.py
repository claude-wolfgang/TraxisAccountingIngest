from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient('10.1.1.180', port=502, timeout=5)
connected = client.connect()
print(f"Connected: {connected}")

if connected:
    for dev_id in [1, 2, 0]:
        print(f"\n--- Slave ID {dev_id}, Holding Registers 0-9 ---")
        try:
            result = client.read_holding_registers(0, count=10, device_id=dev_id)
            if not result.isError():
                for i, val in enumerate(result.registers):
                    print(f"  Register {i:3d}: {val:5d}  (0x{val:04X})")
            else:
                print(f"  Error: {result}")
        except Exception as e:
            print(f"  Exception: {e}")

    client.close()
    print("\nDone.")
else:
    print("Could not connect.")
