import aiosqlite
from aiogram import *
from aiogram.types import *
from handlers.BotAutomaticWork.universal_bot import bot

UpdatesChatInfo = Router()


async def add_chat_info(chat_id, chat_title, chat_username):
    try:
        async with aiosqlite.connect('sup.db') as db:
            await db.execute('INSERT INTO chats (chat_id, chat_title, chat_username) VALUES (?, ?, ?);',
                             (chat_id, chat_title, chat_username))
            await db.commit()
    except aiosqlite.Error as e:
        await bot.send_message(chat_id='-1002315959104', text=f'😢 <b>Упс...Произошла ошибка с базой данных!</b>\n\n<blockquote>{e}</blockquote>', parse_mode='HTML')




async def check_chat_info(chat_id):
    async with aiosqlite.connect('sup.db') as db:
        cursor = await db.execute('SELECT chat_id FROM chats WHERE chat_id = ?', (chat_id,))
        result = await cursor.fetchone()
        return result




async def update_chat_info(chat_id, chat_title, chat_username):
    try:
        async with aiosqlite.connect('sup.db') as db:
            await db.execute('UPDATE chats SET chat_title = ?, chat_username = ? WHERE chat_id = ?',
                             (chat_title, chat_username, chat_id))
            await db.commit()
    except aiosqlite.Error as e:
        await bot.send_message(chat_id='-1002315959104', text=f'😢 <b>Упс...Произошла ошибка с базой данных!</b>\n\n<blockquote>{e}</blockquote>', parse_mode='HTML')



@UpdatesChatInfo.message(F.text.split("\n", 1)[0].lower() == '!обновить чат87654323456')
@UpdatesChatInfo.message(F.text.split("\n", 1)[0].lower() == '.обновить чат87654323456')
@UpdatesChatInfo.message(F.text.split("\n", 1)[0].lower() == '/обновить чат87654323456')
async def UpdatesForChatInfo(msg: Message):
    try:
        chat_id = msg.chat.id
        chat_title = msg.chat.title
        chat_username = msg.chat.username

        if await check_chat_info(chat_id):
            await update_chat_info(chat_id, chat_title, chat_username)
            await msg.answer('✅ Данные о чате обновлены')
        else:
            await add_chat_info(chat_id, chat_title, chat_username)
            await msg.answer('✅ Данные о чате добавлены')
    except Exception as e:
        await msg.answer(f'⚠️ <b>Что-то пошло не так...</b>\n{e}')
