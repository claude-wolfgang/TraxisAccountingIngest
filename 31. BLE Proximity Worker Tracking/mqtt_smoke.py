"""15-second MQTT smoke test: dump every espresense topic to confirm the
gateways are connected to the broker and what they're publishing."""
import time
from collections import defaultdict
import paho.mqtt.client as mqtt

BROKER = "10.1.1.178"
DURATION = 15

topic_counts = defaultdict(int)
samples = {}


def on_connect(client, userdata, flags, rc, properties):
    print(f"connected to {BROKER}:1883", flush=True)
    client.subscribe("espresense/#")


def on_message(client, userdata, msg):
    topic_counts[msg.topic] += 1
    if msg.topic not in samples:
        try:
            samples[msg.topic] = msg.payload.decode()[:200]
        except UnicodeDecodeError:
            samples[msg.topic] = repr(msg.payload[:200])


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, 1883, 60)
client.loop_start()

time.sleep(DURATION)
client.loop_stop()

print(f"\n--- {DURATION}s scan complete ---")
print(f"unique topics seen: {len(topic_counts)}")
print(f"total messages:     {sum(topic_counts.values())}")
print()
for t in sorted(topic_counts.keys()):
    print(f"  [{topic_counts[t]:4d}]  {t}")
    print(f"           sample: {samples[t]}")
