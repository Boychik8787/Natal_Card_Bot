import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)
from datetime import datetime
from zoneinfo import ZoneInfo
from flatlib.datetime import Datetime as AstroDatetime
from flatlib.geopos import GeoPos
from flatlib.chart import Chart
from flatlib import const
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from PIL import Image, ImageDraw
import math
from io import BytesIO

# Константы состояний для ConversationHandler
DATE, TIME, PLACE = range(3)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот, который построит вашу натальную карту.\n"
        "Пожалуйста, введите дату рождения в формате YYYY-MM-DD."
    )
    return DATE

async def input_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    # Проверяем формат даты
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("❗ Пожалуйста, введите дату в формате YYYY-MM-DD (например, 1988-04-28).")
        return DATE
    context.user_data["date"] = date_text
    await update.message.reply_text("Отлично. Теперь введите время рождения в формате HH:MM (24-часы, например 05:30).")
    return TIME

async def input_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_text = update.message.text.strip()
    # Проверяем формат времени
    try:
        datetime.strptime(time_text, "%H:%M")
    except ValueError:
        await update.message.reply_text("❗ Введите время в формате HH:MM, например 07:45.")
        return TIME
    context.user_data["time"] = time_text
    await update.message.reply_text("Спасибо! Теперь отправьте город и страну места рождения (например: Москва, Россия).")
    return PLACE

async def input_place(update: Update, context: ContextTypes.DEFAULT_TYPE):
    place_text = update.message.text.strip()
    geolocator = Nominatim(user_agent="natal_chart_bot")
    try:
        location = geolocator.geocode(place_text)
    except Exception as e:
        await update.message.reply_text("⚠️ Не удалось подключиться к сервису геокодирования. Попробуйте ещё раз.")
        return PLACE
    if location is None:
        await update.message.reply_text("❗ Место не найдено. Укажите город и страну (например, Минск, Беларусь).")
        return PLACE
    lat, lon = location.latitude, location.longitude
    # Определяем часовой пояс по координатам
    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    if tz_name is None:
        tz_name = "UTC"
    # Парсим введённые дату и время
    date_str = context.user_data["date"]  # формата YYYY-MM-DD
    time_str = context.user_data["time"]  # формата HH:MM
    naive_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    local_dt = naive_dt.replace(tzinfo=tz)
    # Конвертируем локальное время в UTC
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
    # Формируем объекты для расчёта натальной карты
    astro_date = AstroDatetime(utc_dt.strftime("%Y/%m/%d"), utc_dt.strftime("%H:%M"), "+00:00")
    astro_pos = GeoPos(lat, lon)
    chart = Chart(astro_date, astro_pos)
    # Генерируем изображение натальной карты
    img_size = 500
    img = Image.new("RGB", (img_size, img_size), "white")
    draw = ImageDraw.Draw(img)
    center = (img_size//2, img_size//2)
    radius = img_size//2 - 20
    # Рисуем круг (зодиакальный круг)
    draw.ellipse([center[0]-radius, center[1]-radius, center[0]+radius, center[1]+radius], outline="black", width=3)
    # Получаем список планет для отображения
    planets = [const.SUN, const.MOON, const.MERCURY, const.VENUS, const.MARS, const.JUPITER, const.SATURN]
    # Вычисляем смещение угла, чтобы асцендент был на 9 часах (слева)
    asc = chart.get(const.ASC)
    asc_lon = asc.lon  # абсолютная долгота асцендента в градусах
    # Наносим планеты на круг
    for planet in planets:
        obj = chart.get(planet)
        abs_lon = obj.lon  # абсолютная долгота планеты (0-360°)
        # Угол на круге (0° Овна -> смещён для выравнивания по асценденту слева)
        angle_rad = math.radians(abs_lon - asc_lon + 180)
        x = center[0] + radius * 0.9 * math.cos(angle_rad)
        y = center[1] + radius * 0.9 * math.sin(angle_rad)
        # Точка планеты
        draw.ellipse([x-5, y-5, x+5, y+5], fill="black")
        # Подписываем планету сокращенно (например, Sun, Moon...)
        draw.text((x+10, y-10), planet.title(), fill="black")
    # Отправляем изображение пользователю
    bio = BytesIO()
    bio.name = "chart.png"
    img.save(bio, "PNG")
    bio.seek(0)
    await update.message.reply_photo(photo=bio, caption="✨ Ваша натальная карта")
    # Также отправим текстом основные положения планет
    positions = ""
    for planet in planets:
        obj = chart.get(planet)
        # Например: Sun – Pisces 22.79°
        positions += f"{planet.title()} – {obj.sign} {obj.lon % 30:.2f}°\n"
    await update.message.reply_text(f"**Положение планет:**\n{positions}", parse_mode="Markdown")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Отмена. Чтобы начать заново, отправьте команду /start.")
    return ConversationHandler.END

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_date)],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_time)],
            PLACE: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_place)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(conv_handler)
    # Запуск бота (long polling)
    app.run_polling(stop_signals=None)  # stop_signals=None чтобы бот не выключался при SIGTERM на Railway
     
if __name__ == "__main__":
    main()
