import logging
import asyncio
from datetime import datetime
from html import escape
from typing import Optional, Dict, Tuple, Any
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pytz import timezone

from handlers.AgentsFeatures.payment.paymentDB import (
    get_current_datetime, add_to_bag, get_user_bag, remove_from_bag,
    get_bag_info, get_total_sapphires, get_top_bags, get_recent_transfers,
    transfer_sapphires, get_formatted_bag_history, OPERATION_TYPES,
    toggle_bag_visibility, is_bag_hidden, get_user_bag_rank
)
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.Gonfig.config import sanor_ID
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import check_user_access
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text
from handlers.BotAutomaticWork.users.checks.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_global

# Создаем роутер
sapphires_router = Router()

# Настройка времени
TIMEZONE = timezone('Europe/Moscow')
logger = logging.getLogger(__name__)

# Константы
MAX_TRANSFER_AMOUNT = 50_000
MAX_BALANCE = 1_000_000
MIN_TRANSFER_AMOUNT = 1

# Хранилище ожидающих переводов
pending_transfers: Dict[str, Dict] = {}
punishment_data: Dict[Tuple, str] = {}


def get_formatted_time(dt: Optional[datetime] = None) -> str:
    """Возвращает отформатированное московское время"""
    if dt is None:
        dt = datetime.now()
    return dt.astimezone(TIMEZONE).strftime('%d.%m.%Y в %H:%M')


def safe_int(value: str, default: int = 0) -> int:
    """Безопасное преобразование в число"""
    try:
        if isinstance(value, str):
            # Убираем валютные символы и пробелы
            num = int(value.replace(',', '').replace(' ', '').replace('сапф', '').replace('s', ''))
        else:
            num = int(value)
        return max(num, 0)
    except (ValueError, TypeError):
        return default


def parse_command_with_reply(text: str, replied_user_id: Optional[int] = None) -> Tuple[Optional[int], Any, str]:
    """Парсит команду с возможностью ответа на сообщение"""
    parts = text.split(maxsplit=2)  # Уменьшаем максимальное разбиение

    # Если есть reply и в команде только сумма
    if replied_user_id and len(parts) == 2:
        amount_str = parts[1]
        amount = safe_int(amount_str)
        return amount, replied_user_id, ""

    # Если есть reply и в команде сумма + комментарий
    if replied_user_id and len(parts) == 3:
        amount_str = parts[1]
        amount = safe_int(amount_str)
        comment = parts[2]
        return amount, replied_user_id, comment

    # Стандартный парсинг для случая без reply
    if len(parts) < 3:
        return None, None, ""

    # Убираем префикс команды если есть
    amount_str = parts[1]
    amount = safe_int(amount_str)

    target = parts[2].strip()

    # Обрабатываем случай, когда target может быть комментарием
    # Проверяем, является ли target числом (ID) или упоминанием
    if target.startswith('@') or target.isdigit():
        target_user = target
        comment = ""
    else:
        # target - это комментарий, пользователь из reply
        if replied_user_id:
            target_user = replied_user_id
            comment = parts[2]
        else:
            return None, None, ""

    return amount, target_user, comment


def get_bag_level(balance: int) -> tuple:
    """Определяет уровень мешка"""
    levels = [
        (0, "🟡 Пустой", "🎒"),
        (100, "🟢 Начинающий", "💰"),
        (500, "🔵 Опытный", "💼"),
        (1000, "🟣 Богатый", "💎"),
        (5000, "🟣 Очень богатый", "🏦"),
        (10000, "🔴 Король сапфов", "👁️"),
        (50000, "⚡️ ЛЕГЕНДАРНЫЙ", "🌟"),
        (100000, "Супер чел", "🤑"),
        (1000000, "✨ БОГ САПФОВ", "👑")
    ]

    for threshold, name, emoji in reversed(levels):
        if balance >= threshold:
            return name, emoji

    return levels[0][1], levels[0][2]




async def resolve_target_user(msg: Message, target_identifier: str) -> Optional[int]:
    """Определяет ID целевого пользователя"""
    try:
        if msg.reply_to_message and target_identifier.startswith('@'):
            return msg.reply_to_message.from_user.id

        if target_identifier.startswith('@'):
            return await resolve_id(msg, target_identifier)
        elif target_identifier.isdigit():
            return int(target_identifier)
        else:
            return await resolve_id(msg, f"@{target_identifier}")
    except:
        return None


async def user_exists_in_db(user_id: int) -> bool:
    """Проверяет существует ли пользователь в БД"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval(
                'SELECT 1 FROM users WHERE user_id = $1',
                user_id
            )
            return result is not None
    except Exception as e:
        logger.error(f"Error checking user existence: {e}")
        return False


def get_operation_description(operation_type: str, amount: int,
                              agent_id: int, user_id: int,
                              from_user_id: int = None, to_user_id: int = None) -> str:
    """Создает описание операции с HTML-ссылками"""
    try:
        # Получаем ссылки на пользователей
        agent_link = user_link_global(agent_id) if agent_id else "администратора"
        user_link = user_link_global(user_id) if user_id else "Неизвестно"

        if operation_type in ['add', 'purchase', 'reward']:
            return f"От {agent_link} к {user_link}"
        elif operation_type == 'remove':
            return f"От {user_link} к системе"
        elif operation_type in ['user_transfer_in', 'admin_transfer_in']:
            from_link = user_link_global(from_user_id) if from_user_id else "пользователя"
            return f"От {from_link} к {user_link}"
        elif operation_type in ['user_transfer_out', 'admin_transfer_out']:
            to_link = user_link_global(to_user_id) if to_user_id else "пользователя"
            return f"От {user_link} к {to_link}"
        else:
            return "Операция"
    except:
        return "Операция"


# Функция для форматирования истории операций с ссылками
async def format_operation_with_links(operation: dict) -> dict:
    """Добавляет HTML-ссылки к информации об операции"""
    result = dict(operation)

    # Добавляем ссылки на пользователей
    agent_id = operation.get('agent_id')
    user_id = operation.get('user_id')

    if agent_id:
        result['agent_link'] = await user_link_global(agent_id)
    else:
        result['agent_link'] = "Система"

    if user_id:
        result['user_link'] = await user_link_global(user_id)
    else:
        result['user_link'] = "Неизвестно"

    # Создаем описание с ссылками
    operation_type = operation.get('operation_type', '')

    # Для переводов определяем вторую сторону
    if 'transfer_in' in operation_type:
        from_user_id = agent_id
        to_user_id = user_id
        from_link = result['agent_link']
        to_link = result['user_link']
        result['description'] = f"Получен перевод от {from_link}"
    elif 'transfer_out' in operation_type:
        from_user_id = user_id
        to_user_id = agent_id
        from_link = result['user_link']
        to_link = result['agent_link']
        result['description'] = f"Перевод пользователю {to_link}"
    elif operation_type == 'add':
        from_link = result['agent_link']
        to_link = result['user_link']
        result['description'] = f"Пополнение от {from_link}"
    elif operation_type == 'remove':
        from_link = result['user_link']
        result['description'] = f"Списание администратором {from_link}"
    else:
        result['description'] = "Операция"

    return result


# УПРОЩЕННАЯ КОМАНДА ПОПОЛНЕНИЯ С ОТВЕТОМ
@sapphires_router.message(F.text.regexp(r'^[!/.]пополнить\s+\d+'))
async def add_sapphires_handler(msg: Message):
    """Пополнение мешка сапфами с ответом на сообщение"""
    if not msg.from_user.id == sanor_ID:
        return

    try:
        # Определяем целевого пользователя
        target_user_id = None
        if msg.reply_to_message:
            target_user_id = msg.reply_to_message.from_user.id

        amount, target, comment = parse_command_with_reply(msg.text, target_user_id)

        if not amount or amount <= 0:
            await msg.reply("❌ Укажите положительную сумму!")
            return

        if amount > MAX_BALANCE:
            await msg.reply(f"❌ Максимальная сумма: {MAX_BALANCE:,} сапфов")
            return

        # Если target - это строка (юзернейм или ID), а не число
        if isinstance(target, str):
            target_user_id = await resolve_target_user(msg, target)

        if not target_user_id or not await user_exists_in_db(target_user_id):
            await msg.reply("❌ Пользователь не найден в системе!")
            return

        success, new_balance, message = await add_to_bag(
            target_user_id, amount, msg.from_user.id,
            get_current_datetime(), comment
        )

        if success:
            target_link = await user_link_global(target_user_id)
            operator_link = await user_link_global(msg.from_user.id)

            response_text = (
                f'➕ <b>Пополнение сапфирок {target_link}</b>\n\n'
                f'💰 <b>Добавлено:</b> <code>+{amount:,} сапфов ({new_balance:,})</code>\n'
                f'👮 <b>Оператор:</b> {operator_link}\n'
            )

            if comment and comment.strip():
                response_text += f'💬 <b>Комментарий:</b> {comment}\n'

            await msg.reply(
                response_text,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        else:
            await msg.reply(f'❌ {message}',
                            parse_mode='HTML',
                            disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Add sapphires error: {e}", exc_info=True)
        await msg.reply("❌ Ошибка при пополнении!")


# УПРОЩЕННАЯ КОМАНДА УДАЛЕНИЯ С ОТВЕТОМ
@sapphires_router.message(F.text.regexp(r'^[!/.]отнять\s+\d+'))
async def remove_sapphires_handler(msg: Message):
    """Удаление сапфов из мешка с ответом на сообщение"""
    if not msg.from_user.id == sanor_ID:
        return

    try:
        # Определяем целевого пользователя
        target_user_id = None
        if msg.reply_to_message:
            target_user_id = msg.reply_to_message.from_user.id

        amount, target, comment = parse_command_with_reply(msg.text, target_user_id)

        if not amount or amount <= 0:
            await msg.reply("❌ Укажите положительную сумму!")
            return

        # Если target - это строка (юзернейм или ID)
        if isinstance(target, str):
            target_user_id = await resolve_target_user(msg, target)

        if not target_user_id or not await user_exists_in_db(target_user_id):
            await msg.reply("❌ Пользователь не найден в системе!")
            return

        current_balance = await get_user_bag(target_user_id)
        if current_balance < amount:
            await msg.reply(f"❌ Недостаточно сапфов! Доступно: {current_balance:,}")
            return

        success, new_balance, message = await remove_from_bag(
            target_user_id, amount, msg.from_user.id,
            get_current_datetime(), comment
        )

        if success:
            target_link = await user_link_global(target_user_id)
            operator_link = await user_link_global(msg.from_user.id)

            response_text = (
                f'➖ <b>Списание сапфиров у {target_link}</b>\n\n'
                f'💰 <b>Списано:</b> <code>-{amount:,} сапфов ({new_balance:,})</code>\n'
                f'👮 <b>Оператор:</b> {operator_link}\n'
            )

            if comment and comment.strip():
                response_text += f'💬 <b>Комментарий:</b> {comment}\n'

            await msg.reply(
                response_text,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        else:
            await msg.reply(f'❌ {message}',
                            parse_mode='HTML',
                            disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Remove sapphires error: {e}", exc_info=True)
        await msg.reply("❌ Ошибка при списании!")


# ПОКАЗ МЕШКА (ОБЩАЯ КОМАНДА) С МЕСТОМ В ТОПЕ
@sapphires_router.message(F.text.regexp(r'^(?:[!./]:?)?мешок'))
async def check_bag_handler(msg: Message):
    """Показывает мешок с проверкой видимости и местом в топе"""
    try:
        user_id = msg.from_user.id

        # Определяем целевого пользователя
        parts = msg.text.split()
        target_user_id = user_id

        if len(parts) > 1:
            target_user_id = await resolve_target_user(msg, parts[1]) or user_id
        elif msg.reply_to_message:
            target_user_id = msg.reply_to_message.from_user.id

        # Проверяем права доступа
        is_agent = await check_user_access(user_id, 2)  # Агенты ранг 2+

        # Если проверяем не свой мешок
        if target_user_id != user_id:
            # Проверяем, скрыт ли мешок
            if await is_bag_hidden(target_user_id) and not is_agent:
                await msg.reply("🔒 Этот мешок скрыт владельцем")
                return

        # Получаем информацию о мешке
        bag_info = await get_bag_info(target_user_id)
        balance = bag_info['balance']
        level, emoji = get_bag_level(balance)
        user_link = await user_link_global(target_user_id)

        # Получаем место в топе (только для не скрытых мешков)
        rank_text = ""
        if not await is_bag_hidden(target_user_id) and balance > 0:
            rank = await get_user_bag_rank(target_user_id)
            if rank > 0:
                medal = ""
                if rank == 1:
                    medal = "🥇"
                elif rank == 2:
                    medal = "🥈"
                elif rank == 3:
                    medal = "🥉"
                rank_text = f'{medal} <b>Место в топе:</b> #{rank}\n'

        # Формируем сообщение
        text = f'{emoji} <b>Мешок {user_link}</b>\n'
        text += f'💰 <b>Баланс:</b> <code>{balance:,} сапфов</code>\n'
        if rank_text:
            text += rank_text

        # Информация о скрытости (только для агентов или владельца)
        if is_agent or target_user_id == user_id:
            if await is_bag_hidden(target_user_id):
                text += f'👁️ <b>Статус:</b> Скрыт\n'

        await msg.reply(
            text,
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"Check bag error: {e}", exc_info=True)
        await msg.reply("❌ Ошибка при проверке мешка!")


# МОЙ МЕШОК С КНОПКАМИ УПРАВЛЕНИЯ
@sapphires_router.message(F.text.regexp(r'^(?:[!./]:?)?мой мешок'))
async def my_bag_handler(msg: Message):
    """Показывает мешок пользователя с кнопками управления"""
    try:
        user_id = msg.from_user.id
        chat_id = msg.chat.id

        # Проверяем, отправлена ли команда в группе/чате
        is_group = chat_id != user_id

        # Если команда в чате, отправляем уведомление
        if is_group:
            bot_info = await bot.get_me()
            bot_link = bot_info.username

            # Пытаемся отправить сообщение в ЛС
            try:
                # Сначала пробуем отправить уведомление в группе
                await msg.answer(
                    f"👜 Загляните в <a href='https://t.me/{bot_link}'>личные сообщения</a>, мне кажется ваш мешок там....",
                    parse_mode='HTML'
                )

                # Теперь пробуем отправить сам мешок в ЛС
                await send_bag_to_user(user_id, msg.bot)

            except Exception as e:
                # Если бот не может написать в ЛС (юзер не начинал диалог)
                await msg.reply(
                    "❌ Чтобы увидеть свой мешок, напишите мне в личные сообщения!\n"
                    "Сначала начните диалог со мной, затем используйте команду /мой мешок",
                    parse_mode='HTML'
                )
                logger.error(f"Can't send to PM: {e}", exc_info=True)
            return

        # Если команда в ЛС - показываем мешок прямо здесь
        await send_bag_to_user(user_id, msg.bot, reply_to_message_id=msg.message_id)

    except Exception as e:
        logger.error(f"My bag error: {e}", exc_info=True)
        if not is_group:
            await msg.reply("❌ Ошибка при загрузке мешка!", parse_mode='HTML')


async def send_bag_to_user(user_id: int, bot_obj, reply_to_message_id: int = None):
    """Вспомогательная функция для отправки мешка пользователю"""
    try:
        # Получаем информацию о мешке
        bag_info = await get_bag_info(user_id)
        balance = bag_info['balance']
        level, emoji = get_bag_level(balance)
        user_link = await user_link_global(user_id)

        # Получаем место в топе (если мешок не скрыт)
        rank_text = ""
        if not await is_bag_hidden(user_id) and balance > 0:
            rank = await get_user_bag_rank(user_id)
            if rank > 0:
                medal = ""
                if rank == 1:
                    medal = "🥇"
                elif rank == 2:
                    medal = "🥈"
                elif rank == 3:
                    medal = "🥉"
                rank_text = f'{medal} <b>Место в топе:</b> #{rank}\n'

        # Проверяем статус видимости
        is_hidden = await is_bag_hidden(user_id)
        hidden_status = "🔒 Скрыт" if is_hidden else "👁️ Виден всем"

        # Формируем сообщение
        text = f'{emoji} <b>Ваш мешок {user_link}</b>\n'
        text += f'💰 <b>Баланс:</b> <code>{balance:,} сапфов</code>\n'
        if rank_text:
            text += rank_text
        text += f'👁️ <b>Статус видимости:</b> {hidden_status}\n'

        # Создаем кнопки
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])

        # Кнопка скрыть/показать мешок
        if is_hidden:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="👁️ Открыть мешок", callback_data="show_bag")
            ])
        else:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="🔒 Скрыть мешок", callback_data="hide_bag")
            ])

        # Дополнительные кнопки
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="📋 История операций", callback_data=f"bag_hist_{user_id}_1"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="bag_stats")
        ])

        # Отправляем сообщение
        await bot_obj.send_message(
            chat_id=user_id,
            text=text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard,
            reply_to_message_id=reply_to_message_id
        )

    except Exception as e:
        logger.error(f"Send bag error for user {user_id}: {e}", exc_info=True)
        raise


# ТОП МЕШКОВ (ОБЫЧНЫЙ - СКРЫТЫЕ НЕ ПОКАЗЫВАЮТСЯ)
@sapphires_router.message(F.text.regexp(r'^[!/.]топ мешков'))
async def top_bags_handler(msg: Message):
    """Показывает топ пользователей (без скрытых мешков)"""
    try:
        # Определяем страницу
        parts = msg.text.split()
        page = max(1, int(parts[2])) if len(parts) > 2 and parts[2].isdigit() else 1

        limit = 15
        offset = (page - 1) * limit

        # Получаем топ без скрытых мешков
        top_users, total = await get_top_bags(limit, offset, include_hidden=False)
        total_sapphires = await get_total_sapphires()
        total_pages = max(1, (total + limit - 1) // limit)

        if not top_users and page > 1:
            await msg.reply(f"❌ Страница {page} не существует")
            return

        if not top_users:
            await msg.reply("🏆 Пока никто не накопил сапфов!")
            return

        # Формируем текст
        text = f'🏆 <b>Топ богатейших мешков</b> (стр. {page}/{total_pages})\n\n'
        text += f'💰 <b>Всего сапфов:</b> {total_sapphires:,}\n'
        text += f'👥 <b>Пользователей:</b> {total}\n'

        for i, user in enumerate(top_users, start=offset + 1):
            user_link = await user_link_global(user['user_id'])
            medal = ['🥇', '🥈', '🥉'][i - 1] if i <= 3 else f'{i}.'

            text += f'{medal} {user_link}\n'
            text += f'   💰 <code>{user["balance"]:,} сапфов</code>\n\n'

        # Клавиатура пагинации
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        row = []

        if page > 1:
            row.append(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"top_bags_{page}_0"  # 0 = обычный топ
            ))

        if page < total_pages:
            row.append(InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"top_bags_{page + 1}_0"
            ))

        if row:
            keyboard.inline_keyboard.append(row)

        text += f'⏰ <i>Актуально на {get_formatted_time()}</i>'

        await msg.reply(
            text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Top bags error: {e}", exc_info=True)
        await msg.reply("❌ Ошибка при получении топа!")


# ТОП ВСЕХ МЕШКОВ (ТОЛЬКО ДЛЯ АГЕНТОВ)
@sapphires_router.message(F.text.regexp(r'^[!/.]топ всех мешков'))
async def top_all_bags_handler(msg: Message):
    """Показывает топ всех мешков включая скрытые (только для агентов)"""
    try:
        # Проверяем доступ
        if not await check_user_access(msg.from_user.id, 5):
            return

        # Определяем страницу
        parts = msg.text.split()
        page = max(1, int(parts[3])) if len(parts) > 3 and parts[3].isdigit() else 1

        limit = 15
        offset = (page - 1) * limit

        # Получаем топ ВСЕХ мешков включая скрытые
        top_users, total = await get_top_bags(limit, offset, include_hidden=True)
        total_sapphires = await get_total_sapphires()
        total_pages = max(1, (total + limit - 1) // limit)

        if not top_users and page > 1:
            await msg.reply(f"❌ Страница {page} не существует")
            return

        if not top_users:
            await msg.reply("🏆 Пока никто не накопил сапфов!")
            return

        # Формируем текст
        text = f'👁️ <b>Топ ВСЕХ мешков</b> (стр. {page}/{total_pages})\n'
        text += f'🔒 <i>Только для агентов - включены скрытые мешки</i>\n\n'
        text += f'💰 <b>Всего сапфов:</b> {total_sapphires:,}\n'
        text += f'👥 <b>Пользователей:</b> {total}\n\n'

        for i, user in enumerate(top_users, start=offset + 1):
            user_link = await user_link_global(user['user_id'])
            medal = ['🥇', '🥈', '🥉'][i - 1] if i <= 3 else f'{i}.'

            # Добавляем значок скрытого мешка
            hidden_marker = " 🔒" if user.get('is_hidden', False) else ""

            text += f'{medal} {user_link}{hidden_marker}\n'
            text += f'   💰 <code>{user["balance"]:,} сапфов</code>\n'

            # Добавляем информацию о скрытости
            if user.get('is_hidden', False):
                text += f'   👁️ <i>Мешок скрыт от обычных пользователей</i>\n'

            text += '\n'

        # Клавиатура пагинации
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        row = []

        if page > 1:
            row.append(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"top_all_bags_{page - 1}"
            ))

        if page < total_pages:
            row.append(InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"top_all_bags_{page + 1}"
            ))

        if row:
            keyboard.inline_keyboard.append(row)

        # Кнопка для переключения в обычный режим
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text="👤 Обычный топ",
                callback_data=f"top_bags_1_0"
            )
        ])

        text += f'⏰ <i>Актуально на {get_formatted_time()}</i>\n'
        text += f'👮 <i>Доступно: агенты ранг 2+</i>'

        await msg.reply(
            text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Top all bags error: {e}", exc_info=True)
        await msg.reply("❌ Ошибка при получении топа!")


# УПРОЩЕННАЯ КОМАНДА ПЕРЕВОДА С ОТВЕТОМ
@sapphires_router.message(F.text.regexp(r'^[!/.]перевести\s+\d+'))
async def transfer_sapphires_simple_handler(msg: Message):
    """Упрощенный перевод сапфов с ответом на сообщение"""
    try:
        user_id = msg.from_user.id

        # Определяем получателя из reply
        if not msg.reply_to_message:
            await msg.reply(
                "❌ <b>Укажите получателя!</b>\n\n"
                "📌 <b>Способы использования:</b>\n"
                "1. Ответьте на сообщение получателя:\n"
                "   <code>!перевести 500 Спасибо за помощь!</code>\n\n"
                "2. Укажите получателя явно:\n"
                "   <code>!перевести 500 @username Спасибо!</code>",
                parse_mode='HTML'
            )
            return

        to_user_id = msg.reply_to_message.from_user.id

        if to_user_id == user_id:
            await msg.reply("❌ Нельзя переводить самому себе!")
            return

        # Парсим команду
        parts = msg.text.split(maxsplit=2)

        if len(parts) < 2:
            await msg.reply("❌ Укажите сумму для перевода!")
            return

        amount = safe_int(parts[1])
        if amount < MIN_TRANSFER_AMOUNT:
            await msg.reply(f"❌ Минимальный перевод: {MIN_TRANSFER_AMOUNT} сапф")
            return

        if amount > MAX_TRANSFER_AMOUNT:
            await msg.reply(f"❌ Максимальный перевод: {MAX_TRANSFER_AMOUNT:,} сапфов")
            return

        comment = parts[2] if len(parts) > 2 else ""

        # Проверяем баланс
        from_balance = await get_user_bag(user_id)
        if from_balance < amount:
            await msg.reply(
                f"❌ Недостаточно сапфов!\n"
                f"Ваш баланс: <code>{from_balance:,}</code>\n"
                f"Требуется: <code>{amount:,}</code>"
            )
            return

        # Проверяем лимит получателя
        to_balance = await get_user_bag(to_user_id)
        if to_balance + amount > MAX_BALANCE:
            await msg.reply(f"❌ У получателя превышен лимит баланса!")
            return

        # Запрашиваем подтверждение
        to_link = await user_link_global(to_user_id)

        transfer_id = f"{user_id}_{to_user_id}_{amount}_{datetime.now().timestamp()}"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"transfer_confirm_{transfer_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"transfer_cancel_{transfer_id}"
                )
            ]
        ])

        response_text = (
            f'📤 <b>Подтверждение перевода</b>\n\n'
            f'👤 <b>Кому:</b> {to_link}\n'
            f'💰 <b>Сумма:</b> <code>{amount:,} сапфов</code>\n'
        )

        if comment and comment.strip():
            response_text += f'💬 <b>Комментарий:</b> {comment}\n'

        response_text += (
            f'\n<i>После перевода у вас останется: {from_balance - amount:,}</i>'
        )

        await msg.reply(
            response_text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )

        # Сохраняем данные
        pending_transfers[transfer_id] = {
            'from_user_id': user_id,
            'to_user_id': to_user_id,
            'amount': amount,
            'comment': comment,
            'timestamp': datetime.now()
        }

        # Автоочистка
        asyncio.create_task(cleanup_pending_transfer(transfer_id))

    except Exception as e:
        logger.error(f"Simple transfer error: {e}", exc_info=True)
        await msg.reply("❌ Ошибка при создании перевода!")


async def cleanup_pending_transfer(transfer_id: str, delay: int = 300):
    """Очищает старые ожидающие переводы"""
    await asyncio.sleep(delay)
    if transfer_id in pending_transfers:
        del pending_transfers[transfer_id]


# ИСТОРИЯ МЕШКА
@sapphires_router.message(F.text.regexp(r'^[!/.]история мешка'))
async def bag_history_handler(msg: Message):
    """Показывает историю операций мешка с красивым оформлением"""
    try:
        user_id = msg.from_user.id

        # Определяем целевого пользователя
        parts = msg.text.split()
        if len(parts) > 1:
            target_user_id = await resolve_target_user(msg, parts[1]) or user_id
        else:
            target_user_id = user_id

        # Проверяем права для просмотра чужой истории
        if target_user_id != user_id and not await check_user_access(user_id, 3):
            return

        # Определяем страницу
        page = 1
        for part in parts:
            if part.isdigit():
                page = max(1, int(part))
                break

        limit = 10
        history, total = await get_formatted_bag_history(
            target_user_id, limit, (page - 1) * limit
        )
        total_pages = max(1, (total + limit - 1) // limit)

        if not history and page > 1:
            await msg.reply(f"❌ Страница {page} не существует. Всего страниц: {total_pages}")
            return

        user_link = await user_link_global(target_user_id)
        bag_info = await get_bag_info(target_user_id)
        current_balance = bag_info['balance']

        # Формируем заголовок
        text = f'📋 <b>История мешка</b> {user_link}\n'
        text += f'💰 <b>Текущий баланс:</b> <code>{current_balance:,} сапфов</code>\n'
        text += f'📊 <b>Операций:</b> {total} (стр. {page}/{total_pages})\n\n'

        if not history:
            text += '📭 <i>История операций пуста</i>\n'
            text += '<i>Здесь будут отображаться все ваши операции с сапфами</i>'
        else:
            # Отображаем операции в новом формате
            for record in history:
                # Форматируем операцию с ссылками
                formatted_record = await format_operation_with_links(record)

                # Форматируем сумму
                amount_text = formatted_record.get('formatted_amount', '0')

                # Используем безопасный HTML
                display_name = escape(formatted_record.get('display_name', 'Операция'))
                text += f'{formatted_record.get("emoji", "📝")} <b>{display_name}</b>\n'
                text += f'{formatted_record.get("amount_prefix", "📝")} <b>Сумма:</b> <code>{amount_text} сапфов</code>\n'

                # Показываем детали операции с HTML-ссылками
                description = formatted_record.get('description', '')
                if description:
                    text += f'📝 <b>Описание:</b> {description}\n'

                # Показываем баланс до и после
                if 'balance_before' in formatted_record and 'balance_after' in formatted_record:
                    text += f'🏦 <b>Баланс:</b> {formatted_record["balance_before"]:,} → {formatted_record["balance_after"]:,}\n'

                # Комментарий с безопасным HTML (только если есть)
                comment = formatted_record.get('formatted_comment', '')
                if comment and comment.strip() and comment != 'Без комментария':
                    if len(comment) > 50:
                        comment = comment[:47] + '...'
                    safe_comment = escape(comment)
                    text += f'💬 <b>Комментарий:</b> {safe_comment}\n\n'
                else:
                    text += f'\n'

        # Клавиатура пагинации
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        row = []

        if page > 1:
            row.append(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"bag_hist_{target_user_id}_{page - 1}"
            ))

        if page < total_pages:
            row.append(InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"bag_hist_{target_user_id}_{page + 1}"
            ))

        if row:
            keyboard.inline_keyboard.append(row)

        # Добавляем кнопки фильтров если есть операции
        if history and total > 0:
            filters_row = [
                InlineKeyboardButton(text="📥 Пополнения", callback_data=f"filter_in_{target_user_id}_1"),
                InlineKeyboardButton(text="📤 Списания", callback_data=f"filter_out_{target_user_id}_1"),
                InlineKeyboardButton(text="🔄 Переводы", callback_data=f"filter_transfer_{target_user_id}_1")
            ]
            keyboard.inline_keyboard.append(filters_row)

        await msg.reply(text,
                        parse_mode='HTML',
                        disable_web_page_preview=True,
                        reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Bag history error: {e}", exc_info=True)
        await msg.reply("❌ Ошибка при получении истории!")


# УПРОЩЕННАЯ КОМАНДА НАКАЗАНИЯ С ОТВЕТОМ
@sapphires_router.message(F.text.regexp(r'^[!/.]наказать\s+\d+\s+\S*'))
async def punish_sapphires_simple_handler(msg: Message):
    """Упрощенное наказание с ответом на сообщение"""
    if not await check_user_access(msg.from_user.id, 5):
        return

    try:
        user_id = msg.from_user.id

        if not msg.reply_to_message:
            await msg.reply(
                "❌ <b>Укажите пострадавшего!</b>\n\n"
                "📌 <b>Способы использования:</b>\n"
                "1. Ответьте на сообщение виновника, укажите сумму и пострадавшего:\n"
                "   <code>!наказать 500 @пострадавший За оскорбление</code>\n\n"
                "2. Ответьте на сообщение пострадавшего, укажите сумму и виновника:\n"
                "   <code>!наказать 500 @виновник За порчу имущества</code>\n\n"
                "3. Полный формат:\n"
                "   <code>!наказать 500 @виновник @пострадавший Причина</code>",
                parse_mode='HTML'
            )
            return

        # Определяем виновника и пострадавшего
        parts = msg.text.split(maxsplit=3)

        if len(parts) < 2:
            await msg.reply("❌ Укажите сумму штрафа!")
            return

        amount = safe_int(parts[1])
        if amount <= 0:
            await msg.reply("❌ Сумма должна быть больше 0!")
            return

        if amount > MAX_TRANSFER_AMOUNT:
            await msg.reply(f"❌ Максимальная сумма: {MAX_TRANSFER_AMOUNT:,} сапфов")
            return

        # Определяем кто есть кто
        from_user_id = None
        to_user_id = None
        reason = ""

        # Если указан только получатель в тексте
        if len(parts) >= 3:
            if parts[2].startswith('@') or parts[2].isdigit():
                # parts[2] - это второй пользователь
                second_user = await resolve_target_user(msg, parts[2])
                if msg.reply_to_message:
                    # Reply - это первый пользователь
                    first_user = msg.reply_to_message.from_user.id

                    # Определяем кто виновник, а кто пострадавший
                    # Reply = виновник, Упомянутый = пострадавший
                    from_user_id = first_user
                    to_user_id = second_user

                    if len(parts) > 3:
                        reason = parts[3]
            else:
                # parts[2] - это причина, оба пользователя из reply
                from_user_id = msg.reply_to_message.from_user.id
                to_user_id = None  # Нужен второй пользователь
                reason = parts[2]
        else:
            # Только сумма, нужен второй пользователь
            from_user_id = msg.reply_to_message.from_user.id
            to_user_id = None

        # Если не хватает данных
        if not from_user_id or not to_user_id:
            await msg.reply(
                "❌ <b>Укажите обоих участников!</b>\n\n"
                "Примеры:\n"
                "• Ответьте на сообщение виновника: <code>!наказать 500 @пострадавший Причина</code>\n"
                "• Ответьте на сообщение пострадавшего: <code>!наказать 500 @виновник Причина</code>\n"
                "• Укажите обоих: <code>!наказать 500 @виновник @пострадавший Причина</code>",
                parse_mode='HTML'
            )
            return

        # Проверяем, что это разные пользователи
        if from_user_id == to_user_id:
            await msg.reply("❌ Нельзя наказать самого себя!")
            return

        # Проверяем, что агент не наказывает сам себя
        if from_user_id == user_id:
            await msg.reply("❌ Вы не можете наказать сами себя!")
            return

        # Проверяем баланс виновника
        from_balance = await get_user_bag(from_user_id)
        if from_balance < amount:
            from_user_link = await user_link_global(from_user_id)
            await msg.reply(
                f"❌ Недостаточно сапфов у виновника!\n"
                f"У {from_user_link}: <code>{from_balance:,}</code> сапфов\n"
                f"Требуется: <code>{amount:,}</code> сапфов"
            )
            return

        # Проверяем лимит пострадавшего
        to_balance = await get_user_bag(to_user_id)
        if to_balance + amount > MAX_BALANCE:
            await msg.reply(f"❌ У пострадавшего превышен лимит баланса!")
            return

        # Запрашиваем подтверждение
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Применить наказание",
                    callback_data=f"punish_confirm_{from_user_id}_{to_user_id}_{amount}"
                ),
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="punish_cancel"
                )
            ]
        ])

        from_user_link = await user_link_global(from_user_id)
        to_user_link = await user_link_global(to_user_id)
        agent_link = await user_link_global(user_id)

        response_text = (
            f'⚖️ <b>Подтверждение наказания</b>\n\n'
            f'👤 <b>Виновник:</b> {from_user_link}\n'
            f'👤 <b>Пострадавший:</b> {to_user_link}\n'
            f'💰 <b>Сумма штрафа:</b> <code>{amount:,} сапфов</code>\n'
            f'👮 <b>Судья:</b> {agent_link}\n'
        )

        if reason and reason.strip():
            response_text += f'📝 <b>Причина:</b> {reason}\n'

        response_text += (
            f'\n<i>После наказания:</i>\n'
            f'• {from_user_link}: <code>{from_balance - amount:,}</code>\n'
            f'• {to_user_link}: <code>{to_balance + amount:,}</code>\n\n'
            f'<b>Вы подтверждаете наказание?</b>'
        )

        await msg.reply(
            response_text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )

        # Сохраняем причину в отдельном хранилище
        punishment_data[(from_user_id, to_user_id, amount)] = reason

    except Exception as e:
        logger.error(f"Simple punish error: {e}", exc_info=True)
        await msg.reply("❌ Ошибка при создании наказания!")


# КОМАНДА СТАТИСТИКИ
@sapphires_router.message(F.text.regexp(r'^[!/.]статистика сапфов'))
async def sapphires_stats_handler(msg: Message):
    """Показывает статистику системы"""
    if not await check_user_access(msg.from_user.id, 5):
        return

    try:
        total_sapphires = await get_total_sapphires()

        # Получаем статистику по скрытым/не скрытым мешкам
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Общее количество пользователей с сапфами
            total_users = await conn.fetchval(
                'SELECT COUNT(*) FROM sapphire_bag WHERE balance > 0'
            ) or 0

            # Количество скрытых мешков
            hidden_bags = await conn.fetchval(
                'SELECT COUNT(*) FROM sapphire_bag WHERE balance > 0 AND is_hidden = TRUE'
            ) or 0

            # Количество открытых мешков
            visible_bags = total_users - hidden_bags

        top_users, user_count = await get_top_bags(3, 0, include_hidden=False)

        stats_text = f'📊 <b>Статистика сапфов</b>\n\n'
        stats_text += f'💰 <b>Всего сапфов:</b> {total_sapphires:,}\n'
        stats_text += f'👥 <b>Всего пользователей с сапфами:</b> {total_users}\n'
        stats_text += f'👁️ <b>Открытых мешков:</b> {visible_bags}\n'
        stats_text += f'🔒 <b>Скрытых мешков:</b> {hidden_bags}\n\n'

        if top_users:
            stats_text += f'🏆 <b>Топ-3 богатейших (открытые):</b>\n'
            for i, user in enumerate(top_users, 1):
                user_link = await user_link_global(user['user_id'])
                medal = ['🥇', '🥈', '🥉'][i - 1]
                stats_text += f'{medal} {user_link} — {user["balance"]:,}\n'

        stats_text += f'\n⏰ <i>Актуально на {get_formatted_time()}</i>'

        await msg.reply(stats_text, parse_mode='HTML', disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Stats error: {e}", exc_info=True)
        await msg.reply("❌ Ошибка при получении статистики!")


# УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК САПФОВ
@sapphires_router.message(F.text.regexp(r'^[!/.]сапфы\s+\d+'))
async def sapphires_universal_handler(msg: Message):
    """
    Универсальная команда для работы с сапфами.
    Форматы:
    1. !сапфы 500 @user Причина
    2. !сапфы 500 (в ответ на сообщение пользователя)
    3. !сапфы 500 Причина (в ответ на сообщение)
    """
    if not await check_user_access(msg.from_user.id, 5):
        return

    try:
        # Определяем получателя из reply
        replied_user_id = None
        if msg.reply_to_message:
            replied_user_id = msg.reply_to_message.from_user.id

        # Парсим команду
        parts = msg.text.split(maxsplit=2)
        if len(parts) < 2:
            await msg.reply("❌ Укажите сумму!")
            return

        amount = safe_int(parts[1])
        if amount <= 0:
            await msg.reply("❌ Укажите положительную сумму!")
            return

        # Определяем получателя
        target_user_id = None
        comment = ""

        if replied_user_id:
            # Есть reply - используем этого пользователя
            target_user_id = replied_user_id
            if len(parts) > 2:
                comment = parts[2]
        elif len(parts) > 2:
            # Нет reply, но есть третий аргумент
            # Проверяем, является ли это упоминанием пользователя
            third_arg = parts[2]
            if third_arg.startswith('@') or third_arg.isdigit():
                target_user_id = await resolve_target_user(msg, third_arg)
            else:
                # Третий аргумент - комментарий, но нет пользователя
                await msg.reply("❌ Укажите получателя или ответьте на сообщение!")
                return
        else:
            # Нет reply и нет третьего аргумента
            await msg.reply("❌ Укажите получателя или ответьте на сообщение!")
            return

        if not target_user_id or not await user_exists_in_db(target_user_id):
            await msg.reply("❌ Пользователь не найден в системе!")
            return

        # Определяем тип операции по тексту команды
        command_text = parts[0].lower()

        if 'пополнить' in command_text or 'добавить' in command_text or 'начислить' in command_text:
            # Пополнение
            success, new_balance, message = await add_to_bag(
                target_user_id, amount, msg.from_user.id,
                get_current_datetime(), comment
            )

            if success:
                target_link = await user_link_global(target_user_id)
                operator_link = await user_link_global(msg.from_user.id)

                response_text = (
                    f'➕ <b>Пополнение сапфирок {target_link}</b>\n\n'
                    f'💰 <b>Добавлено:</b> <code>+{amount:,} сапфов ({new_balance:,})</code>\n'
                    f'👮 <b>Оператор:</b> {operator_link}\n'
                )

                if comment:
                    response_text += f'💬 <b>Комментарий:</b> {comment}\n'

                await msg.reply(
                    response_text,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            else:
                await msg.reply(f'❌ {message}', parse_mode='HTML')

        elif 'отнять' in command_text or 'списать' in command_text or 'убрать' in command_text:
            # Списание
            current_balance = await get_user_bag(target_user_id)
            if current_balance < amount:
                await msg.reply(f"❌ Недостаточно сапфов! Доступно: {current_balance:,}")
                return

            success, new_balance, message = await remove_from_bag(
                target_user_id, amount, msg.from_user.id,
                get_current_datetime(), comment
            )

            if success:
                target_link = await user_link_global(target_user_id)
                operator_link = await user_link_global(msg.from_user.id)

                response_text = (
                    f'➖ <b>Списание сапфиров у {target_link}</b>\n\n'
                    f'💰 <b>Списано:</b> <code>-{amount:,} сапфов ({new_balance:,})</code>\n'
                    f'👮 <b>Оператор:</b> {operator_link}\n'
                )

                if comment:
                    response_text += f'💬 <b>Комментарий:</b> {comment}\n'

                await msg.reply(
                    response_text,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            else:
                await msg.reply(f'❌ {message}', parse_mode='HTML')

        else:
            # По умолчанию - пополнение
            success, new_balance, message = await add_to_bag(
                target_user_id, amount, msg.from_user.id,
                get_current_datetime(), comment
            )

            if success:
                target_link = await user_link_global(target_user_id)
                operator_link = await user_link_global(msg.from_user.id)

                response_text = (
                    f'➕ <b>Операция с сапфирами {target_link}</b>\n\n'
                    f'💰 <b>Добавлено:</b> <code>+{amount:,} сапфов ({new_balance:,})</code>\n'
                    f'👮 <b>Оператор:</b> {operator_link}\n'
                )

                if comment:
                    response_text += f'💬 <b>Комментарий:</b> {comment}\n'

                await msg.reply(
                    response_text,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            else:
                await msg.reply(f'❌ {message}', parse_mode='HTML')

    except Exception as e:
        logger.error(f"Universal sapphires error: {e}", exc_info=True)
        await msg.reply("❌ Ошибка при выполнении операции!")


# АВТОМАТИЧЕСКОЕ УВЕДОМЛЕНИЕ ПРИ ПОПОЛНЕНИИ
async def send_sapphire_notification(bot, user_id: int, amount: int, operation_type: str,
                                     from_user_name: str = "", comment: str = ""):
    """Отправляет уведомление пользователю о операции с сапфами"""
    try:
        current_balance = await get_user_bag(user_id)

        # Определяем текст в зависимости от типа операции
        if operation_type == 'add':
            title = "➕ Пополнение сапфов"
            description = f"Администратор {from_user_name} пополнил ваш баланс"
        elif operation_type == 'purchase':
            title = "🧾 Покупка сапфов"
            description = f"Вы приобрели сапфы через {from_user_name}"
        elif operation_type == 'reward':
            title = "🎁 Награда"
            description = f"Вы получили награду от {from_user_name}"
        elif operation_type == 'user_transfer_in':
            title = "📥 Перевод получен"
            description = f"Вы получили перевод от {from_user_name}"
        elif operation_type == 'admin_transfer_in':
            title = "⚖️ Компенсация"
            description = f"Вы получили компенсацию от {from_user_name}"
        else:
            title = "💎 Операция с сапфами"
            description = f"Произведена операция с вашими сапфами"

        # Формируем сообщение
        message = f'{title}\n\n'
        message += f'{description}\n'
        message += f'💰 <b>Сумма:</b> +{amount:,} сапфов\n'
        message += f'🏦 <b>Новый баланс:</b> {current_balance:,}\n'

        # Добавляем комментарий только если он есть
        if comment and comment.strip():
            safe_comment = escape(comment)
            message += f'📝 <b>Комментарий:</b> {safe_comment}\n'

        await bot.send_message(
            user_id,
            message,
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"Failed to send sapphire notification: {e}")


# ОБРАБОТЧИК СКРЫТИЯ/ПОКАЗА МЕШКА
@sapphires_router.callback_query(F.data.in_(["hide_bag", "show_bag"]))
@rate_limit_with_cleanup(limit=1)
async def handle_bag_visibility_toggle(callback: CallbackQuery):
    """Обрабатывает переключение видимости мешка (только в ЛС)"""
    try:
        user_id = callback.from_user.id
        action = callback.data

        if action == "hide_bag":
            success = await toggle_bag_visibility(user_id, True)
            new_text = "🔒 Мешок скрыт"
            button_text = "👁️ Открыть мешок"
            callback_data = "show_bag"
            status_text = "🔒 Скрыт"
        else:
            success = await toggle_bag_visibility(user_id, False)
            new_text = "👁️ Мешок виден всем"
            button_text = "🔒 Скрыть мешок"
            callback_data = "hide_bag"
            status_text = "👁️ Виден всем"

        if success:
            # Получаем обновленную информацию о мешке
            bag_info = await get_bag_info(user_id)
            balance = bag_info['balance']
            level, emoji = get_bag_level(balance)
            user_link = await user_link_global(user_id)

            # Получаем место в топе (если мешок не скрыт)
            rank_text = ""
            if action == "show_bag":  # Если только что открыли мешок
                rank = await get_user_bag_rank(user_id)
                if rank > 0:
                    medal = ""
                    if rank == 1:
                        medal = "🥇"
                    elif rank == 2:
                        medal = "🥈"
                    elif rank == 3:
                        medal = "🥉"
                    rank_text = f'{medal} <b>Место в топе:</b> #{rank}\n'

            # Обновляем текст сообщения
            text = f'{emoji} <b>Ваш мешок {user_link}</b>\n'
            text += f'💰 <b>Баланс:</b> <code>{balance:,} сапфов</code>\n'
            if rank_text:
                text += rank_text
            text += f'👁️ <b>Статус видимости:</b> {status_text}\n'

            # Создаем обновленные кнопки
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])

            # Кнопка скрыть/показать мешок
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text=button_text, callback_data=callback_data)
            ])

            # Дополнительные кнопки
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="📋 История операций", callback_data=f"bag_hist_{user_id}_1"),
                InlineKeyboardButton(text="📤 Переводы", callback_data=f"transfers_1")
            ])

            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="🏆 Топ мешков", callback_data="top_bags_1_0"),
                InlineKeyboardButton(text="📊 Статистика", callback_data="bag_stats")
            ])

            # Обновляем существующее сообщение
            await callback.message.edit_text(
                text,
                parse_mode='HTML',
                disable_web_page_preview=True,
                reply_markup=keyboard
            )
            await callback.answer(new_text)
        else:
            await callback.answer("❌ Ошибка при изменении настроек", show_alert=True)

    except Exception as e:
        logger.error(f"Toggle bag visibility error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при изменении настроек", show_alert=True)


# ОБРАБОТЧИК ПАГИНАЦИИ ИСТОРИИ МЕШКА
@sapphires_router.callback_query(F.data.startswith('bag_hist_'))
@rate_limit_with_cleanup(limit=1)
async def handle_bag_history_pagination(callback: CallbackQuery):
    """Пагинация истории мешка (только в ЛС)"""
    try:
        parts = callback.data.split('_')
        target_user_id = int(parts[2])
        page = int(parts[3])

        # Проверяем права для просмотра чужой истории
        if target_user_id != callback.from_user.id and not await check_user_access(callback.from_user.id, 2):
            await callback.answer("❌ Нет прав для просмотра чужой истории!", show_alert=True)
            return

        limit = 10
        history, total = await get_formatted_bag_history(
            target_user_id, limit, (page - 1) * limit
        )
        total_pages = max(1, (total + limit - 1) // limit)

        if not history and page > 1:
            await callback.answer("❌ Страница не существует!", show_alert=True)
            return

        user_link = await user_link_global(target_user_id)
        bag_info = await get_bag_info(target_user_id)
        current_balance = bag_info['balance']

        # Формируем заголовок
        text = f'📋 <b>История мешка</b> {user_link}\n'
        text += f'💰 <b>Текущий баланс:</b> <code>{current_balance:,} сапфов</code>\n'
        text += f'📊 <b>Операций:</b> {total} (стр. {page}/{total_pages})\n\n'

        if not history:
            text += '📭 <i>История операций пуста</i>\n'
            text += '<i>Здесь будут отображаться все ваши операции с сапфами</i>'
        else:
            # Отображаем операции в новом формате
            for record in history:
                # Форматируем операцию с ссылками
                formatted_record = await format_operation_with_links(record)

                # Форматируем сумму
                amount_text = formatted_record.get('formatted_amount', '0')

                # Используем безопасный HTML
                display_name = escape(formatted_record.get('display_name', 'Операция'))
                text += f'{formatted_record.get("emoji", "📝")} <b>{display_name}</b>\n'
                text += f'{formatted_record.get("amount_prefix", "📝")} <b>Сумма:</b> <code>{amount_text} сапфов</code>\n'

                # Показываем детали операции с HTML-ссылками
                description = formatted_record.get('description', '')
                if description:
                    text += f'📝 <b>Описание:</b> {description}\n'

                # Показываем баланс до и после
                if 'balance_before' in formatted_record and 'balance_after' in formatted_record:
                    text += f'🏦 <b>Баланс:</b> {formatted_record["balance_before"]:,} → {formatted_record["balance_after"]:,}\n'

                # Комментарий с безопасным HTML (только если есть)
                comment = formatted_record.get('formatted_comment', '')
                if comment and comment.strip() and comment != 'Без комментария':
                    if len(comment) > 50:
                        comment = comment[:47] + '...'
                    safe_comment = escape(comment)
                    text += f'💬 <b>Комментарий:</b> {safe_comment}\n\n'
                else:
                    text += '\n'

        # Клавиатура пагинации
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        row = []

        if page > 1:
            row.append(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"bag_hist_{target_user_id}_{page - 1}"
            ))

        if page < total_pages:
            row.append(InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"bag_hist_{target_user_id}_{page + 1}"
            ))

        if row:
            keyboard.inline_keyboard.append(row)

        # Добавляем кнопки фильтров если есть операции
        if history and total > 0:
            filters_row = [
                InlineKeyboardButton(text="📥 Пополнения", callback_data=f"filter_in_{target_user_id}_1"),
                InlineKeyboardButton(text="📤 Списания", callback_data=f"filter_out_{target_user_id}_1"),
                InlineKeyboardButton(text="🔄 Переводы", callback_data=f"filter_transfer_{target_user_id}_1")
            ]
            keyboard.inline_keyboard.append(filters_row)

        # Обновляем сообщение
        await callback.message.edit_text(
            text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Bag history pagination error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при обновлении истории!", show_alert=True)


# ОБРАБОТЧИК ФИЛЬТРОВ ИСТОРИИ
@sapphires_router.callback_query(F.data.startswith('filter_'))
@rate_limit_with_cleanup(limit=1)
async def handle_history_filters(callback: CallbackQuery):
    """Обработчик фильтров истории (только в ЛС)"""
    try:
        data_parts = callback.data.split('_')
        filter_type = data_parts[1]  # in, out, transfer
        target_user_id = int(data_parts[2])
        page = int(data_parts[3]) if len(data_parts) > 3 else 1

        # Проверяем права для просмотра чужой истории
        if target_user_id != callback.from_user.id and not await check_user_access(callback.from_user.id, 2):
            await callback.answer("❌ Нет прав для просмотра чужой истории!", show_alert=True)
            return

        filter_names = {
            'in': '📥 Пополнения',
            'out': '📤 Списания',
            'transfer': '🔄 Переводы'
        }

        filter_name = filter_names.get(filter_type, 'Фильтр')

        # Получаем всю историю
        limit = 10
        all_history, total = await get_formatted_bag_history(target_user_id, 1000, 0)

        # Фильтруем по типу операции
        filtered_history = []
        for record in all_history:
            if filter_type == 'in' and record.get('amount', 0) > 0:
                filtered_history.append(record)
            elif filter_type == 'out' and record.get('amount', 0) < 0:
                filtered_history.append(record)
            elif filter_type == 'transfer' and 'transfer' in record.get('operation_type', ''):
                filtered_history.append(record)

        # Пагинация отфильтрованных результатов
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        page_history = filtered_history[start_idx:end_idx]

        total_filtered = len(filtered_history)
        total_pages = max(1, (total_filtered + limit - 1) // limit)

        user_link = await user_link_global(target_user_id)
        bag_info = await get_bag_info(target_user_id)
        current_balance = bag_info['balance']

        # Формируем текст
        text = f'📋 <b>История мешка</b> {user_link}\n'
        text += f'💰 <b>Текущий баланс:</b> <code>{current_balance:,} сапфов</code>\n'
        text += f'🔍 <b>Фильтр:</b> {filter_name}\n'
        text += f'📊 <b>Найдено операций:</b> {total_filtered} (стр. {page}/{total_pages})\n\n'

        if not page_history:
            text += f'📭 <i>Нет операций по фильтру "{filter_name}"</i>\n'
        else:
            for record in page_history:
                # Форматируем операцию с ссылками
                formatted_record = await format_operation_with_links(record)

                amount_text = formatted_record.get('formatted_amount', '0')

                # Используем безопасный HTML
                display_name = escape(formatted_record.get('display_name', 'Операция'))
                text += f'{formatted_record.get("emoji", "📝")} <b>{display_name}</b>\n'
                text += f'{formatted_record.get("amount_prefix", "📝")} <b>Сумма:</b> <code>{amount_text} сапфов</code>\n'

                # Показываем детали операции с HTML-ссылками
                description = formatted_record.get('description', '')
                if description:
                    text += f'📝 <b>Описание:</b> {description}\n'

                if 'balance_before' in formatted_record and 'balance_after' in formatted_record:
                    text += f'🏦 <b>Баланс:</b> {formatted_record["balance_before"]:,} → {formatted_record["balance_after"]:,}\n'

                # Комментарий с безопасным HTML (только если есть)
                comment = formatted_record.get('formatted_comment', '')
                if comment and comment.strip() and comment != 'Без комментария':
                    if len(comment) > 50:
                        comment = comment[:47] + '...'
                    safe_comment = escape(comment)
                    text += f'💬 <b>Комментарий:</b> {safe_comment}\n\n'
                else:
                    text += '\n'

        # Клавиатура пагинации
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        row = []

        if page > 1:
            row.append(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"filter_{filter_type}_{target_user_id}_{page - 1}"
            ))

        if page < total_pages:
            row.append(InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"filter_{filter_type}_{target_user_id}_{page + 1}"
            ))

        if row:
            keyboard.inline_keyboard.append(row)

        # Кнопки для смены фильтров
        filters_row = []
        for f_type, f_name in filter_names.items():
            is_active = " ✅" if f_type == filter_type else ""
            filters_row.append(InlineKeyboardButton(
                text=f"{f_name}{is_active}",
                callback_data=f"filter_{f_type}_{target_user_id}_1"
            ))

        if filters_row:
            keyboard.inline_keyboard.append(filters_row)

        # Кнопка "Все операции"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text="📋 Все операции",
                callback_data=f"bag_hist_{target_user_id}_1"
            )
        ])

        # Обновляем сообщение
        await callback.message.edit_text(
            text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
        await callback.answer(f"Применён фильтр: {filter_name}")

    except Exception as e:
        logger.error(f"Filter error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка применения фильтра", show_alert=True)


# ОБРАБОТЧИК ПАГИНАЦИИ ОПЕРАЦИЙ
@sapphires_router.callback_query(F.data.startswith('ops_'))
@rate_limit_with_cleanup(limit=1)
async def handle_operations_pagination(callback: CallbackQuery):
    """Пагинация операций (только в ЛС)"""
    try:
        parts = callback.data.split('_')
        target_user_id = int(parts[1])
        page = int(parts[2])

        # Проверяем доступ
        if target_user_id != callback.from_user.id and not await check_user_access(callback.from_user.id, 2):
            await callback.answer("❌ Нет доступа!", show_alert=True)
            return

        limit = 5
        history, total = await get_formatted_bag_history(target_user_id, limit, (page - 1) * limit)

        if not history and page > 1:
            await callback.answer("❌ Страница не существует!", show_alert=True)
            return

        user_link = await user_link_global(target_user_id)
        bag_info = await get_bag_info(target_user_id)
        current_balance = bag_info['balance']
        total_pages = max(1, (total + limit - 1) // limit)

        text = f'📋 <b>Последние операции</b> {user_link}\n'
        text += f'💰 <b>Баланс:</b> <code>{current_balance:,} сапфов</code>\n\n'

        for record in history:
            # Форматируем операцию с ссылками
            formatted_record = await format_operation_with_links(record)

            amount_text = formatted_record.get('formatted_amount', '0')
            emoji = formatted_record.get('emoji', '📝')

            # Сокращенное описание с HTML-ссылками
            description = formatted_record.get('description', 'Операция')
            if len(description) > 30:
                description = description[:27] + '...'

            text += f'{emoji} <code>{amount_text}</code> - {description}\n'

            # Комментарий если есть с безопасным HTML (только если есть)
            comment = formatted_record.get('formatted_comment', '')
            if comment and comment.strip() and comment != 'Без комментария' and len(comment) > 0:
                if len(comment) > 25:
                    comment = comment[:22] + '...'
                safe_comment = escape(comment)
                text += f'   <i>{safe_comment}</i>\n'

            text += '\n'

        text += f'📊 <i>Всего операций: {total} (стр. {page}/{total_pages})</i>'

        # Добавляем кнопки если больше 1 страницы
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])

        if total_pages > 1:
            row = []

            if page > 1:
                row.append(InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"ops_{target_user_id}_{page - 1}"
                ))

            if page < total_pages:
                row.append(InlineKeyboardButton(
                    text="Вперед ➡️",
                    callback_data=f"ops_{target_user_id}_{page + 1}"
                ))

            if row:
                keyboard.inline_keyboard.append(row)

        # Обновляем сообщение
        await callback.message.edit_text(
            text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Operations pagination error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при обновлении операций!", show_alert=True)


# ОБРАБОТЧИК СТАТИСТИКИ МЕШКА
@sapphires_router.callback_query(F.data == "bag_stats")
@rate_limit_with_cleanup(limit=1)
async def handle_bag_stats(callback: CallbackQuery):
    """Показывает статистику мешка (только в ЛС)"""
    try:
        user_id = callback.from_user.id

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Общая статистика
            stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_ops,
                    SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as total_in,
                    SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as total_out,
                    MIN(date) as first_operation,
                    MAX(date) as last_operation
                FROM sapphire_history 
                WHERE user_id = $1
            ''', user_id)

            # Самые частые операции
            frequent_ops = await conn.fetch('''
                SELECT operation_type, COUNT(*) as count
                FROM sapphire_history 
                WHERE user_id = $1
                GROUP BY operation_type 
                ORDER BY count DESC 
                LIMIT 5
            ''', user_id)

        bag_info = await get_bag_info(user_id)
        user_link = await user_link_global(user_id)

        # Получаем место в топе (если мешок не скрыт)
        rank_text = ""
        if not await is_bag_hidden(user_id) and bag_info['balance'] > 0:
            rank = await get_user_bag_rank(user_id)
            if rank > 0:
                medal = ""
                if rank == 1:
                    medal = "🥇"
                elif rank == 2:
                    medal = "🥈"
                elif rank == 3:
                    medal = "🥉"
                rank_text = f'{medal} <b>Место в топе:</b> #{rank}\n'

        text = f'📊 <b>Статистика мешка</b> {user_link}\n\n'
        text += f'💰 <b>Текущий баланс:</b> <code>{bag_info["balance"]:,} сапфов</code>\n'
        if rank_text:
            text += rank_text
        text += f'📅 <b>Всего операций:</b> {stats["total_ops"] or 0}\n'

        if stats["total_in"]:
            text += f'📥 <b>Всего получено:</b> {stats["total_in"]:,} сапфов\n'
        if stats["total_out"]:
            text += f'📤 <b>Всего отправлено:</b> {stats["total_out"]:,} сапфов\n'

        if stats["first_operation"]:
            text += f'📅 <b>Первая операция:</b> {stats["first_operation"].strftime("%d.%m.%Y")}\n'

        text += f'📊 <b>Операций в истории:</b> {bag_info.get("operations_count", 0)}\n\n'

        if frequent_ops:
            text += f'📈 <b>Самые частые операции:</b>\n'
            for op in frequent_ops:
                op_info = OPERATION_TYPES.get(op['operation_type'], {'emoji': '📝', 'name': 'Операция'})
                text += f'{op_info["emoji"]} {op_info["name"]}: {op["count"]} раз\n'

        await callback.message.answer(
            text,
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Bag stats error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при получении статистики", show_alert=True)


# ================= ОБРАБОТЧИКИ ДЛЯ ГРУПП/ЧАТОВ (с проверкой reply_to_message) =================

# ОБРАБОТЧИК ПАГИНАЦИИ ТОПА
@sapphires_router.callback_query(F.data.startswith('top_bags_'))
@rate_limit_with_cleanup(limit=1)
async def handle_top_pagination(callback: CallbackQuery):
    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return
    """Пагинация топа"""
    try:
        parts = callback.data.split('_')
        page = safe_int(parts[2], 1)
        mode = safe_int(parts[3], 0)  # 0 = обычный, 1 = все мешки

        limit = 15
        offset = (page - 1) * limit

        if mode == 0:
            # Обычный топ (без скрытых)
            top_users, total = await get_top_bags(limit, offset, include_hidden=False)
            title = "Топ богатейших мешков"
            show_all_button = True
        else:
            # Проверяем права для просмотра всех мешков
            if not await check_user_access(callback.from_user.id, 2):
                await callback.answer("❌ Нет доступа к просмотру всех мешков!", show_alert=True)
                return

            # Все мешки (включая скрытые)
            top_users, total = await get_top_bags(limit, offset, include_hidden=True)
            title = "Топ ВСЕХ мешков"
            show_all_button = False

        total_sapphires = await get_total_sapphires()
        total_pages = max(1, (total + limit - 1) // limit)

        if not top_users and page > 1:
            await callback.answer("❌ Страница не существует!", show_alert=True)
            return

        # Формируем текст
        if mode == 0:
            text = f'🏆 <b>{title}</b> (стр. {page}/{total_pages})\n\n'
            text += f'💰 <b>Всего сапфов:</b> {total_sapphires:,}\n'
            text += f'👥 <b>Пользователей:</b> {total}\n'
            text += f'👁️ <b>Показаны только открытые мешки</b>\n\n'
        else:
            text = f'👁️ <b>{title}</b> (стр. {page}/{total_pages})\n'
            text += f'🔒 <i>Только для агентов - включены скрытые мешки</i>\n\n'
            text += f'💰 <b>Всего сапфов:</b> {total_sapphires:,}\n'
            text += f'👥 <b>Пользователей:</b> {total}\n\n'

        for i, user in enumerate(top_users, start=offset + 1):
            user_link = await user_link_global(user['user_id'])
            medal = ['🥇', '🥈', '🥉'][i - 1] if i <= 3 else f'{i}.'

            # Добавляем значок скрытого мешка в режиме "все мешки"
            hidden_marker = " 🔒" if mode == 1 and user.get('is_hidden', False) else ""

            text += f'{medal} {user_link}{hidden_marker}\n'
            text += f'   💰 <code>{user["balance"]:,} сапфов</code>\n'

            # Добавляем информацию о скрытости в режиме "все мешки"
            if mode == 1 and user.get('is_hidden', False):
                text += f'   👁️ <i>Мешок скрыт от обычных пользователей</i>\n'

            text += '\n'

        # Клавиатура пагинации
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        row = []

        if page > 1:
            row.append(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"top_bags_{page - 1}_{mode}"
            ))

        if page < total_pages:
            row.append(InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"top_bags_{page + 1}_{mode}"
            ))

        if row:
            keyboard.inline_keyboard.append(row)

        # Добавляем кнопку для переключения режима
        if mode == 0 and await check_user_access(callback.from_user.id, 2):
            # В обычном режиме показываем кнопку "Показать все"
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text="👁️ Показать все мешки",
                    callback_data="show_all_bags_1"
                )
            ])
        elif mode == 1:
            # В режиме "все мешки" показываем кнопку "Обычный топ"
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text="👤 Обычный топ",
                    callback_data=f"top_bags_1_0"
                )
            ])

        text += f'⏰ <i>Актуально на {get_formatted_time()}</i>'

        # Обновляем сообщение
        await callback.message.edit_text(
            text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Top pagination error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при обновлении топа!", show_alert=True)


# ОБРАБОТЧИК ПОКАЗА ВСЕХ МЕШКОВ
@sapphires_router.callback_query(F.data.startswith('show_all_bags_'))
@rate_limit_with_cleanup(limit=1)
async def handle_show_all_bags(callback: CallbackQuery):
    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return
    """Показывает топ всех мешков для агентов"""
    try:
        # Проверяем права
        if not await check_user_access(callback.from_user.id, 2):
            return

        page = safe_int(callback.data.split('_')[3], 1)

        limit = 15
        offset = (page - 1) * limit

        # Получаем топ ВСЕХ мешков включая скрытые
        top_users, total = await get_top_bags(limit, offset, include_hidden=True)
        total_sapphires = await get_total_sapphires()
        total_pages = max(1, (total + limit - 1) // limit)

        if not top_users and page > 1:
            await callback.answer("❌ Страница не существует!", show_alert=True)
            return

        # Формируем текст
        text = f'👁️ <b>Топ ВСЕХ мешков</b> (стр. {page}/{total_pages})\n'
        text += f'🔒 <i>Только для агентов - включены скрытые мешки</i>\n\n'
        text += f'💰 <b>Всего сапфов:</b> {total_sapphires:,}\n'
        text += f'👥 <b>Пользователей:</b> {total}\n\n'

        for i, user in enumerate(top_users, start=offset + 1):
            user_link = await user_link_global(user['user_id'])
            medal = ['🥇', '🥈', '🥉'][i - 1] if i <= 3 else f'{i}.'

            # Добавляем значок скрытого мешка
            hidden_marker = " 🔒" if user.get('is_hidden', False) else ""

            text += f'{medal} {user_link}{hidden_marker}\n'
            text += f'   💰 <code>{user["balance"]:,} сапфов</code>\n'

            # Добавляем информацию о скрытости
            if user.get('is_hidden', False):
                text += f'   👁️ <i>Мешок скрыт от обычных пользователей</i>\n'

            text += '\n'

        # Клавиатура пагинации
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        row = []

        if page > 1:
            row.append(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"show_all_bags_{page - 1}"
            ))

        if page < total_pages:
            row.append(InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"show_all_bags_{page + 1}"
            ))

        if row:
            keyboard.inline_keyboard.append(row)

        # Кнопка для переключения в обычный режим
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text="👤 Обычный топ",
                callback_data=f"top_bags_1_0"
            )
        ])

        text += f'⏰ <i>Актуально на {get_formatted_time()}</i>\n'
        text += f'👮 <i>Доступно: агенты ранг 2+</i>'

        # Обновляем сообщение
        await callback.message.edit_text(
            text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Show all bags error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при обновлении топа!", show_alert=True)


# ОБРАБОТЧИК ПАГИНАЦИИ ИСТОРИИ ПЕРЕВОДОВ
@sapphires_router.callback_query(F.data.startswith('transfers_'))
@rate_limit_with_cleanup(limit=1)
async def handle_transfers_pagination(callback: CallbackQuery):
    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return
    """Пагинация истории переводов"""
    try:
        if not await check_user_access(callback.from_user.id, 2):
            await callback.answer("❌ Нет доступа!", show_alert=True)
            return

        page = safe_int(callback.data.split('_')[1], 1)

        limit = 10
        transfers, total = await get_recent_transfers(limit, (page - 1) * limit)
        total_pages = max(1, (total + limit - 1) // limit)

        if not transfers and page > 1:
            await callback.answer("❌ Страница не существует!", show_alert=True)
            return

        text = f'🔄 <b>История переводов</b> (стр. {page}/{total_pages})\n'
        text += f'📊 <b>Всего переводов:</b> {total}\n\n'

        if not transfers:
            text += '📭 <i>История переводов пуста</i>\n'
            text += '<i>Здесь будут отображаться все переводы между пользователями</i>'
        else:
            for transfer in transfers:
                # Форматируем операцию с ссылками
                formatted_transfer = await format_operation_with_links(transfer)

                # Форматируем сумму
                amount_text = formatted_transfer.get('formatted_amount', '0')

                # Используем безопасный HTML
                display_name = escape(formatted_transfer.get('display_name', 'Перевод'))
                text += f'{formatted_transfer.get("emoji", "📤")} <b>{display_name}</b>\n'
                text += f'{formatted_transfer.get("amount_prefix", "📤")} <b>Сумма:</b> <code>{amount_text} сапфов</code>\n'

                # Показываем участников с HTML-ссылками
                description = formatted_transfer.get('description', '')
                if description:
                    text += f'📝 <b>Описание:</b> {description}\n'

                # Баланс
                if 'balance_before' in formatted_transfer and 'balance_after' in formatted_transfer:
                    text += f'🏦 <b>Баланс:</b> {formatted_transfer["balance_before"]:,} → {formatted_transfer["balance_after"]:,}\n'

                # Комментарий с безопасным HTML (только если есть)
                comment = formatted_transfer.get('formatted_comment', '')
                if comment and comment.strip() and comment != 'Без комментария':
                    if len(comment) > 40:
                        comment = comment[:37] + '...'
                    safe_comment = escape(comment)
                    text += f'💬 <b>Комментарий:</b> {safe_comment}\n'

                # Время и оператор
                agent_link = formatted_transfer.get("agent_link", "Система")
                text += f'👮 <b>Оператор:</b> {agent_link}\n'

        # Пагинация
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        row = []

        if page > 1:
            row.append(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"transfers_{page - 1}"
            ))

        if page < total_pages:
            row.append(InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"transfers_{page + 1}"
            ))

        if row:
            keyboard.inline_keyboard.append(row)

        # Обновляем сообщение
        await callback.message.edit_text(
            text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Transfers pagination error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при обновлении истории!", show_alert=True)


# ОБРАБОТЧИК ПОДТВЕРЖДЕНИЯ ПЕРЕВОДА
@sapphires_router.callback_query(F.data.startswith('transfer_confirm_'))
@rate_limit_with_cleanup(limit=1)
async def handle_confirm_transfer(callback: CallbackQuery):
    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return
    """Подтверждение перевода"""
    try:
        transfer_id = callback.data.split('_', 2)[2]

        if transfer_id not in pending_transfers:
            await callback.answer("❌ Перевод устарел!", show_alert=True)
            return

        data = pending_transfers[transfer_id]

        success, message = await transfer_sapphires(
            data['from_user_id'],
            data['to_user_id'],
            data['amount'],
            data['from_user_id'],
            get_current_datetime(),
            data['comment'],
            is_user_transfer=True
        )

        if success:
            from_link = await user_link_global(data['from_user_id'])
            to_link = await user_link_global(data['to_user_id'])
            from_balance = await get_user_bag(data['from_user_id'])
            to_balance = await get_user_bag(data['to_user_id'])

            # Формируем сообщение с правильной обработкой комментария
            response_text = (
                f'📤 <b>Перевод выполнен!</b>\n\n'
                f'👤 <b>От:</b> {from_link}\n'
                f'👤 <b>Кому:</b> {to_link}\n'
                f'💰 <b>Сумма:</b> <code>{data["amount"]:,} сапфов</code>\n'
            )

            # Добавляем комментарий только если он есть
            if data['comment'] and data['comment'].strip():
                response_text += f'📝 <b>Комментарий:</b> {data["comment"]}\n'

            response_text += f'⏰ <b>Время:</b> {get_formatted_time()}'

            # Обновляем сообщение
            await callback.message.edit_text(
                response_text,
                parse_mode='HTML',
                disable_web_page_preview=True
            )

            # Уведомляем получателя
            try:
                recipient_text = (
                    f'📥 <b>Вы получили перевод!</b>\n\n'
                    f'👤 <b>От:</b> {from_link}\n'
                    f'💰 <b>Сумма:</b> {data["amount"]:,} сапфов\n'
                    f'🏦 <b>Ваш баланс:</b> {to_balance:,}\n'
                )

                if data['comment'] and data['comment'].strip():
                    recipient_text += f'📝 <b>Комментарий:</b> {data["comment"]}'

                await callback.bot.send_message(
                    data['to_user_id'],
                    recipient_text,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            except:
                pass

            await callback.answer("✅ Перевод выполнен!")
        else:
            await callback.answer(f"❌ {message}", show_alert=True)

        # Очищаем
        if transfer_id in pending_transfers:
            del pending_transfers[transfer_id]

    except Exception as e:
        logger.error(f"Confirm transfer error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при переводе!", show_alert=True)


# ОБРАБОТЧИК ОТМЕНЫ ПЕРЕВОДА
@sapphires_router.callback_query(F.data.startswith('transfer_cancel_'))
@rate_limit_with_cleanup(limit=1)
async def handle_cancel_transfer(callback: CallbackQuery):
    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return
    """Отмена перевода"""
    transfer_id = callback.data.split('_', 2)[2]

    if transfer_id in pending_transfers:
        del pending_transfers[transfer_id]

    await callback.message.edit_text(
        "❌ <b>Перевод отменен</b>"
    )
    await callback.answer("❌ Перевод отменен")


# ОБРАБОТЧИК ПОДТВЕРЖДЕНИЯ НАКАЗАНИЯ
@sapphires_router.callback_query(F.data.startswith('punish_confirm_'))
@rate_limit_with_cleanup(limit=1)
async def handle_confirm_punishment(callback: CallbackQuery):
    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return
    """Подтверждение наказания"""
    try:
        user_id = callback.from_user.id

        # Проверяем права
        if not await check_user_access(user_id, 3):
            await callback.answer("❌ Недостаточно прав!", show_alert=True)
            return

        # Парсим данные
        data_parts = callback.data.split('_')
        from_user_id = int(data_parts[2])
        to_user_id = int(data_parts[3])
        amount = int(data_parts[4])

        # Получаем причину из хранилища
        reason = punishment_data.get((from_user_id, to_user_id, amount), "Наказание по решению администрации")

        # Выполняем перевод как административный
        success, message = await transfer_sapphires(
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            amount=amount,
            agent_id=user_id,
            date=get_current_datetime(),
            comment=reason,
            is_user_transfer=False  # Административный перевод
        )

        if success:
            # Получаем обновленные данные
            from_user_link = await user_link_global(from_user_id)
            to_user_link = await user_link_global(to_user_id)
            agent_link = await user_link_global(user_id)
            from_new_balance = await get_user_bag(from_user_id)
            to_new_balance = await get_user_bag(to_user_id)

            # Форматируем время
            formatted_time = get_formatted_time()

            # Формируем сообщение с правильной обработкой комментария
            response_text = (
                f'⚖️ <b>Судебная кара применена</b>\n\n'
                f'👤 <b>Виновник:</b> {from_user_link}\n'
                f'👤 <b>Пострадавший:</b> {to_user_link}\n'
                f'💰 <b>Штраф:</b> <code>{amount:,} сапфов</code>\n'
                f'👮 <b>Судья:</b> {agent_link}\n'
            )

            # Добавляем причину только если она есть
            if reason and reason.strip():
                response_text += f'📝 <b>Причина:</b> {reason}\n'
            else:
                response_text += '\n'

            response_text += (
                f'\n<b>Новые балансы:</b>\n'
                f'• {from_user_link}: <code>{from_new_balance:,} сапфов</code>\n'
                f'• {to_user_link}: <code>{to_new_balance:,} сапфов</code>\n\n'
                f'⏰ <b>Время:</b> {formatted_time}'
            )

            # Обновляем сообщение
            await callback.message.edit_text(
                response_text,
                parse_mode='HTML',
                disable_web_page_preview=True
            )

            # Отправляем уведомление виновнику
            try:
                punish_text = (
                    f'⚖️ <b>Вам вынесено наказание</b>\n\n'
                    f'👮 <b>Судья:</b> {agent_link}\n'
                    f'👤 <b>Пострадавший:</b> {to_user_link}\n'
                    f'💰 <b>Штраф:</b> {amount:,} сапфов\n'
                    f'🏦 <b>Ваш новый баланс:</b> {from_new_balance:,}\n'
                )

                if reason and reason.strip():
                    punish_text += f'📝 <b>Причина:</b> {reason}\n'
                else:
                    punish_text += '\n'

                punish_text += '\n<i>В случае несогласия обратитесь к судье</i>'

                await callback.bot.send_message(
                    from_user_id,
                    punish_text,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"Failed to send punishment notification to {from_user_id}: {e}")

            # Отправляем уведомление пострадавшему
            try:
                compensation_text = (
                    f'⚖️ <b>Вы получили компенсацию</b>\n\n'
                    f'👤 <b>Виновник:</b> {from_user_link}\n'
                    f'👮 <b>Судья:</b> {agent_link}\n'
                    f'💰 <b>Сумма:</b> {amount:,} сапфов\n'
                    f'🏦 <b>Ваш новый баланс:</b> {to_new_balance:,}\n'
                )

                if reason and reason.strip():
                    compensation_text += f'📝 <b>Причина:</b> {reason}\n'
                else:
                    compensation_text += '\n'

                compensation_text += '\n<i>Это компенсация за нанесенный ущерб</i>'

                await callback.bot.send_message(
                    to_user_id,
                    compensation_text,
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )
            except Exception as e:
                logger.error(f"Failed to send compensation notification to {to_user_id}: {e}")

            # Очищаем данные наказания
            if (from_user_id, to_user_id, amount) in punishment_data:
                del punishment_data[(from_user_id, to_user_id, amount)]

            await callback.answer("✅ Судебная кара применена!")

        else:
            await callback.answer(f"❌ {message}", show_alert=True)

    except Exception as e:
        logger.error(f"Confirm punishment error: {e}", exc_info=True)
        await callback.answer("❌ Ошибка при применении наказания!", show_alert=True)


# ОБРАБОТЧИК ОТМЕНЫ НАКАЗАНИЯ
@sapphires_router.callback_query(F.data == "punish_cancel")
@rate_limit_with_cleanup(limit=1)
async def handle_cancel_punishment(callback: CallbackQuery):
    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return
    """Отмена наказания"""
    await callback.message.edit_text(
        "❌ <b>Наказание отменено</b>\n"
        "Администратор отменил применение штрафа.",
        parse_mode='HTML'
    )
    await callback.answer("❌ Наказание отменен")