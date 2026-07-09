import html
import re

from aiogram import Router, F, types
from aiogram.enums import ChatMemberStatus
# Добавляем TelegramForbiddenError для обработки 403 ошибки (кик из чата)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from AdminsTools.ChatSettings.chats_migrations.migrationDB import transfer_chat_data
from BotAutomaticWork.AddChatsBot.link.chats_global_link import chat_global_link
from BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

migration_router = Router()

COMMAND_REGEXP = r'(?i)^[!./]перенести\s+(настройки|стату|всё)\s+(-?\d+)'


@migration_router.message(F.text.regexp(COMMAND_REGEXP))
async def cmd_transfer_chat(message: types.Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 98):
        return

    match = re.match(COMMAND_REGEXP, message.text.strip())
    if not match:
        return

    sub_command = match.group(1).lower()
    try:
        old_chat_id = int(match.group(2))
    except ValueError:
        await message.answer("❌ Указан неверный формат ID старого чата.", parse_mode="HTML")
        return

    new_chat_id = message.chat.id
    user_id = message.from_user.id

    # 1. Защита от миграции "в самого себя"
    if old_chat_id == new_chat_id:
        await message.answer("❌ Идентификаторы чатов не должны совпадать.", parse_mode="HTML")
        return

    # 2. ПРОВЕРКА ПРАВ: Текущий (новый) чат
    try:
        new_chat_member = await message.bot.get_chat_member(chat_id=new_chat_id, user_id=user_id)
        if new_chat_member.status != ChatMemberStatus.CREATOR:
            await message.answer("❌ Вы должны быть <b>Владельцем</b> этого чата для выполнения переноса.",
                                 parse_mode="HTML")
            return
    except TelegramBadRequest:
        await message.answer("❌ Не удалось проверить ваши права в текущем чате.", parse_mode="HTML")
        return

    # 3. ПРОВЕРКА ПРАВ И ПРИСУТСТВИЯ БОТА: Старый чат
    try:
        old_chat_member = await message.bot.get_chat_member(chat_id=old_chat_id, user_id=user_id)
        if old_chat_member.status != ChatMemberStatus.CREATOR:
            await message.answer("❌ Вы должны быть <b>Владельцем</b> старого чата для выполнения переноса.",
                                 parse_mode="HTML")
            return

    except TelegramForbiddenError:
        # Сюда прилетит ошибка, если бота кикнули из супергруппы
        await message.answer(
            "❌ <b>Перенос данных невозможен!</b>\n\n"
            "Меня <b>удалили</b> из старого чата. Пожалуйста, "
            "добавьте меня обратно туда, иначе проверить владельцев и перенести данные не получится.",
            parse_mode="HTML"
        )
        return

    except TelegramBadRequest:
        # Сюда прилетит, если чат вообще не существует или ID неверный
        await message.answer(
            "❌ <b>Ошибка доступа к старому чату!</b>\n"
            "Убедитесь, что ID указан верно и я нахожусь в том чате.",
            parse_mode="HTML"
        )
        return

    # Определение режима работы
    mode = 'all'
    if sub_command == 'настройки':
        mode = 'settings'
    elif sub_command == 'стату':
        mode = 'stats'

    old_chat_link = await chat_global_link(old_chat_id)
    new_chat_link = await chat_global_link(new_chat_id)

    # Начальное сообщение
    status_msg = await message.answer(
        f"🔄 <b>Запуск процесса миграции</b>\n"
        f"Из чата: {old_chat_link}\n"
        f"⏳ <i>Пожалуйста, подождите...</i>",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

    # Итерация по генератору изменений базы данных
    async for percent, status_text in transfer_chat_data(old_chat_id, new_chat_id, mode):
        if percent == -1:
            await status_msg.edit_text(
                f"🛑 <b>Критическая ошибка миграции!</b>\n\n{status_text}",
                parse_mode="HTML"
            )
            return

    # Итоговый HTML-баннер о завершении
    finish_banner = (
        f"🎉 <b>Миграция успешно завершена!</b>\n"
        f"Текущий чат {new_chat_link} получил обновленные данные из {old_chat_link}.\n"
        f"Выбранный режим: <code>{html.escape(sub_command)}</code>"
    )

    try:
        await status_msg.edit_text(finish_banner,
                                   parse_mode="HTML",
                                   disable_web_page_preview=True)
    except Exception:
        await message.answer(finish_banner,
                             parse_mode="HTML",
                             disable_web_page_preview=True)