import logging

from aiogram import Router, F, types
from aiogram.types import CallbackQuery

from handlers.AdminsTools.ChatSettings.first_comment.first_commentDB import get_pending_first_comment, \
    approve_first_comment, reject_first_comment, delete_pending_first_comment
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


@check_text_agents_router.callback_query(F.data.startswith(("approve_", "reject_")))
@rate_limit_with_cleanup(limit=1)
async def handle_moderation(callback: CallbackQuery):
    try:
        if not await check_user_access(callback.from_user.id, 1):
            return

        # Разделяем callback_data по двоеточию
        data_parts = callback.data.split(':')

        # Минимальный формат: approve_note:chat_id:user_id:note_name
        if len(data_parts) < 4:
            await callback.answer("❌ Неверный формат данных", show_alert=True)
            return

        # Первая часть: approve_note или reject_note
        action_type = data_parts[0]
        action = action_type.split('_')[0]  # approve или reject
        content_type = "note"  # Всегда заметка в этом формате

        chat_id = int(data_parts[1])
        user_id = int(data_parts[2])
        notes_name = data_parts[3]

        await handle_note_moderation(callback, action, chat_id, user_id, notes_name)

    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка в формате callback_data: {e}, data: {callback.data}", exc_info=True)
        await callback.answer("❌ Ошибка в формате данных", show_alert=True)
    except Exception as e:
        logger.error(e, exc_info=True)
        await callback.answer("Произошла ошибка")


async def handle_text_moderation(callback: CallbackQuery, action: str, content_type: str, chat_id: int, user_id: int):
    """Обработка модерации правил и приветствий (для старых форматов)"""
    try:
        user_id = callback.from_user.id
        await check_user_access(user_id, 1)

        record = await get_pending_moderation(chat_id, content_type)
        if not record:
            await callback.answer("Запись не найдена или уже обработана")
            return

        text = record['text']
        message_id = record['message_id']

        # Удаляем запись из БД модерации
        await delete_pending_moderation(chat_id, content_type)

        # Определяем русские названия для отображения
        if content_type == "welcome":
            content_type_display = "приветствия"
        else:  # rules
            content_type_display = "правил"

        await update_admin_message(callback, action, content_type_display, text, chat_id, user_id,
                                   callback.from_user.id)
        await send_user_notification(callback, action, content_type_display, chat_id, message_id, content_type, text)
        await callback.answer(f"Текст {content_type_display} {'одобрен' if action == 'approve' else 'отклонён'}")

    except Exception as e:
        logger.error(e, exc_info=True)
        await callback.answer("Произошла ошибка")


async def handle_note_moderation(callback: CallbackQuery, action: str, chat_id: int, user_id: int, notes_name: str):
    """Обработка модерации заметок"""
    try:
        user_id = callback.from_user.id
        await check_user_access(user_id, 1)

        record = await get_pending_moderation_note(chat_id, notes_name)
        if not record:
            await callback.answer("Заметка не найдена или уже обработана")
            return

        notes_text = record['notes_text']
        message_id = record['message_id']
        is_edit = record.get('is_edit', False)  # Получаем из БД

        # Удаляем запись из БД модерации
        await delete_pending_moderation_note(chat_id, notes_name)

        await update_admin_message_note(callback, action, notes_name, notes_text, chat_id, user_id,
                                        callback.from_user.id, is_edit)
        await send_note_user_notification(callback, action, chat_id, message_id, notes_name, notes_text, is_edit)
        await callback.answer(f"Заметка {'одобрена' if action == 'approve' else 'отклонена'}")

    except Exception as e:
        logger.error(e, exc_info=True)
        await callback.answer("Произошла ошибка")


async def update_admin_message(callback: CallbackQuery, action: str, content_type: str, text: str,
                               chat_id: int, user_id: int, admin_id: int):
    """Обновление сообщения в админ-чате для правил/приветствий"""
    gender = await get_user_gender(admin_id)

    status_text = f"одобр{g('ил', gender)}" if action == "approve" else f"отклон{g('ил', gender)}"
    status_text_emoji = "✅" if action == "approve" else "🔴"

    chat_link = await chat_global_link(chat_id)
    user_link = await user_link_global(user_id)
    admin_link = await user_link_global(admin_id)

    await callback.bot.edit_message_text(
        chat_id=AGENT_CHAT_ID_CheckTextApprovals,
        message_id=callback.message.message_id,
        text=f"{status_text_emoji} {admin_link} <b>{status_text}</b> текст\n\n"
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
    status_text_emoji = "✅" if action == "approve" else "🔴"

    operation_text = "редактирование" if is_edit else "создание"

    chat_link = await chat_global_link(chat_id)
    user_link = await user_link_global(user_id)
    admin_link = await user_link_global(admin_id)

    await callback.bot.edit_message_text(
        chat_id=AGENT_CHAT_ID_CheckTextApprovals,
        message_id=callback.message.message_id,
        text=f"{status_text_emoji} <b>{admin_link} {status_text} заметку</b>\n\n"
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


async def send_user_notification(callback: CallbackQuery, action: str, content_type: str,
                                 chat_id: int, message_id: int, content_type_db: str, text: str):
    """Отправка уведомления пользователю для правил/приветствий"""
    try:
        if action == "approve":
            if content_type_db == "welcome":
                await add_welcome_text(chat_id, text)
            else:  # rules
                await set_rules(chat_id, text)

            await callback.bot.send_message(
                chat_id,
                f"✅ Текст {content_type} одобрен!",
                reply_to_message_id=message_id
            )
        else:  # reject
            await callback.bot.send_message(
                chat_id,
                f"❌ Текст {content_type} не одобрен.",
                reply_to_message_id=message_id
            )
    except Exception as e:
        logger.error(e, exc_info=True)


async def send_note_user_notification(callback: CallbackQuery, action: str, chat_id: int,
                                      message_id: int, notes_name: str, notes_text: str, is_edit: bool = False):
    """Отправка уведомления пользователю для заметок"""
    try:
        if action == "approve":
            if is_edit:
                # Для редактирования используем update_note_text
                success = await update_note_text(chat_id, notes_name, notes_text)

                if success:
                    await callback.bot.send_message(
                        chat_id,
                        f"✅ Заметка «{notes_name}» обновлена!",
                        reply_to_message_id=message_id
                    )
                else:
                    await callback.bot.send_message(
                        chat_id,
                        f"❌ Ошибка при обновлении заметки «{notes_name}»",
                        reply_to_message_id=message_id
                    )
            else:
                # Для создания используем add_note
                result = await add_note(chat_id, notes_name, notes_text)
                if result['success']:
                    await callback.bot.send_message(
                        chat_id,
                        f"✅ Заметка «{notes_name}» добавлена!",
                        reply_to_message_id=message_id
                    )
                else:
                    await callback.bot.send_message(
                        chat_id,
                        f"❌ Ошибка при добавлении заметки: {result.get('error', 'Неизвестная ошибка')}",
                        reply_to_message_id=message_id
                    )
        else:  # reject
            operation_text = "редактирование" if is_edit else "создание"
            await callback.bot.send_message(
                chat_id,
                f"❌ {operation_text.capitalize()} заметки «{notes_name}» не одобрено.",
                reply_to_message_id=message_id
            )
    except Exception as e:
        logger.error(e, exc_info=True)


@check_text_agents_router.callback_query(F.data.startswith(("approve_first_comment", "reject_first_comment")))
async def handle_first_comment_moderation(callback: types.CallbackQuery):
    """Обработка модерации первого комментария"""
    try:
        if not await check_user_access(callback.from_user.id, 1):
            return

        data_parts = callback.data.split(':')
        if len(data_parts) < 3:
            await callback.answer("❌ Неверный формат данных", show_alert=True)
            return

        action_type = data_parts[0]  # approve_first_comment или reject_first_comment
        action = action_type.split('_')[0]  # approve или reject
        channel_id = int(data_parts[1])
        user_id = int(data_parts[2])

        # Получаем данные о модерации
        pending_comment = await get_pending_first_comment(channel_id)
        if not pending_comment:
            await callback.answer("Комментарий не найден или уже обработан", show_alert=True)
            return

        # Обновляем сообщение админа
        gender = await get_user_gender(callback.from_user.id)
        status_text = f"одобр{g('ил', gender)}" if action == "approve" else f"отклон{g('ил', gender)}"
        status_emoji = "✅" if action == "approve" else "❌"

        admin_link = await user_link_global(callback.from_user.id)
        channel_link = await chat_global_link(channel_id)
        user_link = await user_link_global(user_id)

        await callback.bot.edit_message_text(
            chat_id=AGENT_CHAT_ID_CheckTextApprovals,
            message_id=callback.message.message_id,
            text=f"{status_emoji} <b>{admin_link} {status_text} первый комментарий</b>\n\n"
                 f"<b>Канал:</b> {channel_link}\n"
                 f"<b>Пользователь:</b> {user_link}\n\n"
                 f"<b>Текст:</b>\n{pending_comment['comment_text'][:300]}...",
            reply_markup=None,
            parse_mode='HTML',
            disable_web_page_preview=True
        )

        # Выполняем действие
        if action == "approve":
            success = await approve_first_comment(channel_id)
            if success:
                # Уведомляем пользователя
                await callback.bot.send_message(
                    channel_id,
                    f"✅ Первый комментарий одобрен и установлен!",
                    reply_to_message_id=pending_comment['user_message_id']
                )
            else:
                await callback.answer("❌ Ошибка при одобрении", show_alert=True)
                return
        else:
            success = await reject_first_comment(channel_id)
            if success:
                # Уведомляем пользователя
                await callback.bot.send_message(
                    channel_id,
                    f"❌ Первый комментарий не одобрен.",
                    reply_to_message_id=pending_comment['user_message_id']
                )
            else:
                await callback.answer("❌ Ошибка при отклонении", show_alert=True)
                return

        # Удаляем из таблицы модерации
        await delete_pending_first_comment(channel_id)

        await callback.answer(f"Комментарий {'одобрен' if action == 'approve' else 'отклонён'}")

    except Exception as e:
        logger.error(f"Ошибка в handle_first_comment_moderation: {e}", exc_info=True)
        await callback.answer("Произошла ошибка")