import asyncio
import logging
import time
import psutil
from typing import Dict, Any, List
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message

from BotAutomaticWork.Middleware.SmartIntRefreshed import SmartInt
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.Gonfig.config import sanor_ID
# Импорт обновленных модулей middleware
from handlers.BotAutomaticWork.Middleware.MiddlewareMultiBot.SuperBotLoadEstimator import super_bot_load_estimator
from handlers.BotAutomaticWork.Middleware.MiddlewareMultiBot.BotRPSManager import bot_rps_manager
# Добавляем импорт для работы с пакетной обработкой
from handlers.BotAutomaticWork.Middleware.MiddlewareTimers import timer_manager
from handlers.BotAutomaticWork.Middleware.MiddlewareBackground import get_queue_stats, log_queue_stats

logger = logging.getLogger(__name__)
server_stats_router = Router(name="server_stats_fast")

# ============================================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ: кэш инстансов Bot
# ============================================================================
# Хранит: bot_id -> Bot_instance
_bot_instances_cache: Dict[str, Bot] = {}


def _get_bot_instance_by_id(bot_id: str) -> Bot:
    """Оптимизированная функция получения инстанса бота"""
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
# ФОНОВАЯ ЗАДАЧА: ОПТИМИЗИРОВАННЫЙ МОНИТОРИНГ ПИНГОВ
# ============================================================================
async def _background_ping_monitor(bot_instances: Dict[str, Bot]):
    """Оптимизированный фоновый мониторинг пингов - использует пакетную обработку"""
    logger.info("🔁 Запущен оптимизированный фоновый мониторинг пингов ботов")
    while True:
        try:
            # Собираем все пинги в пакет
            ping_tasks = []
            bot_ids = list(bot_instances.keys())

            for bot_id in bot_ids:
                bot = bot_instances[bot_id]
                ping_tasks.append(_measure_bot_ping(bot_id, bot))

            # Выполняем все пинги параллельно
            await asyncio.gather(*ping_tasks, return_exceptions=True)

            await asyncio.sleep(30)
        except asyncio.CancelledError:
            logger.info("⏹ Оптимизированный фоновый мониторинг пингов остановлен")
            break
        except Exception as e:
            logger.error(f"Ошибка в оптимизированном фоновом пинге: {e}")
            await asyncio.sleep(30)


async def _measure_bot_ping(bot_id: str, bot: Bot):
    """Измеряет пинг одного бота с обработкой ошибок"""
    try:
        start = time.time()
        await bot.get_me()
        ping_ms = (time.time() - start) * 1000

        if ping_ms < 5000:  # Игнорируем аномалии
            stats = bot_rps_manager.get_or_create_bot_stats(bot_id)
            stats.record_ping(ping_ms)
    except Exception as e:
        logger.debug(f"Пинг бота {bot_id} не удался: {e}")


def start_background_ping_monitor(bot_instances: Dict[str, Bot]):
    """Оптимизированный запуск фоновой задачи"""
    global _background_ping_task
    if _background_ping_task is None:
        _background_ping_task = asyncio.create_task(_background_ping_monitor(bot_instances))
        # Запускаем фоновую задачу пакетной обработки
        asyncio.create_task(timer_manager.start_batch_processing())


def stop_background_ping_monitor():
    """Оптимизированная остановка фоновых задач"""
    global _background_ping_task
    if _background_ping_task:
        _background_ping_task.cancel()
        _background_ping_task = None

    # Останавливаем пакетную обработку
    asyncio.create_task(timer_manager.stop_batch_processing())


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
    for chat_id, bot_id in mapping.items():  # ИСПРАВЛЕНО: chat_id, bot_id
        bot_chat_counts[bot_id] = bot_chat_counts.get(bot_id, 0) + 1

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
    """Оптимизированная функция измерения пинга БД"""
    pool = get_db_pool()
    start = time.time()
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as e:
        logger.error(f"❌ Ошибка пинга БД: {e}")
        return "-1"
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
    try:
        db_ping_val = float(db_ping)
        if db_ping_val < 5:
            return "🟢"
        elif db_ping_val < 20:
            return "🟡"
        elif db_ping_val < 50:
            return "🟠"
        else:
            return "🔴"
    except:
        return "🔴"


# ============================================================================
# КОМАНДА: !боты - ОПТИМИЗИРОВАННАЯ
# ============================================================================
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == "!бот")
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == ".бот")
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == "/бот")
async def cmd_bots_fast(message: Message):
    if message.from_user.id != sanor_ID:
        return

    try:
        start_time = time.time()
        bot_data = await _get_all_bot_data()

        ping_tasks = []
        bot_instances = {}

        for d in bot_data:
            bot_instance = _get_bot_instance_by_id(d['bot_id'])
            bot_instances[d['bot_id']] = bot_instance
            ping_tasks.append(_measure_single_bot_ping(bot_instance))

        pings_results = await asyncio.gather(*ping_tasks, return_exceptions=True)

        text_parts = ["🤖 <b>Сапфиры:</b>\n"]
        for i, d in enumerate(bot_data):
            stats = d["stats"]
            current_ping = pings_results[i] if i < len(pings_results) and not isinstance(pings_results[i],
                                                                                         Exception) else 0

            ping_stats = stats.get("ping_stats", {})
            best = ping_stats.get("best")
            worst = ping_stats.get("worst")

            load_emoji = get_load_emoji(d['load_pct'])
            ping_emoji = get_ping_emoji(current_ping)
            queue_info = d.get("queue_info", {})
            worker_status = queue_info.get("worker_running", False)

            bot_instance = bot_instances[d['bot_id']]
            try:
                bot_info = await bot_instance.get_me()
                username = bot_info.username
                bot_link = f"<a href='https://t.me/{username}'>{d['bot_name']}</a>"
            except:
                bot_link = f"{d['bot_name']}"

            # ✅ ИСПРАВЛЕНО: убраны лишние фигурные скобки
            queue_size = queue_info.get('queue_size', 0)

            text_parts.append(
                f"<b>{bot_link}</b>\n"
                f"{load_emoji} Нагрузка: {d['load_pct']:.1f}%\n"
                f"{ping_emoji} Пинг: {format_ping(current_ping)} [{format_ping(best) if best else '–'} | {format_ping(worst) if worst else '–'}]\n"
                f"{'🟢' if worker_status else '🔴'} Воркер: {'активен' if worker_status else 'остановлен'}\n"
                f"🗃️ Очередь: {SmartInt(queue_size)}\n"  # ✅ Убраны лишние скобки
            )

        processing_time = time.time() - start_time
        text_parts.append(f"\n⏱️ Обработано за {processing_time:.2f}с")

        await message.answer("\n".join(text_parts), parse_mode='HTML', disable_web_page_preview=True)
    except Exception as e:
        logger.exception("Ошибка в !боты")
        await message.answer("❌ Не удалось получить данные", parse_mode='HTML', disable_web_page_preview=True)


async def _measure_single_bot_ping(bot: Bot) -> float:
    """Измеряет пинг одного бота"""
    start = time.time()
    try:
        await bot.get_me()
    except:
        pass
    return (time.time() - start) * 1000


# ============================================================================
# КОМАНДА: !актив ботов - ОПТИМИЗИРОВАННАЯ
# ============================================================================
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == "!актив бота")
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == ".актив бота")
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == "/актив бота")
@server_stats_router.message(Command("bot_active_5_min"))
async def cmd_bots_activity(message: Message):
    if message.from_user.id != sanor_ID:
        return

    try:
        bot_data = await _get_all_bot_data()
        text_parts = [""]

        total_chats = sum(d["chat_count"] for d in bot_data)

        text_parts.append("📊 <b>ДАННЫЕ БОТОВ ЗА 5 МИНУТ:</b>")
        for d in bot_data:
            stats = d["stats"]
            errors = stats.get("error_count", 0)

            load_emoji = get_load_emoji(d['load_pct'])
            chat_share = (d['chat_count'] / total_chats * 100) if total_chats > 0 else 0

            hist_stats = d["load_history_stats"]
            avg_load = hist_stats["avg_load"]
            max_load = hist_stats["max_load"]
            trend = hist_stats["trend_load"]
            trend_emoji = "↗️" if trend > 1 else "↘️" if trend < -1 else "➡️"

            rps_stats = bot_rps_manager.get_or_create_bot_stats(d['bot_id'])
            rps_5min = rps_stats.get_rps_stats_for_last_minutes(5)
            avg_msg_rps_5min = rps_5min["avg_msg_rps"]
            peak_msg_rps_5min = rps_5min["peak_msg_rps"]
            avg_ups_rps_5min = rps_5min["avg_ups_rps"]
            peak_ups_rps_5min = rps_5min["peak_ups_rps"]

            avg_queue = hist_stats["avg_load"] / 10
            max_queue = hist_stats["max_load"] / 10
            avg_ping_internal = hist_stats["avg_handler_time"]

            bot_instance = _get_bot_instance_by_id(d['bot_id'])
            lele = await bot_instance.get_me()
            username = lele.username
            bot_link = f"<a href='https://t.me/{username}'>{d['bot_name']}</a>"

            text_parts.append(
                f"<b>\n{bot_link}</b> ({SmartInt(d['chat_count'])})\n"  # ✅ Обёрнуто в SmartInt
                f"{trend_emoji} Нагрузка: {avg_load:.1f}% ({trend:+.1f}) (пик: {max_load:.1f}%)\n"
                f"RPS:\n"
                f"      💬: {avg_msg_rps_5min:.0f} смс (пик: {peak_msg_rps_5min:.0f})\n"
                f"      👤: {avg_ups_rps_5min:.0f} юзеров (пик:  {peak_ups_rps_5min:.0f})\n"
                f"Очередь: {avg_queue:.0f} сек (пик: {max_queue:.0f} сек)\n"
                f"Внутр. время: {format_ping(avg_ping_internal) if avg_ping_internal else '–'}\n"
            )

        text_parts.append("\n⚡ <b>В ДАННЫЙ МОМЕНТ:</b>")

        db_ping = await get_db_ping_ms()
        db_ping_emoji = get_ping_db_emoji(db_ping)

        text_parts.append(f'{db_ping_emoji} Пинг бд: {SmartInt(db_ping)}мс\n\n')  # ✅ Обёрнуто в SmartInt

        for d in bot_data:
            stats = d["stats"]
            current_msg_rps = stats.get("current_msg_rps", 0)
            current_ups_rps = stats.get("current_ups_rps", 0)
            success_info = stats.get("success_info", "0/0 (0%)")

            ping_stats = stats.get("ping_stats", {})
            best = ping_stats.get("best")
            worst = ping_stats.get("worst")

            bot_instance = _get_bot_instance_by_id(d['bot_id'])
            start_ping = time.time()
            await bot_instance.get_me()
            current_ping = (time.time() - start_ping) * 1000

            load_emoji = get_load_emoji(d['load_pct'])
            rps_emoji = get_rps_emoji(current_msg_rps)
            ping_emoji = get_ping_emoji(current_ping)
            queue_emoji = get_queue_emoji(d['queue_time'])

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
# КОМАНДА: !баланс - ОПТИМИЗИРОВАННАЯ
# ============================================================================
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == "!баланс бота чек кек")
async def cmd_balance(message: Message):
    """Оптимизированная команда для балансировки ботов"""
    if message.from_user.id != sanor_ID:
        return

    try:
        start_time = time.time()
        bot_data = await _get_all_bot_data()

        total_chats = sum(d["chat_count"] for d in bot_data)
        text_parts = ["⚖️ <b>БАЛАНСИРОВКА БОТОВ</b>\n"]

        for d in bot_data:
            chat_share = (d['chat_count'] / total_chats * 100) if total_chats > 0 else 0
            load_emoji = get_load_emoji(d['load_pct'])
            queue_info = d.get("queue_info", {})
            queue_size = queue_info.get("queue_size", 0)

            text_parts.append(
                f"{load_emoji} <b>{d['bot_name']}</b>: {d['chat_count']} чатов ({chat_share:.1f}%) | "
                f"Нагр: {d['load_pct']:.1f}% | Очередь: {queue_size}\n"
            )

        text_parts.append(f"\n📊 Всего чатов: {total_chats}")

        # Добавляем рекомендации по балансировке
        if total_chats > 0:
            avg_chats_per_bot = total_chats / len(bot_data)
            text_parts.append(f"\n💡 <b>Рекомендации:</b>")

            overloaded = [d for d in bot_data if d['chat_count'] > avg_chats_per_bot * 1.5 and d['load_pct'] > 70]
            underloaded = [d for d in bot_data if d['chat_count'] < avg_chats_per_bot * 0.5 and d['load_pct'] < 30]

            if overloaded:
                text_parts.append("⚠️ Перегруженные боты:")
                for bot in overloaded:
                    text_parts.append(
                        f"  • {bot['bot_name']} ({bot['chat_count']} чатов, {bot['load_pct']:.1f}% нагрузки)")

            if underloaded:
                text_parts.append("✅ Недогруженные боты:")
                for bot in underloaded:
                    text_parts.append(
                        f"  • {bot['bot_name']} ({bot['chat_count']} чатов, {bot['load_pct']:.1f}% нагрузки)")

            if not overloaded and not underloaded:
                text_parts.append("✅ Балансировка оптимальна!")

        processing_time = time.time() - start_time
        text_parts.append(f"\n⏱️ Обработано за {processing_time:.2f}с")

        await message.answer("\n".join(text_parts), parse_mode='HTML')
    except Exception as e:
        logger.exception("Ошибка в !баланс")
        await message.answer("❌ Не удалось получить баланс", parse_mode='HTML')


# ============================================================================
# КОМАНДА: !сервер - ОПТИМИЗИРОВАННАЯ
# ============================================================================
def get_server_info() -> str:
    """Оптимизированная функция получения информации о сервере"""
    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.1)

    # RAM
    ram = psutil.virtual_memory()
    ram_used_gb = ram.used / (1024 ** 3)
    ram_total_gb = ram.total / (1024 ** 3)
    ram_percent = ram.percent

    # Диск
    disk = psutil.disk_usage("/")
    disk_free_gb = disk.free / (1024 ** 3)
    disk_total_gb = disk.total / (1024 ** 3)
    disk_percent = (disk_total_gb - disk_free_gb) / disk_total_gb * 100

    # Сеть
    net_io = psutil.net_io_counters()
    bytes_sent = net_io.bytes_sent / (1024 ** 2)  # MB
    bytes_recv = net_io.bytes_recv / (1024 ** 2)  # MB

    # Процессы
    process_count = len(psutil.pids())

    return (
        f"🖥 <b>СИСТЕМНАЯ ИНФОРМАЦИЯ</b>\n"
        f"• CPU: {cpu_percent:.1f}%\n"
        f"• RAM: {ram_percent:.1f}% ({ram_used_gb:.1f} / {ram_total_gb:.1f} GB)\n"
        f"• Диск: {disk_percent:.1f}% занято ({disk_free_gb:.1f} GB свободно)\n"
        f"• Сеть: {bytes_sent:.1f} MB отправлено, {bytes_recv:.1f} MB получено\n"
        f"• Процессы: {process_count}\n"
    )


@server_stats_router.message(F.text.split("\n", 1)[0].lower() == "!сервер")
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == ".сервер")
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == "/сервер")
async def cmd_server_info(message: Message):
    """Оптимизированная команда для получения информации о сервере"""
    if message.from_user.id != sanor_ID:
        return

    try:
        start_time = time.time()
        info = get_server_info()
        processing_time = time.time() - start_time
        info += f"\n⏱️ Получено за {processing_time:.2f}с"
        await message.answer(info, parse_mode="HTML")
    except Exception as e:
        logger.exception("Ошибка в !сервер")
        await message.answer("❌ Не удалось получить данные сервера")


# ============================================================================
# ДОПОЛНИТЕЛЬНАЯ КОМАНДА: !очередь - НОВОЕ
# ============================================================================
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == "!очередь")
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == ".очередь")
@server_stats_router.message(F.text.split("\n", 1)[0].lower() == "/очередь")
async def cmd_queue_stats(message: Message):
    """Новая команда для детального просмотра очередей обработки"""
    if message.from_user.id != sanor_ID:
        return

    try:
        start_time = time.time()
        stats = get_queue_stats()

        text_parts = ["🗃️ <b>СТАТИСТИКА ОЧЕРЕДЕЙ</b>\n"]

        for bot_id, stat in stats.items():
            queue_size = stat['queue_size']
            worker_running = stat['worker_running']
            max_delay = stat['max_delay']
            last_update = stat['last_update']

            # Определяем статус очереди
            if queue_size == 0:
                queue_status = "✅ Пуста"
            elif queue_size < 50:
                queue_status = "🟡 Нормальная"
            elif queue_size < 200:
                queue_status = "🟠 Загружена"
            else:
                queue_status = "🔴 Перегружена"

            # Определяем статус воркера
            worker_status = "🟢 Активен" if worker_running else "🔴 Остановлен"

            # Время с последнего обновления
            time_since_update = time.time() - last_update if last_update else 0
            update_status = "✅ Актуальна" if time_since_update < 30 else f"⚠️ Не обновлялась {time_since_update:.0f}с"

            text_parts.append(
                f"<b>봇 {bot_id}</b>\n"
                f"Статус: {queue_status}\n"
                f"Размер: {queue_size} элементов\n"
                f"Воркер: {worker_status}\n"
                f"Макс. задержка: {max_delay:.2f}с\n"
                f"Данные: {update_status}\n"
            )

        processing_time = time.time() - start_time
        text_parts.append(f"\n⏱️ Обработано за {processing_time:.2f}с")

        await message.answer("\n".join(text_parts), parse_mode='HTML', disable_web_page_preview=True)
    except Exception as e:
        logger.exception("Ошибка в !очередь")
        await message.answer("❌ Не удалось получить статистику очередей", parse_mode='HTML',
                             disable_web_page_preview=True)


# ============================================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ для фоновой задачи
# ============================================================================
_background_ping_task = None
_PING_INTERVAL = 30  # секунд