import asyncio
import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from handlers.AgentsFeatures.chat_info.ChatsInfoDB import get_chat_info, get_chat_stats, format_number
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.Gonfig.config import sanor_ID
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_global
from handlers.BotAutomaticWork.AddChatsBot.link.chats_global_link import chat_global_link

chat_info_router = Router()
logger = logging.getLogger(__name__)


@chat_info_router.message(F.text.startswith('!чат инфо'))
@chat_info_router.message(F.text.startswith('.чат инфо'))
@chat_info_router.message(F.text.startswith('/чат инфо'))
async def chat_info_command(msg: Message):
    try:
        # Проверка доступа
        if msg.from_user.id != sanor_ID:
            return

        # Парсинг аргументов
        args = msg.text.split()
        if len(args) < 3:
            await msg.reply(
                "❌ <b>Неверный формат команды</b>\n\n"
                "Используйте: <code>!чат инфо chat_id</code>\n"
                "Пример: <code>!чат инфо -1001234567890</code>",
                parse_mode='HTML'
            )
            return

        try:
            chat_id = int(args[2])
        except ValueError:
            await msg.reply("❌ <b>Некорректный chat_id</b>\n\nChat_id должен быть числом", parse_mode='HTML')
            return

        # Получаем информацию о чате
        chat_data = await get_chat_info(chat_id)
        if not chat_data:
            await msg.reply(f"❌ Чат с ID <code>{chat_id}</code> не найден в базе данных", parse_mode='HTML')
            return

        # Получаем статистику сообщений
        stats = await get_chat_stats(chat_id)

        # Формируем ссылки
        chat_link = await chat_global_link(chat_id)

        # Форматируем даты
        first_seen = chat_data.get('first_seen', 'Неизвестно')
        last_update = chat_data.get('last_update', 'Неизвестно')

        # Форматируем статусы
        def get_status_emoji(status):
            return "✅" if status == 'on' else "❌" if status == 'off' else "🔄"

        def get_yes_no(value):
            return "Да" if value == 'yes' else "Нет" if value == 'no' else str(value)

        # Получаем ссылку на владельца если есть
        owner_link = "Не указан"
        if chat_data.get('owner_id'):
            owner_link = await user_link_global(chat_data['owner_id'])

        # Создаем текст сообщения
        response_text = (
            f"💬 <b>Информация о чате</b> {chat_link}\n\n"

            f"<b>📋 Основная информация:</b>\n"
            f"🆔 Chat ID: <code>{chat_data['chat_id']}</code>\n"
            f"📛 Название: <code>{chat_data.get('chat_title', 'Не указано')}</code>\n"
            f"👤 Юзернейм: @{chat_data.get('chat_username', 'Нет')}\n"
            f"👑 Владелец: {owner_link}\n"
            f"📅 Первое появление: {first_seen}\n"
            f"🔄 Последнее обновление: {last_update}\n\n"

            f"<b>⚙️ Настройки:</b>\n"
            f"🔔 Пуш-уведомления: {get_status_emoji(chat_data.get('push_status'))} {get_yes_no(chat_data.get('push_status'))}\n"
            f"🚫 Антиспам: {get_status_emoji(chat_data.get('antispam'))} {get_yes_no(chat_data.get('antispam'))}\n"
            f"➕ Статус V: {'✅' if chat_data.get('status_v') == 'yes' else '❌'} {get_yes_no(chat_data.get('status_v'))}\n"
            f"➖ Статус E: {'✅' if chat_data.get('status_e') == 'yes' else '❌'} {get_yes_no(chat_data.get('status_e'))}\n"
            f"🤖 Статус бота: {chat_data.get('bot_chat_status', 'Не указан')}\n"
            f"👁️ Игнор-статус: {chat_data.get('chat_ignore_status', 'Не указан')}\n"
            f"🔢 Число для инпутов: {chat_data.get('number_for_inputs', 'Не указано')}\n"
        )

        # Добавляем пригласительную ссылку если есть
        if chat_data.get('invite_link'):
            response_text += f"🔗 Пригласительная ссылка: {chat_data['invite_link']}\n"
            if chat_data.get('invite_link_updated_at'):
                response_text += f"⏰ Обновлена: {chat_data['invite_link_updated_at']}\n"

        # Добавляем статистику если есть данные
        if stats['total'] > 0:
            response_text += f"\n<b>📊 Статистика сообщений:</b>\n"
            response_text += f"💬 Всего сообщений: {format_number(stats['total'])}\n"
            response_text += f"📈 За сегодня: {format_number(stats['daily'])}\n"
            response_text += f"📅 За неделю: {format_number(stats['weekly'])}\n"
            response_text += f"🗓️ За месяц: {format_number(stats['monthly'])}\n"
            response_text += f"🎯 За год: {format_number(stats['yearly'])}\n"
            response_text += f"👥 Участников в статистике: {stats['users_count']}\n"
            response_text += f"📊 Среднее на пользователя: {stats['avg_per_user']}\n"

        await msg.reply(response_text, parse_mode='HTML', disable_web_page_preview=True)

    except Exception as e:
        await msg.reply(f"❌ Произошла ошибка при получении информации о чате:\n\n<code>{str(e)}</code>",
                        parse_mode='HTML')
        logger.error(f"Ошибка в команде !чат инфо: {e}", exc_info=True)


@chat_info_router.message(F.text.lower() == "!чаты рассылка")
async def mass_mailing_to_chats_command(msg: Message):
    """
    Команда для рассылки сообщения во все чаты из базы данных
    """
    try:
        # Проверка доступа
        if msg.from_user.id != sanor_ID:
            return

        # Создаем текст рассылки
        mailing_text = (
            "👋 Привет! Хочешь быть среди первых, кто повлияет на развитие нового чат-модератора?\n\n"
            "🚀 Прямо сейчас запускается @sap_sp_bot помощник для чатов!\n\n"
            "💡 Мы ищем активных пользователей, которые:\n"
            "• Хотят помочь тестировать новые функции\n"
            "• Имеют идеи по улучшению бота\n"
            "• Готовы давать обратную связь\n\n"
            "🔗 Присоединяйся к нашему новому сообществу! Твой вклад поможет сделать бота лучше для всех."
        )

        # Создаем клавиатуру с кнопками
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='🪄 Добавить в чат',
                        url='https://t.me/sap_sp_bot?startgroup=sap&admin=change_info+delete_messages+invite_users+restrict_members+pin_messages+promote_members'
                    )
                ],
                [
                    InlineKeyboardButton(
                        text='💬 Перейти в наш чат',
                        url='https://t.me/sap_sp_chat'
                    )
                ]
            ]
        )

        # Получаем список всех чатов из базы данных
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('SELECT chat_id FROM chats ORDER BY chat_id')

        if not rows:
            await msg.reply("❌ В базе данных нет чатов для рассылки")
            return

        # Отправляем стартовое сообщение
        total_chats = len(rows)
        status_message = await msg.reply(
            f"📨 <b>Начинаю рассылку по {total_chats} чатам...</b>\n"
            f"✅ Отправлено: 0/{total_chats}\n"
            f"❌ Ошибок: 0",
            parse_mode='HTML'
        )

        # Статистика
        successful = 0
        failed = 0
        failed_chats = []

        # Рассылка по всем чатам
        for i, row in enumerate(rows, 1):
            chat_id = row['chat_id']

            try:
                # Пытаемся отправить сообщение в чат
                await msg.bot.send_message(
                    chat_id=chat_id,
                    text=mailing_text,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
                successful += 1

                # Обновляем статус каждые 5 чатов или если это последний чат
                if i % 5 == 0 or i == total_chats:
                    await status_message.edit_text(
                        f"📨 <b>Рассылка по {total_chats} чатам...</b>\n"
                        f"✅ Отправлено: {successful}/{total_chats}\n"
                        f"❌ Ошибок: {failed}\n"
                        f"📊 Прогресс: {i}/{total_chats} ({i / total_chats * 100:.1f}%)",
                        parse_mode='HTML'
                    )

                # Небольшая задержка чтобы не перегружать API
                await asyncio.sleep(0.5)

            except Exception as e:
                failed += 1
                failed_chats.append((chat_id, str(e)))
                #logger.error(f"Ошибка при отправке в чат {chat_id}: {e}")

                # Обновляем статус при ошибке
                if i % 5 == 0 or i == total_chats:
                    await status_message.edit_text(
                        f"📨 <b>Рассылка по {total_chats} чатам...</b>\n"
                        f"✅ Отправлено: {successful}/{total_chats}\n"
                        f"❌ Ошибок: {failed}\n"
                        f"📊 Прогресс: {i}/{total_chats} ({i / total_chats * 100:.1f}%)",
                        parse_mode='HTML'
                    )

        # Итоговое сообщение
        result_text = (
            f"✅ <b>Рассылка по чатам завершена!</b>\n\n"
            f"📊 <b>Итоги:</b>\n"
            f"✅ Успешно: {successful} чатов\n"
            f"❌ Ошибок: {failed} чатов\n"
            f"📈 Эффективность: {successful / total_chats * 100:.1f}%"
        )

        if failed > 0:
            result_text += f"\n\n<b>Чаты с ошибками ({min(failed, 10)} из {failed}):</b>\n"
            for chat_id, error in failed_chats[:10]:  # Показываем только первые 10 ошибок
                short_error = error[:50] + "..." if len(error) > 50 else error
                result_text += f"• <code>{chat_id}</code> - {short_error}\n"

            if failed > 10:
                result_text += f"\n... и ещё {failed - 10} чатов с ошибками"

        await status_message.edit_text(result_text, parse_mode='HTML')

    except Exception as e:
        await msg.reply(f"❌ Произошла ошибка при выполнении рассылки по чатам:\n\n<code>{str(e)}</code>",
                        parse_mode='HTML')
        #logger.error(f"Ошибка в команде !чаты рассылка: {e}", exc_info=True)


@chat_info_router.message(F.text.lower() == "!юзеры рассылка")
async def mass_mailing_to_users_command(msg: Message):
    """
    Команда для рассылки сообщения всем пользователям из базы данных
    """
    try:
        # Проверка доступа
        if msg.from_user.id != sanor_ID:
            return

        # Создаем текст рассылки (можно адаптировать для пользователей)
        mailing_text = (
            "🚀 Хотите оставить свой след в самом начале чего-то большого?\n"
            "Прямо сейчас запускается новый чат-модератор @sap_sp_bot и мы ищем активных, инициативных и вдумчивых участников, готовых помочь ему стать лучше!\n\n"
            "💡 У вас есть идеи? Предложения? Желание повлиять на развитие бота с самого нуля?\n"
            "Тогда именно вы нам нужны! Присоединяйтесь, ваш голос будет услышан, а вклад действительно важен.\n\n"
            "👇🏻 Скорее добавьте меня в свои чаты!"
        )

        # Создаем клавиатуру с кнопкой
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='🪄 Добавить в чат',
                        url='https://t.me/sap_sp_bot?startgroup=sap&admin=change_info+delete_messages+invite_users+restrict_members+pin_messages+promote_members'
                    )
                ],
                [
                    InlineKeyboardButton(
                        text='💬 Перейти в наш чат',
                        url='https://t.me/sap_sp_chat'
                    )
                ]
            ]
        )

        # Получаем список всех пользователей из базы данных
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Получаем user_id из таблицы users (предполагаемая структура)
            rows = await conn.fetch('''
                SELECT user_id FROM users 
                WHERE user_id IS NOT NULL 
                ORDER BY user_id
            ''')

        if not rows:
            await msg.reply("❌ В базе данных нет пользователей для рассылки")
            return

        # Отправляем стартовое сообщение
        total_users = len(rows)
        status_message = await msg.reply(
            f"📨 <b>Начинаю рассылку по {total_users} пользователям...</b>\n"
            f"✅ Отправлено: 0/{total_users}\n"
            f"❌ Ошибок: 0",
            parse_mode='HTML'
        )

        # Статистика
        successful = 0
        failed = 0
        failed_users = []

        # Рассылка по всем пользователям
        for i, row in enumerate(rows, 1):
            user_id = row['user_id']

            try:
                # Проверяем, что это действительно user_id (не чат)
                # user_id обычно положительный, chat_id для чатов отрицательный
                if user_id > 0:
                    # Пытаемся отправить сообщение пользователю
                    await msg.bot.send_message(
                        chat_id=user_id,
                        text=mailing_text,
                        reply_markup=keyboard,
                        parse_mode='HTML'
                    )
                    successful += 1
                else:
                    # Пропускаем отрицательные ID (скорее всего это чаты)
                    failed += 1
                    failed_users.append((user_id, "Неверный формат ID (возможно это чат)"))
                    continue

                # Обновляем статус каждые 10 пользователей или если это последний
                if i % 10 == 0 or i == total_users:
                    await status_message.edit_text(
                        f"📨 <b>Рассылка по {total_users} пользователям...</b>\n"
                        f"✅ Отправлено: {successful}/{total_users}\n"
                        f"❌ Ошибок: {failed}\n"
                        f"📊 Прогресс: {i}/{total_users} ({i / total_users * 100:.1f}%)",
                        parse_mode='HTML'
                    )

                # Небольшая задержка чтобы не перегружать API (для пользователей можно сделать меньше)
                await asyncio.sleep(0.3)

            except Exception as e:
                failed += 1
                error_msg = str(e)
                failed_users.append((user_id, error_msg))
                #logger.error(f"Ошибка при отправке пользователю {user_id}: {e}")

                # Обновляем статус при ошибке
                if i % 10 == 0 or i == total_users:
                    await status_message.edit_text(
                        f"📨 <b>Рассылка по {total_users} пользователям...</b>\n"
                        f"✅ Отправлено: {successful}/{total_users}\n"
                        f"❌ Ошибок: {failed}\n"
                        f"📊 Прогресс: {i}/{total_users} ({i / total_users * 100:.1f}%)",
                        parse_mode='HTML'
                    )

        # Итоговое сообщение
        result_text = (
            f"✅ <b>Рассылка по пользователям завершена!</b>\n\n"
            f"📊 <b>Итоги:</b>\n"
            f"✅ Успешно: {successful} пользователей\n"
            f"❌ Ошибок: {failed} пользователей\n"
            f"📈 Эффективность: {successful / total_users * 100:.1f}%"
        )

        if failed > 0:
            result_text += f"\n\n<b>Пользователи с ошибками ({min(failed, 10)} из {failed}):</b>\n"
            for user_id, error in failed_users[:10]:  # Показываем только первые 10 ошибок
                short_error = error[:50] + "..." if len(error) > 50 else error
                result_text += f"• <code>{user_id}</code> - {short_error}\n"

            if failed > 10:
                result_text += f"\n... и ещё {failed - 10} пользователей с ошибками"

        await status_message.edit_text(result_text, parse_mode='HTML')

    except Exception as e:
        await msg.reply(f"❌ Произошла ошибка при выполнении рассылки по пользователям:\n\n<code>{str(e)}</code>",
                        parse_mode='HTML')
        #logger.error(f"Ошибка в команде !юзеры рассылка: {e}", exc_info=True)


@chat_info_router.message(F.text.lower() == "!все рассылка")
async def mass_mailing_to_all_command(msg: Message):
    """
    Команда для рассылки сообщения и чатам и пользователям
    """
    try:
        # Проверка доступа
        if msg.from_user.id != sanor_ID:
            return

        # Создаем тексты рассылки
        chat_mailing_text = (
            "🚀 Хотите оставить свой след в самом начале чего-то большого?\n"
            "Прямо сейчас запускается новый чат-модератор @sap_sp_bot и мы ищем активных, инициативных и вдумчивых участников, готовых помочь ему стать лучше!\n\n"
            "💡 У вас есть идеи? Предложения? Желание повлиять на развитие бота с самого нуля?\n"
            "Тогда именно вы нам нужны! Присоединяйтесь, ваш голос будет услышан, а вклад действительно важен.\n\n"
            "👇🏻 Скорее добавьте меня в свои чаты!"
        )

        user_mailing_text = (
            "👋 Привет! Хочешь быть среди первых, кто повлияет на развитие нового чат-модератора?\n\n"
            "🚀 Прямо сейчас запускается @sap_sp_bot помощник для чатов!\n\n"
            "💡 Мы ищем активных пользователей, которые:\n"
            "• Хотят помочь тестировать новые функции\n"
            "• Имеют идеи по улучшению бота\n"
            "• Готовы давать обратную связь\n\n"
            "🔗 Присоединяйся к нашему новому сообществу! Твой вклад поможет сделать бота лучше для всех."
        )

        # Создаем клавиатуры
        chat_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='🪄 Добавить в чат',
                        url='https://t.me/sap_sp_bot?startgroup=sap&admin=change_info+delete_messages+invite_users+restrict_members+pin_messages+promote_members'
                    )
                ],
                [
                    InlineKeyboardButton(
                        text='💬 Перейти в наш чат',
                        url='https://t.me/sap_sp_chat'
                    )
                ]
            ]
        )

        user_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='🪄 Добавить в чат',
                        url='https://t.me/sap_sp_bot?startgroup=sap&admin=change_info+delete_messages+invite_users+restrict_members+pin_messages+promote_members'
                    )
                ],
                [
                    InlineKeyboardButton(
                        text='💬 Перейти в наш чат',
                        url='https://t.me/sap_sp_chat'
                    )
                ]
            ]
        )

        # Получаем данные из базы
        pool = await get_db_pool()

        # Получаем чаты
        async with pool.acquire() as conn:
            chat_rows = await conn.fetch('SELECT chat_id FROM chats ORDER BY chat_id')
            user_rows = await conn.fetch('''
                SELECT user_id FROM users 
                WHERE user_id IS NOT NULL AND user_id > 0 
                ORDER BY user_id
            ''')

        total_chats = len(chat_rows) if chat_rows else 0
        total_users = len(user_rows) if user_rows else 0
        total_all = total_chats + total_users

        if total_all == 0:
            await msg.reply("❌ В базе данных нет чатов и пользователей для рассылки")
            return

        # Стартовое сообщение
        status_message = await msg.reply(
            f"📨 <b>Начинаю полную рассылку...</b>\n\n"
            f"💬 Чатов: {total_chats}\n"
            f"👤 Пользователей: {total_users}\n"
            f"📊 Всего: {total_all}\n\n"
            f"✅ Отправлено: 0/{total_all}\n"
            f"❌ Ошибок: 0",
            parse_mode='HTML'
        )

        # Общая статистика
        successful = 0
        failed = 0
        failed_entities = []

        # 1. Рассылка по чатам
        if chat_rows:
            await status_message.edit_text(
                f"📨 <b>Полная рассылка - этап 1: Чаты</b>\n\n"
                f"💬 Отправка по {total_chats} чатам...\n"
                f"✅ Отправлено: {successful}/{total_all}\n"
                f"❌ Ошибок: {failed}",
                parse_mode='HTML'
            )

            for i, row in enumerate(chat_rows, 1):
                chat_id = row['chat_id']

                try:
                    await msg.bot.send_message(
                        chat_id=chat_id,
                        text=chat_mailing_text,
                        reply_markup=chat_keyboard,
                        parse_mode='HTML'
                    )
                    successful += 1

                    if i % 5 == 0 or i == total_chats:
                        await status_message.edit_text(
                            f"📨 <b>Полная рассылка - этап 1: Чаты</b>\n\n"
                            f"💬 Отправка по {total_chats} чатам...\n"
                            f"📊 Прогресс: {i}/{total_chats}\n"
                            f"✅ Отправлено: {successful}/{total_all}\n"
                            f"❌ Ошибок: {failed}",
                            parse_mode='HTML'
                        )

                    await asyncio.sleep(0.5)

                except Exception as e:
                    failed += 1
                    failed_entities.append((f"Чат {chat_id}", str(e)))
                    #logger.error(f"Ошибка при отправке в чат {chat_id}: {e}")

        # 2. Рассылка по пользователям
        if user_rows:
            await status_message.edit_text(
                f"📨 <b>Полная рассылка - этап 2: Пользователи</b>\n\n"
                f"👤 Отправка по {total_users} пользователям...\n"
                f"✅ Отправлено: {successful}/{total_all}\n"
                f"❌ Ошибок: {failed}",
                parse_mode='HTML'
            )

            for i, row in enumerate(user_rows, 1):
                user_id = row['user_id']

                try:
                    await msg.bot.send_message(
                        chat_id=user_id,
                        text=user_mailing_text,
                        reply_markup=user_keyboard,
                        parse_mode='HTML'
                    )
                    successful += 1

                    if i % 10 == 0 or i == total_users:
                        await status_message.edit_text(
                            f"📨 <b>Полная рассылка - этап 2: Пользователи</b>\n\n"
                            f"👤 Отправка по {total_users} пользователям...\n"
                            f"📊 Прогресс: {i}/{total_users}\n"
                            f"✅ Отправлено: {successful}/{total_all}\n"
                            f"❌ Ошибок: {failed}",
                            parse_mode='HTML'
                        )

                    await asyncio.sleep(0.3)

                except Exception as e:
                    failed += 1
                    failed_entities.append((f"Пользователь {user_id}", str(e)))
                    #logger.error(f"Ошибка при отправке пользователю {user_id}: {e}")

        # Итоговое сообщение
        result_text = (
            f"✅ <b>Полная рассылка завершена!</b>\n\n"
            f"📊 <b>Итоги:</b>\n"
            f"💬 Чатов: {total_chats}\n"
            f"👤 Пользователей: {total_users}\n"
            f"📊 Всего адресатов: {total_all}\n\n"
            f"✅ Успешно: {successful}\n"
            f"❌ Ошибок: {failed}\n"
            f"📈 Эффективность: {successful / total_all * 100:.1f}%"
        )

        if failed > 0:
            result_text += f"\n\n<b>Ошибки ({min(failed, 10)} из {failed}):</b>\n"
            for entity, error in failed_entities[:10]:
                short_error = error[:50] + "..." if len(error) > 50 else error
                result_text += f"• {entity} - {short_error}\n"

            if failed > 10:
                result_text += f"\n... и ещё {failed - 10} ошибок"

        await status_message.edit_text(result_text, parse_mode='HTML')

    except Exception as e:
        await msg.reply(f"❌ Произошла ошибка при выполнении полной рассылки:\n\n<code>{str(e)}</code>",
                        parse_mode='HTML')
        #logger.error(f"Ошибка в команде !все рассылка: {e}", exc_info=True)


# Константы
CHATS_PER_PAGE = 5  # Уменьшил для удобства просмотра
STATE_TIMEOUT = 300  # 5 минут до очистки состояния


class ChatListPagination(StatesGroup):
    waiting_for_page = State()


# Словарь для хранения времени последней активности
user_last_activity = {}


async def cleanup_states_worker(bot, state_storage):
    """Фоновая задача для очистки устаревших состояний"""
    while True:
        try:
            now = datetime.now()
            to_delete = []

            # Проверяем всех пользователей
            for user_id, last_time in list(user_last_activity.items()):
                if (now - last_time).seconds > STATE_TIMEOUT:
                    to_delete.append(user_id)

            # Удаляем устаревшие состояния
            for user_id in to_delete:
                try:
                    # Создаем ключ для удаления
                    key = StorageKey(
                        bot_id=bot.id,
                        user_id=user_id,
                        chat_id=user_id
                    )
                    # Получаем текущее состояние и очищаем его
                    current_state = await state_storage.get_storage(key)
                    if current_state:
                        await state_storage.set_data(key, {})
                        await state_storage.set_state(key, None)
                    del user_last_activity[user_id]
                    #logger.debug(f"Очищено состояние для пользователя {user_id}")
                except Exception as e:
                    logger.error(f"Ошибка при очистке состояния {user_id}: {e}")

            await asyncio.sleep(60)  # Проверяем каждую минуту

        except Exception as e:
            logger.error(f"Ошибка в cleanup_states_worker: {e}")
            await asyncio.sleep(60)


def setup_cleanup_task(bot, state_storage):
    """Настройка фоновой задачи очистки"""
    asyncio.create_task(cleanup_states_worker(bot, state_storage))


@chat_info_router.message(F.text.lower() == "!ид чатов")
async def chat_id_list_command(msg: Message, state: FSMContext):
    try:

        if msg.from_user.id != sanor_ID:
            return

        # Обновляем время активности
        user_last_activity[msg.from_user.id] = datetime.now()

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT chat_id, chat_title 
                FROM chats 
                ORDER BY chat_id
            ''')

        if not rows:
            await msg.reply("❌ В базе данных нет чатов")
            await state.clear()
            if msg.from_user.id in user_last_activity:
                del user_last_activity[msg.from_user.id]
            return

        # Сохраняем данные
        await state.update_data(
            all_chats=[dict(row) for row in rows],  # Конвертируем в dict
            current_page=0,
            total_chats=len(rows),
            total_pages=(len(rows) + CHATS_PER_PAGE - 1) // CHATS_PER_PAGE
        )

        # Устанавливаем состояние
        await state.set_state(ChatListPagination.waiting_for_page)

        # Отправляем первую страницу
        await send_chat_page(msg, state)

    except Exception as e:
        await msg.reply(f"❌ Ошибка при получении списка чатов")
        logger.error(f"Ошибка в команде !чат ид: {e}", exc_info=True)


# ОБРАБОТЧИК КНОПОК - ВАЖНО: без фильтра состояния для коллбэков
@chat_info_router.callback_query(F.data.startswith("page_"))
async def process_page_callback(callback: CallbackQuery, state: FSMContext):
    """Обработка навигации по страницам"""
    try:

        if callback.from_user.id != sanor_ID:
            return

        # Проверяем, есть ли состояние у пользователя
        current_state = await state.get_state()
        if current_state != ChatListPagination.waiting_for_page.state:
            await callback.answer("❌ Сессия истекла. Используйте команду !чат ид снова.", show_alert=True)
            await callback.message.delete()
            return

        # Обновляем время активности
        user_last_activity[callback.from_user.id] = datetime.now()

        data = await state.get_data()
        current_page = data.get('current_page', 0)
        total_pages = data.get('total_pages', 1)

        if callback.data == "page_prev":
            new_page = max(0, current_page - 1)
        elif callback.data == "page_next":
            new_page = min(total_pages - 1, current_page + 1)
        else:
            await callback.answer()
            return

        # Обновляем страницу
        await state.update_data(current_page=new_page)

        # Обновляем сообщение
        await update_chat_page(callback.message, state)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка в process_page_callback: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка", show_alert=True)


# Отдельный хендлер для кнопки "Закрыть"
@chat_info_router.callback_query(F.data == "close")
async def close_pagination(callback: CallbackQuery, state: FSMContext):
    """Закрытие пагинации"""
    try:

        if callback.from_user.id != sanor_ID:
            return

        # Удаляем сообщение
        await callback.message.delete()

        # Очищаем состояние
        await state.clear()

        # Удаляем из активностей
        if callback.from_user.id in user_last_activity:
            del user_last_activity[callback.from_user.id]

        await callback.answer("✅ Список закрыт")

    except Exception as e:
        logger.error(f"Ошибка при закрытии пагинации: {e}")
        await callback.answer("❌ Ошибка при закрытии")


@chat_info_router.callback_query(F.data == "current")
async def current_page_info(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != sanor_ID:
        return

    """Информация о текущей странице"""
    data = await state.get_data()
    current_page = data.get('current_page', 0)
    total_pages = data.get('total_pages', 1)
    await callback.answer(f"Страница {current_page + 1} из {total_pages}")


async def send_chat_page(message: Message, state: FSMContext):
    """Отправка первой страницы с чатами"""
    try:
        data = await state.get_data()
        all_chats = data.get('all_chats', [])
        current_page = data.get('current_page', 0)
        total_pages = data.get('total_pages', 1)

        # Формируем сообщение
        page_text = await format_chat_page(all_chats, current_page, total_pages)

        # Создаем клавиатуру
        keyboard = create_pagination_keyboard(current_page, total_pages)

        # Отправляем сообщение
        await message.answer(
            page_text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка в send_chat_page: {e}", exc_info=True)
        await message.reply("❌ Ошибка при формировании списка чатов")


async def update_chat_page(message: Message, state: FSMContext):
    """Обновление существующего сообщения с чатами"""
    try:
        data = await state.get_data()
        all_chats = data.get('all_chats', [])
        current_page = data.get('current_page', 0)
        total_pages = data.get('total_pages', 1)

        # Формируем сообщение
        page_text = await format_chat_page(all_chats, current_page, total_pages)

        # Создаем клавиатуру
        keyboard = create_pagination_keyboard(current_page, total_pages)

        # Обновляем сообщение
        await message.edit_text(
            page_text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка в update_chat_page: {e}", exc_info=True)


async def format_chat_page(all_chats, current_page, total_pages):
    """Форматирование текста страницы"""
    start_idx = current_page * CHATS_PER_PAGE
    end_idx = min(start_idx + CHATS_PER_PAGE, len(all_chats))

    response_lines = []
    response_lines.append(f"📋 <b>Список чатов (страница {current_page + 1}/{total_pages}):</b>\n")

    for i in range(start_idx, end_idx):
        row = all_chats[i]
        chat_id = row['chat_id']
        chat_link = await chat_global_link(chat_id)
        chat_name = row.get('chat_title') or "Без названия"

        response_lines.append(f"<b>{i + 1}.</b> {chat_link}")
        response_lines.append(f"   🆔 <code>{chat_id}</code>")
        response_lines.append("")

    return "\n".join(response_lines)


def create_pagination_keyboard(current_page, total_pages):
    """Создание клавиатуры пагинации"""
    keyboard_buttons = []

    # Кнопка "Назад"
    if current_page > 0:
        keyboard_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="page_prev"))

    # Кнопка с текущей страницей
    keyboard_buttons.append(InlineKeyboardButton(
        text=f"📄 {current_page + 1}/{total_pages}",
        callback_data="current"
    ))

    # Кнопка "Вперед"
    if current_page < total_pages - 1:
        keyboard_buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data="page_next"))

    # Кнопка "Закрыть"
    keyboard_buttons.append(InlineKeyboardButton(text="❌ Закрыть", callback_data="close"))

    return InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])