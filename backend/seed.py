"""
Seed script — populates Supabase with 4 weeks of realistic workout data.

Run with the backend live:
  1. Start the backend: uvicorn main:app --reload
  2. Set USER_ID below to your Supabase user UUID (find it in Supabase → Auth → Users)
  3. Run: python seed.py

Designed so eval.py questions are answerable:
  - Bench press progression: 70 → 75 → 80 → 82.5 → 85kg
  - Legs 2x/week, upper 3x/week (visible frequency imbalance)
  - 3 cardio sessions with improving pace (27 → 26 → 25 min)
  - One session with explicit exercise ordering (triceps before bench)
  - Pull-up and row progression for pulling strength questions
"""

import requests
import time

USER_ID = ""   # paste your Supabase user UUID here
API     = "http://127.0.0.1:8000"

WORKOUTS = [
    # ── Week 1 ─────────────────────────────────────────────────────────────────
    (
        "Monday chest and triceps — week 1: started with tricep pushdowns 3x15 at 20kg, "
        "then bench press 4x8 at 70kg. Felt a bit weak on bench — probably pre-fatigued "
        "from the pushdowns. Overhead press 3x10 at 40kg to finish."
    ),
    (
        "Wednesday back and biceps — week 1: pull-ups 4 sets to failure (8, 7, 6, 6 reps). "
        "Barbell rows 3x10 at 60kg. Bicep curls 3x12 at 15kg each arm."
    ),
    (
        "Friday legs — week 1: squat 4x6 at 80kg, felt solid. "
        "Romanian deadlift 3x10 at 60kg. Leg press 3x15 at 120kg."
    ),
    (
        "Sunday cardio — week 1: ran 5km in 27 minutes. Steady pace throughout, "
        "nothing special but got it done."
    ),

    # ── Week 2 ─────────────────────────────────────────────────────────────────
    (
        "Monday chest and triceps — week 2: bench press 4x8 at 75kg, "
        "felt noticeably stronger than last week. Overhead press 3x10 at 42.5kg. "
        "Tricep pushdowns 3x15 at 22.5kg."
    ),
    (
        "Wednesday back and biceps — week 2: pull-ups 4 sets (9, 8, 7, 6). "
        "Barbell rows 3x10 at 62.5kg. Hammer curls 3x12."
    ),
    (
        "Friday legs — week 2: squat 4x6 at 82.5kg. "
        "Romanian deadlift 3x10 at 62.5kg. Leg curls 3x12."
    ),
    (
        "Sunday cardio — week 2: ran 5km in 26 minutes, felt good. "
        "A full minute faster than last week."
    ),

    # ── Week 3 ─────────────────────────────────────────────────────────────────
    (
        "Monday chest and triceps — week 3: bench press 4x8 at 80kg — "
        "first time over 80, big milestone. All reps clean. "
        "Overhead press 3x10 at 45kg. Tricep dips 3x10 bodyweight."
    ),
    (
        "Wednesday back and biceps — week 3: pull-ups 4 sets (10, 8, 7, 7). "
        "Barbell rows 3x10 at 65kg. Bicep curls 3x12 at 17.5kg."
    ),
    (
        "Friday legs — week 3: squat 4x5 at 85kg. Struggled badly on the last set, "
        "only got 4 reps. Romanian deadlift 3x10 at 65kg."
    ),

    # ── Week 4 ─────────────────────────────────────────────────────────────────
    (
        "Monday chest and triceps — week 4: bench press 4x8 at 82.5kg, "
        "steady progress continuing. Tricep dips 3x12 bodyweight. "
        "Overhead press 3x10 at 45kg."
    ),
    (
        "Wednesday back and biceps — week 4: pull-ups 4 sets (10, 9, 8, 7), "
        "best session yet. Barbell rows 3x10 at 67.5kg."
    ),
    (
        "Friday legs — week 4: squat 4x6 at 85kg, felt much better than last week "
        "when I struggled. All 6 reps on every set."
    ),
    (
        "Sunday cardio — week 4: ran 5km in 25 minutes — new personal best. "
        "Felt strong the whole way."
    ),

    # ── Week 5 (partial) ───────────────────────────────────────────────────────
    (
        "Monday chest — week 5: bench press 4x8 at 85kg. All reps clean, "
        "no grind. Overhead press 3x10 at 47.5kg. Best chest session in a while."
    ),
]


def main():
    if not USER_ID:
        print("ERROR: Set USER_ID at the top of this file before running.")
        return

    print(f"Seeding {len(WORKOUTS)} workouts for user {USER_ID}...\n")

    for i, text in enumerate(WORKOUTS, 1):
        try:
            res = requests.post(
                f"{API}/log",
                json={"user_id": USER_ID, "text": text},
                timeout=30,
            )
            data = res.json()
            print(f"[{i:02d}/{len(WORKOUTS)}] chunks={data.get('chunks_stored', '?')} | {text[:60]}...")
        except Exception as e:
            print(f"[{i:02d}] ERROR: {e}")
        time.sleep(0.5)   # avoid rate-limiting Voyage AI / Claude

    print(f"\nDone. Check Supabase — you should see {len(WORKOUTS)} unique raw_text entries.")


if __name__ == "__main__":
    main()
