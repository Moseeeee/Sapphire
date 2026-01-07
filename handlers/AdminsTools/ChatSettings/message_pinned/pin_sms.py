import logging
from datetime import datetime
from typing import Tuple, List

import pytz
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import asyncio

from handlers.AdminsTools.ChatSettings.message_pinned.pin_smsDB import clear_chat_pins, add_pinned_message, \
    remove_pinned_message, is_message_pinned
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.parse_time_auto import parse_time_string, format_duration
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text

pin_sms = Router()

MOSCOW_TZ = pytz.timezone('Europe/Moscow')
logger = logging.getLogger(__name__)


@pin_sms.message(F.text & F.text.casefold().startswith("+пин"))
async def pin_message_handler(message: Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 53):
        return

    try:
        # Проверяем, есть ли сообщение для ответа или указан ID
        command_parts = message.text.split()

        # Если указан ID сообщения (например, +пин 12345 или +пин громко 12345)
        message_id = None
        time_str = None

        # Определяем тип закрепления (тихий или громкий)
        is_loud = False
        loud_index = -1

        # Ищем слово "громко" в команде
        for i, part in enumerate(command_parts[1:], 1):
            if part.lower() == "громко":
                is_loud = True
                loud_index = i
                break

        # Парсим аргументы после команды
        args_start = 1  # Начинаем с индекса 1 (после +пин)
        if is_loud:
            args_start = loud_index + 1  # Пропускаем слово "громко"

        # Остальные аргументы
        remaining_args = command_parts[args_start:] if args_start < len(command_parts) else []

        if not message.reply_to_message:
            # Проверяем, указан ли ID сообщения
            if remaining_args:
                try:
                    # Пробуем получить ID из первого аргумента
                    message_id = int(remaining_args[0])

                    # Остальное - возможное время
                    time_parts = remaining_args[1:]
                    time_str = " ".join(time_parts) if time_parts else None
                except ValueError:
                    # Если первый аргумент не число - это время
                    time_str = " ".join(remaining_args)
                    await message.reply("❌ Для закрепления по ID укажите ID сообщения\n"
                                        "Пример: +пин 12345 5 минут")
                    return
            else:
                await message.reply("❌ Ответьте на сообщение или укажите ID сообщения для закрепления")
                return
        else:
            # Если есть ответ на сообщение, берем его ID
            message_id = message.reply_to_message.message_id

            # Проверяем остальные аргументы для времени
            if remaining_args:
                time_str = " ".join(remaining_args)
            elif is_loud:
                # Если только "громко" без времени
                time_str = None

        # Определяем параметр уведомления
        disable_notification: bool = not is_loud

        # Закрепляем сообщение
        chat_id = message.chat.id

        try:
            # Пытаемся закрепить сообщение
            await bot.pin_chat_message(
                chat_id=chat_id,
                message_id=message_id,
                disable_notification=disable_notification
            )
        except Exception as e:
            if "message to pin not found" in str(e).lower():
                await message.reply("❌ Сообщение с таким ID не найдено в этом чате")
                return
            elif "not enough rights" in str(e).lower():
                await message.reply("❌ У бота недостаточно прав для закрепления сообщений")
                return
            else:
                logger.error(f"Ошибка при закреплении сообщения: {e}")
                await message.reply("❌ Произошла ошибка при закреплении сообщения")
                return

        # Формируем текст для подтверждения
        pin_text = f'<a href="https://t.me/c/{str(chat_id)[4:]}/{message_id}">Сообщение</a>'
        pin_type = "🔔 ГРОМКО" if is_loud else "🔇 ТИХО"

        # Если время не указано - простое закрепление
        if time_str is None:
            await message.reply(
                f"📌 {pin_text} закреплено ({pin_type})",
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            return

        # Закрепление с временем
        pin_duration = parse_time_string(time_str)
        if not pin_duration:
            await message.reply(
                "❌ Неверный формат времени.\n"
                "Пример: 5 часов 30 минут"
            )
            return

        # Рассчитываем время открепления в московском часовом поясе
        unpin_time = datetime.now(MOSCOW_TZ) + pin_duration

        # Сохраняем в БД для автоматического открепления
        await add_pinned_message(chat_id, message_id, unpin_time)

        # Отправляем подтверждение с временем
        duration_text = format_duration(pin_duration)
        await message.reply(
            f"📌 {pin_text} закреплено ({pin_type}) на {duration_text}\n"
            f"⏰ Будет откреплено: {unpin_time.strftime('%d.%m.%Y в %H:%M')}",
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"Ошибка при закреплении сообщения: {e}", exc_info=True)
        await message.reply("❌ Произошла ошибка при закреплении сообщения")


# Также обновим команду -пин для поддержки ID сообщений

@pin_sms.message(F.text & F.text.casefold().startswith("-пин"))
async def unpin_message_handler(message: Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 53):
        return

    """Открепляет сообщение"""
    try:
        args = message.text.split()

        # Если указано "все" - показываем подтверждение с кнопками
        if len(args) > 1 and args[1].lower() == "все":
            # Проверяем, есть ли закрепленные сообщения в чате
            try:
                # Проверка через getChat
                chat = await bot.get_chat(chat_id=message.chat.id)
                pinned_message_id = chat.pinned_message

                # Если pinned_message_id is None, значит нет закрепленных сообщений
                if pinned_message_id is None:
                    # Проверяем в нашей БД на всякий случай
                    pinned_in_db = await get_chat_pinned_messages(message.chat.id)
                    if not pinned_in_db:
                        await message.reply("ℹ️ В этом чате нет закрепленных сообщений.")
                        return
            except Exception as e:
                logger.warning(f"Не удалось проверить закрепки через getChat: {e}")
                # Проверяем в БД
                pinned_in_db = await get_chat_pinned_messages(message.chat.id)
                if not pinned_in_db:
                    await message.reply("ℹ️ В этом чате нет закрепленных сообщений.")
                    return

            # Сохраняем ID исходного сообщения
            original_message_id = message.message_id

            # Создаем inline-кнопки только для "все"
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Да, уверен",
                            callback_data=f"unpin_all_confirm_{message.chat.id}_{original_message_id}"
                        ),
                        InlineKeyboardButton(
                            text="❌ Отмена",
                            callback_data="unpin_all_cancel"
                        )
                    ]
                ]
            )

            # Отправляем сообщение с подтверждением
            confirm_msg = await message.reply(
                "❓ Вы уверены, что хотите открепить ВСЕ закреплённые сообщения?",
                reply_markup=keyboard
            )

            # Ждем 30 секунд, если не нажали кнопку - удаляем сообщение с подтверждением
            await asyncio.sleep(30)
            try:
                await confirm_msg.delete()
            except:
                pass

            return

        # ПРОСТОЙ -пин (без "все")
        target_message_id = None

        if message.reply_to_message:
            # Если ответ на сообщение
            target_message_id = message.reply_to_message.message_id
        elif len(args) > 1:
            # Если указан ID сообщения
            try:
                target_message_id = int(args[1])
            except ValueError:
                await message.reply("❌ Укажите правильный ID сообщения\n"
                                    "Пример: -пин 12345")
                return

        if not target_message_id:
            # Если нет аргументов и не ответ на сообщение - показываем справку
            await message.reply(
                "ℹ️ Использование команды:\n"
                "• Ответьте на сообщение с `-пин` чтобы открепить его\n"
                "• Используйте `-пин [ID]` чтобы открепить сообщение по ID\n"
                "• Используйте `-пин все` чтобы открепить все сообщения\n\n"
                "Пример: `-пин 12345`"
            )
            return

        # Проверяем, есть ли такое сообщение в БД
        if await is_message_pinned(message.chat.id, target_message_id):
            try:
                await bot.unpin_chat_message(
                    chat_id=message.chat.id,
                    message_id=target_message_id
                )
                await remove_pinned_message(message.chat.id, target_message_id)
                await message.reply("📌 Сообщение откреплено")
            except Exception as e:
                logger.error(f"Ошибка при откреплении: {e}")
                # Возможно, сообщение уже не закреплено, но есть в БД
                await remove_pinned_message(message.chat.id, target_message_id)
                await message.reply("⚠️ Сообщение не было закреплено, но удалено из базы данных")
        else:
            # Проверяем, закреплено ли сообщение вообще
            try:
                chat = await bot.get_chat(chat_id=message.chat.id)
                if chat.pinned_message and chat.pinned_message.message_id == target_message_id:
                    # Просто открепляем
                    await bot.unpin_chat_message(
                        chat_id=message.chat.id,
                        message_id=target_message_id
                    )

                    unpin_text = f'<a href="https://t.me/c/{str(message.chat.id)[4:]}/{target_message_id}">Сообщение</a>'
                    await message.reply(f"📌 {unpin_text} откреплено")
                else:
                    await message.reply("❌ Это сообщение не закреплено или не найдено")
            except Exception as e:
                logger.error(f"Ошибка при проверке закрепки: {e}")
                await message.reply("❌ Это сообщение не закреплено или не найдено")

    except Exception as e:
        logger.error(f"Ошибка при откреплении сообщения: {e}", exc_info=True)
        await message.reply("❌ Произошла ошибка при откреплении сообщения")


@pin_sms.message(F.text & F.text.casefold().startswith("!пины"))
async def show_pinned_info(message: Message):
    """Показывает информацию о закрепленных сообщениях"""

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 63):
        return

    try:
        chat_id = message.chat.id

        # Получаем все записи о закреплениях для этого чата
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT message_id, unpin_time 
                FROM pinned_messages 
                WHERE chat_id = $1 
                ORDER BY unpin_time NULLS LAST
            ''', chat_id)

        current_time = datetime.now(MOSCOW_TZ)

        # Формируем красивое сообщение
        response_parts = ["🔹 *Информация о закрепленных сообщениях*\n"]

        if not rows:
            response_parts.append("📭 *В базе данных нет записей*")
        else:
            # Разделяем сообщения на категории
            scheduled = []
            permanent = []
            expired = []

            for row in rows:
                message_id = row['message_id']
                unpin_time = row['unpin_time']
                link = f"https://t.me/c/{str(chat_id)[4:]}/{message_id}"

                if unpin_time:
                    time_left = unpin_time - current_time
                    if time_left.total_seconds() < 0:
                        expired.append((message_id, link, unpin_time))
                    else:
                        time_text = format_duration(time_left)
                        scheduled.append((message_id, link, unpin_time, time_text))
                else:
                    permanent.append((message_id, link))

            # Форматируем каждую категорию

            # Просроченные
            if expired:
                response_parts.append(f"\n🔴 *Просроченные ({len(expired)})*")
                for msg_id, link, unpin_time in expired:
                    response_parts.append(
                        f"   └ [{msg_id}]({link}) — "
                        f"*{unpin_time.strftime('%d.%m.%Y %H:%M')}*"
                    )

            # С автооткреплением
            if scheduled:
                response_parts.append(f"\n🟡 *С автооткреплением ({len(scheduled)})*")
                for msg_id, link, unpin_time, time_left in scheduled:
                    response_parts.append(
                        f"   └ [{msg_id}]({link}) — "
                        f"*{unpin_time.strftime('%d.%m.%Y %H:%M')}*\n"
                        f"      ⏳ *Осталось:* {time_left}"
                    )

            # Бессрочные
            if permanent:
                response_parts.append(f"\n🟢 *Бессрочные ({len(permanent)})*")
                for msg_id, link in permanent:
                    response_parts.append(f"   └ [{msg_id}]({link})")

            # Общая статистика
            response_parts.append(f"\n📊 *Статистика:*")
            total = len(rows)
            if total:
                response_parts.append(f"   ├ Всего записей: {total}")
                if expired:
                    response_parts.append(f"   ├ Просрочено: {len(expired)}")
                if scheduled:
                    response_parts.append(f"   ├ Ожидают открепления: {len(scheduled)}")
                if permanent:
                    response_parts.append(f"   └ Бессрочные: {len(permanent)}")

        # Информация о текущем закрепленном сообщении
        #try:
            #chat_info = await bot.get_chat(chat_id)
            #if chat_info.pinned_message:
                #current_pin_id = chat_info.pinned_message.message_id
               # pin_link = f"https://t.me/c/{str(chat_id)[4:]}/{current_pin_id}"
                #response_parts.append(f"\n📍 *Текущее закрепленное:*")
                #response_parts.append(f"   └ [{current_pin_id}]({pin_link})")
            #else:
                #response_parts.append(f"\n📍 *Текущее закрепленное:*")
                #response_parts.append(f"   └ Нет закрепленных сообщений")
        #except Exception as e:
            #logger.warning(f"Не удалось получить информацию о текущем пине: {e}")
            #response_parts.append(f"\n📍 *Текущее закрепленное:*")
            #response_parts.append(f"   └ Не удалось получить данные")

        # Собираем финальное сообщение
        response = "\n".join(response_parts)
        await message.reply(response, parse_mode='Markdown', disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Ошибка при получении информации о пинах: {e}", exc_info=True)
        await message.reply("❌ *Произошла ошибка при получении информации*", parse_mode='Markdown')



@pin_sms.callback_query(F.data.startswith("unpin_all_confirm_"))
@rate_limit_with_cleanup(limit=1)
async def handle_unpin_all_confirm(callback: CallbackQuery):

    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    """Обработчик подтверждения открепления всех сообщений"""
    try:
        # Извлекаем данные из callback_data: unpin_all_confirm_{chat_id}_{original_msg_id}
        parts = callback.data.split("_")
        chat_id = int(parts[3])
        original_msg_id = int(parts[4]) if len(parts) > 4 else None

        # Создаем кнопку для удаления
        delete_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗑️ УДАЛИТЬ",
                        callback_data=f"unpin_all_execute_{chat_id}_{original_msg_id}"
                    ),
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="unpin_all_cancel"
                    )
                ]
            ]
        )

        # Изменяем сообщение, добавляя новую кнопку
        await callback.message.edit_text(
            "⚠️ ВНИМАНИЕ! Вы собираетесь открепить ВСЕ закреплённые сообщения.\n\n"
            "Это действие невозможно отменить!",
            reply_markup=delete_keyboard
        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при подтверждении открепления: {e}")
        await callback.answer("❌ Ошибка при подтверждении", show_alert=True)


@pin_sms.callback_query(F.data.startswith("unpin_all_execute_"))
@rate_limit_with_cleanup(limit=1)
async def handle_unpin_all_execute(callback: CallbackQuery):

    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    """Обработчик выполнения открепления всех сообщений"""
    try:
        # Извлекаем данные из callback_data: unpin_all_execute_{chat_id}_{original_msg_id}
        parts = callback.data.split("_")
        chat_id = int(parts[3])

        # Показываем "выполняется..."
        await callback.message.edit_text("⏳ Открепляю все сообщения...", reply_markup=None)

        # Выполняем открепление
        try:
            await bot.unpin_all_chat_messages(chat_id=chat_id)
        except Exception as e:
            logger.error(f"Ошибка при откреплении всех сообщений: {e}")
            await callback.message.edit_text(
                "⚠️ Не удалось открепить все сообщения. Возможно, у бота недостаточно прав.")
            await callback.answer()
            return

        # Очищаем записи в БД
        await clear_chat_pins(chat_id)

        # Показываем результат
        await callback.message.edit_text("✅ Все сообщения успешно откреплены!")

    except Exception as e:
        logger.error(f"Ошибка при выполнении открепления: {e}")
        await callback.message.edit_text("❌ Ошибка при откреплении сообщений")
        await callback.answer("Ошибка", show_alert=True)


@pin_sms.callback_query(F.data == "unpin_all_cancel")
@rate_limit_with_cleanup(limit=1)
async def handle_unpin_all_cancel(callback: CallbackQuery):

    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    """Обработчик отмены открепления всех сообщений"""
    try:
        # Изменяем сообщение, показывая отмену
        await callback.message.edit_text("❌ Открепление отменено.")

        await callback.answer("Действие отменено")

    except Exception as e:
        logger.error(f"Ошибка при отмене открепления: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


async def get_chat_pinned_messages(chat_id: int) -> List[Tuple[int, int]]:
    """Получает все закрепленные сообщения чата"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT message_id, unpin_time 
                FROM pinned_messages 
                WHERE chat_id = $1
            ''', chat_id)
            return [(row['message_id'], row['unpin_time']) for row in rows]
    except Exception as e:
        logger.error(f"Ошибка при получении закреплений чата: {e}")
        return []


async def cleanup_expired_pins():
    """Автоматическая очистка истёкших закрепов"""
    while True:
        try:
            current_time = datetime.now(MOSCOW_TZ)

            # Получаем истёкшие закрепки
            pool = get_db_pool()
            async with pool.acquire() as conn:
                # Находим сообщения, время открепления которых наступило
                expired_records = await conn.fetch('''
                    SELECT chat_id, message_id 
                    FROM pinned_messages 
                    WHERE unpin_time IS NOT NULL 
                    AND unpin_time <= $1
                ''', current_time)

            # Обрабатываем каждую истёкшую запись
            for record in expired_records:
                chat_id = record['chat_id']
                message_id = record['message_id']

                try:
                    # Пытаемся открепить сообщение
                    await bot.unpin_chat_message(
                        chat_id=chat_id,
                        message_id=message_id
                    )
                    logger.info(f"Автооткрепление: chat_id={chat_id}, message_id={message_id}")
                except Exception as e:
                    # Если не удалось открепить (уже откреплено или удалено), просто логируем
                    if "message to unpin not found" not in str(e).lower():
                        logger.warning(f"Не удалось автооткрепить: chat_id={chat_id}, message_id={message_id}: {e}")

                # Удаляем запись из БД
                await remove_pinned_message(chat_id, message_id)

            #if expired_records:
                #logger.info(f"Автоочистка: обработано {len(expired_records)} истёкших закрепок")

            # Ждём 60 секунд перед следующей проверкой
            await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"Ошибка в автоочистке закрепок: {e}", exc_info=True)
            await asyncio.sleep(300)  # Ждём 5 минут при ошибке