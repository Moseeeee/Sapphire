from aiogram import *
from aiogram.types import *

from handlers.AdminsTools.ChatSettings.PuchCommandSettings.push_command_settingsDB import edit_push_status
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

PushCommandSettings = Router()



@PushCommandSettings.message(F.text.split("\n", 1)[0].lower() == '+уведы о доступе')
@PushCommandSettings.message(F.text.split("\n", 1)[0].lower() == '+уведомления о доступе')
@PushCommandSettings.message(F.text.split("\n", 1)[0].lower() == '+уод')
async def on_push(m: Message):
    if m.chat.type == 'private':
        return
    ChatId = m.chat.id
    if not await auto_check_AccessLevel_for_rang(m.from_user.id, ChatId, 55):
        return

    push_status = 'on'
    await edit_push_status(ChatId, push_status)

    await m.answer('Уведы были включены')


@PushCommandSettings.message(F.text.split("\n", 1)[0].lower() == '-уведы о доступе')
@PushCommandSettings.message(F.text.split("\n", 1)[0].lower() == '-уведомления о доступе')
@PushCommandSettings.message(F.text.split("\n", 1)[0].lower() == '-уод')
async def off_push(m: Message):
    if m.chat.type == 'private':
        return
    ChatId = m.chat.id
    if not await auto_check_AccessLevel_for_rang(m.from_user.id, ChatId, 55):
        return

    push_status = 'off'
    await edit_push_status(ChatId, push_status)
    await m.answer('Уведы были выключены')