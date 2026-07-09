import aiohttp
import asyncio
import uuid
from datetime import datetime
from typing import Optional, Dict, Tuple

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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

# Для кнопки "обновить"
weather_refresh_state: Dict[str, str] = {}


# ---------------------------
# Эмодзи и вспомогательные функции
# ---------------------------
def interpret_weather_code(code: int, is_day: bool = True) -> Tuple[str, str]:
    """Интерпретация кода погоды с эмодзи"""
    codes = {
        0: ("<tg-emoji emoji-id='5469947168523558652'>☀️</tg-emoji>", "Ясно") if is_day else ("🌙", "Ясно"),
        1: ("<tg-emoji emoji-id='5283075860188898177'>🌤</tg-emoji>", "Преимущественно ясно") if is_day else ("☁️", "Преимущ. ясно"),
        2: ("<tg-emoji emoji-id='5283197442123114023'>⛅️</tg-emoji>", "Частично облачно"),
        3: ("<tg-emoji emoji-id='5287571024500498635'>☁️</tg-emoji>", "Пасмурно"),
        45: ("<tg-emoji emoji-id='6334544061101246165'>🌫</tg-emoji>", "Туман"),
        48: ("<tg-emoji emoji-id='5458849741829842481'>🌫</tg-emoji>", "Инейный туман"),
        51: ("<tg-emoji emoji-id='5283097055852503586'>🌦</tg-emoji>", "Легкая морось"),
        53: ("<tg-emoji emoji-id='6334638988468422492'>🌧</tg-emoji>", "Умеренная морось"),
        55: ("<tg-emoji emoji-id='6334638988468422492'>🌧</tg-emoji>", "Сильная морось"),
        56: ("<tg-emoji emoji-id='5431895003821513760'>❄️</tg-emoji>", "Ледяная морось"),
        57: ("<tg-emoji emoji-id='5431895003821513760'>❄️</tg-emoji>", "Сильная ледяная морось"),
        61: ("<tg-emoji emoji-id='6334638988468422492'>🌧</tg-emoji>", "Небольшой дождь"),
        63: ("<tg-emoji emoji-id='6334638988468422492'>🌧</tg-emoji>", "Умеренный дождь"),
        65: ("<tg-emoji emoji-id='6332360083116132292'>⛈</tg-emoji>", "Сильный дождь"),
        66: ("<tg-emoji emoji-id='5458521056572611622'>🌧</tg-emoji>", "Ледяной дождь"),
        67: ("<tg-emoji emoji-id='5458521056572611622'>🌧</tg-emoji>", "Сильный ледяной дождь"),
        71: ("<tg-emoji emoji-id='5282833267551117457'>🌨</tg-emoji>", "Небольшой снег"),
        73: ("<tg-emoji emoji-id='5282833267551117457'>🌨</tg-emoji>", "Умеренный снег"),
        75: ("<tg-emoji emoji-id='5282833267551117457'>🌨</tg-emoji>", "Сильный снег"),
        77: ("<tg-emoji emoji-id='5282833267551117457'>🌨</tg-emoji>", "Снежные зерна"),
        80: ("<tg-emoji emoji-id='6334638988468422492'>🌧</tg-emoji>", "Небольшие ливни"),
        81: ("<tg-emoji emoji-id='6334751585331054055'>🌧</tg-emoji>", "Умеренные ливни"),
        82: ("<tg-emoji emoji-id='6332360083116132292'>⛈</tg-emoji>", "Сильные ливни"),
        85: ("<tg-emoji emoji-id='5458521056572611622'>🌧</tg-emoji>", "Снежные ливни"),
        86: ("<tg-emoji emoji-id='5458521056572611622'>🌧</tg-emoji>", "Сильные снежные ливни"),
        95: ("<tg-emoji emoji-id='5282731554135615450'>🌩</tg-emoji>", "Гроза"),
        96: ("<tg-emoji emoji-id='5282731554135615450'>🌩</tg-emoji>", "Гроза с градом"),
        99: ("<tg-emoji emoji-id='5282731554135615450'>🌩</tg-emoji>", "Сильная гроза с градом"),
    }
    return codes.get(code, ("❓", "Неизвестно"))


def temp_emoji(temp: float) -> str:
    """Эмодзи в зависимости от температуры"""
    if temp < -20:
        return "<tg-emoji emoji-id='5404728536810398694'>🥶</tg-emoji>"
    elif temp < -10:
        return "<tg-emoji emoji-id='5471950641918121951'>☃️</tg-emoji>"
    elif temp < 0:
        return "<tg-emoji emoji-id='5449449325434266744'>❄️</tg-emoji>"
    elif temp < 10:
        return "🧣"
    elif temp < 15:
        return "🧥"
    elif temp < 20:
        return "<tg-emoji emoji-id='5283075860188898177'>🌤</tg-emoji>"
    elif temp < 25:
        return "<tg-emoji emoji-id='5458842406025699616'>☀️</tg-emoji>"
    elif temp < 30:
        return "<tg-emoji emoji-id='6334402121022048240'>🔥</tg-emoji>"
    elif temp < 35:
        return "<tg-emoji emoji-id='5465432711218863135'>♨️</tg-emoji>"
    else:
        return "<tg-emoji emoji-id='5188649101515827817'>🌋</tg-emoji>"


def wind_emoji(speed: float) -> str:
    """Эмодзи в зависимости от скорости ветра"""
    if speed < 0.5:
        return "<tg-emoji emoji-id='5253944419870062295'>🍃</tg-emoji>"
    elif speed < 2:
        return "<tg-emoji emoji-id='5233706705769997857'>🪁</tg-emoji>"
    elif speed < 5:
        return "<tg-emoji emoji-id='6334814175889459151'>🌬</tg-emoji>"
    elif speed < 10:
        return "<tg-emoji emoji-id='5458875859525970449'>💨</tg-emoji>"
    elif speed < 15:
        return "<tg-emoji emoji-id='6332347924063717264'>🌪</tg-emoji>"
    else:
        return "<tg-emoji emoji-id='6334446006997877909'>🌀</tg-emoji>"


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
        return "<tg-emoji emoji-id='5449380056201697322'>💚</tg-emoji>"
    elif uv < 6:
        return "<tg-emoji emoji-id='5449366943666543715'>💛</tg-emoji>"
    elif uv < 8:
        return "<tg-emoji emoji-id='5449599833973203438'>🧡</tg-emoji>"
    elif uv < 11:
        return "<tg-emoji emoji-id='5434006487053655876'>❤️</tg-emoji>"
    else:
        return "<tg-emoji emoji-id='5471954395719539651'>💔</tg-emoji>"


def cloud_emoji(cover: float) -> str:
    """Эмодзи облачности"""
    if cover < 10:
        return "<tg-emoji emoji-id='5469947168523558652'>☀️</tg-emoji>"
    elif cover < 30:
        return "<tg-emoji emoji-id='5283075860188898177'>🌤</tg-emoji>"
    elif cover < 70:
        return "<tg-emoji emoji-id='5283155153875116393'>🌥</tg-emoji>"
    elif cover < 90:
        return "<tg-emoji emoji-id='5287571024500498635'>☁️</tg-emoji>"
    else:
        return "<tg-emoji emoji-id='5287571024500498635'>☁️</tg-emoji>"


def visibility_emoji(vis: float) -> str:
    """Эмодзи видимости"""
    if vis > 10:
        return "<tg-emoji emoji-id='5372846474881146350'>🔭</tg-emoji>"
    elif vis > 5:
        return "<tg-emoji emoji-id='5424892643760937442'>👁</tg-emoji>"
    elif vis > 2:
        return "<tg-emoji emoji-id='5424885441100782420'>👀</tg-emoji>"
    elif vis > 1:
        return "<tg-emoji emoji-id='6334544061101246165'>🌫</tg-emoji>"
    else:
        return "<tg-emoji emoji-id='5188311512791393083'>🔎</tg-emoji>"


def precipitation_emoji(precip: float) -> str:
    """Эмодзи осадков"""
    if precip == 0:
        return "<tg-emoji emoji-id='5469947168523558652'>☀️</tg-emoji>"
    elif precip < 2:
        return "<tg-emoji emoji-id='5283097055852503586'>🌦</tg-emoji>"
    elif precip < 10:
        return "<tg-emoji emoji-id='5283243028905994049'>🌧</tg-emoji>"
    elif precip < 20:
        return "<tg-emoji emoji-id='6332360083116132292'>⛈</tg-emoji>"
    elif precip < 50:
        return "<tg-emoji emoji-id='6334423144886961819'>🌊</tg-emoji>"
    else:
        return "<tg-emoji emoji-id='6332360083116132292'>⛈</tg-emoji>"


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


def plural_ru(n: int, forms: Tuple[str, str, str]) -> str:
    """Правильное окончание для русского языка"""
    n = abs(n) % 100
    n1 = n % 10
    if 11 <= n <= 19:
        return forms[2]
    if 2 <= n1 <= 4:
        return forms[1]
    if n1 == 1:
        return forms[0]
    return forms[2]


def build_refresh_keyboard(token: str) -> InlineKeyboardMarkup:
    """Кнопка обновления"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=f"weather_refresh:{token}"
                )
            ]
        ]
    )


def register_refresh_state(city: str) -> str:
    """Регистрируем город для кнопки обновления"""
    token = uuid.uuid4().hex[:10]
    weather_refresh_state[token] = city
    return token


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
        precip_emoji = "<tg-emoji emoji-id='6334768713660631269'>☔️</tg-emoji>" if precip_prob > 30 else "<tg-emoji emoji-id='6334546560772213058'>💧</tg-emoji>" if precip_prob > 0 else "<tg-emoji emoji-id='5283075860188898177'>🌤</tg-emoji>"

        forecast_days.append(
            f"<b>{date_str}</b>\n"
            f"{day_emoji} {day_desc}\n{temp_emoji(day_max)} {day_min}° → {day_max}°\n"
            f"{precip_emoji} {precip_prob}%\n{wind_emoji(wind_max)} {wind_max} м/с"
        )

    # Эмодзи для времени суток
    time_emoji = "🌅" if 5 <= int(data["current_time"].split(':')[0]) < 12 else \
        "🌇" if 12 <= int(data["current_time"].split(':')[0]) < 18 else \
            "🌃" if 18 <= int(data["current_time"].split(':')[0]) < 22 else "🌌"

    # Формируем итоговое сообщение
    message = (
        f"📡 <b>ПОГОДА В {city_name.upper()}</b>\n"
        f"<tg-emoji emoji-id='5429337960682113944'>🗓</tg-emoji> {data['weekday']}, {data['current_date']} | 🕒 {data['current_time']}\n\n"

        f"<b>{emoji} {desc.upper()} (облачность {cloud_cover}%)</b>\n"
        f"{temp_emoji_str} <b>{temp}°C</b> (ощущается как {feels}°C)\n\n"

        f"<tg-emoji emoji-id='5384177187018519962'>💧</tg-emoji> <b>Влажность:</b> {humidity}% (осадки {precipitation}мм)\n"
        f"{wind_direction_emoji(wind_dir)} <b>Ветер:</b> {wind_speed} м/с (порывы до {wind_gust} м/с)\n"
        f"📊 <b>Давление:</b> {pressure} гПа\n"
        f"{visibility_emoji(visibility)} <b>Видимость:</b> {visibility} км\n"
        f"{uv_index_emoji(uv_index)} <b>UV-индекс:</b> {uv_index}\n\n"

        f"<tg-emoji emoji-id='5366340737594051897'>⌚️</tg-emoji> <b>ПРОГНОЗ ПО ЧАСАМ</b>\n"
        f"<blockquote expandable>{today_forecast_text}</blockquote>\n\n"

        f"<tg-emoji emoji-id='5429337960682113944'>🗓</tg-emoji> <b>ПРОГНОЗ НА 5 ДНЕЙ</b>\n"
    )

    forecast_days_text = "\n\n".join(forecast_days)
    message += f"<blockquote expandable>{forecast_days_text}</blockquote>\n\n"

    message += f"💫 Обновлено: {datetime.now().strftime('%H:%M:%S')}\n"

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
        token = register_refresh_state(city)
        try:
            await message.answer(
                weather,
                parse_mode="HTML",
                reply_markup=build_refresh_keyboard(token)
            )
        except Exception as e:
            if "message is too long" in str(e):
                # Если сообщение слишком длинное, отправляем частями
                parts = [weather[i:i + 4000] for i in range(0, len(weather), 4000)]
                for i, part in enumerate(parts):
                    if i > 0:
                        await asyncio.sleep(0.5)
                    if i == 0:
                        await message.answer(
                            part,
                            parse_mode="HTML",
                            reply_markup=build_refresh_keyboard(token)
                        )
                    else:
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
        token = register_refresh_state(city)
        try:
            await message.answer(
                weather,
                parse_mode="HTML",
                reply_markup=build_refresh_keyboard(token)
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}")
    else:
        await message.answer(
            "❌ <b>Не удалось найти город</b>\n\nПопробуйте указать точное название или добавить страну",
            parse_mode="HTML"
        )


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
        token = register_refresh_state(city)
        try:
            await message.answer(
                weather,
                parse_mode="HTML",
                reply_markup=build_refresh_keyboard(token)
            )
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}")
    else:
        await message.answer("❌ <b>Магия не сработала!</b>\n\nПроверьте название города и попробуйте снова",
                             parse_mode="HTML")


@weather_router.callback_query(F.data.startswith("weather_refresh:"))
async def weather_refresh_handler(callback: CallbackQuery):
    token = callback.data.split(":", 1)[1]
    city = weather_refresh_state.get(token)

    if not city:
        await callback.answer("Эта кнопка устарела.", show_alert=True)
        return

    # Проверяем кэш или получаем новые данные
    cache_key = city.lower()

    if cache_key in weather_cache:
        timestamp, _ = weather_cache[cache_key]
        age = int((datetime.now() - timestamp).total_seconds())
        remaining = CACHE_TTL - age

        if remaining > 0:
            minutes, seconds = divmod(remaining, 60)
            warning_text = (
                f"⚠️ Данные еще актуальны!\n"
                f"Обновление будет доступно через: "
                f"{minutes} {plural_ru(minutes, ('минуту', 'минуты', 'минут'))} "
                f"{seconds} {plural_ru(seconds, ('секунду', 'секунды', 'секунд'))}"
            )
            await callback.answer(warning_text, show_alert=True)
            return

    # Если время кэша истекло, выполняем обновление
    weather = await process_weather_command(city)

    if not weather:
        await callback.answer("Не удалось обновить погоду.", show_alert=True)
        return

    try:
        await callback.message.edit_text(
            weather,
            parse_mode="HTML",
            reply_markup=build_refresh_keyboard(token)
        )
        await callback.answer("Данные обновлены!")
    except Exception as e:
        await callback.answer(f"Ошибка обновления: {str(e)}", show_alert=True)


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