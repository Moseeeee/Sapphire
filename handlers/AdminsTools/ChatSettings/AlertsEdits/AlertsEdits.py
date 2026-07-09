from aiogram import *
from aiogram.types import *


from handlers.AdminsTools.ChatSettings.AlertsEdits.AlertsEditsDB import edit_status_e, edit_status_v
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

alerts = Router()





@alerts.message(F.text.split("\n", 1)[0].lower() == '+входы')
async def edit_status_v_on(m: Message):
    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 54):
        return
    chat_id = m.chat.id
    status_v = "yes"
    await edit_status_v(chat_id, status_v)
    await m.answer('Уведомления о входе включены')

@alerts.message(F.text.split("\n", 1)[0].lower() == '-входы')
async def edit_status_v_off(m: Message):
    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 54):
        return
    chat_id = m.chat.id
    status_v = "no"
    await edit_status_v(chat_id, status_v)
    await m.answer('Уведомления о входе выключены')


@alerts.message(F.text.split("\n", 1)[0].lower() == '+выходы')
async def edit_status_e_on(m: Message):
    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 54):
        return
    chat_id = m.chat.id
    status_e = "yes"
    await edit_status_e(chat_id, status_e)
    await m.answer('Уведомления о выходе включены')

@alerts.message(F.text.split("\n", 1)[0].lower() == '-выходы')
async def edit_status_e_off(m: Message):
    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 54):
        return
    chat_id = m.chat.id
    status_e = "no"
    await edit_status_e(chat_id, status_e)
    await m.answer('Уведомления о выходе выключены')

