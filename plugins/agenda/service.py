import logging
import hashlib
import traceback
from datetime import datetime, date, timedelta
from pathlib import Path
import json
from common.conf_manager import cfg, Utils, setup_logging
from plugins.agenda.my_calendar import CalendarService

setup_logging()
logger = logging.getLogger(__name__)
LOCK_PATH = Path("/tmp/agenda_notification.lock")

def scheduled(autostart=False, **config):
    def decorator(func):
        config["autostart"] = autostart
        func.schedule_config = config
        return func
    return decorator


def get_event_hash(summary):
    return hashlib.md5(summary.encode('utf-8')).hexdigest()

def parse_datetime(raw_dt):
    if isinstance(raw_dt, dict):
        raw_dt = raw_dt.get('date') or raw_dt.get('dateTime')

    if isinstance(raw_dt, str):
        raw_dt = raw_dt.replace("Z", "+00:00")
        raw_dt = datetime.fromisoformat(raw_dt)

    if isinstance(raw_dt, datetime):
        if raw_dt.tzinfo is not None:
            raw_dt = raw_dt.replace(tzinfo=None)
        return raw_dt

    if isinstance(raw_dt, date):
        return datetime.combine(raw_dt, datetime.min.time())

    raise TypeError(f"Unsupported datetime type: {type(raw_dt)} = {raw_dt!r}")

def parse_event_datetime(event):
    raw_dt = event.get('start') or event.get('dtstart') or event.get('dt')
    return parse_datetime(raw_dt)

def parse_end_event_datetime(event):
    raw_dt = event.get('end') or event.get('dtend') or event.get('dt')
    return parse_datetime(raw_dt)

def is_event_for_today(event_datetime):
    now = datetime.now()
    return now - timedelta(minutes=5) <= event_datetime <= now + timedelta(hours=24)

def fire_alarm(bot, event):
    summary = event.get('summary', 'Event')
    msg = f"**REMINDER**: '{summary}' starts in 2 hours!"
    files = []
    if "concert" in summary.lower():
        try:
            concert_data = json.loads(Utils.call_mcp_tool("get_next_concert"))
            logger.info(f"Concert data: {concert_data}")
            if concert_data and concert_data.get('pdf'):
                pdf_path = Path(cfg.agenda.path_concert) / concert_data['pdf']
                if pdf_path.exists():
                    files = [str(pdf_path)]
                    msg = f"**CONCERT**: '{summary}' in 2h!\nYour ticket is attached."
        except Exception as e:
            logger.error(f"Error retrieving PDF: {e}")
            logger.error(traceback.format_exc())

    Utils.send_discord_notification(msg, channel=cfg.bot.notification, files=files)
    event_datetime = parse_end_event_datetime(event)
    run_time = event_datetime + timedelta(minutes=30)
    bot.scheduler.add_job(
        task_sync_daily_alarm,
        'date',
        run_date=run_time,
        args=[bot]
    )
    logger.info(f"Rescheduling sync task for {run_time}")

@scheduled(autostart=True, trigger="cron", hour=6, minute=0)
def task_sync_daily_alarm(bot):
    try:
        event = json.loads(Utils.call_mcp_tool("get_next_calendar_event"))
        logger.info(f"Next event: {event}")
        summary = event.get('summary', 'Unknown')
        current_hash = get_event_hash(summary)

        already_notified = False
        if LOCK_PATH.exists():
            last_hash = LOCK_PATH.read_text().strip()
            if last_hash == current_hash:
                already_notified = True

        if already_notified:
            event_datetime = parse_end_event_datetime(event)
            resume_time = event_datetime + timedelta(minutes=30)
            logger.info(f"'{summary}' already notified (Hash match). Pause until {resume_time}")
            bot.scheduler.add_job(task_sync_daily_alarm, 'date', run_date=resume_time, args=[bot])
            return

        event_datetime = parse_event_datetime(event)

        if not is_event_for_today(event_datetime):
            logger.info(f"'{summary}' is not for today.")
            return

        alarm_time = event_datetime - timedelta(hours=2)
        if alarm_time <= datetime.now():
            fire_alarm(bot, event)
        else:
            logger.info(f"Alarm scheduled for {alarm_time}")
            bot.loop.call_soon_threadsafe(
                lambda: bot.scheduler.add_job(
                    lambda: fire_alarm(bot, event),
                    trigger="date",
                    run_date=alarm_time,
                    id="dynamic_agenda_alarm",
                    replace_existing=True
                )
            )
    except Exception as e:
        logger.error(f"ERROR : {e}\n{traceback.format_exc()}")