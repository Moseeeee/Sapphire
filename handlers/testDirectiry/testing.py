from aiogram import *
from aiogram.types import *
from handlers.BotAutomaticWork.universal_bot import bot

SlechCommands = Router()




@SlechCommands.message(F.text.split("\n", 1)[0].lower() == "+слеш команды админ")
@SlechCommands.message(F.text.split("\n", 1)[0].lower() == "!слеш команды админ")
@SlechCommands.message(F.text.split("\n", 1)[0].lower() == ".слеш команды админ")
@SlechCommands.message(F.text.split("\n", 1)[0].lower() == "/слеш команды админ")
async def add_admin_slech_command(msg: Message):
    try:
        if msg.chat.type == 'private':
            return

        ChatId = msg.chat.id

        #if not await auto_check_AccessLevel_for_rang(msg.from_user.id, ChatId, 0):
            #return

        admin_commands = [
            types.BotCommand(command="list_connected_chats", description="🗃️ Просмотр привязанных чатов"),
            types.BotCommand(command="report_stats", description="📊 Статистика проверок репортов"),
            types.BotCommand(command="report_list", description="📖 Не проверенные репорты")
        ]

        await bot.set_my_commands(
            commands=admin_commands,
            scope=BotCommandScopeChat(chat_id=ChatId)
        )

        await msg.answer('Установлены слеш-команды для админов')

    except Exception as e:
        await msg.reply(f'<b>Произошла ошибка:</b>\n\n{e}', parse_mode='HTML', disable_web_page_preview=True)





@SlechCommands.message(F.text.split("\n", 1)[0].lower() == "+слеш команды")
@SlechCommands.message(F.text.split("\n", 1)[0].lower() == "!слеш команды")
@SlechCommands.message(F.text.split("\n", 1)[0].lower() == ".слеш команды")
@SlechCommands.message(F.text.split("\n", 1)[0].lower() == "/слеш команды")
async def add_users_slech_command(msg: Message):
    try:
        if msg.chat.type == 'private':
            return

        ChatId = msg.chat.id

        #if not await auto_check_AccessLevel_for_rang(msg.from_user.id, ChatId, 0):
            #return

        user_commands = [
            types.BotCommand(command="rules", description="📖 Правила чата"),
            types.BotCommand(command="report", description="😡 Пожаловаться на сообщение"),
            types.BotCommand(command="admins", description="👮🏻 Администраторы чата")
        ]

        await bot.set_my_commands(
            commands=user_commands,
            scope=BotCommandScopeChat(chat_id=ChatId)
        )

        await msg.answer('Установлены слеш-команды')

    except Exception as e:
        await msg.reply(f'<b>Произошла ошибка:</b>\n\n{e}', parse_mode='HTML', disable_web_page_preview=True)


@SlechCommands.message(F.text.split("\n", 1)[0].lower() == "-слеш команды")
@SlechCommands.message(F.text.split("\n", 1)[0].lower() == "!отключить слеш команды")
@SlechCommands.message(F.text.split("\n", 1)[0].lower() == "выкл слеш команды")
async def delete_slech_command(msg: Message):
    try:
        if msg.chat.type == 'private':
            return

        ChatId = msg.chat.id

        #if not await auto_check_AccessLevel_for_rang(msg.from_user.id, ChatId, 0):
            #return

        await bot.set_my_commands([])

        await msg.answer('Слеш-команды удалены')

    except Exception as e:
        await msg.reply(f'<b>Произошла ошибка:</b>\n\n{e}', parse_mode='HTML', disable_web_page_preview=True)