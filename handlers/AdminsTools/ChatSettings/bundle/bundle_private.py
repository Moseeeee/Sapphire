import logging
from aiogram import Router, F, types

from handlers.AdminsTools.ChatSettings.bundle.bundle_db import create_bundle, get_user_bundles, get_bundle_by_name, \
    set_selected_bundle, get_selected_bundle, get_bundle_info, delete_bundle
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global


logger = logging.getLogger(__name__)
private_bundle = Router()


@private_bundle.message(F.text.regexp(r'(?i)^[!./]создать\s+связку\s+\S+'))
async def cmd_create_bundle(message: types.Message):
    if message.chat.type != 'private':
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Укажите название связки.\nПример: /создать связку Модерация")
        return
    name = args[2].strip()
    if len(name) > 50:
        await message.answer("Название должно быть не более 50 символов.")
        return
    bundle_id = await create_bundle(message.from_user.id, name)
    if bundle_id:
        await message.answer(
            f"✅ Связка «{name}» создана!\n"
            f"Теперь в каждом нужном чате напишите: <code>+связка {name}</code>",
            parse_mode="HTML"
        )
    else:
        await message.answer(f"Связка «{name}» уже существует.")


@private_bundle.message(F.text.regexp(r'(?i)^[!./]мои\s+связки$'))
async def cmd_my_bundles(message: types.Message):
    if message.chat.type != 'private':
        return
    bundles = await get_user_bundles(message.from_user.id)
    if not bundles:
        await message.answer("📭 Нет связок. Создайте: /создать связку Название")
        return
    text = "📦 <b>Ваши связки:</b>\n\n"
    for b in bundles:
        text += f"<b>{b['name']}</b> – чатов: {b['chat_count']}\n"
    await message.answer(text, parse_mode="HTML")


@private_bundle.message(F.text.regexp(r'(?i)^[!./]выбрать\s+связку\s+\S+'))
async def cmd_select_bundle(message: types.Message):
    if message.chat.type != 'private':
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Укажите название: /выбрать связку Модерация")
        return
    name = args[2].strip()
    bundle_id = await get_bundle_by_name(message.from_user.id, name)
    if not bundle_id:
        await message.answer(f"Связка «{name}» не найдена.")
        return
    await set_selected_bundle(message.from_user.id, bundle_id)
    await message.answer(f"✅ Связка «{name}» выбрана по умолчанию.")


@private_bundle.message(F.text.regexp(r'(?i)^[!./]связка\s+инфо(\s+\S+)?$'))
async def cmd_bundle_info(message: types.Message):
    if message.chat.type != 'private':
        return
    parts = message.text.split(maxsplit=2)
    name = parts[2].strip() if len(parts) > 2 else None
    bundle_id = None
    if name:
        bundle_id = await get_bundle_by_name(message.from_user.id, name)
    else:
        bundle_id = await get_selected_bundle(message.from_user.id)
    if not bundle_id:
        await message.answer("Связка не найдена. Укажите название или выберите через /выбрать связку")
        return
    info = await get_bundle_info(bundle_id)
    if not info:
        await message.answer("Ошибка.")
        return
    owner_link = await user_link_global(info['owner_id'])
    created = info['created_at'].strftime("%d.%m.%Y %H:%M") if info['created_at'] else "?"
    chats = info['chats']
    text = f"📌 <b>Связка «{info['name']}»</b>\n"
    text += f"Владелец: {owner_link}\nСоздана: {created}\nЧатов: {len(chats)}\n\n"
    #if chats:
     #   text += "📋 <b>Чаты:</b>\n"
      #  for chat_id in chats[:20]:
       #     try:
        #        chat = await bot.get_chat(chat_id)
         #       if str(chat_id).startswith('-100'):
          #          link = f"https://t.me/c/{str(chat_id)[4:]}"
           #         text += f"• <a href='{link}'>{chat.title or 'Чат'}</a>\n"
            #    else:
             #       text += f"• {chat.title or chat_id}\n"
           # except:
            #    text += f"• {chat_id}\n"
       # if len(chats) > 20:
        #    text += f"... и ещё {len(chats)-20}"
   # else:
    #    text += "⚠️ Чаты не добавлены."
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@private_bundle.message(F.text.regexp(r'(?i)^[!./]удалить\s+связку\s+\S+'))
async def cmd_delete_bundle(message: types.Message):
    if message.chat.type != 'private':
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Укажите название: /удалить связку Модерация")
        return
    name = args[2].strip()
    bundle_id = await get_bundle_by_name(message.from_user.id, name)
    if not bundle_id:
        await message.answer(f"Связка «{name}» не найдена.")
        return
    await delete_bundle(bundle_id)
    await message.answer(f"✅ Связка «{name}» удалена.")