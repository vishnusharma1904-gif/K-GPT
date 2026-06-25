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


def derive(admission_year: int | None, course: str | None = None,
           today: date | None = None) -> tuple[int | None, int | None]:
    """Return (current_year, semester) where semester is 1 (Odd) or 2 (Even).
    Returns (None, None) if admission_year is missing."""
    if not admission_year:
        return None, None
    today = today or date.today()
    ay_start = today.year if today.month >= 7 else today.year - 1  # July boundary
    year = ay_start - int(admission_year) + 1
    sem = 1 if today.month >= 7 else 2
    year = max(1, min(year, _max_year(course)))
    return year, sem
