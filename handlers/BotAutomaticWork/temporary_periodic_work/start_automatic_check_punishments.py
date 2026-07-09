import aiohttp
import asyncio
import logging
from datetime import datetime
from typing import List, Tuple
import pytz
from aiogram import Router
from aiogram.exceptions import TelegramBadRequest

from handlers.AdminsTools.ChatSettings.message_pinned.pin_smsDB import remove_pinned_message
from handlers.AdminsTools.CommandsModerations.warns.warnsDB import clear_expired_warns
from handlers.AdminsTools.CommandsModerations.mute.muteDB import remove_mute_info
from handlers.AdminsTools.CommandsModerations.bans.banDB import remove_ban_info
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.BotAutomaticWork.universal_bot import bot

logger = logging.getLogger(__name__)
MOSCOW_TZ = pytz.timezone('Europe/Moscow')


def get_moscow_time() -> datetime:
    """Получить текущее время в московском часовом поясе."""
    return datetime.now(MOSCOW_TZ)


async def get_expired_punishments() -> List[Tuple[int, int, str]]:
    """Получает список истекших банов и мутов."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            current_time = get_moscow_time()

            # Получаем все истекшие наказания одним запросом
            rows = await conn.fetch('''
                SELECT chat_id, user_id, types 
                FROM punishment_time 
                WHERE types IN ('ban', 'mute') 
                  AND time_end::TIMESTAMPTZ <= $1::TIMESTAMPTZ
            ''', current_time)

            return [(row['chat_id'], row['user_id'], row['types']) for row in rows]

    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def get_expired_warns() -> List[Tuple[int, int]]:
    """Получает список истекших предупреждений."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            current_time = get_moscow_time()
            rows = await conn.fetch('''
                SELECT chat_id, user_id 
                FROM warns 
                WHERE expires_at::TIMESTAMPTZ <= $1::TIMESTAMPTZ
            ''', current_time)
            return [(row['chat_id'], row['user_id']) for row in rows]
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


async def perform_auto_unban(chat_id: int, user_id: int) -> bool:
    """Выполняет автоматический разбан."""
    try:
        try:
            await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
            await remove_ban_info(chat_id, user_id)

            user_link = await user_link_global(user_id)
            await bot.send_message(
                chat_id=chat_id,
                text=f'✅ {user_link} был разбанен.\nТеперь он может вернуться в чат!',
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            return True
        except TelegramBadRequest as e:
            error_message = str(e).lower()
            # Если пользователь уже разбанен, не найден или стал админом
            if "not found" in error_message or "administrator" in error_message or "admin" in error_message:
                logger.warning(f"⚠️ Предупреждение при разбане {user_id} в чате {chat_id}: {e}. Удаляем запись.")
                await remove_ban_info(chat_id, user_id)
                return True
            elif "not enough rights" in error_message or "not an administrator" in error_message:
                logger.error(f"❌ Бот не имеет прав для разбана {user_id} в чате {chat_id}")
                return False
            else:
                logger.error(f"❌ Ошибка Telegram при разбане {user_id}: {e}")
                await remove_ban_info(chat_id, user_id)
                return True
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


async def perform_auto_unmute(chat_id: int, user_id: int) -> bool:
    """Выполняет автоматический размут."""
    try:
        try:
            chat_member = await bot.get_chat_member(chat_id, user_id)
            chat = await bot.get_chat(chat_id)

            # Если пользователь администратор - просто удаляем запись
            if chat_member.status in ['administrator', 'creator']:
                logger.warning(f"⚠️ Пользователь {user_id} является администратором, удаляем запись о муте")
                await remove_mute_info(chat_id, user_id)

                user_link = await user_link_global(user_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=f'ℹ️ {user_link} является администратором, запись о муте удалена.',
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
                return True

            # Если не администратор - размут
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=chat.permissions
            )
            await remove_mute_info(chat_id, user_id)

            user_link = await user_link_global(user_id)
            await bot.send_message(
                chat_id=chat_id,
                text=f'✅ {user_link} снова может общаться в чате.',
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            return True

        except TelegramBadRequest as e:
            error_message = str(e).lower()

            # Пользователь является администратором
            if "administrator" in error_message or "admin" in error_message:
                logger.warning(f"⚠️ Пользователь {user_id} администратор, удаляем запись о муте")
                await remove_mute_info(chat_id, user_id)
                return True

            # Бот не является администратором или нет прав
            elif "not an administrator" in error_message or "not enough rights" in error_message:
                logger.error(f"❌ Бот не имеет прав для размута {user_id} в чате {chat_id}")
                return False

            # Пользователь или чат не найдены
            elif "user not found" in error_message or "chat not found" in error_message:
                logger.warning(f"⚠️ Пользователь {user_id} или чат {chat_id} не найден, удаляем запись")
                await remove_mute_info(chat_id, user_id)
                return True

            # Неизвестная ошибка Telegram
            else:
                logger.error(f"❌ Неизвестная ошибка Telegram при размуте {user_id}: {error_message}")
                await remove_mute_info(chat_id, user_id)
                return True

        except asyncio.TimeoutError:
            logger.error(f"⏰ Таймаут при размуте {user_id} в чате {chat_id}")
            return False

        except aiohttp.ClientError as e:
            logger.error(f"🌐 Ошибка сети при размуте {user_id}: {e}")
            return False

        except Exception as e:
            logger.error(f"❌ Непредвиденная ошибка при размуте {user_id} в чате {chat_id}: {e}", exc_info=True)
            return False

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в perform_auto_unmute для {user_id}: {e}", exc_info=True)
        return False


async def perform_auto_unpin(chat_id: int, message_id: int) -> bool:
    """Автоматически открепляет сообщение"""
    try:
        await bot.unpin_chat_message(chat_id=chat_id, message_id=message_id)
        await remove_pinned_message(chat_id, message_id)
        pin_text = f'<a href="https://t.me/c/{str(chat_id)[4:]}/{message_id}">Сообщение</a>'
        await bot.send_message(chat_id=chat_id,
                               text=f'{pin_text} было откреплено!')
        return True
    except Exception as e:
        logger.error(f"Ошибка при автооткреплении: {e}")
        await remove_pinned_message(chat_id, message_id)
        return False


async def get_expired_pinned_messages_auto() -> List[Tuple[int, int]]:
    """Получает список сообщений для автооткрепления"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            current_time = get_moscow_time()
            rows = await conn.fetch('''
                SELECT chat_id, message_id 
                FROM pinned_messages 
                WHERE unpin_time::TIMESTAMPTZ <= $1::TIMESTAMPTZ
            ''', current_time)
            return [(row['chat_id'], row['message_id']) for row in rows]
    except Exception as e:
        logger.error(f"Ошибка при получении истекших закреплений: {e}")
        return []


async def get_next_check_interval() -> int:
    """Определяет оптимальный интервал до следующей проверки."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            current_time = get_moscow_time()

            result = await conn.fetchval('''
                SELECT MIN(next_time) FROM (
                    SELECT MIN(time_end::TIMESTAMPTZ) AS next_time FROM punishment_time WHERE time_end::TIMESTAMPTZ > $1::TIMESTAMPTZ
                    UNION ALL
                    SELECT MIN(expires_at::TIMESTAMPTZ) AS next_time FROM warns WHERE expires_at::TIMESTAMPTZ > $1::TIMESTAMPTZ
                    UNION ALL
                    SELECT MIN(unpin_time::TIMESTAMPTZ) AS next_time FROM pinned_messages WHERE unpin_time::TIMESTAMPTZ > $1::TIMESTAMPTZ
                ) AS sub
            ''', current_time)

            if result:
                if isinstance(result, datetime):
                    next_expiry = result
                else:
                    next_expiry = datetime.fromisoformat(str(result))

                if next_expiry.tzinfo is None:
                    next_expiry = next_expiry.replace(tzinfo=MOSCOW_TZ)
                else:
                    next_expiry = next_expiry.astimezone(MOSCOW_TZ)

                current_time_moscow = get_moscow_time()
                seconds_until_next = (next_expiry - current_time_moscow).total_seconds()

                if seconds_until_next > 0:
                    # Динамически спим до следующего наказания (не чаще 5 сек и не реже 30 сек для отзывчивости)
                    return max(30, min(int(seconds_until_next), 500))

        return 500  # Если активных задач в БД нет, спим 30 секунд

    except Exception as e:
        logger.error(e, exc_info=True)
        return 500


async def auto_punishment_check():
    """Основной цикл автоматической проверки наказаний и закреплений"""
    logger.info("🔁 Система автоматической проверки наказаний и закреплений запущена")
    while True:
        try:
            check_interval = await get_next_check_interval()

            expired_punishments = await get_expired_punishments()
            expired_warns = await get_expired_warns()
            expired_pins = await get_expired_pinned_messages_auto()

            if expired_punishments:
                for chat_id, user_id, p_type in expired_punishments:
                    if p_type == 'ban':
                        await perform_auto_unban(chat_id, user_id)
                    elif p_type == 'mute':
                        await perform_auto_unmute(chat_id, user_id)
                    await asyncio.sleep(0.5)

            if expired_warns:
                await clear_expired_warns()

            await asyncio.sleep(check_interval)

        except asyncio.CancelledError:
            logger.info("Система автоматической проверки остановлена")
            break
        except Exception as e:
            logger.error(f"Ошибка в автоматической проверке: {e}")
            await asyncio.sleep(30)


start_checking_punishments = Router()


@start_checking_punishments.startup()
async def start_auto_punishment_check():
    """Запускает фоновую задачу автоматической проверки."""
    try:
        logger.info("🚀 Запуск системы автоматической проверки наказаний...")
        asyncio.create_task(auto_punishment_check())
        print('ok 010101001010101010101010101010100')
    except Exception as e:
        logger.error(e, exc_info=True)
        print('error')