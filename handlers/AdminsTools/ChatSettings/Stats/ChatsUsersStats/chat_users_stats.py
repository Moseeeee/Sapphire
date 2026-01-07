# handlers/AdminsTools/ChatSettings/Stats/ChatsUsersStats/router.py
from aiogram import Router, types, F
from handlers.AdminsTools.ChatSettings.Stats.ChatsUsersStats.chat_users_statsDB import get_period_stats
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

CUS = Router()  # CUS = Chat Users Stats


@CUS.message(lambda m: m.text and m.text.lower().startswith(('.участники инфо',
                                                             '!участники инфо',
                                                             '/участники инфо')))
async def participants_info_day(message: types.Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 57):
        return

    """Статистика за день (по умолчанию)"""
    chat_id = message.chat.id
    result = await get_period_stats(chat_id, 'день')
    await message.answer(result, parse_mode='HTML')


@CUS.message(F.text.split("\n", 1)[0].lower().startswith("!участники инфо "))
@CUS.message(F.text.split("\n", 1)[0].lower().startswith(".участники инфо "))
@CUS.message(F.text.split("\n", 1)[0].lower().startswith("/участники инфо "))
async def participants_info_period(message: types.Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 57):
        return

    """Статистика за выбранный период"""
    parts = message.text.lower().split()
    if len(parts) < 3:
        await message.answer("❌ Укажите период: день, неделя, месяц, год, всего")
        return

    period_input = parts[2]
    # Поддержка "вся" как альтернатива "всего"
    period = "всего" if period_input == "вся" else period_input

    if period not in {'день', 'неделя', 'месяц', 'год', 'всего'}:
        await message.answer("❌ Неверный период. Используйте: день, неделя, месяц, год, всего")
        return

    result = await get_period_stats(message.chat.id, period)
    await message.answer(result, parse_mode='HTML')