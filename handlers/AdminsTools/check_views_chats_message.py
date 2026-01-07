import re

from aiogram import Router, F
from aiogram.types import Message
from handlers.BotAutomaticWork.AddChatsBot.link.chats_global_link import chat_global_link
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

CVCM = Router() #CVCM = первые буквы файла

async def send_message(chat_link):

    channel_message = await bot.send_message('-1003223396462',
                                             f"👀 Проверка текущего онлайна в «{chat_link}»\n\nЧтобы узнать текущий статус проверьте просмотры  ↘️",
                                             parse_mode='HTML',
                                             disable_web_page_preview=True)
    return channel_message

@CVCM.message(F.text.regexp(re.compile(r'^[!/.]актив(\s|$)', re.IGNORECASE)))
async def send_activity(message: Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 57):
        return

    chat_id = message.chat.id
    chat_link = await chat_global_link(chat_id)
    channel_message = await send_message(chat_link)
    await bot.forward_message(chat_id=chat_id,
                              from_chat_id=channel_message.chat.id,
                              message_id=channel_message.message_id,)