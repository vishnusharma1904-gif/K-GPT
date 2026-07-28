"""Derive a student's CURRENT academic year + semester from their admission
(batch) year and today's date, so the cohort advances automatically with time
and never needs a manual update.

Academic calendar (typical Indian university):
  * The academic year starts in **July**.
  * **Odd** semester  ≈ Jul–Dec  (semester 1 within the year)
  * **Even** semester ≈ Jan–Jun  (semester 2 within the year)
"""
from __future__ import annotations

from datetime import date

# Nominal programme length (years) → clamps the derived year so a graduated
# batch doesn't show "Year 7".
_COURSE_YEARS = {"M.TECH": 2, "MTECH": 2, "MBA": 2, "MCA": 2, "DIPLOMA": 3}


def _max_year(course: str | None) -> int:
    if not course:
        return 4
    return _COURSE_YEARS.get(course.upper().replace(".", "").replace(" ", ""), 4)


def _ay_start(today: date) -> int:
    """The calendar year the current academic year started in (July boundary)."""
    return today.year if today.month >= 7 else today.year - 1


def derive(admission_year: int | None, course: str | None = None,
           today: date | None = None) -> tuple[int | None, int | None]:
    """Return (current_year, semester) where semester is 1 (Odd) or 2 (Even).
    Returns (None, None) if admission_year is missing."""
    if not admission_year:
        return None, None
    today = today or date.today()
    year = _ay_start(today) - int(admission_year) + 1
    sem = 1 if today.month >= 7 else 2
    year = max(1, min(year, _max_year(course)))
    return year, sem


def batch_year_for(current_year: int, today: date | None = None) -> int:
    """Convert a student's STATED current academic year into an effective batch
    (admission) year, anchored to today's academic calendar.

    We ask students their current year directly instead of their admission year:
    a detained student keeps their old roll number / admission year but actually
    studies a year (or more) behind, so deriving the year from the roll-number
    batch would be wrong. Anchoring from the stated current year fixes that, while
    still letting the cohort roll forward automatically each July via `derive()`.
    """
    today = today or date.today()
    return _ay_start(today) - (int(current_year) - 1)
