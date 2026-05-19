"""Pulse-check the MQTT broker — print every message on every topic for 15s."""
import time
import paho.mqtt.client as mqtt

count = [0]
start = time.time()

def on_connect(client, *_):
    print(f"connected at {time.time()-start:.1f}s")
    client.subscribe("#")

def on_message(client, userdata, msg):
    count[0] += 1
    if count[0] <= 30:
        try:
            payload = msg.payload.decode()[:200]
        except UnicodeDecodeError:
            payload = "<binary>"
        print(f"  [{time.time()-start:5.1f}s] {msg.topic} :: {payload}")

c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.on_connect = on_connect
c.on_message = on_message
c.connect("10.1.1.108", 1883, 60)
c.loop_start()
time.sleep(15)
c.loop_stop()
print(f"\nTotal messages in 15s: {count[0]}")
