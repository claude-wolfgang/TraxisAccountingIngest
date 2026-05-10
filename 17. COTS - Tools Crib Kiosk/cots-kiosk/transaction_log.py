import csv
import os
from datetime import datetime

FIELDS = ["timestamp", "employee", "ots_id", "item_name", "action", "quantity", "new_qty", "ref_type", "ref_number"]


class TransactionLog:
    def __init__(self, path):
        self.path = path
        if not os.path.exists(path):
            with open(path, "w", newline="") as f:
                csv.writer(f).writerow(FIELDS)

    def log(self, employee_name, ots_id, item_name, action, quantity, new_quantity,
            ref_type="", ref_number=""):
        with open(self.path, "a", newline="") as f:
            csv.writer(f).writerow([
                datetime.now().isoformat(timespec="seconds"),
                employee_name,
                ots_id,
                item_name,
                action,
                quantity,
                new_quantity,
                ref_type,
                ref_number,
            ])

    def get_recent(self, n=50):
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r") as f:
            rows = list(csv.DictReader(f))
        return list(reversed(rows[-n:]))
