from datetime import datetime, timedelta
import pytz

BEIJING_TZ = pytz.timezone('Asia/Shanghai')

def get_beijing_now():
    """
    Get current Beijing time with timezone information
    """
    return datetime.now(BEIJING_TZ)

def get_beijing_now_naive():
    """
    Get current Beijing time as naive datetime (without timezone info)
    """
    beijing_now = get_beijing_now()
    return beijing_now.replace(tzinfo=None)

def utc_to_beijing(utc_dt):
    """
    Convert UTC datetime to Beijing time
    """
    if utc_dt.tzinfo is None:
        utc_dt = pytz.UTC.localize(utc_dt)
    return utc_dt.astimezone(BEIJING_TZ)

def beijing_time_plus_days(days):
    """
    Get Beijing time plus specified number of days
    """
    return get_beijing_now() + timedelta(days=days) 