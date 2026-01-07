from aiogram import Router, F
from aiogram.types import *
from datetime import datetime

from handlers.AgentsFeatures.server_info import get_db_ping_ms
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
import logging, asyncio
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import check_agent_access

pingin = Router()
logger = logging.getLogger(__name__)


async def process_ping_command(message: Message, command_type: str):
    """Общая функция обработки ping/puy команд"""
    try:
        ##user_id = message.from_user.id
        ##agent_rang = await check_agent_access(user_id)
        ##if agent_rang <= 0:
            ##return

        db_ping_str = await get_db_ping_ms()
        db_ping = int(db_ping_str)

        # Измерение ping до бд
        if db_ping < 5:
            skorost = 'Отклик бд отличный!'
            emodji = '🟢'
        elif db_ping < 8:
            skorost = 'Отклик бд быстрый'
            emodji = '🟡'
        elif db_ping < 15:
            skorost = 'Отклик бд медленный'
            emodji = '🟠'
        elif db_ping < 25:
            skorost = 'Отклик бд очень медленный'
            emodji = '🔴'
        else:
            skorost = 'Отклик бд ужасный!'
            emodji = '💔'


        # Измерение server ping
        a = datetime.now()
        message_ping = await message.reply("Проверка...")
        b = datetime.now()
        server_ping = (b - a).microseconds // 1000

        # Определение статуса ping до Telegram
        if server_ping < 300:
            tg = f'💬 Ответ бота <code>{server_ping} мс</code>\n'
            error = ''
        elif server_ping < 800:
            tg = f'⚠️ У бота наблюдается задержка <code>{server_ping} мс</code>\n'
            error = ''
        elif server_ping < 1400:
            tg = f'❗ Бот немного перегружен запросами, поэтому он может долго не отвечать (примерно 5-40 секунд) <code>{server_ping} мс</code>\n'
            error = '\n\n🐞 Флудить командами бота нежелательно, потому что может возникнуть ошибка <code>FloodWait</code>.'
        else:
            tg = f'‼️ Бот перегружен запросами. (бот может длительное время игнорировать пользователей) <code>{server_ping} мс</code>\n'
            error = '\n\n🐞 Флудить командами бота нежелательно, потому что может возникнуть ошибка <code>FloodWait</code>.'

        # Формирование ответа в зависимости от типа команды
        if command_type == "ping":
            title = f'🏓 <b>ПОНГ</b>'
        else:  # puy
            title = f'🔫 <b>ПАУ</b>'

        await message_ping.edit_text(
            f'{title}\n'
            f'{tg}'
            f'{emodji} {skorost} \n'
            f'{error}',
            parse_mode='HTML'
        )

    except Exception as e:
        await message.reply(f'⌛ Попробуйте позже.\n\n<blockquote>{e}</blockquote>', parse_mode='HTML')


# Обработчики команд
@pingin.message(
    (F.text.split("\n", 1)[0].lower().strip() == "пинг") |
    (F.text.split("\n", 1)[0].lower().strip() == ".пинг") |
    (F.text.split("\n", 1)[0].lower().strip() == "!пинг") |
    (F.text.split("\n", 1)[0].lower().strip() == "сап пинг")
)
async def ping(message: Message):
    await process_ping_command(message, "ping")


@pingin.message(
    (F.text.split("\n", 1)[0].lower().strip() == "пиу") |
    (F.text.split("\n", 1)[0].lower().strip() == ".пиу") |
    (F.text.split("\n", 1)[0].lower().strip() == "!пиу") |
    (F.text.split("\n", 1)[0].lower().strip() == "сап пиу")
)
async def puy(message: Message):
    await process_ping_command(message, "puy")




@pingin.message(F.text.split("\n", 1)[0].lower() == '1111111111111111.................7754311111ф//////////////ффаолдждлорпавууе4еп6гн7ш8щ9д8грт11113456411111111888888643')
async def status_command(m: Message):

    start = datetime.now()
    message = await m.answer('🏓⚾=====🏓')
    await message.edit_text('🏓=⚾====🏓')
    await message.edit_text('🏓==⚾===🏓')
    await message.edit_text('🏓===⚾==🏓')
    await message.edit_text('🏓====⚾=🏓')
    await message.edit_text('🏓=====⚾🏓')
    end = datetime.now()
    ping1_ms = (end - start).microseconds // 1000

    await asyncio.sleep(15)
    start = datetime.now()
    await message.edit_text('🏓====⚾=🏓')
    await message.edit_text('🏓===⚾==🏓')
    await message.edit_text('🏓==⚾===🏓')
    await message.edit_text('🏓=⚾====🏓')
    await message.edit_text('🏓⚾=====🏓')
    end = datetime.now()
    ping2_ms = (end - start).microseconds // 1000
    await asyncio.sleep(15)
    start = datetime.now()
    await message.edit_text('🏓=⚾====🏓')
    await message.edit_text('🏓==⚾===🏓')
    await message.edit_text('🏓===⚾==🏓')
    await message.edit_text('🏓====⚾=🏓')
    await message.edit_text('🏓=====⚾🏓')
    end = datetime.now()
    ping3_ms = (end - start).microseconds // 1000
    await asyncio.sleep(15)
    start = datetime.now()
    await message.edit_text('🏓====⚾=🏓')
    await message.edit_text('🏓===⚾==🏓')
    await message.edit_text('🏓==⚾===🏓')
    await message.edit_text('🏓=⚾====🏓')
    await message.edit_text('🏓⚾=====🏓')
    end = datetime.now()
    ping4_ms = (end - start).microseconds // 1000
    await asyncio.sleep(10)
    await message.edit_text(f'✅ <b>я закончил</>\n1️⃣ <code>{ping1_ms}</>\n2️⃣ <code>{ping2_ms}</>\n3️⃣ <code>{ping3_ms}</>\n4️⃣ <code>{ping4_ms}</>')
