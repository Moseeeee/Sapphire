from aiogram import *
from aiogram.types import *

from handlers.AdminsTools.ChatSettings.AntiSpamSettings.AntiSpamSettingsDB import edit_antispam_status
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

ACSettings = Router()



@ACSettings.message(F.text.split("\n", 1)[0].lower() == '+антиспам')
async def on_push(m: Message):
    if m.chat.type == 'private':
        return

    ChatId = m.chat.id

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, ChatId, 46):
        return

    antispam_status = 'on'
    await edit_antispam_status(ChatId, antispam_status)

    await m.answer('Защита антиспама включена')


@ACSettings.message(F.text.split("\n", 1)[0].lower() == '-антиспам')
async def off_push(m: Message):
    if m.chat.type == 'private':
        return
    ChatId = m.chat.id

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, ChatId, 46):
        return

    antispam_status = 'off'
    await edit_antispam_status(ChatId, antispam_status)
    await m.answer('Защита антиспама отключена')