"""Generate a FICTIONAL 7-day alarm log for an aseptic vial-filling line.
Not from any real plant. Run:  python sample/make_sample.py"""
import csv
import os
import random
from datetime import datetime, timedelta

random.seed(42)
START = datetime(2026, 11, 2, 0, 0, 0)
DAYS = 7

# tag, message, priority, relative frequency
TAGS = [
    ("FIL3_STOPPER_BOWL_LOW", "Filler 3 stopper bowl level low", "Low", 9),
    ("FIL3_NEEDLE_BLOCK", "Filler 3 filling needle blocked", "High", 1),
    ("FIL3_CHECKWEIGH_REJ", "Filler 3 check-weigh reject rate high", "Medium", 4),
    ("INS3_REJECT_BIN_FULL", "Inspection 3 reject bin full", "Low", 3),
    ("INS3_CAMERA_FAULT", "Inspection 3 camera 2 fault", "Medium", 1),
    ("TUN1_BELT_SPEED_DEV", "Depyro tunnel belt speed deviation", "Medium", 3),
    ("TUN1_HOT_ZONE_TEMP_LO", "Depyro tunnel hot-zone temperature low", "High", 1),
    ("WSH2_FINAL_RINSE_COND", "Vial washer final rinse conductivity high", "Medium", 2),
    ("RAB3_GLOVE_INTEGRITY", "RABS 3 glove integrity test failed", "High", 1),
    ("RAB3_DP_LOW", "RABS 3 differential pressure low", "High", 2),
    ("CAP3_TORQUE_DEV", "Capper 3 torque deviation", "Low", 5),
    ("CONV3_ACCUM_FULL", "Conveyor 3 accumulation table full", "Low", 8),
    ("WFI_LOOP_TEMP_LO", "WFI loop return temperature low", "Medium", 1),
    ("PW_TOC_HIGH", "Purified water TOC high", "Medium", 1),
    ("CDA_HDR_PRESS_LO", "Clean dry air header pressure low", "Medium", 1),
    ("N2_SUPPLY_PRESS_LO", "Nitrogen supply pressure low", "Medium", 1),
    ("RAB3_DOOR_BYPASS", "RABS 3 door interlock bypass active", "High", 0),
]
INFO = {t[0]: t for t in TAGS}
events = []


def alarm(tag, t, clear_after_s=None):
    _, msg, pri, _ = INFO[tag]
    events.append((t, tag, msg, pri, "Came In"))
    events.append((t + timedelta(seconds=random.randint(20, 300)), tag, msg, pri, "Acknowledged"))
    if clear_after_s is not False:
        events.append((t + timedelta(seconds=clear_after_s or random.randint(60, 1800)), tag, msg, pri, "Went Out"))


# background load: roughly 1.3 alarms per 10 minutes
weights = [t[3] for t in TAGS]
t = START
end = START + timedelta(days=DAYS)
while True:
    t += timedelta(seconds=random.expovariate(1.3 / 600))
    if t >= end:
        break
    alarm(random.choices(TAGS, weights)[0][0], t)

# chattering reject-bin switch: bursts of 3-6 within ~40 s, a few times a day
for d in range(DAYS):
    for _ in range(random.randint(3, 6)):
        b = START + timedelta(days=d, seconds=random.randint(0, 86000))
        for i in range(random.randint(3, 6)):
            alarm("INS3_REJECT_BIN_FULL", b + timedelta(seconds=i * random.randint(5, 9)), clear_after_s=3)

# flood: clean-air header dip on day 3 cascades through the line
f0 = START + timedelta(days=2, hours=14, minutes=3)
alarm("CDA_HDR_PRESS_LO", f0, clear_after_s=900)
for i in range(70):
    tag = random.choice(["RAB3_DP_LOW", "FIL3_NEEDLE_BLOCK", "CAP3_TORQUE_DEV", "CONV3_ACCUM_FULL",
                         "FIL3_CHECKWEIGH_REJ", "TUN1_BELT_SPEED_DEV", "INS3_CAMERA_FAULT", "N2_SUPPLY_PRESS_LO"])
    alarm(tag, f0 + timedelta(seconds=10 + i * random.uniform(4, 11)))

# stale: a bypass alarm that came in on day 2 and never cleared
alarm("RAB3_DOOR_BYPASS", START + timedelta(days=1, hours=9, minutes=41), clear_after_s=False)

events.sort(key=lambda e: e[0])
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alarm_log_sample.csv")
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Timestamp", "Tag", "Message", "Priority", "State"])
    for ts, tag, msg, pri, st in events:
        w.writerow([ts.strftime("%Y-%m-%d %H:%M:%S"), tag, msg, pri, st])
print(f"Wrote {len(events)} events to {out}")
