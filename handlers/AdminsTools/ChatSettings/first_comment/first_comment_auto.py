import logging
from typing import Dict

from aiogram import Router, F
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.AdminsTools.ChatSettings.first_comment.first_commentDB import get_first_comment

first_comment_auto_router = Router()
logger = logging.getLogger(__name__)


@first_comment_auto_router.message(F.sender_chat)
async def handle_channel_message_in_group(message: Message):
    """
    Обработчик сообщений от каналов в группе/чате.
    Срабатывает только на сообщения, отправленные от имени канала (sender_chat).
    """
    try:
        #print(f'ПОЙМАЛ сообщение в чате {message.chat.id}')
        #print(f'Отправитель (sender_chat): {message.sender_chat}')
        #print(f'Текст: {message.text}')

        # Проверяем, что это сообщение от канала (sender_chat не None)
        if not message.sender_chat:
            return

        # Получаем информацию о текущем чате (группе)
        chat_info = await message.bot.get_chat(message.chat.id)

        # Проверяем, есть ли у этого чата привязанный канал
        if not hasattr(chat_info, 'linked_chat_id') or not chat_info.linked_chat_id:
            #print(f"У чата {message.chat.id} нет привязанного канала")
            return

        # Получаем ID привязанного канала
        linked_channel_id = chat_info.linked_chat_id

        # Проверяем, что сообщение пришло именно от привязанного канала
        if message.sender_chat.id != linked_channel_id:
            #print(f"Сообщение не от привязанного канала. "
             #     f"Отправитель: {message.sender_chat.id}, "
              #    f"ожидался: {linked_channel_id}")
            return

        #print(f"✓ Сообщение от привязанного канала {linked_channel_id} в чате {message.chat.id}")

        # Проверяем, есть ли первый комментарий для этого канала
        first_comment = await get_first_comment(linked_channel_id)
        if not first_comment:
            #print(f"Нет первого комментария для канала {linked_channel_id}")
            return

        #print(f"Найден первый комментарий для канала {linked_channel_id}")

        # Отправляем первый комментарий под этим сообщением в ЧАТЕ
        # (не в канале, а прямо в группе под сообщением канала)
        await send_first_comment_in_group(
            message.bot,
            message.chat.id,  # ID группы/чата
            message.message_id,  # ID сообщения канала в группе
            first_comment
        )

        #logger.info(
        #    f"Первый комментарий отправлен в группе {message.chat.id} под сообщением канала {linked_channel_id}")

    except Exception as e:
        logger.error(f"Ошибка в handle_channel_message_in_group: {e}", exc_info=True)


async def send_first_comment_in_group(bot, group_id: int, message_id: int, first_comment_data: Dict):
    """Отправка первого комментария в группе под сообщением канала"""
    try:
        comment_text = first_comment_data.get('comment_text', '')
        buttons = first_comment_data.get('buttons', [])

        if not comment_text:
            #logger.warning(f"Пустой текст комментария")
            return

        # Создаем клавиатуру с кнопками
        keyboard = None
        if buttons:
            builder = InlineKeyboardBuilder()
            for btn in buttons:
                if 'text' in btn and 'url' in btn:
                    builder.button(text=btn['text'], url=btn['url'])

            # Оптимальное расположение кнопок
            if len(buttons) <= 2:
                builder.adjust(1)
            elif len(buttons) <= 4:
                builder.adjust(2)
            else:
                builder.adjust(2, 2)

            keyboard = builder.as_markup()

        # Отправляем комментарий в ГРУППЕ как ответ на сообщение канала
        await bot.send_message(
            chat_id=group_id,  # ID группы/чата
            text=comment_text,
            reply_to_message_id=message_id,  # ID сообщения канала в группе
            reply_markup=keyboard,
            parse_mode='HTML',
            disable_web_page_preview=True
        )

        #logger.info(f"Комментарий отправлен в группе {group_id} под сообщением {message_id}")

    except Exception as e:
        logger.error(f"Ошибка при отправке комментария в группе: {e}", exc_info=True)


# ДОПОЛНИТЕЛЬНЫЙ обработчик для ручной активации через команду
#@first_comment_auto_router.message(F.text == "!отправить_комментарий")
async def manual_send_comment(message: Message):
    """Ручная отправка первого комментария"""
    try:
        # Проверяем, что сообщение является ответом
        if not message.reply_to_message:
            await message.reply("❌ Ответьте на сообщение канала командой !отправить_комментарий")
            return

        # Проверяем, что ответ на сообщение от канала
        if not message.reply_to_message.sender_chat:
            await message.reply("❌ Это не сообщение от канала")
            return

        # Получаем информацию о чате
        chat_info = await message.bot.get_chat(message.chat.id)

        if not hasattr(chat_info, 'linked_chat_id') or not chat_info.linked_chat_id:
            await message.reply("❌ У этого чата нет привязанного канала")
            return

        linked_channel_id = chat_info.linked_chat_id

        # Проверяем, что ответ на сообщение от привязанного канала
        if message.reply_to_message.sender_chat.id != linked_channel_id:
            await message.reply("❌ Это сообщение не от привязанного канала")
            return

        # Получаем первый комментарий
        first_comment = await get_first_comment(linked_channel_id)
        if not first_comment:
            await message.reply("❌ Для этого канала не настроен первый комментарий")
            return

        # Отправляем комментарий
        await send_first_comment_in_group(
            message.bot,
            message.chat.id,
            message.reply_to_message.message_id,
            first_comment
        )

        await message.reply("✅ Первый комментарий отправлен")

    except Exception as e:
        logger.error(f"Ошибка в manual_send_comment: {e}", exc_info=True)
        await message.reply(f"❌ Ошибка: {str(e)}")