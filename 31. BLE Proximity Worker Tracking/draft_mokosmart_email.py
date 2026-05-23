"""One-shot: drop a vendor-support draft into Outlook 'Purchasing - To Review'.

Uses the existing P31 Photo Upload Service email_draft helper (Graph API,
.traxis.env creds). Wolfgang reviews + sends from Outlook.
"""
import importlib.util
from pathlib import Path

# Reuse P31 Photo Upload Service's Graph helper. Direct-load via importlib so we
# don't put its directory on sys.path (it contains a local queue.py that would
# shadow stdlib's queue module and break urllib3).
HELPER_PATH = (
    Path(__file__).resolve().parents[1]
    / "31. Photo Upload Service"
    / "photo-uploader"
    / "purchasing"
    / "email_draft.py"
)
_spec = importlib.util.spec_from_file_location("email_draft_helper", HELPER_PATH)
email_draft = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(email_draft)

TO = "lora@mokosmart.com"
SUBJECT = "B2 Smart Badge (Order #3765, 2026-04-29) — initial configuration / MokoBeaconX connect"

BODY = """您好，以下是关于 B2 Smart Badge 初始配置的技术问题。中英文回复均可，谢谢。
(Hi — below are technical questions about the B2 Smart Badge initial configuration. A reply in either Chinese or English is fine — thank you.)

---

Hello MOKOSmart support team,

I received 10x B2 Smart Wearable Badges. To help you locate the shipment in your system, here are the references from the shipping label and my order:

- Possible SO / order number on label: 2695673481
- Carrier waybill (Cathay Cargo): 2049985207371173888
- Carton ID: PC7260328
- Label date: 2026-05-01 (Hong Kong → United States, route DHK01)
- Our internal purchase reference: Order #3765 (placed 2026-04-29)

The bundled user manual covers product specifications and SOS button usage in an emergency, but it does not document the initial setup needed to configure the badges via the MokoBeaconX app. Could you send me the B2 configuration quick-start, or answer the following directly:

1. What is the exact button-press pattern to wake a B2 from its shipped state and put it into a connectable / pairing mode that MokoBeaconX can connect to? (Single click, double, triple, long-press of N seconds?)

2. What do the various LED colors and blink patterns mean? In particular: idle / broadcasting iBeacon / connectable advertising mode / SOS triggered / low battery / charging.

3. After the badge enters connectable advertising mode, how long does that window stay open before the radio drops back to broadcast-only? We are observing that MokoBeaconX scan finds the badge but tapping "Connect" reports a connection failure even when attempted immediately.

4. Is the default app password "Moko4321" correct for the B2, or does this model ship with a different default?

5. Are these badges shipped in any kind of deep-sleep or transport mode that requires a non-button activation step (for example, removing and reinserting a battery insulator, or first-time charging)? The B2 has no externally visible port; we have not opened the case.

6. What is the recommended factory-reset procedure if a badge becomes unresponsive (we'd like to document this for our fleet before deploying)?

Context: we plan to deploy these as worker-identity beacons across a CNC machine shop, with ESP32-based ESPresense gateways acting as receivers via Kalman-filtered RSSI to MQTT. The badges themselves do not need to receive data — we only need stable, identifiable iBeacon broadcasts with adjustable TX power, advertising interval, and a non-default access password for tamper resistance. Any quick-start documentation or application note covering the standard provisioning workflow for B2 would be very welcome.

Thanks for your help,

Wolfgang
Traxis Manufacturing
"""


def main():
    msg_id = email_draft.create_draft(TO, SUBJECT, BODY)
    print(f"Draft created: {msg_id}")
    print(f"Outlook link:  {email_draft.draft_web_url(msg_id)}")
    print()
    print(f"Folder:        '{email_draft.DRAFT_FOLDER_NAME}' under {email_draft.DRAFT_MAILBOX}")
    print("Review and Send from Outlook when ready.")


if __name__ == "__main__":
    main()
