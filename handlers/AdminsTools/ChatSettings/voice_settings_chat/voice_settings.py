from aiogram import *
from aiogram.types import *

from handlers.AdminsTools.ChatSettings.voice_settings_chat.voice_settingsDB import edit_status_voice_settings
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

settings_voice = Router()





@settings_voice.message(F.text.split("\n", 1)[0].lower() == '+гс')
async def edit_status_voice_settings_on(m: Message):
    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 79):
        return
    chat_id = m.chat.id
    status_v = "yes"
    await edit_status_voice_settings(chat_id, status_v)
    await m.answer('✅ Распознание голосовых включено')


@settings_voice.message(F.text.split("\n", 1)[0].lower() == '-гс')
async def edit_status_voice_settings_off(m: Message):
    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 79):
        return

    chat_id = m.chat.id
    status = "no"
    await edit_status_voice_settings(chat_id, status)
    await m.answer('❌ Распознавание голосовых выключено')



