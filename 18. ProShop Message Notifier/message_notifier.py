"""
ProShop Message Notifier
========================
Polls ProShop for new human-sent messages and displays a pulsing
green disc overlay in the upper-right corner of the screen.
Clicking the disc opens the ProShop messages page.

How it works:
  1. On startup, snapshots the current unread count as baseline
  2. Every POLL_INTERVAL seconds, checks if the count increased
  3. If new messages exist, fetches them from the end of the list
  4. Filters for human senders (not system-generated)
  5. Shows pulsing green disc with sender name if human messages found
  6. Clicking the disc opens ProShop messages and resets baseline
  7. Right-click drag to reposition the disc on screen
"""

import sys
import time
import math
import queue
import threading
import webbrowser
import tkinter as tk

import json
import requests
import config


# ============================================================================
# ProShop API Client
# ============================================================================

class ProShopMessenger:
    """Efficiently detects new human messages via unread count tracking."""

    INBOX_QUERY = """
        query ($userId: String!, $filter: UserInboxFilter, $size: Int, $start: Int) {
            user(id: $userId) {
                messages(filter: $filter, pageSize: $size, pageStart: $start) {
                    totalRecords
                    records {
                        id subject postDate isSystemSent
                        fromPlainText
                        from { firstName lastName }
                    }
                }
            }
        }
    """

    def __init__(self):
        self._token = None
        self._token_obtained_at = 0
        self._token_expires_in = 86400
        self._baseline_total = None

    def _ensure_token(self):
        now = time.time()
        if self._token and now < (self._token_obtained_at + self._token_expires_in - 300):
            return
        resp = requests.post(config.TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": config.CLIENT_ID,
            "client_secret": config.CLIENT_SECRET,
            "scope": config.SCOPE,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_obtained_at = time.time()
        self._token_expires_in = data.get("expires_in", 86400)

    def _query(self, query, variables=None):
        self._ensure_token()
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = requests.post(config.GRAPHQL_URL, json=payload, headers={
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }, timeout=30)
        if resp.status_code == 401:
            self._token = None
            self._ensure_token()
            resp = requests.post(config.GRAPHQL_URL, json=payload, headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            }, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        if "errors" in body and not body.get("data"):
            raise Exception("; ".join(e.get("message", str(e)) for e in body["errors"]))
        return body

    def _get_inbox(self, page_size=1, page_start=0):
        """Query inbox and return (totalRecords, records)."""
        result = self._query(self.INBOX_QUERY, {
            "userId": config.USER_ID,
            "filter": {"boxType": "INBOX", "showOnlyUnread": True},
            "size": page_size,
            "start": page_start,
        })
        msgs = result.get("data", {}).get("user", {}).get("messages", {})
        return msgs.get("totalRecords", 0), msgs.get("records", [])

    def check_for_new(self):
        """
        Returns (new_human_messages, total_unread).
        On first call, establishes baseline and returns empty list.
        """
        total, _ = self._get_inbox(page_size=1, page_start=0)

        if self._baseline_total is None:
            self._baseline_total = total
            return [], total

        if total > self._baseline_total:
            diff = total - self._baseline_total
            fetch_count = min(diff + 5, 50)
            start = max(0, total - fetch_count)
            _, records = self._get_inbox(page_size=fetch_count, page_start=start)

            human = [m for m in records if not m.get("isSystemSent")]
            if human:
                return human, total

        self._baseline_total = total
        return [], total

    def acknowledge(self):
        """User clicked the disc — reset baseline to current count."""
        try:
            total, _ = self._get_inbox(page_size=1, page_start=0)
            self._baseline_total = total
        except Exception:
            pass


# ============================================================================
# Pulsing Overlay Widget
# ============================================================================

class PulsingDisc:
    """Always-on-top pulsing green disc with sonar rings and sender info."""

    SIZE = 250
    DISC_R = 62
    RING_EXPAND = 32
    NUM_RINGS = 3
    MARGIN = 12

    # Color palette
    GREEN_DARK = (21, 128, 61)       # #15803d
    GREEN_MID = (34, 197, 94)        # #22c55e
    GREEN_BRIGHT = (74, 222, 128)    # #4ade80
    GREEN_GLOW = (134, 239, 172)     # #86efac

    def __init__(self, on_click=None):
        self.on_click = on_click
        self.visible = False
        self.frame = 0

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.wm_attributes('-topmost', True)

        w, h = self.SIZE, self.SIZE
        screen_w = self.root.winfo_screenwidth()
        x = screen_w - w - self.MARGIN
        y = self.MARGIN
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        bg = '#010101'
        self.root.wm_attributes('-transparentcolor', bg)
        self.root.configure(bg=bg)

        self.canvas = tk.Canvas(
            self.root, width=w, height=h,
            bg=bg, highlightthickness=0, bd=0
        )
        self.canvas.pack()

        cx, cy = w // 2, h // 2
        r = self.DISC_R

        # Sonar rings (expand outward with fading) + ring labels
        self.rings = []
        self.ring_labels = []
        for _ in range(self.NUM_RINGS):
            ring = self.canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                fill='', outline='#22c55e', width=2, state='hidden'
            )
            label = self.canvas.create_text(
                cx, cy + r, text="CLICK HERE", fill='#22c55e',
                font=("Segoe UI", 14, "bold"), state='hidden'
            )
            self.rings.append(ring)
            self.ring_labels.append(label)

        # Outer glow disc (slightly larger, semi-transparent look)
        self.glow_disc = self.canvas.create_oval(
            cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3,
            fill='#166534', outline='', width=0
        )

        # Main disc
        self.disc = self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill='#22c55e', outline='#15803d', width=3
        )

        # Inner highlight (top-left, gives 3D dome effect)
        hr = r - 20
        self.highlight = self.canvas.create_oval(
            cx - hr - 8, cy - hr - 12,
            cx + hr - 16, cy + hr - 24,
            fill='#4ade80', outline='', width=0
        )

        # Text: "NEW"
        self.text_new = self.canvas.create_text(
            cx, cy - 22, text="NEW", fill="white",
            font=("Segoe UI", 15, "bold")
        )

        # Text: "MESSAGE"
        self.text_msg = self.canvas.create_text(
            cx, cy - 2, text="MESSAGE", fill="#f0fdf4",
            font=("Segoe UI", 10, "bold")
        )

        # Thin separator
        self.sep = self.canvas.create_line(
            cx - 32, cy + 14, cx + 32, cy + 14,
            fill='#bbf7d0', width=1
        )

        # Sender name (prominent)
        self.text_sender = self.canvas.create_text(
            cx, cy + 30, text="", fill="white",
            font=("Segoe UI", 11, "bold")
        )

        # Message count (below sender if multiple)
        self.text_count = self.canvas.create_text(
            cx, cy + 46, text="", fill="#bbf7d0",
            font=("Segoe UI", 8)
        )

        # Click binding on all elements
        all_items = [
            self.glow_disc, self.disc, self.highlight,
            self.text_new, self.text_msg, self.sep,
            self.text_sender, self.text_count,
        ] + self.rings + self.ring_labels
        for item in all_items:
            self.canvas.tag_bind(item, '<Button-1>', self._handle_click)
        self.canvas.bind('<Button-1>', self._handle_click)

        # Right-click drag to reposition
        self._drag_data = {"x": 0, "y": 0}
        self.canvas.bind('<ButtonPress-3>', self._drag_start)
        self.canvas.bind('<B3-Motion>', self._drag_motion)

        self._animate()

    def _handle_click(self, event):
        if self.on_click:
            self.on_click()

    def _drag_start(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _drag_motion(self, event):
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")

    @staticmethod
    def _lerp_color(c1, c2, t):
        """Interpolate between two RGB tuples."""
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _animate(self):
        if self.visible:
            self.frame += 1
            cx, cy = self.SIZE // 2, self.SIZE // 2
            cycle = 90  # frames per full cycle (~3s at 30fps)

            # ── Main disc pulse ──
            t = (self.frame % cycle) / cycle
            wave = math.sin(t * 2 * math.pi)
            intensity = 0.5 + 0.5 * wave

            disc_color = self._lerp_color(self.GREEN_MID, self.GREEN_BRIGHT, intensity)
            pr = self.DISC_R + int(3 * wave)
            self.canvas.coords(
                self.disc,
                cx - pr, cy - pr, cx + pr, cy + pr
            )
            self.canvas.itemconfig(self.disc, fill=disc_color)

            # Glow disc follows
            gr = pr + 3
            self.canvas.coords(
                self.glow_disc,
                cx - gr, cy - gr, cx + gr, cy + gr
            )
            glow_color = self._lerp_color(self.GREEN_DARK, (22, 101, 52), intensity)
            self.canvas.itemconfig(self.glow_disc, fill=glow_color)

            # Highlight shimmer
            hi = intensity * 0.6 + 0.2
            hl_color = self._lerp_color(self.GREEN_MID, self.GREEN_GLOW, hi)
            self.canvas.itemconfig(self.highlight, fill=hl_color)

            # ── Sonar rings + labels ──
            ring_cycle = 120  # slower cycle for rings
            for i, ring in enumerate(self.rings):
                label = self.ring_labels[i]
                phase = ((self.frame + i * (ring_cycle // self.NUM_RINGS)) % ring_cycle) / ring_cycle
                # Expand from disc edge outward
                expand = phase * self.RING_EXPAND
                rr = self.DISC_R + expand
                self.canvas.coords(ring, cx - rr, cy - rr, cx + rr, cy + rr)

                # Move label to bottom of ring
                self.canvas.coords(label, cx, cy + rr + 8)

                # Fade out as it expands
                fade = 1.0 - phase
                ring_color = self._lerp_color(
                    (1, 1, 1),  # near-transparent (close to bg)
                    self.GREEN_MID,
                    fade * fade  # quadratic fade for smoother falloff
                )
                # Width thins as it expands
                ring_width = max(1, int(3 * fade))
                self.canvas.itemconfig(ring, outline=ring_color, width=ring_width, state='normal')
                self.canvas.itemconfig(label, fill=ring_color, state='normal')

            # ── Text pulse ──
            tv = int(210 + 45 * wave)
            self.canvas.itemconfig(self.text_new, fill=f"#{tv:02x}{tv:02x}{tv:02x}")
            ts = int(230 + 25 * wave)
            self.canvas.itemconfig(self.text_sender, fill=f"#{ts:02x}{ts:02x}{ts:02x}")

        self.root.after(33, self._animate)

    def show(self, count=1, sender=""):
        # Format sender display
        if sender:
            self.canvas.itemconfig(self.text_sender, text=sender)
        else:
            self.canvas.itemconfig(self.text_sender, text="")

        if count > 1:
            self.canvas.itemconfig(self.text_count, text=f"{count} messages")
        else:
            self.canvas.itemconfig(self.text_count, text="")

        if not self.visible:
            self.visible = True
            self.frame = 0
            # Show rings and labels
            for ring in self.rings:
                self.canvas.itemconfig(ring, state='normal')
            for label in self.ring_labels:
                self.canvas.itemconfig(label, state='normal')
            self.root.deiconify()

    def hide(self):
        if self.visible:
            self.visible = False
            for ring in self.rings:
                self.canvas.itemconfig(ring, state='hidden')
            for label in self.ring_labels:
                self.canvas.itemconfig(label, state='hidden')
            self.root.withdraw()

    def test_show(self):
        """Show the disc briefly for visual testing."""
        self.show(1, "Ben Simon")


# ============================================================================
# Main Application
# ============================================================================

class MessageNotifier:
    """Ties the API poller to the overlay widget."""

    def __init__(self, test_mode=False):
        self.api = ProShopMessenger()
        self.result_queue = queue.Queue()
        self.disc = PulsingDisc(on_click=self._on_disc_click)
        self.test_mode = test_mode

        if test_mode:
            # Show disc immediately for visual testing
            self.disc.root.after(500, self.disc.test_show)
        else:
            # Start polling (interval set in config.POLL_INTERVAL)
            self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
            self.poll_thread.start()
            self.disc.root.after(2000, self._check_queue)

    def _write_heartbeat(self, status="ok", error=""):
        """Write heartbeat file for overseer monitoring."""
        try:
            with open(config.HEARTBEAT_PATH, "w") as f:
                json.dump({
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "status": status,
                    "error": error,
                    "user_id": config.USER_ID,
                    "poll_interval": config.POLL_INTERVAL,
                }, f)
        except Exception:
            pass

    def _single_check(self):
        """One-time check on startup (auto-poll disabled to reduce API load)."""
        try:
            messages, total = self.api.check_for_new()
            self.result_queue.put(("ok", messages, total))
            self._write_heartbeat("ok")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Initial check error: {e}")
            self.result_queue.put(("error", [], 0))
            self._write_heartbeat("error", str(e))

    def _poll_loop(self):
        """Background: poll API, push results to queue."""
        while True:
            try:
                messages, total = self.api.check_for_new()
                self.result_queue.put(("ok", messages, total))
                self._write_heartbeat("ok")
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] Poll error: {e}")
                self.result_queue.put(("error", [], 0))
                self._write_heartbeat("error", str(e))
            time.sleep(config.POLL_INTERVAL)

    def _check_queue(self):
        """Main thread: read queue, update UI."""
        try:
            while True:
                status, messages, total = self.result_queue.get_nowait()
                if status == "error":
                    continue
                if messages:
                    sender = ""
                    if len(messages) >= 1:
                        frm = messages[0].get("from") or {}
                        first = frm.get("firstName", "")
                        last = frm.get("lastName", "")
                        sender = f"{first} {last[0]}." if last else first
                    self.disc.show(len(messages), sender)
                    print(f"[{time.strftime('%H:%M:%S')}] {len(messages)} new human message(s)")
                    for m in messages:
                        f = m.get("from", {})
                        print(f"  From: {f.get('firstName','')} {f.get('lastName','')} — {m.get('subject','')}")
                else:
                    self.disc.hide()
        except queue.Empty:
            pass
        self.disc.root.after(1000, self._check_queue)

    def _on_disc_click(self):
        """Open ProShop messages and acknowledge."""
        webbrowser.open(config.MESSAGES_URL)
        self.api.acknowledge()
        self.disc.hide()

    def run(self):
        print(f"ProShop Message Notifier running")
        print(f"  User: {config.USER_ID}")
        print(f"  Poll interval: {config.POLL_INTERVAL}s")
        print(f"  Click disc to open: {config.MESSAGES_URL}")
        if self.test_mode:
            print(f"  TEST MODE — showing disc immediately")
        self.disc.root.mainloop()


# ============================================================================

if __name__ == "__main__":
    if not config.CLIENT_SECRET:
        print("ERROR: PROSHOP_CLIENT_SECRET environment variable not set.")
        print("Set it before running: set PROSHOP_CLIENT_SECRET=<your secret>")
        sys.exit(1)

    test = "--test" in sys.argv
    app = MessageNotifier(test_mode=test)
    app.run()
