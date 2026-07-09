import logging
from typing import Optional

from aiogram import Router, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery


from handlers.AdminsTools.ChatSettings.rules.rulesDB import set_rules
from handlers.AdminsTools.ChatSettings.welcome.welcomeDB import add_welcome_text
from handlers.AgentsFeatures.CheckTextApprovals.CheckTextApprovalsDB import (
    get_pending_moderation, delete_pending_moderation,
    get_pending_moderation_note, delete_pending_moderation_note
)
from handlers.AdminsTools.ChatSettings.notes.notesDB import add_note, update_note_text
from handlers.BotAutomaticWork.Gonfig.config import AGENT_CHAT_ID_CheckTextApprovals
from handlers.BotAutomaticWork.AddChatsBot.link.chats_global_link import chat_global_link
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import check_user_access
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender


check_text_agents_router = Router()
logger = logging.getLogger(__name__)


# =============================================================================
# ОБЩИЙ ХЕНДЛЕР МОДЕРАЦИИ (правила, приветствия, заметки)
# =============================================================================

@check_text_agents_router.callback_query(
    F.data.startswith((
            "approve_note:", "reject_note:",
            "approve_rule:", "reject_rule:",
            "approve_welcome:", "reject_welcome:"
    ))
)
@rate_limit_with_cleanup(limit=1)
async def handle_moderation(callback: CallbackQuery):
    try:
        admin_id = callback.from_user.id

        if not await check_user_access(admin_id, 1):
            await callback.answer("❌ Нет доступа", show_alert=True)
            return

        data_parts = callback.data.split(':')
        if len(data_parts) < 3:
            await callback.answer("❌ Неверный формат данных", show_alert=True)
            return

        action_type = data_parts[0]  # approve_rule
        action = action_type.split('_')[0]  # approve / reject
        content_type = action_type.split('_')[1]  # rule / welcome / note

        chat_id = int(data_parts[1])
        user_id = int(data_parts[2])  # ID автора контента — НЕ перезаписываем!
        item_name = data_parts[3] if len(data_parts) > 3 else None

        if content_type == "note" and item_name:
            await handle_note_moderation(callback, action, chat_id, user_id, item_name, admin_id)
        elif content_type in ["rule", "welcome"]:
            await handle_text_moderation(callback, action, content_type, chat_id, user_id, admin_id)
        else:
            await callback.answer("❌ Неизвестный тип контента", show_alert=True)

    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка в формате callback: {e}, data: {callback.data}", exc_info=True)
        await callback.answer("❌ Ошибка в формате данных", show_alert=True)
    except Exception as e:
        logger.error(e, exc_info=True)
        await callback.answer("Произошла ошибка", show_alert=True)


async def handle_text_moderation(callback: CallbackQuery, action: str, content_type: str,
                                 chat_id: int, user_id: int, admin_id: int):
    """Обработка модерации правил и приветствий"""
    try:
        await check_user_access(admin_id, 1)

        record = await get_pending_moderation(chat_id, content_type)
        if not record:
            await callback.answer("Запись не найдена или уже обработана", show_alert=True)
            return

        text = record['text']
        message_id = record['message_id']

        await delete_pending_moderation(chat_id, content_type)

        content_type_display = {"welcome": "приветствия", "rule": "правил"}.get(content_type, content_type)

        await update_admin_message(callback, action, content_type_display, text, chat_id, user_id, admin_id)
        await send_user_notification(callback, action, content_type_display, chat_id, message_id, content_type, text)
        await callback.answer(f"Текст {content_type_display} {'одобрен' if action == 'approve' else 'отклонён'}")

    except Exception as e:
        logger.error(e, exc_info=True)
        await callback.answer("Произошла ошибка", show_alert=True)


async def handle_note_moderation(callback: CallbackQuery, action: str, chat_id: int,
                                 user_id: int, notes_name: str, admin_id: int):
    """Обработка модерации заметок"""
    try:
        await check_user_access(admin_id, 1)

        record = await get_pending_moderation_note(chat_id, notes_name)
        if not record:
            await callback.answer("Заметка не найдена или уже обработана", show_alert=True)
            return

        notes_text = record['notes_text']
        message_id = record['message_id']
        is_edit = record.get('is_edit', False)

        await delete_pending_moderation_note(chat_id, notes_name)

        await update_admin_message_note(callback, action, notes_name, notes_text, chat_id, user_id, admin_id, is_edit)
        await send_note_user_notification(callback, action, chat_id, message_id, notes_name, notes_text, is_edit)
        await callback.answer(f"Заметка {'одобрена' if action == 'approve' else 'отклонена'}")

    except Exception as e:
        logger.error(e, exc_info=True)
        await callback.answer("Произошла ошибка", show_alert=True)


# =============================================================================
# ОБНОВЛЕНИЕ СООБЩЕНИЙ АДМИНА
# =============================================================================

async def update_admin_message(callback: CallbackQuery, action: str, content_type: str, text: str,
                               chat_id: int, user_id: int, admin_id: int):
    """Обновление сообщения в админ-чате для правил/приветствий"""
    gender = await get_user_gender(admin_id)
    status_text = f"одобр{g('ил', gender)}" if action == "approve" else f"отклон{g('ил', gender)}"
    status_emoji = "✅" if action == "approve" else "🔴"

    chat_link = await chat_global_link(chat_id)
    user_link = await user_link_global(user_id)
    admin_link = await user_link_global(admin_id)

    await callback.bot.edit_message_text(
        chat_id=AGENT_CHAT_ID_CheckTextApprovals,
        message_id=callback.message.message_id,
        text=f"{status_emoji} {admin_link} <b>{status_text}</b> текст\n\n"
             f"<b>Текст:</b>\n{text}\n\n"
             f"ℹ️ Некая информация:\n"
             f"<b>Чат:</b> «{chat_link}»\n"
             f"<b>Пользователь:</b> {user_link}\n",
        reply_markup=None,
        parse_mode='HTML',
        disable_web_page_preview=True
    )


async def update_admin_message_note(callback: CallbackQuery, action: str, notes_name: str, notes_text: str,
                                    chat_id: int, user_id: int, admin_id: int, is_edit: bool = False):
    """Обновление сообщения в админ-чате для заметок"""
    gender = await get_user_gender(admin_id)
    status_text = f"одобр{g('ил', gender)}" if action == "approve" else f"отклон{g('ил', gender)}"
    status_emoji = "✅" if action == "approve" else "🔴"
    operation_text = "редактирование" if is_edit else "создание"

    chat_link = await chat_global_link(chat_id)
    user_link = await user_link_global(user_id)
    admin_link = await user_link_global(admin_id)

    await callback.bot.edit_message_text(
        chat_id=AGENT_CHAT_ID_CheckTextApprovals,
        message_id=callback.message.message_id,
        text=f"{status_emoji} <b>{admin_link} {status_text} заметку</b>\n\n"
             f"<b>Операция:</b> {operation_text}\n"
             f"<b>Название:</b> {notes_name}\n\n"
             f"<b>💬 Текст заметки:</b>\n{notes_text}\n\n"
             f"ℹ️ Некая информация:\n"
             f"<b>Чат:</b> «{chat_link}»\n"
             f"<b>Пользователь:</b> {user_link}",
        reply_markup=None,
        parse_mode='HTML',
        disable_web_page_preview=True
    )


# =============================================================================
# УВЕДОМЛЕНИЯ ПОЛЬЗОВАТЕЛЯМ
# =============================================================================

async def send_user_notification(callback: CallbackQuery, action: str, content_type: str,
                                 chat_id: int, message_id: int, content_type_db: str, text: str):
    """Отправка уведомления пользователю для правил/приветствий"""
    try:
        if action == "approve":
            if content_type_db == "welcome":
                await add_welcome_text(chat_id, text)
            else:
                await set_rules(chat_id, text)
            await safe_send_message(callback.bot, chat_id, f"✅ Текст {content_type} одобрен!", message_id)
        else:
            await safe_send_message(callback.bot, chat_id, f"❌ Текст {content_type} не одобрен.", message_id)
    except Exception as e:
        logger.error(e, exc_info=True)


async def send_note_user_notification(callback: CallbackQuery, action: str, chat_id: int,
                                      message_id: int, notes_name: str, notes_text: str, is_edit: bool = False):
    """Отправка уведомления пользователю для заметок"""
    try:
        if action == "approve":
            if is_edit:
                success = await update_note_text(chat_id, notes_name, notes_text)
                msg = f"✅ Заметка «{notes_name}» обновлена!" if success else f"❌ Ошибка при обновлении заметки «{notes_name}»"
            else:
                result = await add_note(chat_id, notes_name, notes_text)
                msg = f"✅ Заметка «{notes_name}» добавлена!" if result.get(
                    'success') else f"❌ Ошибка: {result.get('error', 'Неизвестная')}"
            await safe_send_message(callback.bot, chat_id, msg, message_id)
        else:
            operation = "редактирование" if is_edit else "создание"
            await safe_send_message(callback.bot, chat_id,
                                    f"❌ {operation.capitalize()} заметки «{notes_name}» не одобрено.", message_id)
    except Exception as e:
        logger.error(e, exc_info=True)


async def safe_send_message(bot, chat_id: int, text: str, reply_to_message_id: Optional[int] = None):
    """Безопасная отправка сообщения"""
    try:
        if reply_to_message_id:
            await bot.send_message(chat_id, text, reply_to_message_id=reply_to_message_id)
        else:
            await bot.send_message(chat_id, text)
    except TelegramBadRequest as e:
        if "reply to message not found" in str(e).lower() or "message to be replied" in str(e).lower():
            await bot.send_message(chat_id, text)
        else:
            raise
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}", exc_info=True)
        raise



# =============================================================================
# ХЕНДЛЕР ПЕРВОГО КОММЕНТАРИЯ
# =============================================================================


@check_text_agents_router.callback_query(
    F.data.startswith(("approve_first_comment:", "reject_first_comment:"))
)
async def handle_first_comment_moderation(callback: types.CallbackQuery):
    """Обработка модерации первого комментария"""
    try:
        admin_id = callback.from_user.id

        if not await check_user_access(admin_id, 1):
            await callback.answer("❌ Нет доступа", show_alert=True)
            return

        data_parts = callback.data.split(':')
        if len(data_parts) < 3:
            await callback.answer("❌ Неверный формат данных", show_alert=True)
            return

        action_type = data_parts[0]
        action = action_type.split('_')[0]
        chat_id = int(data_parts[1])  # это ID ГРУППЫ
        user_id = int(data_parts[2])

        # Получаем запись на модерацию
        from handlers.AdminsTools.ChatSettings.first_comment.first_commentDB import get_pending_first_comment
        pending_comment = await get_pending_first_comment(chat_id)

        if not pending_comment:
            await callback.answer("Комментарий не найден или уже обработан", show_alert=True)
            return

        # Обновляем сообщение в админ-чате
        gender = await get_user_gender(admin_id)
        status_text = f"одобр{g('ил', gender)}" if action == "approve" else f"отклон{g('ил', gender)}"
        status_emoji = "✅" if action == "approve" else "❌"

        admin_link = await user_link_global(admin_id)
        chat_link = await chat_global_link(chat_id)
        user_link = await user_link_global(user_id)

        preview = pending_comment['comment_text'][:300] + ('...' if len(pending_comment['comment_text']) > 300 else '')

        await callback.bot.edit_message_text(
            chat_id=AGENT_CHAT_ID_CheckTextApprovals,
            message_id=callback.message.message_id,
            text=f"{status_emoji} <b>{admin_link} {status_text} первый комментарий</b>\n\n"
                 f"<b>Чат:</b> {chat_link}\n"
                 f"<b>Пользователь:</b> {user_link}\n\n"
                 f"<b>Текст:</b>\n{preview}",
            reply_markup=None,
            parse_mode='HTML',
            disable_web_page_preview=True
        )

        # Выполняем одобрение/отклонение
        if action == "approve":
            from handlers.AdminsTools.ChatSettings.first_comment.first_commentDB import approve_first_comment
            success = await approve_first_comment(chat_id)
            if success:
                await safe_send_message(
                    callback.bot,
                    chat_id,
                    "✅ Первый комментарий одобрен и установлен!",
                    pending_comment.get('message_id')
                )
            else:
                await callback.answer("❌ Ошибка при одобрении", show_alert=True)
                return
        else:
            from handlers.AdminsTools.ChatSettings.first_comment.first_commentDB import reject_first_comment
            success = await reject_first_comment(chat_id)
            if success:
                await safe_send_message(
                    callback.bot,
                    chat_id,
                    "❌ Первый комментарий не одобрен.",
                    pending_comment.get('message_id')
                )
            else:
                await callback.answer("❌ Ошибка при отклонении", show_alert=True)
                return

        await callback.answer(f"Комментарий {'одобрен' if action == 'approve' else 'отклонён'}")

    except Exception as e:
        logger.error(f"❌ Ошибка в handle_first_comment_moderation: {e}", exc_info=True)
        await callback.answer("Произошла ошибка", show_alert=True)