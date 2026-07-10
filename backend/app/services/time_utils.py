from datetime import datetime, timedelta, timezone


LOCAL_OFFSET = timedelta(hours=8)


def local_now():
    return datetime.now(timezone.utc).replace(tzinfo=None) + LOCAL_OFFSET


def local_naive_to_utc(value):
    return value - LOCAL_OFFSET


def utc_naive_to_local(value):
    return value + LOCAL_OFFSET


def parse_local_datetime(value, is_end=False):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == "%Y-%m-%d" and is_end:
            parsed += timedelta(days=1)
        elif fmt != "%Y-%m-%d" and is_end:
            parsed += timedelta(seconds=1)
        return local_naive_to_utc(parsed)
    raise ValueError("Invalid date format")
