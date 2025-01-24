import telebot
from flask import Flask, request
from datetime import datetime, timedelta
import threading
import requests
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('TELEGRAM_TOKEN')
bot = telebot.TeleBot(TOKEN)


app = Flask(__name__)

group_locations = {}
group_prayer_dates = {}


def get_user_location():
    try:
        response = requests.get("https://ipinfo.io/")
        data = response.json()
        if "city" in data and "country" in data:
            return data["city"], data["country"]
    except Exception as e:
        print("Error fetching user location:", e)
    return "الرياض", "المملكة العربية السعودية"


def fetch_prayer_times(city, country):
    try:
        response = requests.get(
            "https://api.aladhan.com/v1/timingsByCity",
            params={"city": city, "country": country, "method": 2},
        )
        data = response.json()
        if data and data.get("data"):
            timings = data["data"]["timings"]
            prayer_date = data["data"]["date"]["gregorian"]
            return {
                "الفجر": timings["Fajr"],
                "الظهر": timings["Dhuhr"],
                "العصر": timings["Asr"],
                "المغرب": timings["Maghrib"],
                "العشاء": timings["Isha"],
            }, prayer_date
    except Exception as e:
        print("Error fetching prayer times:", e)
    return {
        "الفجر": "05:00",
        "الظهر": "12:30",
        "العصر": "15:45",
        "المغرب": "18:20",
        "العشاء": "20:00"
    }, None

def send_prayer_reminder(prayer_name, chat_id, reminder_type="10-min"):
    if reminder_type == "10-min":
        bot.send_message(chat_id, f"⏰ تذكير: صلاة {prayer_name} بعد 10 دقائق.")
    elif reminder_type == "on-time":
        bot.send_message(chat_id, f"🕋 حان الآن موعد صلاة {prayer_name}. لا تنسَ الصلاة!")

# Schedule reminders for prayers
def schedule_reminders_for_group(chat_id, city, country):
    times, prayer_date = fetch_prayer_times(city, country)
    group_prayer_dates[chat_id] = prayer_date
    for prayer, time_str in times.items():
        now = datetime.now()
        prayer_time = datetime.strptime(time_str, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day
        )

        # Adjust for the next day if the prayer time has passed
        if prayer_time < now:
            prayer_time += timedelta(days=1)

        # Schedule 10 minutes before the prayer time
        reminder_time = prayer_time - timedelta(minutes=10)
        delay = (reminder_time - now).total_seconds()
        threading.Timer(delay, send_prayer_reminder, args=(prayer, chat_id, "10-min")).start()

        # Schedule exactly at the prayer time
        on_time_delay = (prayer_time - now).total_seconds()
        threading.Timer(on_time_delay, send_prayer_reminder, args=(prayer, chat_id, "on-time")).start()

@bot.message_handler(commands=['start'])
def start(message):
    if message.chat.type in ['group', 'supergroup']:
        welcome_text = (
            "🌙 مرحبًا بكم في بوت تذكير مواعيد الصلاة!\n\n"
            "📍 استخدم الأمر /set_place لتحديد موقع المجموعة.\n"
            "⏰ سيقوم البوت بتذكير المجموعة بمواعيد الصلاة قبل 10 دقائق من كل صلاة وعند وقت الصلاة."
        )
        bot.send_message(message.chat.id, welcome_text)

@bot.message_handler(commands=['set_place'])
def set_place(message):
    if message.chat.type in ['group', 'supergroup']:
        city, country = get_user_location()
        group_locations[message.chat.id] = (city, country)
        bot.send_message(
            message.chat.id,
            f"📍 تم تعيين موقع هذه المجموعة إلى {city}, {country}.",
        )
        # Schedule reminders for the group
        schedule_reminders_for_group(message.chat.id, city, country)

@bot.message_handler(commands=['show'])
def show_times(message):
    if message.chat.type in ['group', 'supergroup']:
        location = group_locations.get(message.chat.id)
        if not location:
            bot.send_message(
                message.chat.id,
                "❗ لم يتم تعيين الموقع! استخدم /set_place لتحديد موقع المجموعة."
            )
            return

        city, country = location
        times, prayer_date = fetch_prayer_times(city, country)

        if prayer_date:
            # Check if the month name is available in Arabic, else map manually
            month_name = prayer_date.get('month', {}).get('ar', None)

            # If Arabic month name is not found, use an alternative or fallback
            if not month_name:
                month_mapping = {
                    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 
                    5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس", 
                    9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"
                }
                month_number = prayer_date.get('month', {}).get('number', None)
                month_name = month_mapping.get(month_number, "غير متوفر")
            
            prayer_times_text = f"🕌 مواعيد الصلاة في {city}, {country} (تم جلبها في {prayer_date['day']} {month_name} {prayer_date['year']}):\n"
        else:
            prayer_times_text = f"🕌 مواعيد الصلاة في {city}, {country}:\n"
        
        for prayer, time_str in times.items():
            prayer_times_text += f"🕰️ {prayer}: {time_str}\n"

        bot.send_message(message.chat.id, prayer_times_text)

@bot.message_handler(commands=['left'])
def time_left(message):
    if message.chat.type in ['group', 'supergroup']:
        location = group_locations.get(message.chat.id)
        if not location:
            bot.send_message(
                message.chat.id,
                "❗ لم يتم تعيين الموقع! استخدم /set_place لتحديد موقع المجموعة."
            )
            return

        city, country = location
        times, _ = fetch_prayer_times(city, country)
        now = datetime.now()
        next_prayer, next_time = None, None

        for prayer, time_str in times.items():
            prayer_time = datetime.strptime(time_str, "%H:%M").replace(
                year=now.year, month=now.month, day=now.day
            )

            # Adjust for the next day if the prayer time has passed
            if prayer_time < now:
                prayer_time += timedelta(days=1)

            if not next_prayer or prayer_time < next_time:
                next_prayer, next_time = prayer, prayer_time

        if next_prayer and next_time:
            time_diff = next_time - now
            hours, remainder = divmod(time_diff.seconds, 3600)
            minutes = remainder // 60
            bot.send_message(
                message.chat.id,
                f"⏳ الوقت المتبقي حتى {next_prayer}: {hours} ساعات و {minutes} دقائق."
            )

#
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = request.stream.read().decode("utf-8")
    bot.process_new_updates([telebot.types.Update.de_json(update)])
    return "OK", 200

@app.route("/")
def home():
    return "بوت تذكير مواعيد الصلاة يعمل!", 200

if __name__ == "__main__":
    from os import getenv
    WEBHOOK_URL = getenv("RENDER_EXTERNAL_URL") + TOKEN
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=5000)