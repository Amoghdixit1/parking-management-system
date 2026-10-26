import os
import math
from datetime import datetime

# Configuration
DATA_DIR = "parking_data"
SLOTS_FILE = os.path.join(DATA_DIR, "slots.txt")
ACTIVE_FILE = os.path.join(DATA_DIR, "active_sessions.txt")
TRANS_FILE = os.path.join(DATA_DIR, "transactions.txt")
REVENUE_FILE = os.path.join(DATA_DIR, "revenue.txt")

TIME_FMT = "%Y-%m-%d %H:%M:%S"
FLOORS = 3
SLOTS_PER_FLOOR = {"Compact": 6, "Large": 3, "EV": 2}

ALLOWED_SLOTS = {
    "compact": ["Compact", "Large"],
    "large": ["Large"],
    "ev": ["EV"],
}


# Module 1: Slot classes and polymorphism
class ParkingSlot:
    slot_type = "Generic"
    hourly_rate = 20

    def __init__(self, floor, number):
        self.location = (floor, number)
        self.slot_id = f"F{floor}-{self.slot_type[0]}{number:02d}"
        self.occupied = False

    @property
    def floor(self):
        return self.location[0]

    def calculate_fee(self, hours):
        return self.hourly_rate * hours

    def __str__(self):
        state = "OCCUPIED" if self.occupied else "FREE"
        return (
            f"{self.slot_id:<8} {self.slot_type:<8} "
            f"Rs.{self.hourly_rate}/hr  {state}"
        )


class CompactSlot(ParkingSlot):
    slot_type = "Compact"
    hourly_rate = 20


class LargeSlot(ParkingSlot):
    slot_type = "Large"
    hourly_rate = 40

    def calculate_fee(self, hours):
        return min(self.hourly_rate * hours, 400)


class EVChargingSlot(ParkingSlot):
    slot_type = "EV"
    hourly_rate = 30
    CHARGING_RATE = 25

    def calculate_fee(self, hours):
        return (self.hourly_rate + self.CHARGING_RATE) * hours


# Module 3: File management
def save_records(filename, records):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(filename, "w", encoding="utf-8") as file:
            for record in records:
                file.write(record + "\n")
    except OSError as e:
        print(f"[!] Could not save {filename}: {e}")


def load_records(filename):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            return [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        return []
    except OSError as e:
        print(f"[!] Could not read {filename}: {e}")
        return []


# Parking lot management
class ParkingLot:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.slots = []
        self.active = {}
        self.transactions = []
        self.revenue = 0.0
        self.next_ticket = 1001

        self.create_slots()
        self.load_data()

    def create_slots(self):
        slot_classes = {
            "Compact": CompactSlot,
            "Large": LargeSlot,
            "EV": EVChargingSlot,
        }

        for floor in range(1, FLOORS + 1):
            for slot_type, count in SLOTS_PER_FLOOR.items():
                for number in range(1, count + 1):
                    self.slots.append(
                        slot_classes[slot_type](floor, number)
                    )

    def load_data(self):
        # Restore active parking sessions.
        for line in load_records(ACTIVE_FILE):
            try:
                ticket, reg, category, slot_id, entry_text = line.split("|")
                slot = next(
                    s for s in self.slots if s.slot_id == slot_id
                )

                entry = datetime.strptime(entry_text, TIME_FMT)

                if slot.occupied or any(
                    session["reg"] == reg for session in self.active.values()
                ):
                    continue

                slot.occupied = True
                self.active[ticket] = {
                    "reg": reg,
                    "category": category,
                    "slot": slot,
                    "entry": entry,
                }
                self.next_ticket = max(
                    self.next_ticket, int(ticket[1:]) + 1
                )
            except (ValueError, StopIteration):
                print(f"[!] Skipping invalid active session: {line}")

        self.transactions = load_records(TRANS_FILE)

        try:
            records = load_records(REVENUE_FILE)
            if records:
                self.revenue = float(records[0])
        except ValueError:
            self.revenue = 0.0

        # Ensure all data files exist.
        self.save_active()
        self.save_slots()
        self.save_transactions()
        self.save_revenue()

    def save_slots(self):
        save_records(
            SLOTS_FILE,
            [
                f"{s.slot_id}|{s.slot_type}|{int(s.occupied)}"
                for s in self.slots
            ],
        )

    def save_active(self):
        records = []
        for ticket, session in self.active.items():
            records.append(
                f"{ticket}|{session['reg']}|{session['category']}|"
                f"{session['slot'].slot_id}|"
                f"{session['entry'].strftime(TIME_FMT)}"
            )
        save_records(ACTIVE_FILE, records)

    def save_transactions(self):
        save_records(TRANS_FILE, self.transactions)

    def save_revenue(self):
        save_records(REVENUE_FILE, [f"{self.revenue:.2f}"])

    def check_in(self, reg, category):
        category = category.lower()

        if category not in ALLOWED_SLOTS:
            raise RuntimeError("Invalid vehicle category.")

        available_types = ALLOWED_SLOTS[category]
        slot = next(
            (
                s for s in self.slots
                if not s.occupied and s.slot_type in available_types
            ),
            None,
        )

        if slot is None:
            raise RuntimeError("No suitable parking slot available.")

        ticket = f"T{self.next_ticket}"
        entry = datetime.now()

        slot.occupied = True
        self.active[ticket] = {
            "reg": reg,
            "category": category,
            "slot": slot,
            "entry": entry,
        }
        self.next_ticket += 1

        self.save_active()
        self.save_slots()

        return ticket, slot, entry

    def check_out(self, ticket):
        if ticket not in self.active:
            raise KeyError("Invalid ticket number or session not found.")

        session = self.active[ticket]
        exit_time = datetime.now()

        elapsed_seconds = max(
            0, (exit_time - session["entry"]).total_seconds()
        )
        hours = max(1, math.ceil(elapsed_seconds / 3600))

        slot = session["slot"]
        fee = slot.calculate_fee(hours)

        record = (
            f"{ticket}|{session['reg']}|{slot.slot_id}|"
            f"{session['entry'].strftime(TIME_FMT)}|"
            f"{exit_time.strftime(TIME_FMT)}|{hours}|{fee:.2f}"
        )

        slot.occupied = False
        del self.active[ticket]
        self.transactions.append(record)
        self.revenue += fee

        self.save_active()
        self.save_slots()
        self.save_transactions()
        self.save_revenue()

        return {
            "ticket": ticket,
            "reg": session["reg"],
            "slot": slot.slot_id,
            "entry": session["entry"],
            "exit": exit_time,
            "hours": hours,
            "fee": fee,
        }, fee


# User interface
def ask_category():
    print("Vehicle category:")
    print("1. Compact")
    print("2. Large")
    print("3. EV")

    choices = {"1": "compact", "2": "large", "3": "ev"}
    choice = input("Choose (1-3): ").strip()

    if choice not in choices:
        raise RuntimeError("Invalid vehicle category.")

    return choices[choice]


def print_ticket(ticket, reg, slot, entry):
    print("\n========== PARKING TICKET ==========")
    print(f"Ticket       : {ticket}")
    print(f"Registration : {reg}")
    print(f"Slot         : {slot.slot_id}")
    print(f"Slot type    : {slot.slot_type}")
    print(f"Floor        : {slot.floor}")
    print(f"Entry time   : {entry.strftime(TIME_FMT)}")
    print("====================================\n")


def print_receipt(record, billed):
    print("\n========== PARKING RECEIPT =========")
    print(f"Ticket       : {record['ticket']}")
    print(f"Registration : {record['reg']}")
    print(f"Slot         : {record['slot']}")
    print(f"Entry        : {record['entry'].strftime(TIME_FMT)}")
    print(f"Exit         : {record['exit'].strftime(TIME_FMT)}")
    print(f"Billed hours : {record['hours']}")
    print(f"Total fee    : Rs.{billed:.2f}")
    print("====================================\n")


def handle_check_in(lot):
    reg = input("Registration number: ").strip().upper()

    if not reg or not reg.replace("-", "").replace(" ", "").isalnum():
        print("[!] Invalid registration number.")
        return

    if any(s["reg"] == reg for s in lot.active.values()):
        print("[!] This vehicle is already parked.")
        return

    try:
        category = ask_category()
        ticket, slot, entry = lot.check_in(reg, category)
        print_ticket(ticket, reg, slot, entry)
    except RuntimeError as e:
        print(f"[!] {e}")


def handle_check_out(lot):
    ticket = input("Ticket number (e.g. T1001): ").strip().upper()

    try:
        record, billed = lot.check_out(ticket)
        print_receipt(record, billed)
    except KeyError as e:
        print(f"[!] {e.args[0]}")


def show_slots(lot):
    print("\n========== PARKING SLOT STATUS ==========")

    for floor in range(1, FLOORS + 1):
        print(f"\nFloor {floor}")
        for slot in lot.slots:
            if slot.floor == floor:
                print(slot)

    free = sum(not slot.occupied for slot in lot.slots)
    occupied = len(lot.slots) - free

    print(f"\nTotal slots : {len(lot.slots)}")
    print(f"Available   : {free}")
    print(f"Occupied    : {occupied}")
    print(f"Revenue     : Rs.{lot.revenue:.2f}\n")


def main():
    lot = ParkingLot()

    menu = """
===== PARKING MANAGEMENT SYSTEM =====
1. Vehicle check-in
2. Vehicle check-out
3. Show slot status
4. Exit
"""

    while True:
        print(menu)

        try:
            choice = input("Enter choice: ").strip()

            if choice == "1":
                handle_check_in(lot)
            elif choice == "2":
                handle_check_out(lot)
            elif choice == "3":
                show_slots(lot)
            elif choice == "4":
                print("Goodbye! All data has been saved.")
                break
            else:
                print("[!] Please enter a number from 1 to 4.")

        except (EOFError, KeyboardInterrupt):
            print("\nExiting. Data is saved.")
            break
        except Exception as e:
            print(f"[!] Unexpected error: {e}")


if __name__ == "__main__":
    main()
