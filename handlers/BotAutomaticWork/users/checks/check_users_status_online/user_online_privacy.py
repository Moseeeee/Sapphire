import logging
from datetime import datetime, timedelta
import pytz

from BotAutomaticWork.parse_time_auto import format_time_ago
# Убедись, что импорт функции корректен для твоего проекта
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# =====================================================================
# ГЛАВНЫЙ ГЕНЕРАТОР ФРАЗЫ ДЛЯ ПРОФИЛЯ
# =====================================================================
async def get_user_online_phrase(user_id: int, gender_verb: str = "был(а)", bypass_privacy: bool = False) -> str:
    """
    bypass_privacy=True — принудительно показывает точное время (для админ-команды 'чек онлайн').
    bypass_privacy=False — учитывает настройки приватности юзера.
    """
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT last_activity, online_mode FROM users WHERE user_id = $1',
                int(user_id)
            )

        if not row or not row['last_activity']:
            return f"{gender_verb} давно"

        mode = row['online_mode'] or 'exact'
        dt = row['last_activity']

        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        if dt.tzinfo is None:
            dt = MOSCOW_TZ.localize(dt)

        now = datetime.now(MOSCOW_TZ)
        diff = now - dt
        time_ago_str = format_time_ago(dt) # Получаем строку типа "только что" или "1 минуту назад"

        # 1. Принудительный показ для админа (чек онлайн)
        if bypass_privacy:
            # Даже если онлайн (<= 2 мин), теперь добавим время
            if diff <= timedelta(minutes=2):
                return f"{gender_verb} {time_ago_str}"
            return f"{gender_verb} {time_ago_str}"

        # 2. Обычный режим (твой онлайн)
        if mode == 'hidden':
            return "онлайн пользователя не доступен"

        # Прямо сейчас в сети (до 2 мин)
        if diff <= timedelta(minutes=2):
            return f"{gender_verb} {time_ago_str}"

        # Примерный режим
        if mode == 'approx':
            if diff <= timedelta(days=3):
                return f"{gender_verb} недавно"
            elif diff <= timedelta(days=7):
                return f"{gender_verb} неделю назад"
            else:
                return f"{gender_verb} давно"

        # Точный режим
        return f"{gender_verb} {time_ago_str}"

    except Exception as e:
        logger.error(f"Ошибка в get_user_online_phrase для {user_id}: {e}", exc_info=True)
        return f"{gender_verb} давно"


async def get_user_online_emoji(user_id: int) -> str:
    """
    Матрица статусов:
    hidden -> всегда 😴
    approx -> ☀️ (до 2 мин) -> сразу 😴
    exact  -> ☀️ (до 2 мин) -> 🥱 (до 15 мин) -> 😴
    """
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT last_activity, online_mode FROM users WHERE user_id = $1',
                int(user_id)
            )

        if not row or not row['last_activity']:
            return "😴"

        mode = row['online_mode'] or 'exact'
        dt = row['last_activity']

        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        if dt.tzinfo is None:
            dt = MOSCOW_TZ.localize(dt)

        diff = datetime.now(MOSCOW_TZ) - dt

        # 1. СКРЫТЫЙ РЕЖИМ — глухая стена
        if mode == 'hidden':
            return "🌑"

        # Если юзер активен прямо сейчас (до 2 мин) — светится и у 'exact', и у 'approx'
        if diff <= timedelta(minutes=2):
            return "☀️"

        # --- Далее идут те, кто НЕ в сети (> 2 минут) ---

        # 2. ЧАСТИЧНЫЙ РЕЖИМ — минуя "🥱", сразу падает в "😴"
        if mode == 'approx':
            return "🌑"

        # 3. ТОЧНЫЙ РЕЖИМ — проверяем хвост "неактивен" (от 2 до 15 мин)
        if diff <= timedelta(minutes=15):
            return "🌗"

        return "🌑"

    except Exception as e:
        logger.error(f"Ошибка в get_user_online_emoji для {user_id}: {e}")
        return "🌑"