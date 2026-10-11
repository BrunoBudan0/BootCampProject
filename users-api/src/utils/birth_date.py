from datetime import date, datetime
from zoneinfo import ZoneInfo

SAO_PAULO_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def parse_calendar_date(raw_value: str):
    try:
        return date.fromisoformat(raw_value)
    except ValueError:
        return None


def today_in_sao_paulo() -> date:
    return datetime.now(SAO_PAULO_TIMEZONE).date()


def age_in_years(birth_date: date, today: date) -> int:
    had_birthday_this_year = (today.month, today.day) >= (birth_date.month, birth_date.day)
    completed_years = today.year - birth_date.year

    if had_birthday_this_year:
        return completed_years

    return completed_years - 1
