import asyncio
import json
import logging
import vobject
import requests
from datetime import datetime, timedelta
from pathlib import Path
from config_loader import cfg
from ollama_service import llm
from ollama_config import OllamaConfig
from utils import Utils
from plugins.agenda.my_calendar import CalendarService
import hashlib

logger = logging.getLogger(__name__)
calendar_plugin = CalendarService()

LOCK_PATH = Path("/tmp/agenda_notification.lock")

def scheduled(autostart=False, **config):
    def decorator(func):
        config["autostart"] = autostart
        func.schedule_config = config
        return func
    return decorator

async def handle_agenda(self, m):
    await asyncio.to_thread(manage_request, self, m)

def get_event_hash(summary):
    return hashlib.md5(summary.encode('utf-8')).hexdigest()

def parse_datetime(raw_dt):
    if isinstance(raw_dt, dict):
        raw_dt = raw_dt.get('date') or raw_dt.get('dateTime')
    if not isinstance(raw_dt, datetime):
        raw_dt = datetime.combine(raw_dt, datetime.min.time())
    return raw_dt

def parse_event_datetime(event):
    raw_dt = event.get('dt') or event.get('start')
    return parse_datetime(raw_dt)

def is_event_for_today(event_datetime):
    return event_datetime.date() == datetime.now().date()

def get_resume_time(event_datetime):
    resume_time = event_datetime + timedelta(minutes=30)
    if resume_time < datetime.now():
        resume_time = datetime.now() + timedelta(hours=1)
    return resume_time

def fire_alarm(bot, event):
    summary = event.get('summary', 'Event')
    msg = f"**REMINDER**: '{summary}' starts in 2 hours!"
    files = []

    if "concert" in summary.lower():
        try:
            concert_data = calendar_plugin.get_next_concert_data()
            if concert_data and concert_data.get('pdf'):
                pdf_path = Path(cfg.agenda.path_concert) / concert_data['pdf']
                if pdf_path.exists():
                    files = [str(pdf_path)]
                    msg = f"**CONCERT**: '{summary}' in 2h!\nYour ticket is attached."
        except Exception as e:
            logger.error(f"Error retrieving PDF: {e}")

    try:
        payload = {
            "channel_name": cfg.bot.notification,
            "msg": msg,
            "attachments": files
        }
        response = requests.post(f"http://127.0.0.1:{cfg.system.port}/send", json=payload, timeout=15)

        if response.status_code == 200:
            logger.info(f"Notification sent for '{summary}'")
            event_hash = get_event_hash(summary)
            LOCK_PATH.write_text(event_hash)
            logger.info(f"Stored hash {event_hash} in {LOCK_PATH}")
        else:
            logger.error(f"Send failed ({response.status_code}): {response.text}")

    except Exception as e:
        logger.error(f"Critical error in fire_alarm dispatch: {e}")

    run_time = datetime.now() + timedelta(minutes=30)
    bot.scheduler.add_job(
        task_sync_daily_alarm,
        'date',
        run_date=run_time,
        args=[bot]
    )
    logger.info(f"Rescheduling sync task for {run_time}")

def generate_ics_from_template(output_path, name_event, date, location):
    with open(cfg.agenda.ics_template, 'r', encoding='utf-8') as f:
        content = f.read()

    now = datetime.now().strftime("%Y%m%dT%H%M%S")
    uid = f"{now}-{name_event.replace(' ', '_')}@bot"

    try:
        start_dt = datetime.strptime(date, "%Y%m%dT%H%M%S")
        dtend = (start_dt + timedelta(hours=3)).strftime("%Y%m%dT%H%M%S")
    except Exception:
        dtend = date

    formatted_content = content.format(
        uid=uid,
        now=now,
        artist=name_event,
        dtstart=date,
        dtend=dtend,
        location=location
    )

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(formatted_content)

def _execute_save(bot, m):
    system_prompt_event = cfg.agents.agenda_extract_event_name
    if 'concert' in m.content.lower() or m.attachments:
        system_prompt_event = cfg.agents.agenda_extract_artist
        path = Path(cfg.agenda.path_concert) / "concerts.json"
        index = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    index = json.load(f)
            except Exception as e:
                logger.error(f"Error reading JSON: {e}")

    resp_event = Utils.llm_call('qwen2.5:3b', system_prompt_event, m.content)
    event = resp_event.get("event", "Unknown")

    resp_venue = Utils.llm_call('qwen2.5:3b', cfg.agents.agenda_extract_venue, m.content)
    venue = resp_venue.get("location", "Unknown")

    resp_date = Utils.llm_call('qwen2.5:3b', cfg.agents.agenda_extract_date, m.content)
    date = resp_date.get("date")

    logger.debug(f"_execute_save extract data : {event} | {venue} | {date} ")
    already_exists = any(
        item.get("data", {}).get("event", "").lower() == event.lower() or
        item.get("data", {}).get("date") == date
        for item in index.values()
    )

    if already_exists:
        return f"**{event}** or this date is already in the calendar."

    if m.attachments:
        attachment = m.attachments[0]
        filename = attachment.filename
        save_dir = Path(cfg.agenda.path_concert)
        save_dir.mkdir(parents=True, exist_ok=True)
        r = requests.get(attachment.url)
        with open(save_dir / filename, 'wb') as f:
            f.write(r.content)

        index[filename] = {
            "status": "ics_pending",
            "data": {
                "artist": event,
                "venue": venue,
                "date": date
            },
            "event": None
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=4, ensure_ascii=False)
        event = 'Concert : ' + event

    ics_path = Path(cfg.agenda.path_concert) / f"{event}.ics"
    try:
        logger.info(f"Attempt to create ICS : {ics_path}")
        generate_ics_from_template(ics_path, event, date, venue)

        if not ics_path.exists():
            logger.error(f"FAILURE: The file {ics_path} does not exist after calling generate_ics_from_template")
            files_to_send = []
        else:
            logger.info(f"SUCCESS: ICS file created.")
            files_to_send = [str(ics_path)]

    except Exception as e:
        logger.error(f"Error during ICS generation: {e}")
        files_to_send = []

    Utils.send_discord_notification(
        f"Event to add: **{event}**",
        channel=m.channel.name,
        files=files_to_send
    )
    bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(m.add_reaction("✅")))

    return f"Ticket saved for **{event}**"

def manage_request(bot, m):
    try:
        if m.attachments:
            result_text = _execute_save(bot, m)
            return

        resp = Utils.llm_call('qwen2.5:3b', cfg.agents.agenda_router, m.content)
        action = resp.get("action")
        if not action:
            bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(m.add_reaction("❌")))
            return

        files = None

        if action == "SAVE_EVENT":
            result_text = _execute_save(bot, m)
            return

        elif action == "NEXT_CONCERT":
            concert = calendar_plugin.get_next_concert_data()
            result_text = f"Next Concert: {concert['summary']} on {concert['dt']}" if concert else "No concerts found."
        elif action == "NEXT_RDV":
            events = calendar_plugin.fetch_calendar_events(limit=1)
            result_text = f"Next Appointment: {events[0]['summary']} ({events[0]['dt'].strftime('%Y/%m/%d')})" if events else "No appointments found."
        elif action == "CURRENT_WEEK":
            events = calendar_plugin.get_week_events(offset=0)
            result_text = _format_week("This Week", events)
        elif action == "NEXT_WEEK":
            events = calendar_plugin.get_week_events(offset=1)
            result_text = _format_week("Next Week", events)

        if result_text:
            resp = Utils.llm_call('qwen2.5:3b', cfg.agents.agenda_report, result_text)
            report = resp.get("content", result_text)
            if not report:
                report = result_text
            bot.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(bot.send_smart_split(m.channel, report, files=files))
            )

    except Exception as e:
        logger.error(f"Agenda Router Error: {e}")
        bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(m.add_reaction("❌")))


def _format_week(label, events):
    if not events:
        return f"No events for {label}."
    return f"**{label}:**\n" + "\n".join([f"• {e['dt'].strftime('%a %d')}: {e['summary']}" for e in events])

@scheduled(autostart=True, trigger="cron", hour=1, minute=0)
def task_sync_daily_alarm(bot):
    from datetime import datetime, timedelta
    import traceback

    try:
        events = calendar_plugin.fetch_calendar_events(limit=1)
        if not events:
            bot.scheduler.add_job(task_sync_daily_alarm, 'date', run_date=datetime.now() + timedelta(hours=1), args=[bot])
            return

        event = events[0]
        summary = event.get('summary', 'Unknown')
        current_hash = get_event_hash(summary)

        already_notified = False
        if LOCK_PATH.exists():
            last_hash = LOCK_PATH.read_text().strip()
            if last_hash == current_hash:
                already_notified = True

        if already_notified:
            event_datetime = parse_event_datetime(event)
            resume_time = get_resume_time(event_datetime)
            logger.info(f"'{summary}' already notified (Hash match). Pause until {resume_time}")
            bot.scheduler.add_job(task_sync_daily_alarm, 'date', run_date=resume_time, args=[bot])
            return

        event_datetime = parse_event_datetime(event)

        if not is_event_for_today(event_datetime):
            logger.info(f"'{summary}' is not for today.")
            bot.scheduler.add_job(task_sync_daily_alarm, 'date', run_date=datetime.now() + timedelta(hours=1), args=[bot])
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
        bot.scheduler.add_job(task_sync_daily_alarm, 'date', run_date=datetime.now() + timedelta(minutes=30), args=[bot])
