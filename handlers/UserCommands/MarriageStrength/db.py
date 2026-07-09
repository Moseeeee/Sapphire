# db.py
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# Первый уровень начинается с 0 очков
LEVELS = [
    (0, "Первый шаг"),           # Вместо "Знакомство"
    (150, "Взаимная симпатия"),   # Вместо "Симпатия"
    (500, "Живой интерес"),       # Вместо "Интерес"
    (1200, "Тайное влечение"),    # Вместо "Влечение"
    (3000, "Искренняя нежность"),  # Вместо "Нежность"
    (10000, "Глубокая привязанность"), # Вместо "Привязанность"
    (23000, "Страстный роман"),   # Вместо "Страстные отношения"
    (35000, "Полное доверие"),    # Вместо "Доверительные отношения"
    (70000, "Абсолютная гармония"), # Вместо "Гармоничные отношения"
    (150000, "Духовное единство"), # Вместо "Единство"
    (270000, "Крепкий союз"),     # Уже было 2 слова, звучит отлично
    (400000, "Дружная семья"),    # Вместо "Крепкая семья"
    (830000, "Нерушимая связь"),  # Уже было 2 слова
    (1500000, "Вечная любовь"),   # Уже было 2 слова
    (5000000, "Легендарный союз") # Вместо "Легендарные отношения"
]


def get_level_by_points(points: int) -> Tuple[int, str]:
    # Проверяем уровни с конца, чтобы определить текущий максимальный
    for i in range(len(LEVELS) - 1, -1, -1):
        if points >= LEVELS[i][0]:
            return i + 1, LEVELS[i][1]
    return 1, LEVELS[0][1]


def get_next_level_info(points: int) -> Tuple[int, str, int]:
    # Ищем первый порог, который строго больше текущих очков
    for i, (req, name) in enumerate(LEVELS):
        if points < req:
            return i + 1, name, req - points
    # Если достигнут максимальный уровень
    return len(LEVELS), LEVELS[-1][1], 0


def format_points(points: int) -> str:
    if points >= 1_000_000:
        millions = points / 1_000_000
        return f"{millions:.1f}M".replace('.', ',')
    elif points >= 1000:
        thousands = points / 1000
        return f"{thousands:.1f}к".replace('.', ',')
    else:
        return str(points)


# ==================== БРАКИ ====================
async def create_marriage(chat_id: int, user1_id: int, user2_id: int) -> int:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO marriages_strength (chat_id, user1_id, user2_id) VALUES ($1, $2, $3) RETURNING id",
            chat_id, user1_id, user2_id
        )
        return row["id"]


async def get_marriage_by_user(chat_id: int, user_id: int) -> Optional[Dict]:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, user1_id, user2_id, married_at, level, points, cooldowns, action_counters "
            "FROM marriages_strength WHERE chat_id = $1 AND (user1_id = $2 OR user2_id = $2)",
            chat_id, user_id
        )
        if row:
            data = dict(row)
            data["cooldowns"] = json.loads(data["cooldowns"] or "{}")
            data["action_counters"] = json.loads(data["action_counters"] or "{}")
            return data
        return None


async def get_marriage(marriage_id: int) -> Optional[Dict]:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM marriages_strength WHERE id = $1", marriage_id)
        if row:
            data = dict(row)
            data["cooldowns"] = json.loads(data["cooldowns"] or "{}")
            data["action_counters"] = json.loads(data["action_counters"] or "{}")
            return data
        return None


async def update_points(marriage_id: int, delta: int) -> Tuple[int, int]:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT points FROM marriages_strength WHERE id = $1", marriage_id)
        if not row:
            return 0, 0
        new_points = max(0, row["points"] + delta)
        new_level, _ = get_level_by_points(new_points)
        await conn.execute(
            "UPDATE marriages_strength SET points = $1, level = $2, last_interaction = NOW() WHERE id = $3",
            new_points, new_level, marriage_id
        )
        return new_points, new_level


async def update_cascade_cooldowns(marriage_id: int, new_cooldowns: dict):
    pool = get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT cooldowns FROM marriages_strength WHERE id = $1", marriage_id)
        cooldowns = json.loads(row["cooldowns"] or "{}") if row else {}

        now_ts = now_utc().timestamp()

        for action_name, cooldown_seconds in new_cooldowns.items():
            target_expiry = now_ts + cooldown_seconds
            if cooldowns.get(action_name, 0) < target_expiry:
                cooldowns[action_name] = target_expiry

        await conn.execute(
            "UPDATE marriages_strength SET cooldowns = $1 WHERE id = $2",
            json.dumps(cooldowns), marriage_id
        )


async def is_action_on_cooldown(marriage_id: int, action_name: str) -> Tuple[bool, int]:
    marriage = await get_marriage(marriage_id)
    if not marriage:
        return False, 0

    expiry = marriage.get("cooldowns", {}).get(action_name, 0)
    now_ts = now_utc().timestamp()

    if expiry > now_ts:
        return True, int(expiry - now_ts)
    return False, 0


async def is_epic_action_used(marriage_id: int, action_name: str) -> bool:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM marriage_epic_actions WHERE marriage_id = $1 AND action_name = $2",
            marriage_id, action_name
        )
        return row is not None


async def mark_epic_action_used(marriage_id: int, action_name: str):
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO marriage_epic_actions (marriage_id, action_name) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            marriage_id, action_name
        )


async def add_gift(marriage_id: int, gift_name: str, giver_id: int, points: int):
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO marriage_gifts (marriage_id, gift_name, giver_id, points) VALUES ($1, $2, $3, $4)",
            marriage_id, gift_name, giver_id, points
        )


async def increment_action_counter(marriage_id: int, action_name: str) -> int:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT action_counters FROM marriages_strength WHERE id = $1", marriage_id)
        counters = json.loads(row["action_counters"] or "{}") if row else {}
        new_val = counters.get(action_name, 0) + 1
        counters[action_name] = new_val
        await conn.execute(
            "UPDATE marriages_strength SET action_counters = $1 WHERE id = $2",
            json.dumps(counters), marriage_id
        )
        return new_val


async def delete_marriage(marriage_id: int):
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM marriages_strength WHERE id = $1", marriage_id)


async def get_all_marriages() -> list:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM marriages_strength")
        res = []
        for row in rows:
            data = dict(row)
            data["cooldowns"] = json.loads(data["cooldowns"] or "{}")
            data["action_counters"] = json.loads(data["action_counters"] or "{}")
            res.append(data)
        return res