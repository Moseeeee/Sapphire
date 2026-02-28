from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

sapphire_commands = Router()



@sapphire_commands.message(F.text.func(lambda text: text and text.split("\n", 1)[0].lower() in ['.команды',
                                                                             '/команды',
                                                                             '!команды',
                                                                             'команды']))
@sapphire_commands.message(Command("commands"))
async def help_sapphire_commands(m: Message):
    if m.chat.type == 'private':
        await m.reply(
            '<tg-emoji emoji-id="5282843764451195532">📋</tg-emoji> <a href="https://teletype.in/@sap_sp/commands">Список команд «Sapphire | Chat Manager»</a>')
        return


    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 77):
        return

    await m.reply(
        '<tg-emoji emoji-id="5282843764451195532">📋</tg-emoji> <a href="https://teletype.in/@sap_sp/commands">Список команд «Sapphire | Chat Manager»</a>')




@sapphire_commands.message(F.text.func(lambda text: text and text.split("\n", 1)[0].lower() in ['.репорты помощь',
                                                                                                '/репорты помощь',
                                                                                                '!репорты помощь',
                                                                                                'репорты помощь',
                                                                                                '!помощь репорты',
                                                                                                '.помощь репорты',
                                                                                                '/помощь репорты',
                                                                                                'помощь репорты']))
@sapphire_commands.message(Command("reports_settings"))
async def help_reports_command(m: Message):
    if m.chat.type == 'private':
        await m.reply(
            '<tg-emoji emoji-id="5282843764451195532">📋</tg-emoji> <a href="https://teletype.in/@sap_sp/reports">Гайд по настройке системы репортов</a>')
        return


    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 77):
        return

    await m.reply(
                    '<tg-emoji emoji-id="5282843764451195532">📋</tg-emoji> <a href="https://teletype.in/@sap_sp/reports">Гайд по настройке системы репортов</a>')



@sapphire_commands.message(Command("resources"))
async def full_sapphire_commands_help(m: Message):
    if m.chat.type == 'private':
        text = '<tg-emoji emoji-id="5271604874419647061">🔗</tg-emoji> <b>Полезные ссылки и гайды по боту</b>\n'
        text += '1.  <a href="https://teletype.in/@sap_sp/reports">Гайд по настройке системы репортов</a>'


        await m.reply(text
                      )



