import logging
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from handlers.AdminsTools.ChatSettings.Stats.msg_stats_users.SmsStatsDB import get_stats
from typing import Tuple

from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_global

logger = logging.getLogger(__name__)

UCS = Router()

PERIODS = {
    'день': 'день',
    'неделя': 'неделю',
    'месяц': 'месяц',
    'год': 'год',
    'всего': 'всё время',
    'вся': 'всё время'
}

ITEMS_PER_PAGE = 10


def build_keyboard(chat_id: int, period: str, page: int, total_users: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    has_prev = page > 0
    has_next = (page + 1) * ITEMS_PER_PAGE < total_users

    if has_prev:
        builder.add(InlineKeyboardButton(text="⬅️", callback_data=f"stat:{chat_id}:{period}:{page - 1}"))

    builder.add(InlineKeyboardButton(text="🔄", callback_data=f"stat:{chat_id}:{period}:{page}"))

    if has_next:
        builder.add(InlineKeyboardButton(text="➡️", callback_data=f"stat:{chat_id}:{period}:{page + 1}"))

    return builder.as_markup()


async def format_stats(chat_id: int, period: str, page: int = 0) -> Tuple[str, InlineKeyboardMarkup]:
    # Определяем период для запроса к БД
    stats_period = "всего" if period == "вся" else period

    try:
        # Получаем статистику из БД для указанного периода
        raw_stats = await get_stats(chat_id, stats_period)
    except Exception as e:
        logger.error(e, exc_info=True)
        return "🚫 Ошибка при получении статистики.", None

    total_users = len(raw_stats)

    if not raw_stats:
        return "🚫 Нет данных за этот период.", None

    # Пагинация
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    page_stats = raw_stats[start:end]

    if not page_stats:
        return "🚫 Нет данных на этой странице.", None

    # Форматируем статистику
    lines = []
    for i, (user_id, _, count) in enumerate(page_stats, start=start + 1):
        try:
            mention = await user_link_global(user_id)
        except:
            mention = f"ID {user_id}"
        lines.append(f"{i}. {mention} — {count}")

    period_name = PERIODS.get(period, period)
    total_messages = sum(count for _, _, count in raw_stats)

    text = f"📈 Статистика сообщений за {period_name}:\n"
    text += "\n".join(lines)
    text += f"\n\n📨 Всего сообщений: {total_messages}"

    # Создаем клавиатуру только если есть необходимость в пагинации
    kb = build_keyboard(chat_id, period, page, total_users) if total_users > ITEMS_PER_PAGE else None
    return text, kb


@UCS.message(F.text.split("\n", 1)[0].lower().startswith("!стата "))
@UCS.message(F.text.split("\n", 1)[0].lower().startswith(".стата "))
@UCS.message(F.text.split("\n", 1)[0].lower().startswith("/стата "))
@UCS.message(F.text.split("\n", 1)[0].lower().startswith("стата "))

@UCS.message(F.text.split("\n", 1)[0].lower().startswith("!статистика "))
@UCS.message(F.text.split("\n", 1)[0].lower().startswith(".статистика "))
@UCS.message(F.text.split("\n", 1)[0].lower().startswith("/статистика "))
@UCS.message(F.text.split("\n", 1)[0].lower().startswith("статистика "))

@UCS.message(F.text.split("\n", 1)[0].lower().startswith("!статистика за "))
@UCS.message(F.text.split("\n", 1)[0].lower().startswith(".статистика за "))
@UCS.message(F.text.split("\n", 1)[0].lower().startswith("/статистика за "))
@UCS.message(F.text.split("\n", 1)[0].lower().startswith("статистика за "))
async def cmd_stats(message: types.Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 56):
        return

    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    chat_id = message.chat.id

    if not args:
        arg = 'день'
    else:
        arg = args[0].lower()

    if arg not in PERIODS:
        await message.answer("❌ Неверный период. Используй: день, неделя, месяц, год, всего, вся.")
        return

    text, kb = await format_stats(chat_id, arg)
    await message.reply(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)


@UCS.callback_query(lambda c: c.data.startswith("stat:"))
@rate_limit_with_cleanup(limit=1)
async def cb_stats(callback: types.CallbackQuery):

    if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await callback.answer(f"{random_text}", show_alert=True)
        return

    _, chat_id_str, period, page_str = callback.data.split(":")
    chat_id = int(chat_id_str)
    page = int(page_str)

    # Получаем статистику для проверки наличия данных
    stats_period = "всего" if period == "вся" else period
    try:
        raw_stats = await get_stats(chat_id, stats_period)
    except Exception as e:
        logging.error(e)
        await callback.answer("🚫 Ошибка при получении статистики.", show_alert=True)
        return

    total_users = len(raw_stats)

    # Проверяем, есть ли данные на запрошенной странице
    start = page * ITEMS_PER_PAGE
    if start >= total_users:
        await callback.answer("🚫 Больше нет данных для отображения.", show_alert=False)
        return

    text, kb = await format_stats(chat_id, period, page)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()