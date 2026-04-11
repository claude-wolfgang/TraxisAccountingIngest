#!/usr/bin/env python3
"""
Traxis Clock-In/Out Feedback Display
Displays personalized feedback when employees clock in or out.

Run this on a dedicated display near the time clock.
It polls ProShop for clock events and shows feedback.

Version: 1.0.0
Build Date: 2026-01-23

Usage:
    python clock_feedback_display_v1_0_0.py
"""

VERSION = "1.0.0"
BUILD_DATE = "2026-01-23"

import requests
import json
import tkinter as tk
from tkinter import font as tkfont
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import time
import os

# === CONFIGURATION ===
CLIENT_ID = "3923-9C1C-7291"
CLIENT_SECRET = ""  # Set this or use environment variable PROSHOP_CLIENT_SECRET
TOKEN_URL = "https://traxismfg.adionsystems.com/home/member/oauth/accesstoken"
GRAPHQL_URL = "https://traxismfg.adionsystems.com/api/graphql"
SCOPES = "parts:rwdp+workorders:rwdp+users:r+toolpots:r"

# Polling interval in seconds
POLL_INTERVAL = 30

# How long to show the feedback message (seconds)
MESSAGE_DISPLAY_TIME = 15

# Data file for tracking metrics
DATA_FILE = "clock_feedback_data.json"

# === COLORS ===
BG_COLOR = "#1a1a2e"
TEXT_COLOR = "#ffffff"
ACCENT_COLOR = "#4ecca3"
SECONDARY_COLOR = "#7f8c8d"
GOOD_COLOR = "#2ecc71"
WARN_COLOR = "#f39c12"


class ProShopAPI:
    """Handle ProShop API communication."""
    
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expires = None
    
    def get_token(self):
        """Get or refresh access token."""
        if self.token and self.token_expires and datetime.now() < self.token_expires:
            return self.token
        
        response = requests.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": SCOPES
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            self.token = data.get("access_token")
            # Assume 1 hour expiry, refresh at 50 minutes
            self.token_expires = datetime.now() + timedelta(minutes=50)
            return self.token
        else:
            print(f"Token error: {response.text}")
            return None
    
    def query(self, query_str, variables=None):
        """Execute GraphQL query."""
        token = self.get_token()
        if not token:
            return None
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        payload = {"query": query_str}
        if variables:
            payload["variables"] = variables
        
        response = requests.post(GRAPHQL_URL, headers=headers, json=payload)
        result = response.json()
        
        if "errors" in result:
            print(f"Query error: {result['errors']}")
        
        return result.get("data")
    
    def get_latest_clock_punches(self):
        """Get latest clock punch for each user."""
        query = """
        query {
          clockPunch {
            latestClockPunches(pageSize: 50) {
              records {
                clockPunchId
                punchDate
                inOrOut
                operator
              }
            }
          }
        }
        """
        data = self.query(query)
        if data:
            return data.get("clockPunch", {}).get("latestClockPunches", {}).get("records", [])
        return []
    
    def get_users(self):
        """Get all active users."""
        query = """
        query {
          users(pageSize: 50) {
            records {
              id
              firstName
              lastName
              isActive
            }
          }
        }
        """
        data = self.query(query)
        if data:
            return data.get("users", {}).get("records", [])
        return []
    
    def get_user_time_tracking(self, user_id, days_back=7):
        """Get time tracking entries for a user."""
        query = """
        query($userId: String!) {
          user(id: $userId) {
            firstName
            lastName
            timeTracking(pageSize: 100) {
              totalRecords
              records {
                timeIn
                timeOut
                status
                operationNumber
                workOrderPlainText
                spentDoing
                qtyRun
              }
            }
            timeClock(pageSize: 50) {
              records {
                punchDate
                inOrOut
              }
            }
          }
        }
        """
        data = self.query(query, {"userId": user_id})
        if data:
            return data.get("user")
        return None


class MetricsTracker:
    """Track and calculate employee metrics."""
    
    def __init__(self, data_file):
        self.data_file = data_file
        self.data = self.load_data()
    
    def load_data(self):
        """Load saved metrics data."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"daily_metrics": {}, "employee_stats": {}}
    
    def save_data(self):
        """Save metrics data."""
        with open(self.data_file, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def get_today_key(self):
        return datetime.now().strftime("%Y-%m-%d")
    
    def get_week_start(self):
        today = datetime.now()
        return (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
    
    def record_clock_event(self, user_id, event_type, timestamp):
        """Record a clock in/out event."""
        today = self.get_today_key()
        
        if today not in self.data["daily_metrics"]:
            self.data["daily_metrics"][today] = {}
        
        if user_id not in self.data["daily_metrics"][today]:
            self.data["daily_metrics"][today][user_id] = {
                "clock_in": None,
                "clock_out": None,
                "hours_worked": 0
            }
        
        if event_type == "in":
            self.data["daily_metrics"][today][user_id]["clock_in"] = timestamp
        else:
            self.data["daily_metrics"][today][user_id]["clock_out"] = timestamp
            # Calculate hours if we have both
            clock_in = self.data["daily_metrics"][today][user_id].get("clock_in")
            if clock_in:
                try:
                    t_in = datetime.fromisoformat(clock_in.replace('Z', '+00:00'))
                    t_out = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    hours = (t_out - t_in).total_seconds() / 3600
                    self.data["daily_metrics"][today][user_id]["hours_worked"] = round(hours, 2)
                except:
                    pass
        
        self.save_data()
    
    def get_employee_stats(self, user_id):
        """Get stats for an employee."""
        today = self.get_today_key()
        week_start = self.get_week_start()
        
        # Calculate week hours
        week_hours = 0
        days_worked = 0
        
        for date_key, day_data in self.data.get("daily_metrics", {}).items():
            if date_key >= week_start and user_id in day_data:
                hours = day_data[user_id].get("hours_worked", 0)
                if hours > 0:
                    week_hours += hours
                    days_worked += 1
        
        # Yesterday's hours
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_hours = 0
        if yesterday in self.data.get("daily_metrics", {}):
            yesterday_hours = self.data["daily_metrics"][yesterday].get(user_id, {}).get("hours_worked", 0)
        
        return {
            "week_hours": round(week_hours, 1),
            "days_worked": days_worked,
            "yesterday_hours": round(yesterday_hours, 1)
        }


class FeedbackDisplay:
    """Main display window."""
    
    def __init__(self, api: ProShopAPI, tracker: MetricsTracker):
        self.api = api
        self.tracker = tracker
        self.users = {}
        self.last_punches = {}
        self.current_message = None
        self.message_timer = None
        
        # Load users
        self.refresh_users()
        
        # Setup window
        self.root = tk.Tk()
        self.root.title("Traxis - Clock Feedback")
        self.root.configure(bg=BG_COLOR)
        
        # Fullscreen toggle with Escape
        self.root.bind("<Escape>", self.toggle_fullscreen)
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.fullscreen = False
        
        # Set initial size
        self.root.geometry("800x480")
        
        # Fonts
        self.font_large = tkfont.Font(family="Helvetica", size=48, weight="bold")
        self.font_medium = tkfont.Font(family="Helvetica", size=24)
        self.font_small = tkfont.Font(family="Helvetica", size=16)
        self.font_stat = tkfont.Font(family="Helvetica", size=32, weight="bold")
        
        # Create widgets
        self.create_widgets()
        
        # Start with idle display
        self.show_idle_display()
        
        # Start polling
        self.poll_thread = threading.Thread(target=self.poll_loop, daemon=True)
        self.poll_thread.start()
    
    def refresh_users(self):
        """Load users from ProShop."""
        users = self.api.get_users()
        for u in users:
            if u.get("isActive"):
                self.users[u["id"]] = {
                    "firstName": u.get("firstName", ""),
                    "lastName": u.get("lastName", "")
                }
    
    def create_widgets(self):
        """Create the UI widgets."""
        # Main container
        self.main_frame = tk.Frame(self.root, bg=BG_COLOR)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=30)
        
        # Greeting label
        self.greeting_label = tk.Label(
            self.main_frame,
            text="",
            font=self.font_large,
            fg=TEXT_COLOR,
            bg=BG_COLOR
        )
        self.greeting_label.pack(pady=(20, 10))
        
        # Date label
        self.date_label = tk.Label(
            self.main_frame,
            text="",
            font=self.font_small,
            fg=SECONDARY_COLOR,
            bg=BG_COLOR
        )
        self.date_label.pack(pady=(0, 30))
        
        # Stats frame
        self.stats_frame = tk.Frame(self.main_frame, bg=BG_COLOR)
        self.stats_frame.pack(fill=tk.X, pady=20)
        
        # Stat boxes
        self.stat_boxes = []
        for i in range(3):
            frame = tk.Frame(self.stats_frame, bg="#2d2d44", padx=20, pady=15)
            frame.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=10)
            
            value_label = tk.Label(frame, text="--", font=self.font_stat, fg=ACCENT_COLOR, bg="#2d2d44")
            value_label.pack()
            
            title_label = tk.Label(frame, text="", font=self.font_small, fg=SECONDARY_COLOR, bg="#2d2d44")
            title_label.pack()
            
            self.stat_boxes.append({"frame": frame, "value": value_label, "title": title_label})
        
        # Message label
        self.message_label = tk.Label(
            self.main_frame,
            text="",
            font=self.font_medium,
            fg=TEXT_COLOR,
            bg=BG_COLOR,
            wraplength=700
        )
        self.message_label.pack(pady=30)
        
        # Status bar
        self.status_label = tk.Label(
            self.root,
            text="",
            font=self.font_small,
            fg=SECONDARY_COLOR,
            bg=BG_COLOR,
            anchor="e"
        )
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=10)
    
    def toggle_fullscreen(self, event=None):
        """Toggle fullscreen mode."""
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)
    
    def show_idle_display(self):
        """Show the default idle screen."""
        now = datetime.now()
        
        self.greeting_label.config(text="Traxis Manufacturing")
        self.date_label.config(text=now.strftime("%A, %B %d, %Y"))
        
        # Hide stat boxes in idle mode
        for box in self.stat_boxes:
            box["value"].config(text="")
            box["title"].config(text="")
        
        self.message_label.config(text="Clock in to see your stats", fg=SECONDARY_COLOR)
        self.status_label.config(text=f"Last updated: {now.strftime('%H:%M:%S')}")
    
    def show_clock_in_message(self, user_id, punch_time):
        """Show clock-in feedback."""
        user = self.users.get(user_id, {"firstName": "Team", "lastName": "Member"})
        first_name = user["firstName"]
        
        now = datetime.now()
        stats = self.tracker.get_employee_stats(user_id)
        
        # Greeting based on time of day
        hour = now.hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
        
        self.greeting_label.config(text=f"{greeting}, {first_name}")
        self.date_label.config(text=now.strftime("%A, %B %d"))
        
        # Stats
        self.stat_boxes[0]["value"].config(text=f"{stats['yesterday_hours']}", fg=ACCENT_COLOR)
        self.stat_boxes[0]["title"].config(text="Yesterday")
        
        self.stat_boxes[1]["value"].config(text=f"{stats['week_hours']}", fg=ACCENT_COLOR)
        self.stat_boxes[1]["title"].config(text="This Week")
        
        self.stat_boxes[2]["value"].config(text=f"{stats['days_worked']}", fg=ACCENT_COLOR)
        self.stat_boxes[2]["title"].config(text="Days")
        
        # Motivational message
        messages = [
            "Let's have a great day!",
            "Ready to make some chips!",
            "Time to get it done.",
            "Another day, another part.",
        ]
        import random
        self.message_label.config(text=random.choice(messages), fg=TEXT_COLOR)
        
        # Schedule return to idle
        self.schedule_idle_return()
    
    def show_clock_out_message(self, user_id, punch_time):
        """Show clock-out feedback."""
        user = self.users.get(user_id, {"firstName": "Team", "lastName": "Member"})
        first_name = user["firstName"]
        
        now = datetime.now()
        stats = self.tracker.get_employee_stats(user_id)
        
        self.greeting_label.config(text=f"Nice work, {first_name}")
        self.date_label.config(text=now.strftime("%A, %B %d"))
        
        # Today's stats
        today_key = self.tracker.get_today_key()
        today_data = self.tracker.data.get("daily_metrics", {}).get(today_key, {}).get(user_id, {})
        today_hours = today_data.get("hours_worked", 0)
        
        self.stat_boxes[0]["value"].config(text=f"{round(today_hours, 1)}", fg=GOOD_COLOR)
        self.stat_boxes[0]["title"].config(text="Today")
        
        self.stat_boxes[1]["value"].config(text=f"{stats['week_hours'] + today_hours:.1f}", fg=ACCENT_COLOR)
        self.stat_boxes[1]["title"].config(text="This Week")
        
        self.stat_boxes[2]["value"].config(text=f"{stats['days_worked'] + 1}", fg=ACCENT_COLOR)
        self.stat_boxes[2]["title"].config(text="Days")
        
        self.message_label.config(text="See you tomorrow!", fg=TEXT_COLOR)
        
        # Schedule return to idle
        self.schedule_idle_return()
    
    def schedule_idle_return(self):
        """Schedule return to idle display."""
        if self.message_timer:
            self.root.after_cancel(self.message_timer)
        self.message_timer = self.root.after(MESSAGE_DISPLAY_TIME * 1000, self.show_idle_display)
    
    def process_clock_events(self, punches):
        """Process clock punch events."""
        for punch in punches:
            user_id = punch.get("operator")
            punch_id = punch.get("clockPunchId")
            punch_date = punch.get("punchDate")
            in_or_out = punch.get("inOrOut")
            
            if not user_id or not punch_id:
                continue
            
            # Skip if we've already processed this punch
            if self.last_punches.get(user_id) == punch_id:
                continue
            
            # Check if this is a recent punch (within last 2 minutes)
            try:
                punch_time = datetime.fromisoformat(punch_date.replace('Z', '+00:00'))
                now = datetime.now(punch_time.tzinfo)
                age = (now - punch_time).total_seconds()
                
                if age > 120:  # Older than 2 minutes, skip
                    self.last_punches[user_id] = punch_id
                    continue
            except Exception as e:
                print(f"Date parse error: {e}")
                continue
            
            # Record and display
            self.last_punches[user_id] = punch_id
            self.tracker.record_clock_event(user_id, in_or_out, punch_date)
            
            # Update display on main thread
            if in_or_out == "in":
                self.root.after(0, lambda u=user_id, t=punch_date: self.show_clock_in_message(u, t))
            else:
                self.root.after(0, lambda u=user_id, t=punch_date: self.show_clock_out_message(u, t))
    
    def poll_loop(self):
        """Background polling loop."""
        # Initialize last punches on first run
        initial_punches = self.api.get_latest_clock_punches()
        for punch in initial_punches:
            user_id = punch.get("operator")
            punch_id = punch.get("clockPunchId")
            if user_id and punch_id:
                self.last_punches[user_id] = punch_id
        
        while True:
            time.sleep(POLL_INTERVAL)
            try:
                punches = self.api.get_latest_clock_punches()
                self.process_clock_events(punches)
                
                # Update status
                now = datetime.now()
                self.root.after(0, lambda: self.status_label.config(
                    text=f"Last updated: {now.strftime('%H:%M:%S')}"
                ))
            except Exception as e:
                print(f"Poll error: {e}")
    
    def run(self):
        """Start the display."""
        self.root.mainloop()


def main():
    print("=" * 50)
    print(f"Traxis Clock-In/Out Feedback Display v{VERSION}")
    print(f"Build: {BUILD_DATE}")
    print("=" * 50)
    
    # Get client secret
    secret = CLIENT_SECRET or os.environ.get("PROSHOP_CLIENT_SECRET", "")
    
    if not secret:
        print("\nNo client secret configured.")
        print("Either set CLIENT_SECRET in the script or")
        print("set the PROSHOP_CLIENT_SECRET environment variable.")
        secret = input("\nEnter client secret: ").strip()
    
    if not secret:
        print("No secret provided. Exiting.")
        return
    
    # Initialize
    api = ProShopAPI(CLIENT_ID, secret)
    
    # Test connection
    print("\nTesting API connection...")
    token = api.get_token()
    if not token:
        print("Failed to connect to ProShop API")
        return
    print("✅ Connected to ProShop")
    
    # Initialize tracker
    tracker = MetricsTracker(DATA_FILE)
    
    # Start display
    print("\nStarting display...")
    print("Press F11 or Escape to toggle fullscreen")
    print("Close window to exit")
    
    display = FeedbackDisplay(api, tracker)
    display.run()


if __name__ == "__main__":
    main()
