import logging

from aiogram import Router, F
from aiogram.types import Message

from BotAutomaticWork.users.GenderUtils import g
from BotAutomaticWork.users.checks.acces_commands.check_access_rang import check_user_access, \
    auto_check_AccessLevel_for_rang
from BotAutomaticWork.users.checks.check_UserId.check_users_id import resolve_id
from BotAutomaticWork.users.checks.check_users_status_online.check_online_statusDB import presence_cleanup_task_loop
from BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
# Импортируем ядро генерации текста онлайна (проверь путь):
from handlers.BotAutomaticWork.users.checks.check_users_status_online.user_online_privacy import get_user_online_phrase

privacy_router = Router()
logger = logging.getLogger(__name__)


async def _set_online_mode(user_id: int, mode: str):
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            'UPDATE users SET online_mode = $1 WHERE user_id = $2',
            mode, user_id
        )


# =====================================================================
# 1. ПЕРЕКЛЮЧАТЕЛИ РЕЖИМОВ ПРИВАТНОСТИ
# =====================================================================

# ВАЖНО: ловим строго раньше, чем "+мой онлайн"!
@privacy_router.message(F.text.lower() == "+мой онлайн недавно")
async def cmd_privacy_approx(message: Message):
    if message.chat.type != 'private':
        if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 89):
            return

    await _set_online_mode(message.from_user.id, 'approx')
    await message.answer("🕶 Настройка приватности: Примерный онлайн")


@privacy_router.message(F.text.lower() == "+мой онлайн")
async def cmd_privacy_exact(message: Message):
    if message.chat.type != 'private':
        if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 89):
            return

    await _set_online_mode(message.from_user.id, 'exact')
    await message.answer("👁 Настройка приватности: Точный онлайн")


@privacy_router.message(F.text.lower() == "-мой онлайн")
async def cmd_privacy_hidden(message: Message):
    if message.chat.type != 'private':
        if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 89):
            return

    await _set_online_mode(message.from_user.id, 'hidden')
    await message.answer(
        "🕵️‍♂️ Настройка приватности: Скрытый онлайн")


# =====================================================================
# 2. КОМАНДА: твой онлайн {@username / реплай} [С соблюдением правил]
# =====================================================================
@privacy_router.message(F.text.lower().startswith("твой онлайн"))
async def cmd_show_user_online(m: Message):
    try:

        if m.chat.type != 'private':
            if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 88):
                return

        if m.reply_to_message:
            UserId = m.reply_to_message.from_user.id
        else:
            mention = m.text[len("твой онлайн"):].strip()
            if not mention:
                await m.answer(
                    "❌ <b>Неверный формат команды!</b>\nИспользуйте: твой онлайн {@username} или ответьте на сообщение",
                    parse_mode='HTML')
                return
            UserId = await resolve_id(m, mention)

        if not UserId:
            await m.answer("❌ <b>Пользователь не найден в базе!</b>", parse_mode='HTML')
            return

        # Запрашиваем статус в обычном режиме
        gender = await get_user_gender(UserId)
        genderr = f'б{g("ыл", gender)}'
        phrase = await get_user_online_phrase(UserId, genderr, bypass_privacy=False)

        user_link = await user_link_global(UserId)

        await m.answer(f"Онлайн <b>{user_link}:</b> {phrase}", parse_mode='HTML', disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Ошибка в команде твой онлайн: {e}", exc_info=True)


# =====================================================================
# 3. КОМАНДА: чек онлайн {@username / реплай} [Точный админ-обход]
# =====================================================================
@privacy_router.message(F.text.lower().startswith("чек твой онлайн"))
async def cmd_check_user_online_exact(m: Message):
    try:

        if not await check_user_access(m.from_user.id, 1):
            return

        if m.reply_to_message:
            UserId = m.reply_to_message.from_user.id
        else:
            mention = m.text[len("чек твой онлайн"):].strip()
            if not mention:
                await m.answer(
                    "❌ <b>Неверный формат команды!</b>\nИспользуйте: чек онлайн {@username} или ответьте на сообщение",
                    parse_mode='HTML')
                return
            UserId = await resolve_id(m, mention)

        if not UserId:
            await m.answer("❌ <b>Пользователь не найден в базе!</b>", parse_mode='HTML')
            return

        # Запрашиваем статус в режиме обхода приватности (bypass_privacy=True)
        gender = await get_user_gender(UserId)
        genderr = f'б{g("ыл", gender)}'
        phrase = await get_user_online_phrase(UserId, genderr, bypass_privacy=True)

        user_link = await user_link_global(UserId)

        await m.answer(f"Онлайн <b>{user_link}:</b> {phrase}", parse_mode='HTML', disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Ошибка в команде чек онлайн: {e}", exc_info=True)


#@privacy_router.startup()
async def startup_online_cache_cleanup():
    await presence_cleanup_task_loop()