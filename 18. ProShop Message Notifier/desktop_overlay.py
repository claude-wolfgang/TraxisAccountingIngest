"""
ProShop Message Notifier — Desktop Overlay
===========================================
Always-on-top pulsing green disc that appears over everything
(including minimized browsers) when new ProShop messages arrive.
Polls the Flask API server at http://10.1.1.71:5050.
"""

import sys
import math
import threading
import webbrowser
import tkinter as tk
import winsound
import requests

# ── Config ───────────────────────────────────────────────────

API_BASE = "http://10.1.1.71:5050"
POLL_SECONDS = 30
MESSAGES_URL = "https://traxismfg.adionsystems.com/procnc/users/{user_id}$formName=messageinbox"

# ── Globals ──────────────────────────────────────────────────

selected_user = None  # {"id": "001", "firstName": "Tom", "lastName": "Buerkle"}
has_notification = False
poll_timer = None


# ── Chime (background thread) ───────────────────────────────

def play_chime():
    """3-note ascending chime using Windows beep."""
    def _beep():
        winsound.Beep(523, 200)   # C5
        winsound.Beep(659, 200)   # E5
        winsound.Beep(784, 300)   # G5
    threading.Thread(target=_beep, daemon=True).start()


# ── User Selection Window ────────────────────────────────────

def show_user_selection(on_select):
    """Show a window with buttons for each employee."""
    win = tk.Tk()
    win.title("ProShop Message Notifier")
    win.configure(bg="#0f172a")
    win.attributes("-topmost", True)

    # Center on screen
    win.update_idletasks()
    w, h = 420, 500
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")

    tk.Label(win, text="Who are you?", font=("Segoe UI", 20, "bold"),
             fg="#f1f5f9", bg="#0f172a").pack(pady=(20, 15))

    # Scrollable frame
    outer = tk.Frame(win, bg="#0f172a")
    outer.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    canvas = tk.Canvas(outer, bg="#0f172a", highlightthickness=0)
    scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    frame = tk.Frame(canvas, bg="#0f172a")

    frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=frame, anchor="nw", width=370)
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Mouse wheel scrolling
    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    try:
        resp = requests.get(f"{API_BASE}/api/users", timeout=10)
        users = resp.json()
    except Exception as e:
        tk.Label(frame, text=f"Error loading users:\n{e}",
                 fg="#ef4444", bg="#0f172a", font=("Segoe UI", 11)).pack(pady=30)
        win.mainloop()
        return

    for i, u in enumerate(users):
        name = f"{u['firstName']} {u['lastName']}"
        btn = tk.Button(
            frame, text=name, font=("Segoe UI", 13, "bold"),
            bg="#1e293b", fg="#e2e8f0", activebackground="#15803d",
            activeforeground="white", relief="flat", bd=0, height=2,
            cursor="hand2",
            command=lambda user=u: [win.destroy(), on_select(user)]
        )
        btn.pack(fill="x", pady=3)
        btn.bind("<Enter>", lambda e, b=btn: b.configure(bg="#1a3a2a"))
        btn.bind("<Leave>", lambda e, b=btn: b.configure(bg="#1e293b"))

    win.mainloop()


# ── Overlay Window ───────────────────────────────────────────

class NotificationOverlay:
    """Always-on-top pulsing green disc overlay."""

    DISC_RADIUS = 110
    RING_MAX = 180
    BG_SIZE = 400

    def __init__(self):
        self.root = None
        self.canvas = None
        self.visible = False
        self.anim_step = 0
        self.sender = ""
        self.count = 0

    def create(self):
        self.root = tk.Tk()
        self.root.withdraw()  # start hidden
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#010101")
        self.root.configure(bg="#010101")

        sz = self.BG_SIZE
        # Position bottom-right of screen
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = screen_w - sz - 40
        y = screen_h - sz - 80
        self.root.geometry(f"{sz}x{sz}+{x}+{y}")

        self.canvas = tk.Canvas(self.root, width=sz, height=sz,
                                bg="#010101", highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_click)

        return self.root

    def show(self, sender, count):
        self.sender = sender
        self.count = count
        if not self.visible:
            self.visible = True
            self.anim_step = 0
            self.root.deiconify()
            self.root.lift()
            play_chime()
            self._animate()

    def hide(self):
        if self.visible:
            self.visible = False
            self.root.withdraw()

    def _on_click(self, event):
        global has_notification
        if selected_user:
            url = MESSAGES_URL.format(user_id=selected_user["id"])
            webbrowser.open(url)
            # Acknowledge
            try:
                requests.post(
                    f"{API_BASE}/api/messages/{selected_user['id']}/acknowledge",
                    timeout=5
                )
            except Exception:
                pass
        has_notification = False
        self.hide()

    def _animate(self):
        if not self.visible:
            return

        self.canvas.delete("all")
        cx = self.BG_SIZE // 2
        cy = self.BG_SIZE // 2
        r = self.DISC_RADIUS

        # Throb: scale oscillates 1.0 → 1.06
        throb = 1.0 + 0.06 * math.sin(self.anim_step * 0.05)
        tr = int(r * throb)

        # Sonar rings (3 staggered)
        for ring_idx in range(3):
            phase = (self.anim_step + ring_idx * 40) % 120
            progress = phase / 120.0
            ring_r = int(r + (self.RING_MAX - r) * progress)
            opacity_hex = max(0, int(230 * (1 - progress)))
            green = f"#{0:02x}{max(40, opacity_hex):02x}{0:02x}"
            width = max(1, int(3 * (1 - progress)))
            self.canvas.create_oval(
                cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r,
                outline=green, width=width
            )
            # "CLICK HERE" label on ring
            if 0.2 < progress < 0.7:
                label_y = cy + ring_r + 14
                if label_y < self.BG_SIZE - 5:
                    self.canvas.create_text(
                        cx, label_y, text="CLICK HERE",
                        font=("Segoe UI", 9, "bold"), fill=green
                    )

        # Main disc (green gradient approximation)
        for i in range(tr, 0, -2):
            frac = i / tr
            g = int(197 - 60 * (1 - frac))
            color = f"#22{min(255, g):02x}5e"
            self.canvas.create_oval(
                cx - i, cy - i, cx + i, cy + i,
                fill=color, outline=""
            )

        # Glow
        glow_r = tr + 15
        for gi in range(15, 0, -1):
            gr = tr + gi
            alpha = int(40 * (gi / 15))
            glow_color = f"#22{min(255, 100 + alpha):02x}5e"
            self.canvas.create_oval(
                cx - gr, cy - gr, cx + gr, cy + gr,
                outline=glow_color, width=1
            )

        # Text on disc
        self.canvas.create_text(
            cx, cy - 28, text="NEW",
            font=("Segoe UI", 22, "bold"), fill="white"
        )
        self.canvas.create_text(
            cx, cy - 4, text="MESSAGE",
            font=("Segoe UI", 13, "bold"), fill="#ffffffdd"
        )
        # Separator line
        self.canvas.create_line(
            cx - 35, cy + 16, cx + 35, cy + 16,
            fill="#ffffff99", width=1
        )
        # Sender
        if self.sender:
            self.canvas.create_text(
                cx, cy + 36, text=self.sender,
                font=("Segoe UI", 14, "bold"), fill="white"
            )
        # Count
        if self.count > 1:
            self.canvas.create_text(
                cx, cy + 56, text=f"{self.count} messages",
                font=("Segoe UI", 10), fill="#ffffffbb"
            )

        self.anim_step += 1
        self.root.after(33, self._animate)  # ~30 FPS


# ── Polling ──────────────────────────────────────────────────

def poll_messages(overlay):
    global has_notification

    if not selected_user:
        schedule_poll(overlay)
        return

    try:
        resp = requests.get(
            f"{API_BASE}/api/messages/{selected_user['id']}/check",
            timeout=10
        )
        data = resp.json()

        if data.get("has_new"):
            if not has_notification:
                has_notification = True
                overlay.show(data.get("sender", ""), data.get("count", 1))
            else:
                # Update text if already showing
                overlay.sender = data.get("sender", "")
                overlay.count = data.get("count", 1)
        else:
            if has_notification:
                has_notification = False
                overlay.hide()
    except Exception as e:
        print(f"Poll error: {e}")

    schedule_poll(overlay)


def schedule_poll(overlay):
    overlay.root.after(POLL_SECONDS * 1000, lambda: poll_messages(overlay))


# ── Main ─────────────────────────────────────────────────────

def start_monitoring(user):
    global selected_user
    selected_user = user
    print(f"Monitoring messages for {user['firstName']} {user['lastName']} (ID: {user['id']})")

    overlay = NotificationOverlay()
    root = overlay.create()

    # Start polling after a short delay
    root.after(1000, lambda: poll_messages(overlay))

    # Status message
    root.after(100, lambda: print("Desktop overlay running. Close this window to stop."))

    root.mainloop()


if __name__ == "__main__":
    # Accept optional --user "FirstName LastName" arg
    if len(sys.argv) >= 3 and sys.argv[1] == "--user":
        name = " ".join(sys.argv[2:])
        try:
            resp = requests.get(f"{API_BASE}/api/users/lookup", params={"name": name}, timeout=10)
            if resp.ok:
                start_monitoring(resp.json())
            else:
                print(f"User not found: {name}")
                sys.exit(1)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        show_user_selection(start_monitoring)
