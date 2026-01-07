from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandObject, Command
from handlers.BotAutomaticWork.universal_bot import bot


cs = Router()










@cs.message(Command(commands=["название6654443334567788909097765445678900998765"],prefix="+"))
async def nazvanie(message: Message, command: CommandObject):
    chat_id = message.chat.id
    user_id = message.from_user.id
    chat_member = await bot.get_chat_member(chat_id, user_id)
    admin = await message.bot.get_chat_member(chat_id, user_id)
    if admin.status == 'owner' or admin.status == 'administrator' and admin.can_change_info:
        ags=command.args
        await bot.set_chat_title(chat_id=message.chat.id,title=ags)
        await message.answer(f'✅Название чата изменено на<b>«{ags}»</b>',parse_mode='HTML')
        if chat_member.status == ['member']:
           await message.answer('Вы не администратор чата, поэтому данная команда вам не доступна.')
    else:
        await message.answer('❌У вас нет право администратора <b>«Изменения информации группы»</b>',parse_mode='HTML')
