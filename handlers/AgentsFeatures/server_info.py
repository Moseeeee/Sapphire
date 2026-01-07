import asyncio
import logging
import time
import psutil
from typing import Dict, Any, List
from aiogram import Router, F, Bot
from aiogram.types import Message

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.Gonfig.config import sanor_ID
from handlers.BotAutomaticWork.Middleware.MiddlewareMultiBot.SuperBotLoadEstimator import super_bot_load_estimator
from handlers.BotAutomaticWork.Middleware.MiddlewareMultiBot.BotRPSManager import bot_rps_manager

logger = logging.getLogger(__name__)
server_stats_router = Router(name="server_stats_fast")

# ============================================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ: кэш инстансов Bot
# ============================================================================
# Хранит: bot_id -> Bot_instance
_bot_instances_cache: Dict[str, Bot] = {}


def _get_bot_instance_by_id(bot_id: str) -> Bot:
    """Получить инстанс бота по его ID, создав при необходимости"""
    global _bot_instances_cache
    if bot_id in _bot_instances_cache:
        return _bot_instances_cache[bot_id]

    # Импортируем конфиг
    from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig
    bot_config = MultiBotConfig.get_bot_by_id(bot_id)
    if not bot_config:
        raise RuntimeError(f"Bot config for bot_id '{bot_id}' not found in MultiBotConfig.")

    token = bot_config.get("TOKEN")
    if not token:
        raise RuntimeError(f"Token for bot_id '{bot_id}' is missing.")

    # Создаём инстанс Bot
    new_bot = Bot(token=token)
    _bot_instances_cache[bot_id] = new_bot
    return new_bot


# ============================================================================
# ФОНОВАЯ ЗАДАЧА: ПЕРИОДИЧЕСКАЯ ПРОВЕРКА ПИНГОВ
# ============================================================================
async def _background_ping_monitor(bot_instances: Dict[str, Bot]):
    """Фоновая задача: каждые 30 секунд измеряет пинг всех ботов"""
    logger.info("🔁 Запущен фоновый мониторинг пингов ботов")
    while True:
        try:
            for bot_id, bot in bot_instances.items():
                try:
                    start = time.time()
                    await bot.get_me()  # Реальный вызов Telegram API
                    ping_ms = (time.time() - start) * 1000
                    if ping_ms < 5000:  # Игнорируем аномалии
                        stats = bot_rps_manager.get_or_create_bot_stats(bot_id)
                        stats.record_ping(ping_ms)
                except Exception as e:
                    logger.debug(f"Пинг бота {bot_id} не удался: {e}")
                    # Ошибку НЕ записываем как ошибку обработки — это просто пинг
            await asyncio.sleep(30)  # используем фиксированный интервал
        except asyncio.CancelledError:
            logger.info("⏹ Фоновый мониторинг пингов остановлен")
            break
        except Exception as e:
            logger.error(f"Ошибка в фоновом пинге: {e}")
            await asyncio.sleep(30)


def start_background_ping_monitor(bot_instances: Dict[str, Bot]):
    """Запуск фоновой задачи (вызывать при старте ботов)"""
    global _background_ping_task
    if _background_ping_task is None:
        _background_ping_task = asyncio.create_task(_background_ping_monitor(bot_instances))


def stop_background_ping_monitor():
    """Остановка фоновой задачи"""
    global _background_ping_task
    if _background_ping_task:
        _background_ping_task.cancel()
        _background_ping_task = None


# ============================================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: сбор данных по ботам
# ============================================================================
async def _get_all_bot_data() -> List[Dict[str, Any]]:
    from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig
    from handlers.BotAutomaticWork.Middleware.MiddlewareBackground import get_queue_delay_for_bot

    bot_data = []

    # Считаем, сколько чатов у каждого бота (из multi_bot_config)
    mapping = MultiBotConfig.load_active_bots()
    bot_chat_counts = {}
    for chat_bot_id in mapping.values():
        bot_chat_counts[chat_bot_id] = bot_chat_counts.get(chat_bot_id, 0) + 1

    for cfg in MultiBotConfig.BOTS:
        bot_id = cfg["id"]
        bot_name = cfg.get("name", bot_id)
        stats = await bot_rps_manager.get_bot_stats_detailed(bot_id) or {}
        # Используем подсчёт из multi_bot_config
        chat_count = bot_chat_counts.get(bot_id, 0)
        queue_time = await get_queue_delay_for_bot(bot_id)

        # === НОВОЕ: нагрузка из SuperBotLoadEstimator ===
        load_pct = super_bot_load_estimator.calculate_bot_load(bot_id)

        # Получаем метрики для истории (если нужно)
        metrics = super_bot_load_estimator.get_bot_metrics(bot_id)

        # Получаем статистику за 5 минут
        history_stats = super_bot_load_estimator.get_bot_history_stats(bot_id, 5)

        bot_data.append({
            "bot_id": bot_id,
            "bot_name": bot_name,
            "chat_count": chat_count,
            "load_pct": load_pct,  # теперь это "супер точная нагрузка"
            "load_history_stats": history_stats,
            "queue_time": queue_time,
            "stats": stats
        })
    return bot_data


async def get_db_ping_ms():
    """Измеряет пинг к БД (время ответа SELECT 1)"""
    pool = get_db_pool()
    start = time.time()
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as e:
        logger.error(f"❌ Ошибка пинга БД: {e}")
        return -1  # или float('inf')
    db_ping = (time.time() - start) * 1000
    return f"{db_ping:.0f}"


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ: форматирование и эмодзи
# ============================================================================
def format_ping(value: float) -> str:
    return f"{value:.0f}мс"


def get_load_emoji(load: float) -> str:
    if load < 20:
        return "🟢"
    elif load < 50:
        return "🟡"
    elif load < 80:
        return "🟠"
    else:
        return "🔴"


def get_rps_emoji(msg_rps: float) -> str:
    if msg_rps < 5:
        return "🟢"
    elif msg_rps < 20:
        return "🟡"
    elif msg_rps < 50:
        return "🟠"
    else:
        return "🔴"


def get_ping_emoji(ping: float) -> str:
    if ping < 200:
        return "🟢"
    elif ping < 500:
        return "🟡"
    elif ping < 1000:
        return "🟠"
    else:
        return "🔴"


def get_queue_emoji(queue_time: float) -> str:
    if queue_time < 0.5:
        return "🟢"
    elif queue_time < 2.0:
        return "🟡"
    elif queue_time < 5.0:
        return "🟠"
    else:
        return "🔴"


def get_error_emoji(errors: int) -> str:
    if errors == 0:
        return "🟢"
    elif errors < 5:
        return "🟡"
    elif errors < 10:
        return "🟠"
    else:
        return "🔴"


def get_ping_db_emoji(db_ping) -> str:
    if db_ping < '5':
        return "🟢"
    elif db_ping < '20':
        return "🟡"
    elif db_ping < '50':
        return "🟠"
    else:
        return "🔴"


# ============================================================================
# КОМАНДА: !боты
# ============================================================================
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == "!боты")
async def cmd_bots_fast(message: Message):

    if message.from_user.id != sanor_ID:
        return

    try:
        bot_data = await _get_all_bot_data()
        text_parts = ["🤖 <b>Сапфиры:</b>\n"]
        for d in bot_data:
            stats = d["stats"]

            ping_stats = stats.get("ping_stats", {})
            best = ping_stats.get("best")
            worst = ping_stats.get("worst")

            # === ИСПРАВЛЕНО: пинг сейчас для КОНКРЕТНОГО бота ===
            bot_instance = _get_bot_instance_by_id(d['bot_id'])  # Получаем инстанс по ID
            start_ping = time.time()
            await bot_instance.get_me()  # Вызов get_me() для конкретного бота
            current_ping = (time.time() - start_ping) * 1000

            # Emoji
            load_emoji = get_load_emoji(d['load_pct'])
            ping_emoji = get_ping_emoji(current_ping)
            # queue_emoji = get_queue_emoji(d['queue_time'])

            # Получаем username текущего бота (для ссылки)
            lele = await bot_instance.get_me()  # <- ИСПОЛЬЗУЕМ ТОТ ЖЕ ИНСТАНС
            username = lele.username
            bot_link = f"<a href='https://t.me/{username}'>{d['bot_name']}</a>"

            text_parts.append(
                f"<b>{bot_link}</b>\n"
                f"{load_emoji} Нагрузка: {d['load_pct']:.1f}%\n"
                f"{ping_emoji} Пинг: {format_ping(current_ping)} [{format_ping(best) if best else '–'} | {format_ping(worst) if worst else '–'}]\n"
                # f"{queue_emoji} Очередь: {d['queue_time']:.1f}с\n"
            )
        await message.answer("\n".join(text_parts), parse_mode='HTML', disable_web_page_preview=True)
    except Exception as e:
        logger.exception("Ошибка в !боты")
        await message.answer("❌ Не удалось получить данные", parse_mode='HTML', disable_web_page_preview=True)


# ============================================================================
# КОМАНДА: !актив ботов
# ============================================================================
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == "!актив ботов")
async def cmd_bots_activity(message: Message):

    if message.from_user.id != sanor_ID:
        return

    try:
        bot_data = await _get_all_bot_data()
        text_parts = [""]

        # Считаем общее количество чатов
        total_chats = sum(d["chat_count"] for d in bot_data)

        # === ДАННЫЕ ЗА 5 МИНУТ ===
        text_parts.append("📊 <b>ДАННЫЕ БОТОВ ЗА 5 МИНУТ:</b>")
        for d in bot_data:
            stats = d["stats"]
            errors = stats.get("error_count", 0)

            # Emoji
            load_emoji = get_load_emoji(d['load_pct'])

            # Доля чатов
            chat_share = (d['chat_count'] / total_chats * 100) if total_chats > 0 else 0

            # Данные за 5 минут (из SuperBotLoadEstimator)
            hist_stats = d["load_history_stats"]
            avg_load = hist_stats["avg_load"]
            max_load = hist_stats["max_load"]
            trend = hist_stats["trend_load"]
            trend_emoji = "↗️" if trend > 1 else "↘️" if trend < -1 else "➡️"

            # === НОВОЕ: RPS за 5 минут (из PerBotRPS) ===
            rps_stats = bot_rps_manager.get_or_create_bot_stats(d['bot_id'])
            rps_5min = rps_stats.get_rps_stats_for_last_minutes(5)
            avg_msg_rps_5min = rps_5min["avg_msg_rps"]
            peak_msg_rps_5min = rps_5min["peak_msg_rps"]
            avg_ups_rps_5min = rps_5min["avg_ups_rps"]
            peak_ups_rps_5min = rps_5min["peak_ups_rps"]

            # Очередь за 5 минут (условно)
            avg_queue = hist_stats["avg_load"] / 10  # условно: avg_load / 10 = avg_queue
            max_queue = hist_stats["max_load"] / 10

            # Пинги за 5 минут (из SuperBotLoadEstimator, но это не пинги API, а внутренние метрики)
            avg_ping_internal = hist_stats["avg_handler_time"]  # Это внутреннее время, не пинг API

            # Получаем username текущего бота (для ссылки)
            bot_instance = _get_bot_instance_by_id(d['bot_id'])
            lele = await bot_instance.get_me()
            username = lele.username
            bot_link = f"<a href='https://t.me/{username}'>{d['bot_name']}</a>"

            text_parts.append(
                f"<b>\n{bot_link}</b> ({d['chat_count']})\n"
                f"{trend_emoji} Нагрузка: {avg_load:.1f}% ({trend:+.1f}) (пик: {max_load:.1f}%)\n"
                f"RPS:\n"
                f"      💬: {avg_msg_rps_5min:.0f} смс (пик: {peak_msg_rps_5min:.0f})\n"  # Используем данные из PerBotRPS
                f"      👤: {avg_ups_rps_5min:.0f} юзеров (пик:  {peak_ups_rps_5min:.0f})\n"  # Используем данные из PerBotRPS
                f"Очередь: {avg_queue:.0f} сек (пик: {max_queue:.0f} сек)\n"
                f"Внутр. время: {format_ping(avg_ping_internal) if avg_ping_internal else '–'}\n"
            )

        # === АКТУАЛЬНО СЕЙЧАС ===
        text_parts.append("\n⚡ <b>В ДАННЫЙ МОМЕНТ:</b>")

        db_ping = await get_db_ping_ms()
        db_ping_emoji = get_ping_db_emoji(db_ping)

        text_parts.append(f'{db_ping_emoji} Пинг бд: {db_ping}мс\n\n')

        for d in bot_data:
            stats = d["stats"]
            # === НОВОЕ: текущие RPS (последней секунды) (из PerBotRPS) ===
            current_msg_rps = stats.get("current_msg_rps", 0)
            current_ups_rps = stats.get("current_ups_rps", 0)
            success_info = stats.get("success_info", "0/0 (0%)")

            ping_stats = stats.get("ping_stats", {})
            best = ping_stats.get("best")
            worst = ping_stats.get("worst")

            # === ИСПРАВЛЕНО: пинг сейчас для КОНКРЕТНОГО бота ===
            bot_instance = _get_bot_instance_by_id(d['bot_id'])
            start_ping = time.time()
            await bot_instance.get_me()  # Вызов get_me() для конкретного бота
            current_ping = (time.time() - start_ping) * 1000

            # Emoji
            load_emoji = get_load_emoji(d['load_pct'])
            rps_emoji = get_rps_emoji(current_msg_rps)
            ping_emoji = get_ping_emoji(current_ping)
            queue_emoji = get_queue_emoji(d['queue_time'])

            # Получаем username текущего бота (для ссылки)
            lele = await bot_instance.get_me()
            username = lele.username
            bot_link = f"<a href='https://t.me/{username}'>{d['bot_name']}</a>"

            text_parts.append(
                f"<b>{bot_link}</b> ({success_info})\n"
                f"{load_emoji} Нагрузка: {d['load_pct']:.1f}%\n"
                f"{rps_emoji} RPS: "
                f"{current_ups_rps:.0f} людей в сек. "
                f"({current_msg_rps:.0f} смс в сек.)\n"

                f"{ping_emoji} Пинг: {format_ping(current_ping)} [{format_ping(best) if best else '–'} | {format_ping(worst) if worst else '–'}]\n"
                f"{queue_emoji} Очередь: {d['queue_time']:.1f}с\n"
            )
        await message.answer("\n".join(text_parts), parse_mode='HTML', disable_web_page_preview=True)
    except Exception as e:
        logger.exception("Ошибка в !актив ботов")
        await message.answer("❌ Не удалось получить данные", parse_mode='HTML', disable_web_page_preview=True)


# ============================================================================
# КОМАНДА: !баланс
# ============================================================================
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == "!баланс")
async def cmd_balance(message: Message):

    if message.from_user.id != sanor_ID:
        return

    try:
        from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig
        bot_data = await _get_all_bot_data()

        total_chats = sum(d["chat_count"] for d in bot_data)
        text_parts = ["⚖️ <b>БАЛАНСИРОВКА БОТОВ</b>\n"]

        for d in bot_data:
            chat_share = (d['chat_count'] / total_chats * 100) if total_chats > 0 else 0
            load_emoji = get_load_emoji(d['load_pct'])
            text_parts.append(
                f"{load_emoji} <b>{d['bot_name']}</b>: {d['chat_count']} чатов ({chat_share:.1f}%) | "
                f"Нагр: {d['load_pct']:.1f}%\n"
            )

        text_parts.append(f"\n📊 Всего чатов: {total_chats}")
        await message.answer("\n".join(text_parts), parse_mode='HTML')
    except Exception as e:
        logger.exception("Ошибка в !баланс")
        await message.answer("❌ Не удалось получить баланс", parse_mode='HTML')


# ============================================================================
# КОМАНДА: !сервер
# ============================================================================
def get_server_info() -> str:
    """Возвращает компактную и полезную информацию о сервере"""
    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.1)

    # RAM
    ram = psutil.virtual_memory()
    ram_used_gb = ram.used / (1024 ** 3)
    ram_total_gb = ram.total / (1024 ** 3)
    ram_percent = ram.percent

    # Диск (раздел, где запущен скрипт)
    disk = psutil.disk_usage("/")
    disk_free_gb = disk.free / (1024 ** 3)
    disk_total_gb = disk.total / (1024 ** 3)

    return (
        f"🖥 <b>Данные:</b>\n"
        f"• CPU: {cpu_percent:.1f}%\n"
        f"• RAM: {ram_percent:.1f}% ({ram_used_gb:.1f} / {ram_total_gb:.1f} GB)\n"
        f"• Диск: {disk_free_gb:.1f} / {disk_total_gb:.1f} GB свободно\n"
    )


@server_stats_router.message(F.text.split("\n", 1)[0].lower() == "!сервер")
async def cmd_server_info(message: Message):

    if message.from_user.id != sanor_ID:
        return

    try:
        info = get_server_info()
        await message.answer(info, parse_mode="HTML")
    except Exception as e:
        logger.exception("Ошибка в !сервер")
        await message.answer("❌ Не удалось получить данные сервера")


# ============================================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ для фоновой задачи
# ============================================================================
_background_ping_task = None
_PING_INTERVAL = 30  # секунд