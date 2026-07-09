import logging
from typing import Dict, List

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.AdminsTools.ChatSettings.first_comment.first_commentDB import get_first_comment

first_comment_auto_router = Router()
logger = logging.getLogger(__name__)


# Хендлер для автоматически пересланных сообщений из привязанного канала
@first_comment_auto_router.message(F.is_automatic_forward == True)
async def handle_automatic_forward(message: Message):
    """Обработчик автоматически пересланных сообщений из привязанного канала"""
    try:
        group_id = message.chat.id

        logger.info(f"📨 Получено автоматически пересланное сообщение в группе {group_id}")

        # Получаем информацию о группе
        chat_info = await message.bot.get_chat(group_id)

        # Проверяем, есть ли у группы привязанный канал
        if not hasattr(chat_info, 'linked_chat_id') or not chat_info.linked_chat_id:
            logger.info(f"ℹ️ У группы {group_id} нет привязанного канала")
            return

        logger.info(f"  - Привязанный канал группы: {chat_info.linked_chat_id}")

        # Получаем первый комментарий
        first_comment = await get_first_comment(group_id)

        if not first_comment:
            logger.info(f"📭 Нет первого комментария для группы {group_id}")
            return

        # Отправляем комментарий с кнопками
        await send_first_comment_in_group(
            message.bot,
            group_id,
            message.message_id,
            first_comment
        )

    except Exception as e:
        logger.error(f"❌ Ошибка в handle_automatic_forward: {e}", exc_info=True)


# Альтернативный хендлер для пересланных сообщений (на всякий случай)
@first_comment_auto_router.message(F.forward_from_chat)
async def handle_forwarded_from_channel(message: Message):
    """Обработчик пересланных сообщений из каналов"""
    try:
        # Проверяем, что это автоматическая пересылка (чтобы не дублировать)
        if getattr(message, 'is_automatic_forward', False):
            return

        forwarded_chat = message.forward_from_chat

        if forwarded_chat.type != "channel":
            return

        group_id = message.chat.id

        # Получаем информацию о группе
        chat_info = await message.bot.get_chat(group_id)

        if not hasattr(chat_info, 'linked_chat_id') or not chat_info.linked_chat_id:
            return

        # Проверяем, что переслано из привязанного канала
        if forwarded_chat.id != chat_info.linked_chat_id:
            return

        # Получаем первый комментарий
        first_comment = await get_first_comment(group_id)

        if first_comment:
            await send_first_comment_in_group(
                message.bot,
                group_id,
                message.message_id,
                first_comment
            )

    except Exception as e:
        logger.error(f"❌ Ошибка в handle_forwarded_from_channel: {e}", exc_info=True)


async def send_first_comment_in_group(bot, group_id: int, message_id: int, first_comment_data: Dict):
    """Отправка первого комментария в группе под сообщением канала"""
    try:
        comment_text = first_comment_data.get('comment_text', '')
        buttons = first_comment_data.get('buttons', [])

        if not comment_text:
            logger.warning(f"⚠️ Пустой текст комментария для группы {group_id}")
            return

        logger.info(f"📝 Отправка комментария в группу {group_id}")
        logger.info(f"  - Текст: {comment_text[:100]}...")
        logger.info(f"  - Кнопок: {len(buttons)}")

        # Создаем клавиатуру с кнопками
        keyboard = None
        if buttons:
            builder = InlineKeyboardBuilder()

            for btn in buttons:
                if 'text' in btn and 'url' in btn:
                    builder.button(
                        text=btn['text'],
                        url=btn['url']
                    )
                    logger.debug(f"  - Добавлена кнопка: {btn['text']} -> {btn['url']}")

            # Располагаем кнопки в один ряд
            builder.adjust(1)

            keyboard = builder.as_markup()
            logger.info(f"✅ Создана клавиатура с {len(buttons)} кнопками")

        # Отправляем комментарий
        sent_message = await bot.send_message(
            chat_id=group_id,
            text=comment_text,
            reply_to_message_id=message_id,
            reply_markup=keyboard,
            parse_mode='HTML',
            disable_web_page_preview=True
        )

        logger.info(f"✅ Комментарий отправлен: message_id={sent_message.message_id}")

    except Exception as e:
        logger.error(f"❌ Ошибка при отправке комментария в группе: {e}", exc_info=True)


# Ручная отправка комментария (для тестирования)
#@first_comment_auto_router.message(F.text == "!отправить_комментарий")
async def manual_send_comment(message: Message):
    """Ручная отправка первого комментария"""
    try:
        # Проверяем, что сообщение является ответом
        if not message.reply_to_message:
            await message.reply("❌ Ответьте на сообщение канала командой !отправить_комментарий")
            return

        group_id = message.chat.id

        logger.info(f"🔧 Ручная отправка: группа {group_id}")

        # Получаем первый комментарий
        first_comment = await get_first_comment(group_id)

        if not first_comment:
            await message.reply(f"❌ Для группы {group_id} не настроен первый комментарий")
            return

        # Отправляем комментарий
        await send_first_comment_in_group(
            message.bot,
            group_id,
            message.reply_to_message.message_id,
            first_comment
        )

        await message.reply("✅ Первый комментарий отправлен")

    except Exception as e:
        logger.error(f"❌ Ошибка в manual_send_comment: {e}", exc_info=True)
        await message.reply(f"❌ Ошибка: {str(e)}")


# Отладочный хендлер для проверки структуры кнопок
#@first_comment_auto_router.message(F.text == "!проверить_кнопки")
async def debug_buttons(message: Message):
    """Проверка структуры кнопок в первом комментарии"""
    try:
        group_id = message.chat.id

        first_comment = await get_first_comment(group_id)

        if not first_comment:
            await message.reply("❌ Первый комментарий не найден")
            return

        buttons = first_comment.get('buttons', [])

        if not buttons:
            await message.reply("📭 Нет кнопок в первом комментарии")
            return

        # Показываем информацию о кнопках
        info = f"🔘 <b>Найдено кнопок: {len(buttons)}</b>\n\n"

        for i, btn in enumerate(buttons, 1):
            info += f"{i}. <b>Текст:</b> {btn.get('text', 'Нет текста')}\n"
            info += f"   <b>URL:</b> <code>{btn.get('url', 'Нет URL')}</code>\n\n"

        await message.reply(info, parse_mode='HTML')

    except Exception as e:
        logger.error(f"❌ Ошибка в debug_buttons: {e}", exc_info=True)
        await message.reply(f"❌ Ошибка: {str(e)}")