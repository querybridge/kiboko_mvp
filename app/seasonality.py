"""Retail calendar events the sales forecast expects.

A day's factor scales its typical (same-weekday) sales: Black Friday and Cyber
Monday run at about twice a normal day, the weekend between them somewhat above
normal, and Thanksgiving Day a little below. The forecast projects remaining
days with these factors and divides them out of observed days before taking its
weekday medians, so a Black Friday spike neither inflates nor hides the trend.
The demo data generator (refresh_demo) uses the same table."""
from datetime import date, timedelta

THANKSGIVING = 'thanksgiving'
BLACK_FRIDAY = 'black_friday'
CYBER_WEEKEND = 'cyber_weekend'
CYBER_MONDAY = 'cyber_monday'

EVENT_FACTORS = {
    THANKSGIVING: 0.85,
    BLACK_FRIDAY: 2.0,
    CYBER_WEEKEND: 1.3,
    CYBER_MONDAY: 2.0,
}

EVENT_LABELS = {
    THANKSGIVING: 'Thanksgiving',
    BLACK_FRIDAY: 'Black Friday',
    CYBER_WEEKEND: 'Cyber Weekend',
    CYBER_MONDAY: 'Cyber Monday',
}


def thanksgiving(year):
    """US Thanksgiving: the fourth Thursday of November."""
    first = date(year, 11, 1)
    first_thursday = first + timedelta(days=(3 - first.weekday()) % 7)
    return first_thursday + timedelta(weeks=3)


def black_friday(year):
    return thanksgiving(year) + timedelta(days=1)


def events(year):
    """{date: event key} for the year's retail events."""
    t = thanksgiving(year)
    return {
        t: THANKSGIVING,
        t + timedelta(days=1): BLACK_FRIDAY,
        t + timedelta(days=2): CYBER_WEEKEND,
        t + timedelta(days=3): CYBER_WEEKEND,
        t + timedelta(days=4): CYBER_MONDAY,
    }


def event_for(d):
    """The retail event on day `d`, or None."""
    if d.month not in (11, 12):
        return None
    return events(d.year).get(d)


def day_factor(d):
    """Expected sales on `d` relative to a normal day of the same weekday."""
    ev = event_for(d)
    return EVENT_FACTORS[ev] if ev else 1.0
