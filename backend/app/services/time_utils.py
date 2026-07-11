from datetime import date, datetime, time, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.8 compatibility
    ZoneInfo = None


BUSINESS_TIMEZONE_NAME = "Asia/Shanghai"
UTC = timezone.utc


def _load_business_timezone():
    if ZoneInfo is not None:
        try:
            return ZoneInfo(BUSINESS_TIMEZONE_NAME)
        except Exception:
            pass
    # Asia/Shanghai has used UTC+08:00 since 1991. This fallback keeps older
    # Python/Windows installations usable when the IANA database is absent.
    return timezone(timedelta(hours=8), name=BUSINESS_TIMEZONE_NAME)


BUSINESS_TIMEZONE = _load_business_timezone()


def local_now():
    """Return the current business time as a naive datetime."""
    return datetime.now(UTC).astimezone(BUSINESS_TIMEZONE).replace(tzinfo=None)


def local_naive_to_utc(value):
    """Convert business-local time to the naive UTC form stored by the ORM."""
    if not isinstance(value, datetime):
        raise TypeError("value must be a datetime")
    aware = value.replace(tzinfo=BUSINESS_TIMEZONE) if value.tzinfo is None else value
    return aware.astimezone(UTC).replace(tzinfo=None)


def utc_naive_to_local(value):
    """Convert a stored naive UTC value to naive business-local time."""
    if not isinstance(value, datetime):
        raise TypeError("value must be a datetime")
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.astimezone(BUSINESS_TIMEZONE).replace(tzinfo=None)


def format_local_datetime(value, fmt="%Y-%m-%d %H:%M"):
    if value is None:
        return None
    return utc_naive_to_local(value).strftime(fmt)


def parse_local_datetime(value, is_end=False):
    """Parse a local API value into naive UTC.

    End values are inclusive at the precision supplied by the caller and are
    converted to an exclusive upper bound for database queries.
    """
    if value is None or value == "":
        return None

    parsed = None
    resolution = None
    if isinstance(value, datetime):
        parsed = value
        resolution = timedelta(microseconds=1)
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
        resolution = timedelta(days=1)
    else:
        text = str(value).strip()
        if not text:
            return None
        formats = (
            ("%Y-%m-%d %H:%M:%S", timedelta(seconds=1)),
            ("%Y-%m-%dT%H:%M:%S", timedelta(seconds=1)),
            ("%Y-%m-%d %H:%M", timedelta(minutes=1)),
            ("%Y-%m-%dT%H:%M", timedelta(minutes=1)),
            ("%Y-%m-%d", timedelta(days=1)),
        )
        for fmt, candidate_resolution in formats:
            try:
                parsed = datetime.strptime(text, fmt)
            except ValueError:
                continue
            resolution = candidate_resolution
            break
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Invalid date format") from exc
            resolution = timedelta(microseconds=1)

    if is_end:
        parsed += resolution
    return local_naive_to_utc(parsed)
