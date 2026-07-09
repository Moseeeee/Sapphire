import logging
from datetime import datetime, timedelta
import pytz

from BotAutomaticWork.users.checks.check_users_status_online.check_online_statusDB import get_user_activity

logger = logging.getLogger(__name__)

# Определяем московский часовой пояс
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

async def get_user_status(user_id):
    """
    Проверяет статус пользователя и возвращает соответствующий эмодзи
    🔥 - онлайн (менее 2 минут)
    🥱 - неактивен (более 2 минут, но менее 15 минут)
    😴 - оффлайн (более 15 минут)
    """
    try:
        if user_id is None:
            return '(😴 оффлайн)'

        user_id = int(user_id)
        last_activity_str = await get_user_activity(user_id)

        if not last_activity_str:
            return '(😴 оффлайн)'

        # Если это строка, преобразуем в datetime
        if isinstance(last_activity_str, str):
            last_activity = datetime.fromisoformat(last_activity_str)
            # Если время наивное (без часового пояса), добавляем московский пояс
            if last_activity.tzinfo is None:
                last_activity = MOSCOW_TZ.localize(last_activity)
        else:
            last_activity = last_activity_str

        # Получаем текущее время в московском часовом поясе
        current_time = datetime.now(MOSCOW_TZ)

        time_diff = current_time - last_activity

        if time_diff <= timedelta(minutes=2):
            return '🔥'  # Онлайн
        elif time_diff <= timedelta(minutes=15):
            return '🥱'  # Неактивен
        else:
            return '😴'  # Оффлайн

    except (ValueError, TypeError) as e:
        logger.error(f"Ошибка при обработке времени для пользователя {user_id}: {e}")
        return '❔'
    except Exception as e:
        logger.error(f"Неожиданная ошибка для пользователя {user_id}: {e}", exc_info=True)
        return '❔'