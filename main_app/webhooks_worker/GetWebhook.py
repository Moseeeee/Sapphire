import hashlib
import hmac
import logging
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional

from main_app.webhooks_worker.FilterWebhook import optimizer

logger = logging.getLogger(__name__)

# Роутер для вебхуков
webhook_router = APIRouter()

# Мастер-соль (ЗАМЕНИ НА СВОЮ И НЕ ПОКАЗЫВАЙ НИКОМУ)
# Она должна быть одинаковой в work.py и GetWebhook.py
SECRET_SALT = "SuperSecureSalt_SapphireProject_2026_Protected"


def generate_bot_secure_credentials(bot_token: str) -> tuple[str, str]:
    """Генерирует уникальный URL-хэш и Secret Token для конкретного бота"""
    # Создаем уникальный URL-хэш для пути
    url_hash = hmac.new(SECRET_SALT.encode(), bot_token.encode(), hashlib.sha256).hexdigest()[:32]
    # Создаем уникальный секретный токен для заголовков (от 1 до 256 символов по доке ТГ)
    secret_token = hmac.new((SECRET_SALT + "_headers").encode(), bot_token.encode(), hashlib.sha256).hexdigest()
    return url_hash, secret_token


# Сложный и запутанный путь с маской для префикса и токена
@webhook_router.post("/api/v3/ingress/secure_tunnel/route_obfuscation_{url_hash}/{bot_token}")
async def receive_webhook(
        url_hash: str,
        bot_token: str,
        request: Request,
        x_telegram_bot_api_secret_token: Optional[str] = Header(None)  # Перехватываем секрет из заголовков Telegram
):
    """Эндпоинт повышенной безопасности для приема апдейтов."""

    bots_dict = request.app.state.bots_dict
    dp = request.app.state.dp

    bot = bots_dict.get(bot_token)
    if not bot:
        logger.warning(f"🚨 Попытка доступа с неизвестным токеном бота!")
        raise HTTPException(status_code=403, detail="Access Denied")

    # Пересчитываем валидные хэши для этого конкретного бота
    expected_url_hash, expected_secret_token = generate_bot_secure_credentials(bot_token)

    # 1. Проверка валидности URL-хэша (защита от сканирования путей)
    if not hmac.compare_digest(url_hash, expected_url_hash):
        logger.warning(f"🚨 Фейковый URL-префикс при парсинге вебхука!")
        raise HTTPException(status_code=403, detail="Access Denied")

    # 2. Проверка секретного токена из заголовков (защита от подделки запросов со стороны)
    if not x_telegram_bot_api_secret_token or not hmac.compare_digest(x_telegram_bot_api_secret_token,
                                                                      expected_secret_token):
        logger.warning(f"🚨 Запрос без валидного X-Telegram-Bot-Api-Secret-Token заголовка!")
        raise HTTPException(status_code=403, detail="Access Denied")

    try:
        # Пакет полностью верифицирован, он пришел от реального Telegram-сервера
        update_data = await request.json()

        # Отправляем в оптимизатор-очередь
        await optimizer.add_update(bot, update_data, dp)

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Ошибка при обработке проверенного вебхука: {e}")
        return {"status": "error"}