import logging

from aiogram import Router, F
from aiogram.types import *
from aiogram.filters import Command

from handlers.BotAutomaticWork.Gonfig.config import AGENT_CHAT_ID_CheckTextApprovals
from handlers.AdminsTools.ChatSettings.rules.rulesDB import (
    set_rules,
    delete_rules_text,
    check_rules_text
)
from handlers.BotAutomaticWork.AddChatsBot.link.chats_global_link import chat_global_link
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.AgentsFeatures.CheckTextApprovals.CheckTextApprovalsDB import get_pending_moderation, add_pending_moderation
from handlers.AgentsFeatures.CheckTextApprovals.CheckTextApprovalsUtils import contains_links, get_moderation_keyboard
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_global
from handlers.BotAutomaticWork.universal_bot import bot

rul = Router()


logger = logging.getLogger(__name__)

@rul.message(lambda m: m.text and m.text.lower().startswith("+правила"))
async def new_rules_text(msg: Message):
    try:

        chat_id = msg.chat.id
        user_id = msg.from_user.id

        if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 47):
            return


        # Проверки
        if msg.chat.type == 'private':
            return


        if len(msg.html_text.split("\n", 1)) < 2:
            await msg.reply('⚠️ Укажите текст правил после команды, начиная с новой строки.')
            return




        # Извлекаем текст правил
        rules_text = msg.html_text.split("\n", 1)[1].strip()

        if not rules_text:
            await msg.reply('⚠️ Текст правил не может быть пустым.')
            return

        chat_link = await chat_global_link(chat_id)
        user_link = await user_link_global(user_id)

        check_links_text = contains_links(rules_text)


        # Если есть ссылки - отправляем на модерацию
        if check_links_text:
            try:
                admin_message = await msg.bot.send_message(
                    AGENT_CHAT_ID_CheckTextApprovals,
                    f"📋 <b>Новые правила на проверку</b>\n\n"
                    f"💬 <b>Текст:</b>\n{rules_text}\n\n"
                    f"ℹ️ Некая информация:\n"
                    f"<b>Чат:</b> {chat_link}\n"
                    f"<b>Пользователь:</b> {user_link}",
                    reply_markup=get_moderation_keyboard(chat_id, user_id, "rules"),
                    parse_mode='HTML',
                    disable_web_page_preview=True
                )

                await msg.reply('⚠️ Текст отправлен на проверку, ожидайте.')

                # Общая логика для обновления/создания записи модерации
                existing = await get_pending_moderation(chat_id, 'rules')

                if existing:
                    try:
                        await msg.bot.delete_message(AGENT_CHAT_ID_CheckTextApprovals, existing['admin_message_id'])
                    except Exception:
                        pass  # Игнорируем ошибки удаления старого сообщения

                # Создаем или обновляем запись
                await add_pending_moderation(
                    chat_id,
                    'rules',
                    rules_text,
                    msg.message_id,
                    admin_message.message_id,
                    user_id
                )

            except Exception as e:
                await msg.reply('❌ Ошибка при отправке на модерацию.')
                logger.error(e, exc_info=True)
                return

        else:
            # Если ссылок нет - сразу сохраняем
            try:
                await set_rules(chat_id, rules_text)
                await msg.reply('✅ Правила установлены')
            except Exception as e:
                await msg.reply('❌ Ошибка при сохранении правил.')
                logger.error(e, exc_info=True)

    except Exception as e:
        await msg.reply('❌ Произошла ошибка при обработке команды.')
        logger.error(e, exc_info=True)




@rul.message(F.text.split("\n", 1)[0].lower() == "-правила")
async def del_rules_text(msg: Message):
    try:
        if msg.chat.type == 'private':
            return

        chat_id = msg.chat.id
        user_id = msg.from_user.id

        if not await auto_check_AccessLevel_for_rang(user_id, chat_id, 47):
            return

        che_rules_text = await check_rules_text(chat_id)
        if che_rules_text:
            await delete_rules_text(chat_id)
            await msg.reply('✅ Правила чата удалены')
        else:
            await msg.reply('🤓 Правил чата и не было')
            return
    except Exception as e:
        await msg.reply(f'<b>Произошла ошибка:</b>\n\n{e}', parse_mode='HTML')
        logger.error(e, exc_info=True)


@rul.message(lambda m: m.text and m.text.lower().startswith(('.правила',
                                                             '!правила',
                                                             '/правила')))
@rul.message(Command("rules"))
async def rules_text(msg: Message):
    try:
        if msg.chat.type == 'private':
            return

        chat_id = msg.chat.id

        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, chat_id, 48):
            return


        rules_text = await check_rules_text(chat_id)

        if rules_text:
            await bot.send_message(chat_id=chat_id, text=f'💬 <b>Правила чата:</b>\n{rules_text}',
                                   parse_mode='HTML', disable_web_page_preview=True)
        else:
            await bot.send_message(chat_id=chat_id, text='❌ правила чата не установлены')
            return
    except Exception as e:
        await msg.reply(f'<b>Произошла ошибка:</b>\n\n{e}', parse_mode='HTML', disable_web_page_preview=True)
        logger.error(e, exc_info=True)



