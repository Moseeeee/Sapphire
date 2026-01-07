import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

TARGET = -1001667453682
chat_id = -1002034794371
app = Client("my_account")


@app.on_message(filters.text)
async def teg_on(client: Client, message: Message):
    await message.reply('хахахах')

app.run()