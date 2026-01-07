import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict
import asyncio
import pytz
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
import re
from handlers.BotAutomaticWork.universal_bot import bot

# Импортируем твой парсер времени
from handlers.AdminsTools.ChatSettings.message_pinned.pin_smsDB import MOSCOW_TZ
from handlers.BotAutomaticWork.parse_time_auto import format_time_ago

# Создаем роутер
sms_cleanup = Router()
logger = logging.getLogger(__name__)

# Константы
MAX_MESSAGES_PER_PURGE = 100  # Максимальное количество сообщений за одну очистку
MAX_MESSAGE_AGE_HOURS = 48  # Максимальный возраст сообщения для удаления
DELETE_DELAY = 0.05  # Задержка между удалениями (чтобы не превысить лимиты)
STATUS_MESSAGE_LIFETIME = 5  # Время жизни статусных сообщений в секундах


def is_within_time_limit(message_date: datetime) -> bool:
    """Проверяет, что сообщение не старше MAX_MESSAGE_AGE_HOURS часов"""
    now = datetime.now(MOSCOW_TZ)
    time_diff = now - message_date
    return time_diff <= timedelta(hours=MAX_MESSAGE_AGE_HOURS)


async def check_bot_permissions(chat_id: int) -> bool:
    """Проверяет, есть ли у бота права на удаление сообщений"""
    try:
        # Используем универсального бота
        bot_instance = await bot.get_me()
        chat_member = await bot.get_chat_member(chat_id, bot_instance.id)
        return chat_member.can_delete_messages
    except Exception as e:
        logger.error(f"Ошибка при проверке прав бота: {e}")
        return False


async def get_message_info(chat_id: int, message_id: int) -> Optional[dict]:
    """Получает информацию о сообщении"""
    try:
        # Пробуем получить сообщение напрямую через forward
        message = await bot.forward_message(
            chat_id=chat_id,
            from_chat_id=chat_id,
            message_id=message_id
        )

        # Получаем информацию о дате из пересланного сообщения
        msg_date = message.date.replace(tzinfo=pytz.UTC).astimezone(MOSCOW_TZ)

        # Удаляем пересланное сообщение
        try:
            await message.delete()
        except:
            pass

        return {
            'date': msg_date,
            'exists': True
        }
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        if "message not found" in error_msg or "message to forward not found" in error_msg:
            return {'exists': False, 'error': 'Сообщение не найдено'}
        else:
            logger.error(f"Ошибка при получении информации о сообщении {message_id}: {e}")
            return None
    except Exception as e:
        logger.error(f"Ошибка при получении информации о сообщении {message_id}: {e}")
        return None


async def delete_single_message(chat_id: int, message_id: int) -> bool:
    """Удаляет одно сообщение"""
    try:
        await bot.delete_message(
            chat_id=chat_id,
            message_id=message_id
        )
        return True
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        if "message to delete not found" in error_msg:
            logger.debug(f"Сообщение {message_id} уже удалено")
        elif "not enough rights" in error_msg:
            logger.warning(f"Нет прав для удаления сообщения {message_id}")
        else:
            logger.error(f"Ошибка при удалении сообщения {message_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения {message_id}: {e}")
        return False


async def purge_messages_down(
        chat_id: int,
        start_message_id: int,
        count: int  # Количество сообщений для удаления ВНИЗ
) -> Tuple[List[int], int]:
    """
    Удаляет сообщения ВНИЗ от указанного ID

    Args:
        chat_id: ID чата
        start_message_id: ID начального сообщения (включительно)
        count: Количество сообщений для удаления

    Returns:
        Tuple[List[int], int]: (список ID сообщений, которые не удалось удалить, количество удаленных)
    """
    failed_ids = []
    deleted_count = 0

    try:
        # Удаляем count сообщений, начиная с start_message_id
        for i in range(count):
            current_id = start_message_id + i
            success = await delete_single_message(chat_id, current_id)
            if success:
                deleted_count += 1
            else:
                failed_ids.append(current_id)

            # Небольшая задержка чтобы не превысить лимиты
            await asyncio.sleep(DELETE_DELAY)

    except Exception as e:
        logger.error(f"Ошибка в purge_messages_down: {e}")

    return failed_ids, deleted_count


async def purge_messages_up(
        chat_id: int,
        start_message_id: int,
        count: int  # Количество сообщений для удаления ВВЕРХ
) -> Tuple[List[int], int]:
    """
    Удаляет сообщения ВВЕРХ от указанного ID

    Args:
        chat_id: ID чата
        start_message_id: ID начального сообщения (включительно)
        count: Количество сообщений для удаления

    Returns:
        Tuple[List[int], int]: (список ID сообщений, которые не удалось удалить, количество удаленных)
    """
    failed_ids = []
    deleted_count = 0

    try:
        # Удаляем count сообщений, заканчивая start_message_id
        for i in range(count):
            current_id = start_message_id - i
            if current_id <= 0:
                break  # Дошли до минимального ID

            success = await delete_single_message(chat_id, current_id)
            if success:
                deleted_count += 1
            else:
                failed_ids.append(current_id)

            # Небольшая задержка чтобы не превысить лимиты
            await asyncio.sleep(DELETE_DELAY)

    except Exception as e:
        logger.error(f"Ошибка в purge_messages_up: {e}")

    return failed_ids, deleted_count


async def purge_messages_both(
        chat_id: int,
        center_message_id: int,
        radius: int  # РАДИУС в каждую сторону
) -> Tuple[List[int], int]:
    """
    Удаляет сообщения ВВЕРХ и ВНИЗ от указанного ID

    Args:
        chat_id: ID чата
        center_message_id: ID центрального сообщения
        radius: РАДИУС в каждую сторону

    Returns:
        Tuple[List[int], int]: (список ID сообщений, которые не удалось удалить, общее количество удаленных)
    """
    all_failed_ids = []
    total_deleted = 0

    # Удаляем сообщения вверх (radius сообщений НАД центральным)
    failed_up, deleted_up = await purge_messages_up(
        chat_id=chat_id,
        start_message_id=center_message_id - 1,  # Начинаем с сообщения ПЕРЕД центральным
        count=radius  # Удаляем radius сообщений
    )
    all_failed_ids.extend(failed_up)
    total_deleted += deleted_up

    # Удаляем центральное сообщение
    if await delete_single_message(chat_id, center_message_id):
        total_deleted += 1
    else:
        all_failed_ids.append(center_message_id)

    # Удаляем сообщения вниз (radius сообщений ПОСЛЕ центрального)
    failed_down, deleted_down = await purge_messages_down(
        chat_id=chat_id,
        start_message_id=center_message_id + 1,  # Начинаем с сообщения ПОСЛЕ центрального
        count=radius  # Удаляем radius сообщений
    )
    all_failed_ids.extend(failed_down)
    total_deleted += deleted_down

    return all_failed_ids, total_deleted


async def send_status_message(chat_id: int, text: str) -> Optional[int]:
    """Отправляет статусное сообщение и возвращает его ID, или None если не удалось"""
    try:
        message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode='Markdown'
        )
        return message.message_id
    except Exception as e:
        logger.error(f"Ошибка при отправке статуса: {e}")
        return None


async def edit_status_message(chat_id: int, status_msg_id: int, text: str) -> bool:
    """Редактирует статусное сообщение"""
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg_id,
            text=text,
            parse_mode='Markdown'
        )
        return True
    except TelegramBadRequest as e:
        # Если сообщение уже удалено или недоступно
        error_msg = str(e).lower()
        if "message to edit not found" in error_msg or "message is not modified" in error_msg:
            return False
        logger.error(f"Ошибка при редактировании статуса: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при редактировании статуса: {e}")
        return False


async def delete_status_message(chat_id: int, status_msg_id: int) -> bool:
    """Удаляет статусное сообщение"""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
        return True
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        if "message to delete not found" in error_msg:
            return True  # Уже удалено - это нормально
        logger.error(f"Ошибка при удалении статуса: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при удалении статуса: {e}")
        return False


async def show_result_and_cleanup(
        chat_id: int,
        status_msg_id: Optional[int],
        result_text: str,
        delete_after: int = STATUS_MESSAGE_LIFETIME
):
    """
    Показывает результат операции и автоматически очищает сообщения

    Args:
        chat_id: ID чата
        status_msg_id: ID статусного сообщения (если есть)
        result_text: Текст результата
        delete_after: Через сколько секунд удалить статус
    """
    try:
        if status_msg_id:
            # Пытаемся отредактировать существующее статусное сообщение
            success = await edit_status_message(chat_id, status_msg_id, result_text)

            if not success:
                # Если не удалось отредактировать (сообщение удалено), отправляем новое
                new_status_msg_id = await send_status_message(chat_id, result_text)
                if new_status_msg_id:
                    # Удаляем через указанное время
                    await asyncio.sleep(delete_after)
                    await delete_status_message(chat_id, new_status_msg_id)
        else:
            # Статусного сообщения не было - отправляем результат
            new_status_msg_id = await send_status_message(chat_id, result_text)
            if new_status_msg_id:
                # Удаляем через указанное время
                await asyncio.sleep(delete_after)
                await delete_status_message(chat_id, new_status_msg_id)

    except Exception as e:
        logger.error(f"Ошибка в show_result_and_cleanup: {e}")


def parse_message_link(link: str) -> Optional[Dict[str, int]]:
    """
    Парсит ссылку на сообщение и возвращает chat_id и message_id

    Форматы ссылок:
    - https://t.me/c/1234567890/12345 (чат с отрицательным ID)
    - https://t.me/c/-1234567890/12345 (чат с отрицательным ID с минусом)
    - https://t.me/c/1234567890/12345?thread=123 (с тредом)

    Returns:
        Dict[str, int] или None: {'chat_id': int, 'message_id': int}
    """
    try:
        # Убираем параметры запроса
        link = link.split('?')[0]

        # Парсим ссылку
        match = re.search(r't\.me/c/(-?\d+)/(\d+)', link)
        if match:
            chat_id_part = match.group(1)
            message_id = int(match.group(2))

            # Конвертируем chat_id в правильный формат
            chat_id = int(chat_id_part)

            # Если chat_id положительный и больше 0, конвертируем в формат supergroup
            if chat_id > 0:
                chat_id = int(f"-100{chat_id}")

            return {
                'chat_id': chat_id,
                'message_id': message_id
            }
    except Exception as e:
        logger.error(f"Ошибка при парсинге ссылки {link}: {e}")

    return None


async def check_link_validity(current_chat_id: int, link: str) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Проверяет валидность ссылки и принадлежность к текущему чату

    Args:
        current_chat_id: ID текущего чата
        link: Ссылка на сообщение

    Returns:
        Tuple[bool, Optional[int], Optional[str]]:
        (валидна ли ссылка, message_id, сообщение об ошибке)
    """
    try:
        # Парсим ссылку
        link_data = parse_message_link(link)
        if not link_data:
            return False, None, "❌ Неверный формат ссылки"

        link_chat_id = link_data['chat_id']
        message_id = link_data['message_id']

        # Проверяем, что ссылка ведет в тот же чат
        if link_chat_id != current_chat_id:
            # Пытаемся получить информацию о чате из ссылки
            try:
                chat = await bot.get_chat(link_chat_id)
                chat_title = chat.title if hasattr(chat, 'title') else "неизвестный чат"
                return False, None, f"❌ Ссылка ведет в другой чат: {chat_title}"
            except:
                return False, None, "❌ Ссылка ведет в другой чат"

        # Проверяем, существует ли сообщение
        msg_info = await get_message_info(current_chat_id, message_id)
        if not msg_info:
            return False, None, "❌ Не удалось получить информацию о сообщении"

        if not msg_info.get('exists', False):
            return False, None, "❌ Сообщение не найдено. Возможно, оно уже удалено."

        return True, message_id, None

    except Exception as e:
        logger.error(f"Ошибка при проверке ссылки {link}: {e}")
        return False, None, f"❌ Ошибка при проверке ссылки: {str(e)}"


@sms_cleanup.message(Command("очистка", prefix="!/"))
@sms_cleanup.message(F.text.casefold().startswith("!очистка"))
async def cleanup_help_handler(message: Message):
    """Показывает справку по командам очистки"""

    help_text = (
        "🧹 *СИСТЕМА ОЧИСТКИ СООБЩЕНИЙ*\n\n"

        "🔸 *Быстрое удаление:*\n"
        "`-смс` в ответ на сообщение — удаляет его\n"
        "`-смс [ID]` — удаляет сообщение по ID\n"
        "`-смс [ссылка]` — удаляет по ссылке\n\n"

        "🌀 *Очистка ВНИЗ (ПУРГ):*\n"
        "`!пург` в ответ — удаляет это сообщение\n"
        "`!пург [кол-во]` в ответ — удаляет N сообщений\n"
        "`!пург [кол-во] [ID]` — удаляет N сообщений от ID\n"
        "`!пург [ID1]-[ID2]` — удаляет диапазон\n"
        "`!пург [кол-во] [ссылка]` — удаляет N сообщений от ссылки\n\n"

        "🌊 *Очистка ВВЕРХ (ЦУНАМИ):*\n"
        "`!цунами` в ответ — удаляет это сообщение\n"
        "`!цунами [кол-во]` в ответ — удаляет N сообщений\n"
        "`!цунами [кол-во] [ID]` — удаляет N сообщений до ID\n"
        "`!цунами [ID1]-[ID2]` — удаляет диапазон\n"
        "`!цунами [кол-во] [ссылка]` — удаляет N сообщений до ссылки\n\n"

        "⚡ *Очистка ВОКРУГ (ТОРНАДО):*\n"
        "`!торнадо` в ответ — удаляет это сообщение\n"
        "`!торнадо [радиус]` в ответ — удаляет радиус вокруг\n"
        "`!торнадо [радиус] [ID]` — удаляет радиус вокруг ID\n"
        "`!торнадо [ID1]-[ID2]` — удаляет диапазон\n"
        "`!торнадо [радиус] [ссылка]` — удаляет радиус вокруг ссылки\n\n"

        "📊 *Статистика:*\n"
        "`!статистика` — показывает возможности очистки\n\n"

        "⏰ *Ограничения:*\n"
        f"• Сообщения старше {MAX_MESSAGE_AGE_HOURS} часов удалить нельзя\n"
        f"• Максимум {MAX_MESSAGES_PER_PURGE} сообщений за раз\n"
        "• Требуются права администратора\n"
        "• Ссылки должны вести в тот же чат\n\n"

        "⚠️ *Внимание:* Удаленные сообщения невозможно восстановить!"
    )

    await message.reply(help_text, parse_mode='Markdown')


@sms_cleanup.message(F.text.casefold().startswith("-смс"))
async def delete_single_handler(message: Message):
    """Удаляет одно сообщение"""
    try:
        chat_id = message.chat.id
        command_msg_id = message.message_id

        # Проверяем права бота
        if not await check_bot_permissions(chat_id):
            # Отправляем сообщение об ошибке и удаляем его через 5 секунд
            error_msg = await message.reply("❌ У меня нет прав на удаление сообщений в этом чате")
            await asyncio.sleep(5)
            try:
                await message.delete()
                await error_msg.delete()
            except:
                pass
            return

        # Определяем целевое сообщение
        target_message_id = None

        # Если ответ на сообщение
        if message.reply_to_message:
            target_message_id = message.reply_to_message.message_id
        else:
            # Парсим аргументы
            args = message.text.split()
            if len(args) > 1:
                arg = args[1]

                # Проверяем ссылку
                if 't.me/c/' in arg:
                    # Проверяем валидность ссылки
                    valid, msg_id, error = await check_link_validity(chat_id, arg)
                    if not valid:
                        error_msg = await message.reply(error)
                        await asyncio.sleep(5)
                        try:
                            await message.delete()
                            await error_msg.delete()
                        except:
                            pass
                        return
                    target_message_id = msg_id
                else:
                    # Пробуем получить ID из аргумента
                    try:
                        target_message_id = int(arg)
                    except ValueError:
                        help_text = (
                            "❌ Неверный формат. Используйте:\n"
                            "• `-смс` в ответ на сообщение\n"
                            "• `-смс [ID_сообщения]`\n"
                            "• `-смс [ссылка_на_сообщение]`"
                        )
                        error_msg = await message.reply(help_text, parse_mode='Markdown')
                        await asyncio.sleep(5)
                        try:
                            await message.delete()
                            await error_msg.delete()
                        except:
                            pass
                        return
            else:
                help_text = (
                    "ℹ️ *Использование команды `-смс`:*\n\n"
                    "• Ответьте на сообщение с `-смс` чтобы удалить его\n"
                    "• Используйте `-смс [ID]` чтобы удалить по ID\n"
                    "• Используйте `-смс [ссылка]` чтобы удалить по ссылке\n\n"
                    "*Примеры:*\n"
                    "`-смс 12345`\n"
                    "`-смс https://t.me/c/1234567890/12345`"
                )
                help_msg = await message.reply(help_text, parse_mode='Markdown')
                await asyncio.sleep(5)
                try:
                    await message.delete()
                    await help_msg.delete()
                except:
                    pass
                return

        # Проверяем, существует ли сообщение и его возраст
        msg_info = await get_message_info(chat_id, target_message_id)

        if not msg_info:
            error_msg = await message.reply("❌ Не удалось получить информацию о сообщении")
            await asyncio.sleep(5)
            try:
                await message.delete()
                await error_msg.delete()
            except:
                pass
            return

        if not msg_info.get('exists', False):
            error_msg = await message.reply("❌ Сообщение не найдено. Возможно, оно уже удалено.")
            await asyncio.sleep(5)
            try:
                await message.delete()
                await error_msg.delete()
            except:
                pass
            return

        # Проверяем возраст сообщения
        if 'date' in msg_info:
            msg_date = msg_info['date']
            if not is_within_time_limit(msg_date):
                time_ago = format_time_ago(msg_date)

                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="⚡ Всё равно удалить",
                                callback_data=f"force_single_{chat_id}_{target_message_id}_{command_msg_id}"
                            ),
                            InlineKeyboardButton(
                                text="❌ Отмена",
                                callback_data=f"cancel_{command_msg_id}"
                            )
                        ]
                    ]
                )

                warning_msg = await message.reply(
                    f"⚠️ *Внимание!*\n\n"
                    f"Это сообщение отправлено *{time_ago}*.\n"
                    f"Сообщения старше {MAX_MESSAGE_AGE_HOURS} часов удалить *нельзя*.\n\n"
                    f"Вы уверены, что хотите продолжить?",
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )

                # Удаляем предупреждение через 30 секунд если не нажали
                await asyncio.sleep(30)
                try:
                    await warning_msg.delete()
                except:
                    pass
                return

        # Пытаемся удалить сообщение
        success = await delete_single_message(chat_id, target_message_id)

        # Удаляем команду
        try:
            await message.delete()
        except:
            pass

        if success:
            # Отправляем подтверждение и удаляем через 3 секунды
            confirm_msg_id = await send_status_message(
                chat_id,
                "✅ Сообщение успешно удалено!"
            )
            if confirm_msg_id:
                await asyncio.sleep(3)
                await delete_status_message(chat_id, confirm_msg_id)
        else:
            # Отправляем ошибку и удаляем через 5 секунд
            error_msg_id = await send_status_message(
                chat_id,
                "❌ Не удалось удалить сообщение"
            )
            if error_msg_id:
                await asyncio.sleep(5)
                await delete_status_message(chat_id, error_msg_id)

    except Exception as e:
        logger.error(f"Ошибка в delete_single_handler: {e}", exc_info=True)
        try:
            await message.reply("❌ Произошла ошибка при удалении сообщения")
        except:
            pass


@sms_cleanup.message(F.text.casefold().startswith("!пург"))
async def purge_down_handler(message: Message):
    """Удаляет сообщения ВНИЗ от указанного"""
    await purge_handler(message, direction="down", command_name="!пург")


@sms_cleanup.message(F.text.casefold().startswith("!цунами"))
async def purge_up_handler(message: Message):
    """Удаляет сообщения ВВЕРХ от указанного"""
    await purge_handler(message, direction="up", command_name="!цунами")


@sms_cleanup.message(F.text.casefold().startswith("!торнадо"))
async def purge_both_handler(message: Message):
    """Удаляет сообщения ВВЕРХ и ВНИЗ от указанного"""
    await purge_handler(message, direction="both", command_name="!торнадо")


async def purge_handler(message: Message, direction: str, command_name: str):
    """Обработчик массового удаления сообщений"""
    try:
        chat_id = message.chat.id

        # Проверяем права бота
        if not await check_bot_permissions(chat_id):
            error_msg = await message.reply("❌ У меня нет прав на удаление сообщений в этом чате")
            await asyncio.sleep(5)
            try:
                await message.delete()
                await error_msg.delete()
            except:
                pass
            return

        # Парсим команду
        args = message.text.split()

        # Определяем параметры
        target_message_id = None
        count = 1  # По умолчанию - 1 сообщение

        # Случай 1: Есть ответ на сообщение
        if message.reply_to_message:
            target_message_id = message.reply_to_message.message_id

            # Проверяем, есть ли аргумент с количеством (первый аргумент после команды)
            if len(args) > 1:
                try:
                    # Пытаемся получить количество из первого аргумента
                    count = int(args[1])
                    if count < 1:
                        count = 1
                    elif count > MAX_MESSAGES_PER_PURGE:
                        count = MAX_MESSAGES_PER_PURGE
                except ValueError:
                    # Если не число, проверяем диапазон
                    arg = args[1]
                    if '-' in arg:
                        try:
                            start_id, end_id = map(int, arg.split('-'))
                            return await delete_message_range(
                                message, start_id, end_id, command_name
                            )
                        except ValueError:
                            pass
                    # Если не число и не диапазон, проверяем ссылку
                    elif 't.me/c/' in arg:
                        # Проверяем валидность ссылки
                        valid, msg_id, error = await check_link_validity(chat_id, arg)
                        if not valid:
                            error_msg = await message.reply(error)
                            await asyncio.sleep(5)
                            try:
                                await message.delete()
                                await error_msg.delete()
                            except:
                                pass
                            return
                        target_message_id = msg_id
                        count = 1
                    else:
                        count = 1  # Удаляем только сообщение на которое ответили
        else:
            # Случай 2: Нет ответа на сообщение
            if len(args) > 1:
                first_arg = args[1]

                # Проверяем диапазон
                if '-' in first_arg:
                    try:
                        start_id, end_id = map(int, first_arg.split('-'))
                        return await delete_message_range(
                            message, start_id, end_id, command_name
                        )
                    except ValueError:
                        pass

                # Проверяем, является ли первый аргумент числом (количеством)
                try:
                    count = int(first_arg)
                    if count < 1:
                        count = 1
                    elif count > MAX_MESSAGES_PER_PURGE:
                        count = MAX_MESSAGES_PER_PURGE

                    # Проверяем, есть ли второй аргумент (ID или ссылка)
                    if len(args) > 2:
                        second_arg = args[2]

                        # Проверяем ссылку
                        if 't.me/c/' in second_arg:
                            valid, msg_id, error = await check_link_validity(chat_id, second_arg)
                            if not valid:
                                error_msg = await message.reply(error)
                                await asyncio.sleep(5)
                                try:
                                    await message.delete()
                                    await error_msg.delete()
                                except:
                                    pass
                                return
                            target_message_id = msg_id
                        else:
                            # Пробуем получить ID
                            try:
                                target_message_id = int(second_arg)
                            except ValueError:
                                await show_purge_help(message, command_name, direction)
                                return
                    else:
                        # Нет второго аргумента - нужен ID или ссылка
                        await show_purge_help(message, command_name, direction)
                        return

                except ValueError:
                    # Первый аргумент не число - проверяем ссылку
                    if 't.me/c/' in first_arg:
                        valid, msg_id, error = await check_link_validity(chat_id, first_arg)
                        if not valid:
                            error_msg = await message.reply(error)
                            await asyncio.sleep(5)
                            try:
                                await message.delete()
                                await error_msg.delete()
                            except:
                                pass
                            return
                        target_message_id = msg_id
                        count = 1
                    else:
                        # Пробуем как ID сообщения
                        try:
                            target_message_id = int(first_arg)
                            count = 1  # Только это сообщение
                        except ValueError:
                            await show_purge_help(message, command_name, direction)
                            return
            else:
                # Нет аргументов - показываем справку
                await show_purge_help(message, command_name, direction)
                return

        # Если target_message_id не определён (чего быть не должно)
        if target_message_id is None:
            await show_purge_help(message, command_name, direction)
            return

        # Проверяем, существует ли сообщение и его возраст
        msg_info = await get_message_info(chat_id, target_message_id)

        if not msg_info:
            error_msg = await message.reply("❌ Не удалось получить информацию о сообщении")
            await asyncio.sleep(5)
            try:
                await message.delete()
                await error_msg.delete()
            except:
                return

        if not msg_info.get('exists', False):
            error_msg = await message.reply("❌ Сообщение не найдено. Возможно, оно уже удалено.")
            await asyncio.sleep(5)
            try:
                await message.delete()
                await error_msg.delete()
            except:
                pass
            return

        # Проверяем возраст сообщения
        if 'date' in msg_info:
            msg_date = msg_info['date']
            if not is_within_time_limit(msg_date):
                time_ago = format_time_ago(msg_date)
                direction_text = get_direction_text(direction)

                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="⚡ Всё равно удалить",
                                callback_data=f"force_purge_{chat_id}_{target_message_id}_{direction}_{count}_{message.message_id}"
                            ),
                            InlineKeyboardButton(
                                text="❌ Отмена",
                                callback_data=f"cancel_{message.message_id}"
                            )
                        ]
                    ]
                )

                total_messages = count
                if direction == "both":
                    total_messages = count * 2 + 1  # Радиус в обе стороны + центральное

                warning_msg = await message.reply(
                    f"⚠️ *Внимание!*\n\n"
                    f"Целевое сообщение отправлено *{time_ago}*.\n"
                    f"Сообщения старше {MAX_MESSAGE_AGE_HOURS} часов удалить *нельзя*.\n\n"
                    f"Вы уверены, что хотите удалить {total_messages} сообщений {direction_text}?",
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )

                # Удаляем предупреждение через 30 секунд если не нажали
                await asyncio.sleep(30)
                try:
                    await warning_msg.delete()
                except:
                    pass
                return

        # Удаляем команду
        try:
            await message.delete()
        except:
            pass

        # Отправляем начальный статус
        direction_text = get_direction_text(direction)
        status_msg_id = await send_status_message(
            chat_id,
            f"🌀 *Начинаю удаление {direction_text}...*\n"
            f"📊 Количество: {count} сообщений\n"
            f"📍 От сообщения: {target_message_id}"
        )

        # Выполняем удаление в зависимости от направления
        if direction == "down":
            failed_ids, deleted_count = await purge_messages_down(
                chat_id=chat_id,
                start_message_id=target_message_id,  # Начиная с этого ID
                count=count
            )
        elif direction == "up":
            failed_ids, deleted_count = await purge_messages_up(
                chat_id=chat_id,
                start_message_id=target_message_id,  # Заканчивая этим ID
                count=count
            )
        else:  # both
            # Для торнадо count - это РАДИУС в каждую сторону
            radius = count
            failed_ids, deleted_count = await purge_messages_both(
                chat_id=chat_id,
                center_message_id=target_message_id,
                radius=radius
            )

        # Показываем результат
        await show_purge_result(
            chat_id=chat_id,
            status_msg_id=status_msg_id,
            direction=direction,
            failed_ids=failed_ids,
            deleted_count=deleted_count,
            requested_count=count
        )

    except Exception as e:
        logger.error(f"Ошибка в purge_handler: {e}", exc_info=True)
        try:
            await message.reply("❌ Произошла ошибка при удалении сообщений")
        except:
            pass


async def delete_message_range(
        message: Message,
        start_id: int,
        end_id: int,
        command_name: str
):
    """Удаляет диапазон сообщений"""
    try:
        chat_id = message.chat.id

        if not await check_bot_permissions(chat_id):
            error_msg = await message.reply("❌ У меня нет прав на удаление сообщений в этом чате")
            await asyncio.sleep(5)
            try:
                await message.delete()
                await error_msg.delete()
            except:
                pass
            return

        # Вычисляем точное количество сообщений в диапазоне
        message_count = end_id - start_id + 1

        # Проверяем ограничение
        if message_count > MAX_MESSAGES_PER_PURGE:
            error_msg = await message.reply(
                f"❌ Слишком много сообщений ({message_count}). "
                f"Максимум: {MAX_MESSAGES_PER_PURGE}"
            )
            await asyncio.sleep(5)
            try:
                await message.delete()
                await error_msg.delete()
            except:
                pass
            return

        # Проверяем первое сообщение
        first_msg_info = await get_message_info(chat_id, start_id)
        if first_msg_info and 'date' in first_msg_info:
            if not is_within_time_limit(first_msg_info['date']):
                time_ago = format_time_ago(first_msg_info['date'])

                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="⚡ Всё равно удалить",
                                callback_data=f"force_range_{chat_id}_{start_id}_{end_id}_{message.message_id}"
                            ),
                            InlineKeyboardButton(
                                text="❌ Отмена",
                                callback_data=f"cancel_{message.message_id}"
                            )
                        ]
                    ]
                )

                warning_msg = await message.reply(
                    f"⚠️ *Внимание!*\n\n"
                    f"Первое сообщение отправлено *{time_ago}*.\n"
                    f"Сообщения старше {MAX_MESSAGE_AGE_HOURS} часов удалить *нельзя*.\n\n"
                    f"Вы уверены, что хотите удалить {message_count} сообщений?",
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )

                # Удаляем предупреждение через 30 секунд если не нажали
                await asyncio.sleep(30)
                try:
                    await warning_msg.delete()
                except:
                    pass
                return

        # Удаляем команду
        try:
            await message.delete()
        except:
            pass

        # Отправляем начальный статус
        status_msg_id = await send_status_message(
            chat_id,
            f"🌀 *Удаляю диапазон сообщений...*\n"
            f"📊 Точное количество: {message_count} сообщений"
        )

        # Удаляем точное количество сообщений в диапазоне
        failed_ids = []
        deleted_count = 0

        for msg_id in range(start_id, end_id + 1):
            if await delete_single_message(chat_id, msg_id):
                deleted_count += 1
            else:
                failed_ids.append(msg_id)

            await asyncio.sleep(DELETE_DELAY)

        # Показываем результат
        if failed_ids:
            failed_text = format_failed_ids(failed_ids)
            result_text = (
                f"⚠️ *Удаление завершено с ошибками*\n\n"
                f"✅ Удалено: *{deleted_count}* из *{message_count}* сообщений\n"
                f"❌ Не удалось: *{len(failed_ids)}* сообщений\n\n"
                f"*ID с ошибками:*\n`{failed_text}`"
            )
        else:
            result_text = (
                f"✅ *Диапазон успешно удален!*\n\n"
                f"🗑️ Удалено: *{deleted_count}* сообщений\n"
                f"📋 Диапазон: *{start_id}* - *{end_id}*"
            )

        await show_result_and_cleanup(
            chat_id=chat_id,
            status_msg_id=status_msg_id,
            result_text=result_text
        )

    except Exception as e:
        logger.error(f"Ошибка в delete_message_range: {e}", exc_info=True)
        try:
            await message.reply("❌ Произошла ошибка при удалении диапазона")
        except:
            pass


async def show_purge_result(
        chat_id: int,
        status_msg_id: Optional[int],
        direction: str,
        failed_ids: List[int],
        deleted_count: int,
        requested_count: int = None  # Запрошенное количество
):
    """Показывает результат массового удаления"""
    direction_text = get_direction_text(direction)

    if failed_ids:
        failed_text = format_failed_ids(failed_ids)
        if requested_count:
            result_text = (
                f"⚠️ *Удаление {direction_text} завершено с ошибками*\n\n"
                f"✅ Удалено: *{deleted_count}* из *{requested_count}* сообщений\n"
                f"❌ Не удалось: *{len(failed_ids)}* сообщений\n\n"
                f"*ID сообщений с ошибками:*\n`{failed_text}`"
            )
        else:
            result_text = (
                f"⚠️ *Удаление {direction_text} завершено с ошибками*\n\n"
                f"✅ Удалено: *{deleted_count}* сообщений\n"
                f"❌ Не удалось: *{len(failed_ids)}* сообщений\n\n"
                f"*ID сообщений с ошибками:*\n`{failed_text}`"
            )
    else:
        if requested_count:
            result_text = (
                f"✅ *Сообщения успешно удалены {direction_text}!*\n\n"
                f"🗑️ Удалено: *{deleted_count}* из *{requested_count}* запрошенных сообщений"
            )
        else:
            result_text = (
                f"✅ *Сообщения успешно удалены {direction_text}!*\n\n"
                f"🗑️ Удалено: *{deleted_count}* сообщений"
            )

    await show_result_and_cleanup(
        chat_id=chat_id,
        status_msg_id=status_msg_id,
        result_text=result_text
    )


def get_direction_text(direction: str) -> str:
    """Возвращает текстовое описание направления"""
    if direction == "down":
        return "ВНИЗ"
    elif direction == "up":
        return "ВВЕРХ"
    elif direction == "both":
        return "ВОКРУГ"
    else:
        return ""


def format_failed_ids(failed_ids: List[int]) -> str:
    """Форматирует список ID для отображения"""
    if not failed_ids:
        return "нет"

    # Показываем только первые 10 ID
    if len(failed_ids) <= 10:
        return ", ".join(map(str, failed_ids))
    else:
        first_ten = failed_ids[:10]
        return f"{', '.join(map(str, first_ten))} и ещё {len(failed_ids) - 10}"


async def show_purge_help(message: Message, command_name: str, direction: str):
    """Показывает справку по команде очистки"""
    direction_text = get_direction_text(direction)
    examples = {
        "down": (
            "• `!пург` в ответ на сообщение — удаляет только его\n"
            "• `!пург 10` в ответ — удаляет 10 сообщений от него\n"
            "• `!пург 10 12345` — удаляет 10 сообщений от ID 12345\n"
            "• `!пург 10 https://t.me/c/...` — удаляет 10 сообщений от ссылки\n"
            "• `!пург 100-200` — удаляет диапазон сообщений"
        ),
        "up": (
            "• `!цунами` в ответ на сообщение — удаляет только его\n"
            "• `!цунами 10` в ответ — удаляет 10 сообщений до него\n"
            "• `!цунами 10 12345` — удаляет 10 сообщений до ID 12345\n"
            "• `!цунами 10 https://t.me/c/...` — удаляет 10 сообщений до ссылки\n"
            "• `!цунами 100-200` — удаляет диапазон сообщений"
        ),
        "both": (
            "• `!торнадо` в ответ на сообщение — удаляет только его\n"
            "• `!торнадо 5` в ответ — удаляет 5 сообщений вокруг (всего 11)\n"
            "• `!торнадо 5 12345` — удаляет 5 сообщений вокруг ID 12345\n"
            "• `!торнадо 5 https://t.me/c/...` — удаляет 5 сообщений вокруг ссылки\n"
            "• `!торнадо 100-200` — удаляет диапазон сообщений"
        )
    }

    help_text = (
        f"🌀 *Использование команды `{command_name}`:*\n\n"
        f"Эта команда удаляет сообщения *{direction_text}* от указанного.\n\n"
        f"*Порядок аргументов:*\n"
        f"1. Количество сообщений для удаления (от 1 до {MAX_MESSAGES_PER_PURGE})\n"
        f"2. ID сообщения или ссылка (если не отвечаете на сообщение)\n\n"
        f"*Примеры:*\n{examples.get(direction, '')}\n\n"
        f"*Примечания:*\n"
        f"• Без аргументов в ответ на сообщение удаляет только его\n"
        f"• Ссылки должны вести в тот же чат\n"
        f"• Можно указать диапазон через дефис\n"
        f"• Сообщения старше {MAX_MESSAGE_AGE_HOURS} часов удалить нельзя"
    )

    help_msg = await message.reply(help_text, parse_mode='Markdown')

    # Удаляем справку и команду через 10 секунд
    await asyncio.sleep(10)
    try:
        await message.delete()
        await help_msg.delete()
    except:
        pass


@sms_cleanup.message(F.text.casefold().startswith("!смс помощь"))
async def cleanup_stats_handler(message: Message):
    """Показывает статистику очистки"""

    stats_text = (
        "🔸 *Одно сообщение:*\n"
        "`-смс` — мгновенное удаление\n"
        "`!пург`, `!цунами`, `!торнадо` — без аргументов в ответ\n"
        f"• Возраст до {MAX_MESSAGE_AGE_HOURS} часов\n\n"

        "🌀 *Массовая очистка:*\n"
        "`!пург [N]` в ответ — N сообщений ВНИЗ\n"
        "`!цунами [N]` в ответ — N сообщений ВВЕРХ\n"
        "`!торнадо [R]` в ответ — R сообщений ВОКРУГ\n"
        f"• До {MAX_MESSAGES_PER_PURGE} сообщений за раз\n"

        "📋 *Диапазоны:*\n"
        "`[ID1]-[ID2]` — удаляет все сообщения в диапазоне\n"
        "• Начальный ID должен быть меньше конечного\n"
        "• Поддерживается во всех командах\n\n"

    )

    stats_msg = await message.reply(stats_text, parse_mode='Markdown')

    # Удаляем команду и статистику через 15 секунд
    await asyncio.sleep(15)
    try:
        await message.delete()
        await stats_msg.delete()
    except:
        pass


# Обработчики inline-кнопок
@sms_cleanup.callback_query(F.data.startswith("force_single_"))
async def handle_force_single(callback: CallbackQuery):
    """Обработчик принудительного удаления одного сообщения"""
    try:
        parts = callback.data.split("_")
        chat_id = int(parts[2])
        target_message_id = int(parts[3])
        command_message_id = int(parts[4]) if len(parts) > 4 else None

        # Удаляем сообщение с подтверждением
        try:
            await callback.message.delete()
        except:
            pass

        # Удаляем команду если знаем её ID
        if command_message_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=command_message_id)
            except:
                pass

        # Удаляем целевое сообщение
        success = await delete_single_message(chat_id, target_message_id)

        if success:
            # Отправляем подтверждение
            confirm_msg_id = await send_status_message(
                chat_id,
                "✅ Сообщение удалено (принудительно)"
            )
            await callback.answer("✅ Сообщение удалено!", show_alert=False)

            if confirm_msg_id:
                await asyncio.sleep(3)
                await delete_status_message(chat_id, confirm_msg_id)
        else:
            error_msg_id = await send_status_message(
                chat_id,
                "❌ Не удалось удалить сообщение"
            )
            await callback.answer("❌ Не удалось удалить сообщение", show_alert=False)

            if error_msg_id:
                await asyncio.sleep(5)
                await delete_status_message(chat_id, error_msg_id)

    except Exception as e:
        logger.error(f"Ошибка в handle_force_single: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@sms_cleanup.callback_query(F.data.startswith("force_purge_"))
async def handle_force_purge(callback: CallbackQuery):
    """Обработчик принудительного массового удаления"""
    try:
        parts = callback.data.split("_")
        chat_id = int(parts[2])
        target_message_id = int(parts[3])
        direction = parts[4]
        count = int(parts[5]) if len(parts) > 5 else 1  # ТОЧНОЕ количество
        command_message_id = int(parts[6]) if len(parts) > 6 else None

        # Удаляем сообщение с подтверждением
        try:
            await callback.message.delete()
        except:
            pass

        # Удаляем команду если знаем её ID
        if command_message_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=command_message_id)
            except:
                pass

        # Отправляем статус
        direction_text = get_direction_text(direction)
        status_msg_id = await send_status_message(
            chat_id,
            f"🌀 *Принудительное удаление {direction_text}...*\n"
            f"📊 Количество: {count} сообщений"
        )

        # Выполняем удаление без проверки времени
        if direction == "down":
            failed_ids, deleted_count = await purge_messages_down(
                chat_id=chat_id,
                start_message_id=target_message_id,
                count=count
            )
        elif direction == "up":
            failed_ids, deleted_count = await purge_messages_up(
                chat_id=chat_id,
                start_message_id=target_message_id,
                count=count
            )
        else:  # both
            failed_ids, deleted_count = await purge_messages_both(
                chat_id=chat_id,
                center_message_id=target_message_id,
                radius=count
            )

        # Показываем результат
        if failed_ids:
            failed_text = format_failed_ids(failed_ids)
            result_text = (
                f"⚠️ *Принудительное удаление {direction_text} завершено*\n\n"
                f"✅ Удалено: *{deleted_count}* из *{count}* сообщений\n"
                f"❌ Не удалось: *{len(failed_ids)}* сообщений\n\n"
                f"*ID с ошибками:*\n`{failed_text}`"
            )
        else:
            result_text = (
                f"✅ *Принудительное удаление {direction_text} успешно!*\n\n"
                f"🗑️ Удалено: *{deleted_count}* из *{count}* сообщений"
            )

        await show_result_and_cleanup(
            chat_id=chat_id,
            status_msg_id=status_msg_id,
            result_text=result_text
        )

        await callback.answer("✅ Удаление выполнено", show_alert=False)

    except Exception as e:
        logger.error(f"Ошибка в handle_force_purge: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@sms_cleanup.callback_query(F.data.startswith("force_range_"))
async def handle_force_range(callback: CallbackQuery):
    """Обработчик принудительного удаления диапазона"""
    try:
        parts = callback.data.split("_")
        chat_id = int(parts[2])
        start_id = int(parts[3])
        end_id = int(parts[4])
        command_message_id = int(parts[5]) if len(parts) > 5 else None

        # Удаляем сообщение с подтверждением
        try:
            await callback.message.delete()
        except:
            pass

        # Удаляем команду если знаем её ID
        if command_message_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=command_message_id)
            except:
                pass

        # Вычисляем точное количество
        message_count = end_id - start_id + 1

        # Отправляем статус
        status_msg_id = await send_status_message(
            chat_id,
            f"🌀 *Принудительное удаление диапазона...*\n"
            f"📊 Точное количество: {message_count} сообщений"
        )

        # Удаляем точное количество сообщений в диапазоне
        failed_ids = []
        deleted_count = 0

        for msg_id in range(start_id, end_id + 1):
            if await delete_single_message(chat_id, msg_id):
                deleted_count += 1
            else:
                failed_ids.append(msg_id)

            await asyncio.sleep(DELETE_DELAY)

        # Показываем результат
        if failed_ids:
            failed_text = format_failed_ids(failed_ids)
            result_text = (
                f"⚠️ *Принудительное удаление диапазона завершено*\n\n"
                f"✅ Удалено: *{deleted_count}* из *{message_count}* сообщений\n"
                f"❌ Не удалось: *{len(failed_ids)}* сообщений\n\n"
                f"Диапазон: *{start_id}* - *{end_id}*\n"
                f"*ID с ошибками:*\n`{failed_text}`"
            )
        else:
            result_text = (
                f"✅ *Диапазон успешно удален (принудительно)!*\n\n"
                f"🗑️ Удалено: *{deleted_count}* сообщений\n"
                f"📋 Диапазон: *{start_id}* - *{end_id}*"
            )

        await show_result_and_cleanup(
            chat_id=chat_id,
            status_msg_id=status_msg_id,
            result_text=result_text
        )

        await callback.answer("✅ Диапазон удален", show_alert=False)

    except Exception as e:
        logger.error(f"Ошибка в handle_force_range: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)


@sms_cleanup.callback_query(F.data.startswith("cancel_"))
async def handle_cancel(callback: CallbackQuery):
    """Обработчик отмены операции"""
    try:
        await callback.message.delete()
        await callback.answer("❌ Операция отменена", show_alert=False)
    except Exception as e:
        logger.error(f"Ошибка в handle_cancel: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


# Автоматическое удаление сообщений с командами
@sms_cleanup.message(
    F.text & (
            F.text.casefold().startswith("-смс") |
            F.text.casefold().startswith("!пург") |
            F.text.casefold().startswith("!цунами") |
            F.text.casefold().startswith("!торнадо") |
            F.text.casefold().startswith("!очистка") |
            F.text.casefold().startswith("!статистика")
    )
)
async def auto_delete_command_messages(message: Message):
    """Автоматически удаляет команды через некоторое время"""
    await asyncio.sleep(30)  # Ждем 30 секунд

    try:
        await message.delete()
    except Exception as e:
        logger.debug(f"Не удалось автоудалить команду {message.message_id}: {e}")