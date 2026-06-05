"""
Fills the 2 workout entries that failed to insert during the original seed run
(entries 4 and 11 in seed.py — both hit the Voyage AI free-tier payment wall).

Run with the backend live:
  uvicorn main:app --reload
  python fill_missing.py
"""

import requests
import time

USER_ID = "6fe06b64-be37-48a9-92e5-9ed06fb2db33"
API     = "http://127.0.0.1:8000"

MISSING = [
    # Entry 4 — week 1 cardio (needed for "how has cardio pace changed" eval question)
    (
        "Sunday cardio — week 1: ran 5km in 27 minutes. Steady pace throughout, "
        "nothing special but got it done."
    ),
    # Entry 11 — week 3 legs (needed for "when did I struggle on squats" eval question)
    (
        "Friday legs — week 3: squat 4x5 at 85kg. Struggled badly on the last set, "
        "only got 4 reps. Romanian deadlift 3x10 at 65kg."
    ),
]

for i, text in enumerate(MISSING, 1):
    print(f"[{i}/{len(MISSING)}] Logging: {text[:70]}...")
    for attempt in range(3):
        try:
            res = requests.post(f"{API}/log", json={"user_id": USER_ID, "text": text}, timeout=60)
            if res.status_code == 200:
                data = res.json()
                print(f"  ✓ chunks={data.get('chunks_stored', '?')}")
                break
            else:
                print(f"  attempt {attempt+1} failed ({res.status_code}): {res.json().get('detail', '')[:80]}")
                time.sleep(5)
        except Exception as e:
            print(f"  attempt {attempt+1} error: {e}")
            time.sleep(5)
    if i < len(MISSING):
        print(f"  waiting 45s before next entry...")
        time.sleep(45)  # 3 Voyage calls per /log (embed per chunk × 2 + context call) → stay under 3 RPM

print("\nDone. Both missing entries should now be in Supabase.")
