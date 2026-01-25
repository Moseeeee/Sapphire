# handlers/BotAutomaticWork/Middleware/MiddlewareBackground.py
import asyncio
import logging
import time
import hashlib
from datetime import datetime
from typing import Dict, Any
import pytz
from aiogram.enums import ChatMemberStatus
from handlers.BotAutomaticWork.BotCreatedGlobal import get_bot
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.Middleware.MiddlewareCache import update_ignore_cache
from handlers.BotAutomaticWork.Middleware.MiddlewareMultiBot.SuperBotLoadEstimator import super_bot_load_estimator

logger = logging.getLogger(__name__)
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
_THE_BOT = get_bot()

# === ОЧЕРЕДИ И ТРЕКИНГИ ПО БОТАМ ===
_QUEUES: Dict[str, asyncio.Queue] = {}  # bot_id -> Queue
_DELAY_TRACKERS: Dict[str, dict] = {}  # bot_id -> {"max_delay": float, "last_update": float}
_WORKER_TASKS: Dict[str, asyncio.Task] = {}  # bot_id -> Task


# ====================================

def _ensure_bot_queue(bot_id: str):
    """Создать очередь и трекер для бота, если нет"""
    if bot_id not in _QUEUES:
        _QUEUES[bot_id] = asyncio.Queue(maxsize=2000)
        _DELAY_TRACKERS[bot_id] = {"max_delay": 0.0, "last_update": 0.0}
        logger.info(f"✅ Queue created for bot {bot_id}")


async def enqueue_user_update(data: dict, bot_id: str):
    """Добавить данные в очередь конкретного бота"""
    _ensure_bot_queue(bot_id)

    # Проверяем, запущен ли воркер для этого бота
    if bot_id not in _WORKER_TASKS or _WORKER_TASKS[bot_id].done():
        pool = get_db_pool()
        _WORKER_TASKS[bot_id] = asyncio.create_task(_worker_for_bot(bot_id, _QUEUES[bot_id], pool))

    try:
        # Добавляем временную метку и ID бота
        data["enqueue_time"] = time.time()
        data["bot_id"] = bot_id

        # Логируем размер очереди перед добавлением
        queue_size = _QUEUES[bot_id].qsize()
        if queue_size > 100:
            logger.warning(f"⚠️ [{bot_id}] Queue is large: {queue_size} items")

        # Пробуем добавить в очередь
        _QUEUES[bot_id].put_nowait(data)

        # === НОВОЕ: запись API вызова ===
        metrics = super_bot_load_estimator._get_metrics(bot_id)
        metrics.record_api_call()
    except asyncio.QueueFull:
        logger.error(f"❌ [{bot_id}] Queue is full! Dropping update for user: {data.get('user_id')}")
        try:
            # Пытаемся освободить место
            _QUEUES[bot_id].get_nowait()
            _QUEUES[bot_id].task_done()
            # Пробуем снова
            _QUEUES[bot_id].put_nowait(data)
        except Exception as e:
            logger.error(f"❌ [{bot_id}] Failed to make space in queue: {e}")


async def _worker_for_bot(bot_id: str, queue: asyncio.Queue, pool):
    """Воркер для обработки очереди конкретного бота"""
    batch_size = 100
    logger.info(f"🔄 Worker started for bot {bot_id}")
    while True:
        try:
            data = await queue.get()
            batch = [data]
            # Пытаемся набрать пакет
            try:
                while len(batch) < batch_size and not queue.empty():
                    batch.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                pass

            # Обработка
            for item in batch:
                enqueue_time = item.get("enqueue_time")
                if enqueue_time is not None:
                    delay = time.time() - enqueue_time
                    tracker = _DELAY_TRACKERS.get(bot_id)
                    if tracker:
                        if delay > tracker["max_delay"]:
                            tracker["max_delay"] = delay
                        tracker["last_update"] = time.time()

            await _process_batch(pool, batch)

            for _ in batch:
                queue.task_done()
        except asyncio.CancelledError:
            logger.info(f"🛑 Worker for {bot_id} cancelled")
            break
        except Exception as e:
            logger.error(f"❌ Worker for {bot_id} error: {e}")
            await asyncio.sleep(1)


async def _process_batch(pool, batch: list):
    """Обработать пачку данных"""
    if not batch:
        return

    async with pool.acquire() as conn:
        async with conn.transaction():
            for data in batch:
                try:
                    await _process_single(conn, data)
                except Exception as e:
                    logger.error(f"Error processing user update: {e}")


async def _process_single(conn, data: dict):
    """Обработать одно обновление"""
    try:
        user_id = data["user_id"]
        name = data["name"]
        username = data["username"]
        chat_id = data.get("chat_id")
        chat_title = data.get("chat_title")
        chat_username = data.get("chat_username")

        # Пропускаем ChatMemberUpdated - они уже обработаны
        is_chat_member_update = data.get("is_chat_member_update", False)
        if is_chat_member_update:
            logger.debug(f"  Skipping already processed ChatMemberUpdate for user {user_id}")
            return

        # === НОВОЕ: замер времени БД ===
        db_start = time.time()

        # Обновление пользователя
        now = datetime.now(MOSCOW_TZ)
        now_iso = now.isoformat()

        # Вставляем или обновляем пользователя
        await conn.execute('''
        INSERT INTO users (user_id, name, username, first_seen, last_activity)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id) DO UPDATE SET
        name = EXCLUDED.name,
        username = EXCLUDED.username,
        last_activity = EXCLUDED.last_activity
        ''', user_id, name, username, now_iso, now_iso)

        # Записываем время БД
        db_time_ms = (time.time() - db_start) * 1000
        bot_id = data.get("bot_id", "unknown")
        metrics = super_bot_load_estimator._get_metrics(bot_id)
        metrics.record_db_time(db_time_ms)

        # Привязка к чату
        if chat_id and chat_id < 0:
            db_start = time.time()
            await conn.execute('''
            INSERT INTO users_chats (chat_id, user_id)
            VALUES ($1, $2)
            ON CONFLICT (chat_id, user_id) DO NOTHING
            ''', chat_id, user_id)
            db_time_ms = (time.time() - db_start) * 1000
            metrics.record_db_time(db_time_ms)

        # Обновление информации о чате
        if chat_title is not None:
            await _update_chat_info_smart(conn, chat_id, chat_title, chat_username)

        # Обновление кэша игнора
        ignored = await conn.fetchval('SELECT 1 FROM ignore_users WHERE user_id = $1', user_id)
        await update_ignore_cache(user_id, ignored is not None)

        # === НОВОЕ: запись транзакции ===
        metrics.record_transaction()
    except Exception as e:
        logger.error(f"❌ Error processing user update: {e}", exc_info=True)


async def _process_chat_member_in_background(event):
    """Обработка обновлений статуса участника в фоне"""
    try:
        # Проверяем, не обработали ли уже это событие
        if getattr(event, '_already_processed', False):
            logger.debug(f"  Chat member event already processed, skipping")
            return
        old_status = event.old_chat_member.status
        new_status = event.new_chat_member.status
        user = event.new_chat_member.user
        logger.debug(f"  Background: chat member update user_id={user.id}")
        # Здесь НЕ вызываем handle_join/handle_leave - они уже вызваны в middleware
        # Только логируем
        if old_status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED] and new_status == ChatMemberStatus.MEMBER:
            logger.debug(f"    Background: user joined (already processed)")
        elif old_status == ChatMemberStatus.MEMBER and new_status == ChatMemberStatus.LEFT:
            logger.debug(f"    Background: user left (already processed)")
        elif old_status == ChatMemberStatus.RESTRICTED and new_status == ChatMemberStatus.RESTRICTED:
            logger.debug(f"    Background: restricted status changed")
    except Exception as e:
        logger.error(f"❌ Error in chat member background processing: {e}")


async def _update_chat_info_smart(conn, chat_id: int, title: str, username: str):
    """Умное обновление информации о чате"""
    if _THE_BOT is None:
        return False

    try:
        # ВСЕГДА используем московское время
        current_time = datetime.now(MOSCOW_TZ)

        # Проверяем, нужно ли обновлять
        chat_record = await conn.fetchrow(
            '''SELECT chat_title, chat_username, invite_link_updated_at
            FROM chats WHERE chat_id = $1''',
            chat_id
        )

        needs_update = False
        if not chat_record:
            needs_update = True
        elif chat_record['chat_title'] != title or chat_record['chat_username'] != username:
            needs_update = True
        else:
            # Проверяем по времени (все время в MOSCOW_TZ)
            last_update = chat_record['invite_link_updated_at']
            if last_update:
                # Преобразуем строку из БД в datetime с учетом часового пояса
                if 'Z' in last_update:
                    # Если время в UTC, конвертируем в московское
                    last_update_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00')).astimezone(MOSCOW_TZ)
                elif '+' in last_update or '-' in last_update:
                    # Если есть смещение
                    last_update_dt = datetime.fromisoformat(last_update).astimezone(MOSCOW_TZ)
                else:
                    # Если нет часового пояса, считаем что это московское
                    last_update_dt = MOSCOW_TZ.localize(datetime.fromisoformat(last_update))

                hours_since = (current_time - last_update_dt).total_seconds() / 3600
                if hours_since >= 24 and _should_update_now(chat_id, current_time):
                    needs_update = True
            elif _should_update_now(chat_id, current_time):
                needs_update = True

        if not needs_update:
            logger.debug(f"  No need to update chat {chat_id}")
            return False

        # Получаем информацию о чате
        owner_id = None
        invite_link = None
        try:
            admins = await _THE_BOT.get_chat_administrators(chat_id)
            chat_owner = next((a for a in admins if a.status == 'creator'), None)
            if chat_owner:
                owner_id = chat_owner.user.id
        except Exception as e:
            logger.debug(f"Couldn't fetch admins for {chat_id}: {e}")

        try:
            invite_link = await _THE_BOT.export_chat_invite_link(chat_id)
        except Exception as e:
            logger.debug(f"Couldn't fetch invite link for {chat_id}: {e}")

        # Сохраняем время в московском поясе
        current_time_iso = current_time.isoformat()

        # Обновляем или вставляем запись
        if chat_record:
            await conn.execute('''
            UPDATE chats SET
            chat_title = $1,
            chat_username = $2,
            invite_link = COALESCE($3, invite_link),
            invite_link_updated_at = $4,
            owner_id = COALESCE($5, owner_id)
            WHERE chat_id = $6
            ''', title, username, invite_link, current_time_iso, owner_id, chat_id)
        else:
            await conn.execute('''
            INSERT INTO chats (
            chat_id, chat_title, chat_username, invite_link,
            invite_link_updated_at, owner_id, bot_chat_status, number_for_inputs
            ) VALUES ($1, $2, $3, $4, $5, $6, 'unknown', 1)
            ''', chat_id, title, username, invite_link, current_time_iso, owner_id)

        logger.info(f"✅ Updated chat info for {chat_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Chat update error {chat_id}: {e}", exc_info=True)
        return False


def _should_update_now(chat_id: int, current_time: datetime) -> bool:
    """Определить, нужно ли обновлять чат сейчас (всегда в московском времени)"""
    date_str = current_time.strftime("%Y-%m-%d")
    hash_int = int(hashlib.md5(f"{chat_id}_{date_str}".encode()).hexdigest(), 16)
    return current_time.hour == (hash_int % 24)


async def start_background_worker():
    """Запустить воркер на каждую очередь"""
    pool = get_db_pool()
    for bot_id in _QUEUES:
        if bot_id not in _WORKER_TASKS or _WORKER_TASKS[bot_id].done():
            _WORKER_TASKS[bot_id] = asyncio.create_task(_worker_for_bot(bot_id, _QUEUES[bot_id], pool))
            logger.info(f"✅ Started background worker for bot {bot_id}")
    logger.info("✅ All background workers started per bot")


async def stop_background_worker():
    """Остановить все воркеры"""
    for bot_id, task in _WORKER_TASKS.items():
        if not task.done():
            task.cancel()

    # Ждём завершения
    for bot_id, task in _WORKER_TASKS.items():
        try:
            await task
        except asyncio.CancelledError:
            pass

    logger.info("✅ All background workers stopped")
    _WORKER_TASKS.clear()


# === ПУБЛИЧНЫЙ МЕТОД: получить задержку очереди конкретного бота ===
async def get_queue_delay_for_bot(bot_id: str) -> float:
    """
    Возвращает актуальную задержку очереди конкретного бота в секундах.
    Если очередь не обновлялась >5 сек — возвращает 0.0.
    """
    tracker = _DELAY_TRACKERS.get(bot_id)
    if not tracker:
        return 0.0

    now = time.time()
    if now - tracker["last_update"] > 5.0:
        tracker["max_delay"] = 0.0

    return tracker["max_delay"]


def get_queue_stats() -> Dict[str, Dict[str, Any]]:
    """Получить статистику по всем очередям"""
    stats = {}
    for bot_id, queue in _QUEUES.items():
        stats[bot_id] = {
            "queue_size": queue.qsize(),
            "worker_running": bot_id in _WORKER_TASKS and not _WORKER_TASKS[bot_id].done(),
            "max_delay": _DELAY_TRACKERS.get(bot_id, {}).get("max_delay", 0),
            "last_update": _DELAY_TRACKERS.get(bot_id, {}).get("last_update", 0),
        }
    return stats


async def log_queue_stats():
    """Логировать статистику очередей"""
    stats = get_queue_stats()
    for bot_id, stat in stats.items():
        logger.info(f"📊 [{bot_id}] Queue stats: size={stat['queue_size']}, "
                    f"worker_running={stat['worker_running']}, "
                    f"max_delay={stat['max_delay']:.2f}s")