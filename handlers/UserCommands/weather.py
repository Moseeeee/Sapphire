
import aiohttp
import asyncio
from datetime import datetime
from typing import Optional, Dict, Tuple
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
import pytz
from pyexpat.errors import messages

from handlers.BotAutomaticWork.Gonfig.config import sanor_ID
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

weather_router = Router()

# ---------------------------
# Конфигурация
# ---------------------------
OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

weather_cache: Dict[str, Tuple[datetime, str]] = {}
CACHE_TTL = 600  # 10 минут в секундах


# ---------------------------
# Эмодзи и вспомогательные функции
# ---------------------------
def interpret_weather_code(code: int, is_day: bool = True) -> Tuple[str, str]:
    """Интерпретация кода погоды с эмодзи"""
    codes = {
        0: ("☀️", "Ясно") if is_day else ("🌙", "Ясно"),
        1: ("🌤️", "Преимущественно ясно") if is_day else ("☁️", "Преимущ. ясно"),
        2: ("⛅", "Частично облачно"),
        3: ("☁️", "Пасмурно"),
        45: ("🌫️", "Туман"),
        48: ("🌁", "Инейный туман"),
        51: ("🌦️", "Легкая морось"),
        53: ("🌧️", "Умеренная морось"),
        55: ("🌧️", "Сильная морось"),
        56: ("🌨️", "Ледяная морось"),
        57: ("🌨️", "Сильная ледяная морось"),
        61: ("💧", "Небольшой дождь"),
        63: ("🌧️", "Умеренный дождь"),
        65: ("⛈️", "Сильный дождь"),
        66: ("🧊", "Ледяной дождь"),
        67: ("🧊", "Сильный ледяной дождь"),
        71: ("❄️", "Небольшой снег"),
        73: ("🌨️", "Умеренный снег"),
        75: ("❄️❄️", "Сильный снег"),
        77: ("🌨️", "Снежные зерна"),
        80: ("💧", "Небольшие ливни"),
        81: ("🌧️", "Умеренные ливни"),
        82: ("⛈️", "Сильные ливни"),
        85: ("🌨️💧", "Снежные ливни"),
        86: ("🌨️💧", "Сильные снежные ливни"),
        95: ("⚡", "Гроза"),
        96: ("⚡❄️", "Гроза с градом"),
        99: ("⚡❄️", "Сильная гроза с градом"),
    }
    return codes.get(code, ("❓", "Неизвестно"))


def temp_emoji(temp: float) -> str:
    """Эмодзи в зависимости от температуры"""
    if temp < -20:
        return "🥶"
    elif temp < -10:
        return "❄️"
    elif temp < 0:
        return "☃️"
    elif temp < 10:
        return "🧣"
    elif temp < 15:
        return "🧥"
    elif temp < 20:
        return "🌤️"
    elif temp < 25:
        return "😎"
    elif temp < 30:
        return "🔥"
    elif temp < 35:
        return "♨️"
    else:
        return "🌋"


def wind_emoji(speed: float) -> str:
    """Эмодзи в зависимости от скорости ветра"""
    if speed < 0.5:
        return "🍃"
    elif speed < 2:
        return "🪁"
    elif speed < 5:
        return "🌬️"
    elif speed < 10:
        return "💨"
    elif speed < 15:
        return "🌪️"
    else:
        return "🌀"


def wind_direction_emoji(deg: float) -> str:
    """Эмодзи направления ветра"""
    if deg >= 337.5 or deg < 22.5:
        return "⬇️"  # Северный
    elif deg < 67.5:
        return "↙️"  # Северо-восточный
    elif deg < 112.5:
        return "⬅️"  # Восточный
    elif deg < 157.5:
        return "↖️"  # Юго-восточный
    elif deg < 202.5:
        return "⬆️"  # Южный
    elif deg < 247.5:
        return "↗️"  # Юго-западный
    elif deg < 292.5:
        return "➡️"  # Западный
    else:
        return "↘️"  # Северо-западный


def uv_index_emoji(uv: float) -> str:
    """Эмодзи UV-индекса"""
    if uv < 3:
        return "🟢"
    elif uv < 6:
        return "🟡"
    elif uv < 8:
        return "🟠"
    elif uv < 11:
        return "🔴"
    else:
        return "🟣⚡"


def cloud_emoji(cover: float) -> str:
    """Эмодзи облачности"""
    if cover < 10:
        return "☀️"
    elif cover < 30:
        return "🌤️"
    elif cover < 70:
        return "⛅"
    elif cover < 90:
        return "☁️"
    else:
        return "🌫️☁️"


def visibility_emoji(vis: float) -> str:
    """Эмодзи видимости"""
    if vis > 10:
        return "✨"
    elif vis > 5:
        return "👀"
    elif vis > 2:
        return "🌫️"
    elif vis > 1:
        return "🌁"
    else:
        return "🚫👀"


def precipitation_emoji(precip: float) -> str:
    """Эмодзи осадков"""
    if precip == 0:
        return "☀️"
    elif precip < 2:
        return "🌦️"
    elif precip < 10:
        return "🌧️"
    elif precip < 20:
        return "⛈️"
    elif precip < 50:
        return "🌊"
    else:
        return "☔⚡"


def format_date(date_str: str) -> str:
    """Форматирование даты для отображения"""
    days_ru = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    months_ru = ["января", "февраля", "марта", "апреля", "майя", "июня",
                 "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{days_ru[dt.weekday()]}, {dt.day} {months_ru[dt.month - 1]}"
    except:
        return date_str


# ---------------------------
# Основные функции
# ---------------------------
async def get_city_coords(city: str) -> Optional[Tuple[float, float, str, str]]:
    """Получаем координаты и информацию о городе"""
    params = {"name": city, "count": 1, "language": "ru", "format": "json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(GEOCODING_URL, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("results"):
                        loc = data["results"][0]
                        name = loc.get("name", city)
                        country = loc.get("country", "")
                        admin1 = loc.get("admin1", "")

                        # Формируем полное название
                        full_name = name
                        if admin1 and admin1 != name:
                            full_name += f", {admin1}"
                        if country and country != admin1:
                            full_name += f", {country}"

                        return loc["latitude"], loc["longitude"], loc["timezone"], full_name
    except Exception as e:
        print(f"❌ Ошибка геокодинга: {e}")
    return None


async def get_weather(lat: float, lon: float, tz: str) -> Optional[dict]:
    """Получаем расширенные данные о погоде"""
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": tz,
        "current": [
            "temperature_2m", "relative_humidity_2m", "apparent_temperature",
            "weather_code", "wind_speed_10m", "wind_direction_10m",
            "wind_gusts_10m", "pressure_msl", "visibility", "is_day",
            "uv_index", "precipitation", "cloud_cover"
        ],
        "hourly": [
            "temperature_2m", "weather_code", "precipitation_probability"
        ],
        "daily": [
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "apparent_temperature_max", "apparent_temperature_min",
            "sunrise", "sunset", "precipitation_sum", "precipitation_probability_max",
            "wind_speed_10m_max", "wind_gusts_10m_max", "wind_direction_10m_dominant",
            "uv_index_max", "daylight_duration", "sunshine_duration"
        ],
        "forecast_days": 5,
        "timeformat": "unixtime"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(OPENMETEO_URL, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    # Добавляем текущее время для временной зоны
                    try:
                        tz_obj = pytz.timezone(tz)
                        now = datetime.now(tz_obj)
                        data["current_time"] = now.strftime("%H:%M")
                        data["current_date"] = now.strftime("%d.%m.%Y")
                        data["weekday"] = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"][now.weekday()]
                        data["is_day"] = 6 <= now.hour <= 18
                    except:
                        now = datetime.utcnow()
                        data["current_time"] = now.strftime("%H:%M")
                        data["current_date"] = now.strftime("%d.%m.%Y")
                        data["weekday"] = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"][now.weekday()]
                        data["is_day"] = 6 <= now.hour <= 18

                    return data
    except Exception as e:
        print(f"❌ Ошибка получения погоды: {e}")
    return None


def format_weather(data: dict, city_name: str) -> str:
    """Форматируем красивое сообщение о погоде"""
    current = data["current"]
    daily = data["daily"]

    # Текущая погода
    temp = round(current["temperature_2m"])
    feels = round(current["apparent_temperature"])
    code = current["weather_code"]
    humidity = current["relative_humidity_2m"]
    wind_speed = round(current["wind_speed_10m"])
    wind_gust = round(current["wind_gusts_10m"])
    wind_dir = current["wind_direction_10m"]
    pressure = round(current["pressure_msl"])
    visibility = round(current["visibility"] / 1000, 1)  # в км
    uv_index = current["uv_index"]
    precipitation = round(current["precipitation"], 1)
    cloud_cover = current["cloud_cover"]

    emoji, desc = interpret_weather_code(code, data["is_day"])
    temp_emoji_str = temp_emoji(temp)

    # Прогноз на сегодня по часам
    today_forecast = []
    for i in range(0, min(24, len(data["hourly"]["time"])), 3):
        hour_time = datetime.fromtimestamp(data["hourly"]["time"][i])
        hour_temp = round(data["hourly"]["temperature_2m"][i])
        hour_code = data["hourly"]["weather_code"][i]
        hour_is_day = 6 <= hour_time.hour <= 18
        hour_emoji, _ = interpret_weather_code(hour_code, hour_is_day)
        hour_str = f"{hour_time.hour:02d}"
        today_forecast.append(f"{hour_emoji} <b>{hour_str}</b>: {hour_temp}°")

    today_forecast_text = "\n".join(today_forecast[:8])

    # Прогноз на 5 дней
    forecast_days = []
    for i in range(min(5, len(daily["time"]))):
        day_code = daily["weather_code"][i]
        day_emoji, day_desc = interpret_weather_code(day_code, True)
        day_max = round(daily["temperature_2m_max"][i])
        day_min = round(daily["temperature_2m_min"][i])
        precip_prob = daily["precipitation_probability_max"][i]
        wind_max = round(daily["wind_speed_10m_max"][i])
        date_str = format_date(datetime.fromtimestamp(daily["time"][i]).strftime("%Y-%m-%d"))

        # Эмодзи для осадков
        precip_emoji = "☔" if precip_prob > 30 else "💧" if precip_prob > 0 else "🌤️"

        forecast_days.append(
            f"<b>{date_str}</b>\n"
            f"{day_emoji} {day_desc}\n{temp_emoji(day_max)} {day_min}° → {day_max}°\n"
            f"{precip_emoji} {precip_prob}%\n💨 {wind_emoji(wind_max)} {wind_max} м/с"
        )

    # Эмодзи для времени суток
    time_emoji = "🌅" if 5 <= int(data["current_time"].split(':')[0]) < 12 else \
        "🌇" if 12 <= int(data["current_time"].split(':')[0]) < 18 else \
            "🌃" if 18 <= int(data["current_time"].split(':')[0]) < 22 else "🌌"

    # Формируем итоговое сообщение
    message = (
        f"🌤️ <b>ПОГОДА В {city_name.upper()}</b>\n"
        f"🗓️ {data['weekday']}, {data['current_date']} | 🕒 {data['current_time']}\n\n"

        f"<b>{emoji} {desc.upper()} (облачность {cloud_cover}%)</b>\n"
        f"{temp_emoji_str} <b>{temp}°C</b> (ощущается как {feels}°C)\n\n"

        f"💧 <b>Влажность:</b> {humidity}% (осадки {precipitation}мм)\n"
        f"{wind_direction_emoji(wind_dir)} <b>Ветер:</b> {wind_speed} м/с (порывы до {wind_gust} м/с)\n"
        #f"💫 <b>Порывы:</b> до {wind_gust} м/с\n"
        f"📊 <b>Давление:</b> {pressure} гПа\n"
        f"{visibility_emoji(visibility)} <b>Видимость:</b> {visibility} км\n"
        f"{uv_index_emoji(uv_index)} <b>UV-индекс:</b> {uv_index}\n\n"
        #f"{precipitation_emoji(precipitation)} <b>Осадки:</b> {precipitation} мм\n"
        #f"{cloud_emoji(cloud_cover)} <b>Облачность:</b> {cloud_cover}%\n\n"


        f"🕒 <b>ПРОГНОЗ ПО ЧАСАМ</b>\n"
        f"{today_forecast_text}\n\n"


        f"📅 <b>ПРОГНОЗ НА 5 ДНЕЙ</b>\n"
    )

    # Добавляем прогноз по дням
    message += "\n\n".join(forecast_days)

    message += f"\n\n{'═' * 27}\n"
    message += f"💫 Обновлено: {datetime.now().strftime('%H:%M:%S')}\n"
    #message += f"📡 Источник: Open-Meteo.com"

    return message


async def process_weather_command(city: str) -> Optional[str]:
    """Основная логика обработки погоды"""
    cache_key = city.lower()

    # Проверка кэша
    if cache_key in weather_cache:
        timestamp, data = weather_cache[cache_key]
        if (datetime.now() - timestamp).total_seconds() < CACHE_TTL:
            return data

    # Получаем координаты
    coords_data = await get_city_coords(city)
    if not coords_data:
        return None

    lat, lon, tz, full_city_name = coords_data

    # Получаем погоду
    weather_data = await get_weather(lat, lon, tz)
    if not weather_data:
        return None

    # Форматируем
    result = format_weather(weather_data, full_city_name)

    # Кэшируем
    weather_cache[cache_key] = (datetime.now(), result)

    return result


async def cache_cleaner():
    """Фоновая задача для очистки устаревшего кэша"""
    while True:
        try:
            current_time = datetime.now()
            expired_keys = []

            for key, (timestamp, _) in weather_cache.items():
                if (current_time - timestamp).total_seconds() > CACHE_TTL:
                    expired_keys.append(key)

            for key in expired_keys:
                del weather_cache[key]

            if expired_keys:
                print(f"🧹 Очищен кэш для {len(expired_keys)} городов")

        except Exception as e:
            print(f"❌ Ошибка при очистке кэша: {e}")

        await asyncio.sleep(60)


# ---------------------------
# ОБРАБОТЧИКИ КОМАНД
# ---------------------------
@weather_router.message(Command("погода"))
async def slash_weather_handler(message: Message):
    if message.chat.type != 'private':
        if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 59):
            return

    """Обработчик /погода [город]"""
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer(
            "🌤️ <b>КАК ПОЛУЧИТЬ ПОГОДУ?</b>\n\n"
            "📝 Просто укажите город после команды:\n"
            "<code>/погода Москва</code>\n"
            "<code>/погода Санкт-Петербург</code>\n"
            "<code>/погода Лондон</code>\n"
            "<code>/погода Нью-Йорк</code>\n\n"
            "💡 Совет: можно указать страну для точности:\n"
            "<code>/погода Майами, США</code>",
            parse_mode="HTML"
        )
        return

    city = args[1].strip()

    # Показываем индикатор загрузки
    obloko = await message.answer('☁️')
    processing_msg = await message.answer("⏳ <i>Получаю данные о погоде...</i>\n\n🌤️ <b>Подождите немного</b>",
                                          parse_mode="HTML")

    weather = await process_weather_command(city)

    # Удаляем индикатор загрузки
    await processing_msg.delete()
    await obloko.delete()

    if weather:
        try:
            await message.answer(weather, parse_mode="HTML")
        except Exception as e:
            if "message is too long" in str(e):
                # Если сообщение слишком длинное, отправляем частями
                parts = [weather[i:i + 4000] for i in range(0, len(weather), 4000)]
                for i, part in enumerate(parts):
                    if i > 0:
                        await asyncio.sleep(0.5)
                    await message.answer(part, parse_mode="HTML")
            else:
                await message.answer(f"❌ Ошибка при отправке: {str(e)}")
    else:
        await message.answer(
            "❌ <b>ГОРОД НЕ НАЙДЕН</b>\n\n"
            "🔍 Попробуйте:\n"
            "• Проверить написание города\n"
            "• Указать страну: <code>Париж, Франция</code>\n"
            "• Использовать английское название: <code>Moscow</code>\n\n"
            "💡 Примеры правильных запросов:\n"
            "<code>/погода Берлин</code>\n"
            "<code>/погода Токио, Япония</code>\n"
            "<code>/погода Dubai</code>",
            parse_mode="HTML"
        )


@weather_router.message(F.text.startswith("!погода "))
async def exclamation_weather_handler(message: Message):
    if message.chat.type != 'private':
        if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 59):
            return

    """Обработчик !погода [город]"""
    city = message.text[8:].strip()

    if not city:
        await message.answer("🌤️ <b>Укажите город после команды!</b>\n\nПример: <code>!погода Москва</code>",
                             parse_mode="HTML")
        return

    obloko = await message.answer('☁️')
    processing_msg = await message.answer("🌀 <i>Собираю метеоданные...</i>", parse_mode="HTML")

    weather = await process_weather_command(city)


    await processing_msg.delete()
    await obloko.delete()

    if weather:
        try:
            await message.answer(weather, parse_mode="HTML")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}")
    else:
        await message.answer(
            "❌ <b>Не удалось найти город</b>\n\nПопробуйте указать точное название или добавить страну",
            parse_mode="HTML")


@weather_router.message(F.text.startswith(".погода "))
async def dot_weather_handler(message: Message):
    if message.chat.type != 'private':
        if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 59):
            return


    """Обработчик .погода [город]"""
    city = message.text[8:].strip()

    if not city:
        await message.answer("🌤️ <b>Где город?</b>\n\nИспользуйте: <code>.погода Лондон</code>", parse_mode="HTML")
        return

    obloko = await message.answer('☁️')
    processing_msg = await message.answer("✨ <i>Волшебство погоды в процессе...</i>", parse_mode="HTML")

    weather = await process_weather_command(city)

    await processing_msg.delete()
    await obloko.delete()

    if weather:
        try:
            await message.answer(weather, parse_mode="HTML")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}")
    else:
        await message.answer("❌ <b>Магия не сработала!</b>\n\nПроверьте название города и попробуйте снова",
                             parse_mode="HTML")


@weather_router.message(F.text.startswith(".кеш погоды"))
@weather_router.message(F.text.startswith("!кеш погоды"))
@weather_router.message(F.text.startswith("/кеш погоды"))
async def weather_cache_handler(message: Message):
    if message.from_user.id != sanor_ID:
        return

    obloko = await message.answer('☁️')

    """Показать статистику кэша"""
    cache_size = len(weather_cache)
    current_time = datetime.now()

    stats = []
    for key, (timestamp, _) in list(weather_cache.items())[:5]:  # Первые 5 записей
        age = int((current_time - timestamp).total_seconds())
        stats.append(f"• {key.capitalize()}: обновлено {age} сек. назад")

    response = (
        f"📦 <b>СТАТИСТИКА КЭША</b>\n\n"
        f"🗄️ Всего городов: <b>{cache_size}</b>\n"
        f"⏱️ Время жизни: <b>{CACHE_TTL // 60} минут</b>\n\n"
        f"<b>🔄 Последние обновления:</b>\n"
    )

    if stats:
        response += "\n".join(stats)
    else:
        response += "📭 Кэш пока пуст"


    await obloko.delete()
    await message.answer(response, parse_mode="HTML")


# ---------------------------
# Startup
# ---------------------------
@weather_router.startup()
async def on_startup():
    print("✅ Погодный роутер запущен с эмодзи-магией!")
    asyncio.create_task(cache_cleaner())