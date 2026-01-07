# report_handlers.py
import logging

from aiogram import Router, types, F
from aiogram.filters import Command

from handlers.AdminsTools.ChatSettings.reports.report_statistics.report_statisticsDB import get_active_user_ids_in_chat, \
    get_moderation_stats_by_user_ids, get_all_user_ids_in_chat, get_pending_reports_for_chats
from handlers.AdminsTools.ChatSettings.reports.reportsDB import check_reports_chats_db
from handlers.BotAutomaticWork.AddChatsBot.link.chats_global_link import chat_global_link
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_global

logger = logging.getLogger(__name__)

report_statistics = Router()

# Глобальные переменные для пагинации (лучше вынести в кэш/состояние, но для примера оставим)
report_pages = {}
report_messages = {}


def create_simple_pagination_keyboard(current_page: int, total_pages: int):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    if current_page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"rep_page_{current_page - 1}"))
    if current_page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"rep_page_{current_page + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons] if buttons else [])


@report_statistics.message(lambda m: m.text and m.text.lower().startswith(('.реп стата',
                                                                           '!реп стата',
                                                                           '/реп стата',
                                                                           '!рс',
                                                                           '.рс',
                                                                           '/рс',
                                                                           '.репорт стата',
                                                                           '.репорт стата',
                                                                           '.репорт стата')))
@report_statistics.message(Command("report_stats"))
async def show_moderation_stats(message: types.Message):
    """Показывает статистику модерации для активных участников чата."""
    chat_id = message.chat.id

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, chat_id, 36):
        return

    active_user_ids = await get_active_user_ids_in_chat(chat_id)
    if not active_user_ids:
        await message.answer("❌ В этом чате нет активных участников")
        return

    stats = await get_moderation_stats_by_user_ids(chat_id, active_user_ids)
    if not stats:
        await message.answer("📊 Статистика модерации пуста")
        return

    result_text = "📊 <b>Статистика модерации (активные участники)</b>\n\n"
    for i, (user_id, day, week, month, year, total) in enumerate(stats, 1):
        user_link = await user_link_global(user_id)
        result_text += f"{i}. {user_link}: {day} | {week} | {month} | {year} | {total}\n\n"

    await message.answer(result_text, parse_mode='HTML', disable_web_page_preview=True)


@report_statistics.message(lambda m: m.text and m.text.lower().startswith(('.реп стата вся',
                                                                           '!реп стата вся',
                                                                           '/реп стата вся',
                                                                           '!рсв',
                                                                           '.рсв',
                                                                           '/рсв',
                                                                           '.репорт стата вся',
                                                                           '.репорт стата вся',
                                                                           '.репорт стата вся')))
async def show_all_moderation_stats(message: types.Message):
    """Показывает статистику модерации для всех участников чата."""
    chat_id = message.chat.id

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, chat_id, 36):
        return

    all_user_ids = await get_all_user_ids_in_chat(chat_id)
    if not all_user_ids:
        await message.answer("❌ В базе нет данных об участниках этого чата")
        return

    stats = await get_moderation_stats_by_user_ids(chat_id, all_user_ids)
    if not stats:
        await message.answer("📊 Статистика модерации пуста")
        return

    result_text = "📊 <b>Статистика модерации (все участники)</b>\n\n"
    for i, (user_id, day, week, month, year, total) in enumerate(stats, 1):
        user_link = await user_link_global(user_id)
        result_text += f"{i}. {user_link}: {day} | {week} | {month} | {year} | {total}\n\n"

    await message.answer(result_text, parse_mode='HTML', disable_web_page_preview=True)


@report_statistics.message(lambda m: m.text and m.text.lower().startswith(('.не проверенные репорты',
                                                                           '!не проверенные репорты',
                                                                           '/не проверенные репорты',
                                                                           '.нпр',
                                                                           '!нпр',
                                                                           '/нпр')))
async def show_pending_reports(message: types.Message):
    """Показывает список непроверенных жалоб."""
    chat_id = message.chat.id

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, chat_id, 35):
        return

    report_chats = await check_reports_chats_db(chat_id)

    if not report_chats:
        await message.reply("❌ Для этого чата не настроены чаты для жалоб.")
        return

    reports = await get_pending_reports_for_chats(report_chats)
    if not reports:
        await message.reply("✅ Нет непроверенных жалоб.")
        return

    # Сохраняем для пагинации
    report_pages[chat_id] = {
        'reports': reports,
        'current_page': 0,
        'page_size': 10
    }

    sent_message = await send_report_page(message, chat_id, 0)
    if sent_message:
        report_messages[chat_id] = sent_message.message_id


async def send_report_page(message, chat_id, page_number):
    """Отправляет/редактирует страницу с жалобами."""
    if chat_id not in report_pages:
        await (message.answer if hasattr(message, 'answer') else message.reply)(
            "❌ Данные устарели. Запросите список жалоб снова."
        )
        return None

    data = report_pages[chat_id]
    reports = data['reports']
    page_size = data['page_size']
    total_pages = (len(reports) + page_size - 1) // page_size

    if not (0 <= page_number < total_pages):
        page_number = 0
    data['current_page'] = page_number

    start_idx = page_number * page_size
    page_reports = reports[start_idx:start_idx + page_size]

    report_list = "📋 <b>Список непроверенных жалоб:</b>\n\n"
    for i, (report_id, reported_id, reply_msg_id, msg_id, reported_chat) in enumerate(page_reports, start_idx + 1):
        report_link = await user_link_global(report_id)
        reported_link = await user_link_global(reported_id)
        chat_link = await chat_global_link(reported_chat)

        # Исправлено форматирование ссылок (убраны лишние пробелы)
        chat_short = str(reported_chat)[4:] if str(reported_chat).startswith('-100') else reported_chat
        my_chat_short = str(chat_id)[4:] if str(chat_id).startswith('-100') else chat_id

        link_sms = f"https://t.me/c/{my_chat_short}/{msg_id}"
        reported_link_sms = f"https://t.me/c/{chat_short}/{reply_msg_id}"

        report_list += (
            f"Жалоба #{i}\n"
            f"От {reported_link} на {report_link}\n"
            f"Чат: {chat_link}\n"
            f"🔗 Ссылки: <a href='{link_sms}'>Проверить репорт</a> | <a href='{reported_link_sms}'>К сообщению</a>\n\n"
        )

    report_list += f"📊 Всего жалоб: {len(reports)} ({page_number + 1} из {total_pages})"
    keyboard = create_simple_pagination_keyboard(page_number, total_pages)

    if hasattr(message, 'message'):  # callback
        try:
            await message.message.edit_text(report_list, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)
            return message.message
        except Exception as e:
            logger.error(e, exc_info=True)
            await message.answer("❌ Не удалось обновить сообщение")
            return None
    else:  # обычное сообщение
        return await message.reply(report_list, reply_markup=keyboard, parse_mode="HTML", disable_web_page_preview=True)