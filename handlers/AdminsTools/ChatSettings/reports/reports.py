

import asyncio
import logging
import time
from datetime import datetime, timedelta

from aiogram import *
from aiogram.types import *
from aiogram.filters import Command

from handlers.AdminsTools.ChatSettings.reports.reportsDB import (
    add_chat_reports,
    all_del_chat_reports_with_info,
    del_chat_report,
    add_info_for_report,
    del_info_for_report,
    check_report_chat_id,
    check_report_chats,
    get_all_reports_for_user_reply,
    get_all_reports_for_user,
    search_report_chat_name,
    search_report_chat_link,
    is_reported_chat,
    is_report_chat,
    check_existing_pair, update_moderation_stats
)
from handlers.AdminsTools.CommandsModerations.bans.ban import perform_ban
from handlers.AdminsTools.CommandsModerations.mute.mute import perform_mute
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.SeasonsEmojiUtils import get_emoji
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender
from handlers.BotAutomaticWork.universal_bot import bot

report = Router()

report_cooldown = {}
REPORT_COOLDOWN_MAX_TIME = 40

logger = logging.getLogger(__name__)

async def time_reported(user_id, chat_id, max_time=REPORT_COOLDOWN_MAX_TIME):
    current_time = time.time()
    key = (user_id, chat_id)

    # Очистка устаревших записей
    expired_keys = []
    for k, last_time in list(report_cooldown.items()):
        if current_time - last_time > max_time:
            expired_keys.append(k)
    for k in expired_keys:
        del report_cooldown[k]

    if key in report_cooldown:
        last_time = report_cooldown[key]
        elapsed_time = current_time - last_time

        if elapsed_time < max_time:
            return False

    report_cooldown[key] = current_time
    return True


async def time_reported(user_id, chat_id, max_time=40):
    current_time = time.time()
    key = (user_id, chat_id)

    if key in report_cooldown:
        last_time = report_cooldown[key]
        elapsed_time = current_time - last_time

        if elapsed_time < max_time:
            return False


    report_cooldown[key] = current_time
    return True






@report.message(F.text.lower().startswith('+репорты из'))
@report.message(F.text.lower().startswith('!+репорты из'))
@report.message(F.text.lower().startswith('.+репорты из'))
@report.message(F.text.lower().startswith('сап +репорты из'))
async def add_db_chat(msg: Message):
    try:
        if msg.chat.type == 'private':
            return

        report_chat = msg.chat.id

        # Проверяем права в чате-получателе репортов
        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, report_chat, 37):
            return

        text = msg.text.strip().lower()

        if 'из' not in text:
            await msg.answer("⚠️ Укажите чат после 'из'")
            return

        _, reported_chat_str = text.split('из', 1)
        reported_chat_str = reported_chat_str.strip()

        if not reported_chat_str:
            await msg.answer("❌ Не указан CHAT_ID")
            return

        try:
            reported_chat = int(reported_chat_str)
        except ValueError:
            await msg.answer("🚫 CHAT_ID должен быть числом (например: -100123456789)")
            return

        # Проверяем права в чате-источнике репортов
        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, reported_chat, 37):
            await msg.answer("❌ У вас нет прав в указанном чате")
            return

        chat_title = await search_report_chat_name(reported_chat)
        if not chat_title:
            await msg.answer("❌ Указанный чат не найден в базе данных")
            return

        if reported_chat == report_chat:
            await msg.answer("🔒 Нельзя привязать чат к самому себе")
            return

        if await is_reported_chat(report_chat):
            await msg.answer("❌ Этот чат уже получает репорты из других чатов и не может быть источником репортов")
            return

        if await is_report_chat(reported_chat):
            await msg.answer("❌ Указанный чат уже является чат-репортом и не может быть источником репортов")
            return

        if await check_existing_pair(report_chat, reported_chat):
            await msg.answer("🎉 Этот чат уже привязан к данному чату-репорту")
            return

        existing_reports = await check_report_chats(reported_chat)
        if existing_reports:
            await msg.answer("❎ Этот чат уже отправляет репорты в другой чат")
            return

        # Проверка существования чата в базе
        chat_link = await search_report_chat_link(reported_chat)

        if not chat_title:
            await msg.answer("❌ Указанный чат не найден в базе данных.\nУдалите и добавьте бота заново.")
            return

        chat = f"<a href='{chat_link}'>{chat_title}</a>" if chat_link else chat_title

        await add_chat_reports(report_chat, reported_chat)
        await msg.answer(
            f"Теперь репорты из чата «{chat}» будут приходить сюда",
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(e, exc_info=True)
        await msg.answer(f"⚠️ <b>Ошибка:</b> {str(e)}")





@report.message(F.text.lower().startswith('-чат репорты все'))
@report.message(F.text.lower().startswith('!-чат репорты все'))
@report.message(F.text.lower().startswith('.-чат репорты все'))
@report.message(F.text.lower().startswith('сап -чат репорты все'))
async def all_del_db_chat(msg: Message):
    try:
        if msg.chat.type == 'private':
            return

        chat_id = msg.chat.id

        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, chat_id, 37):
            return

        deleted_count, total_count, chats_info = await all_del_chat_reports_with_info(chat_id)

        if deleted_count > 0:
            message_text = [
                f"✅ Удалено {deleted_count}/{total_count} привязанных чатов:",
                *[f"🔹 <a href='{link}'>{name}</a>" for name, link in chats_info],
                "",
                "⚠️ <b>Важно:</b> Теперь репорты из этих чатов не будут поступать"
            ]

            await msg.reply(
                "\n".join(message_text),
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        else:
            await msg.answer('📣 Нет привязанных чатов для удаления')

    except Exception as e:
        logger.error(e, exc_info=True)
        await msg.reply(f'<b>⚠️ Ошибка:</b>\n{str(e)}', parse_mode='HTML')





@report.message(F.text.lower().startswith('-репорты из'))
@report.message(F.text.lower().startswith('!-репорты из'))
@report.message(F.text.lower().startswith('.-репорты из'))
@report.message(F.text.lower().startswith('сап -репорты из'))
async def del_db_chat(msg: Message):
    try:
        if msg.chat.type == 'private':
            return

        report_chat = msg.chat.id

        # Проверяем права в чате-получателе репортов
        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, report_chat, 37):
            return

        text = msg.text.strip().lower()

        if 'из' not in text:
            await msg.answer("⚠️ Укажите чат после 'из'")
            return

        _, reported_chat_str = text.split('из', 1)
        reported_chat_str = reported_chat_str.strip()

        if not reported_chat_str:
            await msg.answer("❌ Не указан CHAT_ID")
            return

        try:
            reported_chat = int(reported_chat_str)
        except ValueError:
            await msg.answer("🚫 CHAT_ID должен быть числом (например: -100123456789)")
            return

        # Проверяем права в чате-источнике репортов
        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, reported_chat, 37):
            await msg.answer("❌ У вас нет прав в указанном чате")
            return

        chat_title = await search_report_chat_name(reported_chat)
        if not chat_title:
            await msg.answer("❌ Указанный чат не найден в базе данных")
            return

        if reported_chat == report_chat:
            await msg.answer("🔒 Нельзя отвязать этот чат от самого себя")
            return

        if await del_chat_report(report_chat, reported_chat):
            await msg.answer("✅ Чат успешно отвязан")
        else:
            await msg.answer('❌ Привязанный чат не найден')

    except Exception as e:
        logger.error(e, exc_info=True)
        await msg.answer(f"⚠️ <b>Ошибка:</b>\n{str(e)}")


@report.message(F.text.split("\n", 1)[0].lower() == '!привязанные чаты')
@report.message(F.text.split("\n", 1)[0].lower() == '.привязанные чаты')
@report.message(F.text.split("\n", 1)[0].lower() == '/привязанные чаты')
@report.message(F.text.split("\n", 1)[0].lower() == 'сап привязанные чаты')
@report.message(Command("list_connected_chats"))
async def show_linked_chats(msg: Message):
    try:
        if msg.chat.type == 'private':
            return

        report_chat = msg.chat.id

        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, report_chat, 38):
            return

        if not await is_report_chat(report_chat):
            await msg.answer("❌ Этот чат не является чат-репортом")
            return

        pool = get_db_pool()
        linked_chats = []
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                    SELECT cr.reported_chat, c.chat_title, c.invite_link 
                    FROM chat_reports cr
                    LEFT JOIN chats c ON cr.reported_chat = c.chat_id
                    WHERE cr.report_chat = $1
                ''', report_chat)

            linked_chats = [(row['reported_chat'], row['chat_title'], row['invite_link'])
                            for row in rows]

        if not linked_chats:
            await msg.answer("📭 Нет привязанных чатов")
            return

        message_lines = ["💬<b> Список привязанных чатов:</b>"]

        for chat_id, chat_title, invite_link in linked_chats:
            chat_name = chat_title or f"Чат {chat_id}"

            # Правильное формирование ссылки
            if invite_link:
                chat_link = invite_link
            else:
                # Для приватных чатов без инвайт-ссылки
                chat_link = f"https://t.me/c/{str(chat_id).replace('-100', '')}"

            message_lines.append(f"🔹 <a href='{chat_link}'>{chat_name}</a> (ID: <code>{chat_id}</code>)")

        await msg.answer(
            "\n".join(message_lines),
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(e, exc_info=True)
        await msg.answer(f"⚠️ <b>Ошибка:</b>\n{str(e)}", parse_mode='HTML')










@report.message(F.text.split("\n", 1)[0].lower() == '!репорт')
@report.message(F.text.split("\n", 1)[0].lower() == '.репорт')
@report.message(F.text.split("\n", 1)[0].lower() == '/репорт')
@report.message(F.text.split("\n", 1)[0].lower() == 'сап репорт')
@report.message(F.text.split("\n", 1)[0].lower() == '!жалоба')
@report.message(F.text.split("\n", 1)[0].lower() == '.жалоба')
@report.message(F.text.split("\n", 1)[0].lower() == '/жалоба')
@report.message(F.text.split("\n", 1)[0].lower() == 'сап жалоба')
@report.message(Command("report"))
async def reports(msg: Message):
        if msg.chat.type == 'private':
            return

        chat = msg.chat.id

        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, chat, 34):
            return

        report_chat = await check_report_chat_id(chat)
        reply_message = msg.reply_to_message

        if not report_chat:
             await msg.answer('Репорт некуда отправлять')
             await msg.answer_sticker(sticker='CAACAgIAAxkBAAEPgyFo4WQXJ-x7j18MCb0koRsEwSy0DgAC-QADVp29CpVlbqsqKxs2NgQ')
             return


        try:
            if not reply_message:
                return await msg.answer("❌ Эту команду нужно использовать в ответ на сообщение!")

            user_id = reply_message.from_user.id



            reported_id = msg.from_user.id
            reply_message_id = msg.reply_to_message.message_id

            chat_username = msg.chat.username
            chat_name = msg.chat.full_name

            reason = msg.text.partition('\n')[2]

            admins = await bot.get_chat_administrators(chat)

            if user_id in [admin.user.id for admin in admins if admin.status == 'creator']:
                await msg.reply('❎ На владельца чата нельзя отправлять жалобы.')
                return
            if user_id in [admin.user.id for admin in admins]:
                await msg.reply('❎ На администрацию чата нельзя отправлять жалобы.')
                return
            if user_id == msg.from_user.id:
                await msg.reply('❎ Вы пытались отправить на самого себя жалобу.')
                await msg.answer_sticker(
                    sticker='CAACAgIAAxkBAAEPgyNo4WXlQeKd729gw8WbZ_AFUJjSsQACCwEAAladvQpOseemCPvtSTYE')
                return
            if user_id == chat:
                await msg.reply('❎ На чат нельзя отправлять жалобы.')
                return

            chat_info = await bot.get_chat(chat)
            linked_chat_id = chat_info.linked_chat_id

            if (
                    msg.reply_to_message.sender_chat
                    and msg.reply_to_message.sender_chat.id == linked_chat_id
            ):
                await msg.reply('❎ Нельзя жаловаться на привязанный канал!')
                return




            user_link = await user_link_global(user_id)
            reported_link = await user_link_global(reported_id)



            if not await time_reported(user_id, chat):
                remaining_time = 40 - int(time.time() - report_cooldown[(user_id, chat)])
                return await msg.answer(f"<b>{get_emoji('emoji_1')} Слишком частые жалобы на {user_link}!</b> Попробуйте через {remaining_time} секунд.", disable_web_page_preview=True)


            if chat_username:
                chat_link = f'<a href="https://t.me/{chat_username}">{chat_name}</a>'
            else:
                invate_link = await search_report_chat_link(chat)
                chat_link = f'<a href="{invate_link}">{chat_name}</a>'

            send_text = f'\n<b>📍 Новая жалоба из {chat_link}.</b>\n\n'\
                        f'От: {reported_link}\n'\
                        f'На: {user_link}'

            if reason:
                send_text += f'\n\n💬 <b>Причина:</b> {reason}'

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔗 Перейти на сообщение",
                        url=f"https://t.me/c/{str(chat)[4:]}/{reply_message_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⛔️ Забанить",
                        callback_data=f"ban:{user_id}_{reply_message_id}_{chat}"
                    ),
                    InlineKeyboardButton(
                        text="👢 Кикнуть",
                        callback_data=f"kik:{user_id}_{reply_message_id}_{chat}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔇 Заглушить",
                        callback_data=f"mute:{user_id}_{reply_message_id}_{chat}"
                    ),
                    InlineKeyboardButton(
                        text="🗑 Удалить",
                        callback_data=f"del:{user_id}_{reply_message_id}_{chat}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="✅ Чек",
                        callback_data=f"check:{user_id}_{msg.message_id}_{chat}"
                    ),
                    InlineKeyboardButton(
                        text="➖ Игнор",
                        callback_data=f"ignore:{user_id}_{msg.message_id}_{chat}"
                    )
                ]
            ])

            try:
                await reply_message.forward(chat_id=report_chat)
                message_send = await bot.send_message(
                    chat_id=report_chat,
                    text=send_text,
                    parse_mode='HTML',
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
                await add_info_for_report(user_id, reported_id, reply_message_id, message_send.message_id, chat)
                await msg.reply('Жалоба отправлена. Благодарим за помощь!')
            except Exception as e:
                logger.error(e, exc_info=True)
                await msg.answer(f"❌ <b>Ошибка при отправке репорта:</b>\n <blockquote>{e}</blockquote>")
        except Exception as e:
            logger.error(e, exc_info=True)
            await msg.answer(f'⚠️ <b> Произошла ошибка.</b>\n <blockquote>{e}</blockquote>', parse_mode='HTML')



@report.callback_query(lambda c: c.data.startswith("ban:"))
@rate_limit_with_cleanup(limit=1)
async def ban_user_handler(callback: types.CallbackQuery):
    try:
        data = callback.data.split(':')[1]
        user_id_str, msg_id_str, chat_id_str = data.split('_')
        chat_id_int = int(chat_id_str)
        user_id = int(user_id_str)

        chat_link = await search_report_chat_link(chat_id_int)
        chat_title = await search_report_chat_name(chat_id_int)
        chat = f"<a href='{chat_link}'>{chat_title}</a>" if chat_link else chat_title

        user_link = await user_link_global(user_id)

        callback_message = callback.message.message_id
        message_ids = await get_all_reports_for_user(user_id, chat_id_int)
        reply_message_ids = await get_all_reports_for_user_reply(user_id, chat_id_int)

        gender = await get_user_gender(user_id)
        gender_admin = await get_user_gender(callback.from_user.id)

        if not message_ids:
            await callback.answer("⚠️ В базе нет жалоб на этого пользователя!", show_alert=True)
            return


        admin_link = await user_link_global(callback.from_user.id)
        ban_text = (
            f"🚨 <b> <a href='https://t.me/c/{str(callback.message.chat.id)[4:]}/{callback_message}'>Жалоба проверена</a>! Пользователь забанен. ({user_id})</b>\n"
            f"👮‍♂️ Модератор: {admin_link}"
        )

        # ОБНОВЛЯЕМ СТАТИСТИКУ
        try:
            await update_moderation_stats(callback.from_user.id, callback.message.chat.id)
        except Exception as e:
            logger.error(e, exc_info=True)

        await bot.ban_chat_member(chat_id_int, user_id)
        await bot.send_message(chat_id=chat_id_int, text=f'🔔 Пользователь {user_link} (@{user_id}) был исключ{g("ён", gender)} из чата по исходу жалобы.\n🆔 наказания: <code>{callback_message}</code>',
                               parse_mode='HTMl',
                               disable_web_page_preview=True
                               )

        for msg_reply_id in reply_message_ids:
            try:
                await bot.delete_message(chat_id_int, msg_reply_id)
                await asyncio.sleep(0.500)
            except Exception as e:
                await callback.answer(f"⚠️ Не удалось удалить смс с ид {msg_reply_id}", show_alert=True)

        for msg_id in message_ids:
            try:
                await bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=msg_id,
                    text=ban_text,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                await update_moderation_stats(callback.from_user.id, callback.message.chat.id)
                await asyncio.sleep(0.1000)
                await del_info_for_report(msg_id, chat_id_int)



                await callback.answer("✅ Все жалобы обработаны!", show_alert=True)

                await callback.message.edit_text(
                f'📛 <b>Жалоба проверена!</b>\n'
                     f'{admin_link} забан{g("ил", gender_admin)} {user_link} в {chat}'
                     f'\n\n⚠️ Все {g("его", gender)} сообщения (на которые жаловались) были удалены.\n🆔 наказания: <code>{callback_message}</code>',
                    parse_mode='HTML',
                    disable_web_page_preview = True
                )

                await perform_ban(
                    chat_id=chat_id_int,
                    user_id=user_id,
                    duration="навсегда",
                    admin_id=callback.from_user.id,
                    reason=f'Исход репорта. (🆔 наказания: <code>{callback_message}</code>)'
                )

            except Exception as e:
                    await callback.answer(f"⚠️ Произошла ошибка. Попробуйте позже", show_alert=True)
                    logger.error(e, exc_info=True)

    except Exception as e:
        await callback.answer(f"️ Произошла ошибка. Попробуйте позже", show_alert=True)
        logger.error(e, exc_info=True)


@report.callback_query(lambda c: c.data.startswith("del:"))
@rate_limit_with_cleanup(limit=1)
async def del_report_handler(callback: types.CallbackQuery):
    try:
        data = callback.data.split(':')[1]
        user_id_str, msg_id_str, chat_id_str = data.split('_')
        chat_id_int = int(chat_id_str)
        user_id = int(user_id_str)
        msg_id_int = int(msg_id_str)
        callback_message = callback.message.message_id

        user_link = await user_link_global(user_id)
        admin_link = await user_link_global(callback.from_user.id)


        # ОБНОВЛЯЕМ СТАТИСТИКУ
        await update_moderation_stats(callback.from_user.id, callback.message.chat.id)

        try:
            await bot.delete_message(chat_id_int, msg_id_int)
            await del_info_for_report(callback_message, chat_id_int)
            await callback.message.edit_text(
                f"🗑️<b> Жалоба проверена! Сообщение от {user_link} удалено.</b>\nМодератор: {admin_link}\n",
                parse_mode='HTML',
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(e, exc_info=True)
            await callback.answer(
                f"Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML', disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(e, exc_info=True)
        await callback.answer(
            f"Произошла ошибка. Попробуйте позже.",
            parse_mode='HTML', disable_web_page_preview=True
        )

@report.callback_query(lambda c: c.data.startswith("check:"))
@rate_limit_with_cleanup(limit=1)
async def check_report_handler(callback: types.CallbackQuery):
    try:
        data = callback.data.split(':')[1]
        user_id_str, msg_id_str, chat_id_str = data.split('_')
        chat_id_int = int(chat_id_str)
        user_id = int(user_id_str)

        admin_link = await user_link_global(callback.from_user.id)
        user_link = await user_link_global(user_id)

        callback_message = callback.message.message_id


        # ОБНОВЛЯЕМ СТАТИСТИКУ
        await update_moderation_stats(callback.from_user.id, callback.message.chat.id)

        await callback.message.edit_text(
        f"✅<b> Жалоба на {user_link} проверена!</b>"
        f"\nМодератор: {admin_link}\n",
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        await del_info_for_report(callback_message, chat_id_int)
    except Exception as e:
        logger.error(e, exc_info=True)
        await callback.answer(
            f"Произошла ошибка. Попробуйте позже.",
            parse_mode='HTML',
            disable_web_page_preview=True
        )

@report.callback_query(lambda c: c.data.startswith("ignore:"))
@rate_limit_with_cleanup(limit=1)
async def ignore_report_handler(callback: types.CallbackQuery):
    try:
        data = callback.data.split(':')[1]
        user_id_str, msg_id_str, chat_id_str = data.split('_')
        chat_id_int = int(chat_id_str)
        user_id = int(user_id_str)


        admin_link = await user_link_global(callback.from_user.id)
        user_link = await user_link_global(user_id)

        callback_message = callback.message.message_id

        # ОБНОВЛЯЕМ СТАТИСТИКУ
        await update_moderation_stats(callback.from_user.id, callback.message.chat.id)

        await callback.message.edit_text(
            f"💤<b> Жалоба на {user_link} проигнорирована!</b>"
            f"\nМодератор: {admin_link}\n",
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        await del_info_for_report(callback_message, chat_id_int)

    except Exception as e:
        logger.error(e, exc_info=True)
        await callback.answer(
            f"Произошла ошибка. Попробуйте позже.",
            parse_mode='HTML',
            disable_web_page_preview=True
        )


@report.callback_query(lambda c: c.data.startswith("kik:"))
@rate_limit_with_cleanup(limit=1)
async def kik_report_handler(callback: types.CallbackQuery):
    try:
        data = callback.data.split(':')[1]
        user_id_str, msg_id_str, chat_id_str = data.split('_')
        chat_id_int = int(chat_id_str)
        user_id = int(user_id_str)
        callback_message = callback.message.message_id

        admin_link = await user_link_global(callback.from_user.id)
        user_link = await user_link_global(user_id)

        ID_message = callback.message.message_id


        # ОБНОВЛЯЕМ СТАТИСТИКУ
        await update_moderation_stats(callback.from_user.id, callback.message.chat.id)

        try:
            await bot.ban_chat_member(chat_id_int, user_id)
            await del_info_for_report(callback_message, chat_id_int)
            await callback.message.edit_text(
                f"👢<b> Жалоба проверена! {user_link} исключён из чата.</b>\nМодератор: {admin_link}\n",
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            await asyncio.sleep(3)
            await bot.unban_chat_member(chat_id_int, user_id)
        except Exception as e:
            logger.error(e, exc_info=True)
            await callback.answer(
                f"Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML', disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(e, exc_info=True)
        await callback.answer(
            f"Произошла ошибка. Попробуйте позже.",
            parse_mode='HTML', disable_web_page_preview=True
        )


@report.callback_query(lambda c: c.data.startswith("mute:"))
@rate_limit_with_cleanup(limit=1)
async def _report_handler(callback: types.CallbackQuery):
    try:
        data = callback.data.split(':')[1]
        user_id_str, msg_id_str, chat_id_str = data.split('_')
        user_id = int(user_id_str)
        msg_id = int(msg_id_str)
        chat_id = int(chat_id_str)

        admin_link = await user_link_global(callback.from_user.id)
        user_link = await user_link_global(user_id)

        # Получаем причину жалобы из текущего сообщения
        reason = "Не указана"
        if callback.message.text:
            lines = callback.message.text.split('\n')
            for line in lines:
                if 'Причина:' in line:
                    reason = line.split('Причина:')[-1].strip()
                    break
                elif 'причина:' in line:
                    reason = line.split('причина:')[-1].strip()
                    break

        # Клавиатура с выбором времени мута
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔇 1 час",
                    callback_data=f"mutetime:{user_id}_{msg_id}_{chat_id}_3600"
                ),
                InlineKeyboardButton(
                    text="🔇 1 день",
                    callback_data=f"mutetime:{user_id}_{msg_id}_{chat_id}_86400"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔇 1 неделя",
                    callback_data=f"mutetime:{user_id}_{msg_id}_{chat_id}_604800"
                ),
                InlineKeyboardButton(
                    text="🔇 1 месяц",
                    callback_data=f"mutetime:{user_id}_{msg_id}_{chat_id}_2592000"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔇 Навсегда",
                    callback_data=f"mutetime:{user_id}_{msg_id}_{chat_id}_0"
                )
            ],
            #[
                #InlineKeyboardButton(
                    #text="⬅️ Назад",
                    #callback_data=f"back_to_report:{user_id}_{msg_id}_{chat_id}"
                #)
            #]
        ])

        # Обновляем сообщение с предложением выбора времени
        await callback.message.edit_text(
            f"👤 {admin_link}, выберите время мута для {user_link}\n"
            f"📝 Причина: {reason}",
            parse_mode='HTML',
            reply_markup=keyboard, disable_web_page_preview=True
        )

        await callback.answer()

    except Exception as e:
        logger.error(e, exc_info=True)
        await callback.answer(
            "Произошла ошибка. Попробуйте позже.",
            show_alert=True
        )


# Обработчик выбора времени мута
@report.callback_query(lambda c: c.data.startswith("mutetime:"))
@rate_limit_with_cleanup(limit=1)
async def _mute_time_handler(callback: types.CallbackQuery):
    try:
        data = callback.data.split(':')[1]
        parts = data.split('_')

        if len(parts) == 4:
            user_id_str, msg_id_str, chat_id_str, duration_str = parts
        else:
            # Если старая структура
            user_id_str, msg_id_str, chat_id_str, duration_str = parts[:4]

        user_id = int(user_id_str)
        msg_id = int(msg_id_str)
        chat_id = int(chat_id_str)
        duration = int(duration_str)

        ID_message = callback.message.message_id

        # Получаем причину из текущего сообщения
        reason = f"Исход репорта. (🆔 наказания: <code>{ID_message}</code>)"
        if callback.message.text:
            lines = callback.message.text.split('\n')
            for line in lines:
                if 'Причина жалобы:' in line:
                    reason = line.split('Причина жалобы:')[-1].strip()
                    reason += f' (🆔 наказания: <code>{ID_message}</code>)'
                    break
                elif 'Причина:' in line:
                    reason = line.split('Причина:')[-1].strip()
                    reason += f' (🆔 наказания: <code>{ID_message}</code>)'
                    break

        admin_link = await user_link_global(callback.from_user.id)
        user_link = await user_link_global(user_id)

        # Форматируем время для отображения
        time_text = ""
        duration_timedelta = None

        if duration == 0:
            time_text = "навсегда"
            duration_timedelta = 'навсегда'
        elif duration == 3600:
            time_text = "1 час"
            duration_timedelta = timedelta(hours=1)
        elif duration == 86400:
            time_text = "1 день"
            duration_timedelta = timedelta(days=1)
        elif duration == 604800:
            time_text = "1 неделю"
            duration_timedelta = timedelta(weeks=1)
        elif duration == 2592000:
            time_text = "1 месяц"
            duration_timedelta = timedelta(days=30)

        # Применяем мут через вашу функцию perform_mute
        try:
            success, result = await perform_mute(
                chat_id=chat_id,
                user_id=user_id,
                duration=duration_timedelta,
                admin_id=callback.from_user.id,
                reason=reason
            )

            if success:
                # Обновляем клавиатуру после успешного мута
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Мут применен",
                            callback_data="noop"
                        )
                    ]
                ])

                await callback.message.edit_text(
                    f"✅ {admin_link} замутил {user_link} на {result}\n"
                    f"📝 Причина: {reason}\n"
                    f"⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n",
                    parse_mode='HTML',
                    disable_web_page_preview=True,
                    reply_markup=keyboard
                )

                # Также можно уведомить в чате о муте
                try:
                    from pytz import timezone
                    MOSCOW_TZ = timezone('Europe/Moscow')

                    if duration_timedelta == 'навсегда' or duration_timedelta is None:
                        mute_end_text = "никогда (навсегда)"
                    else:
                        end_time = datetime.now(MOSCOW_TZ) + duration_timedelta
                        mute_end_text = end_time.strftime('%d.%m.%Y в %H:%M')

                    mute_notification = (
                        f"👤 Пользователь {user_link} был заглушен администратором {admin_link}\n"
                        f"📝 Причина: {reason}\n"
                    )

                    await bot.send_message(
                        chat_id=chat_id,
                        text=mute_notification,
                        disable_web_page_preview=True,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления в чат: {e}")

            else:
                # Кнопка для возврата при ошибке
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="↩️ Вернуться",
                            callback_data=f"mute:{user_id}_{msg_id}_{chat_id}"
                        )
                    ]
                ])

                await callback.message.edit_text(
                    f"❌ Не удалось замутить {user_link}\n"
                    f"Ошибка: {result}\n\n"
                    f"Попробуйте другое действие.",
                    parse_mode='HTML',
                    disable_web_page_preview=True,
                    reply_markup=keyboard
                )

        except Exception as e:
            logger.error(f"Ошибка при вызове perform_mute: {e}", exc_info=True)

            # Обновляем клавиатуру с кнопкой "Назад"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="↩️ Назад",
                        callback_data=f"mute:{user_id}_{msg_id}_{chat_id}"
                    )
                ]
            ])

            await callback.message.edit_text(
                f"❌ Ошибка при попытке мута {user_link} на {time_text}\n"
                f"📝 Причина: {reason}\n"
                f"Ошибка: {str(e)[:100]}...",
                parse_mode='HTML',
                disable_web_page_preview=True,
                reply_markup=keyboard
            )

        await callback.answer()

    except Exception as e:
        logger.error(e, exc_info=True)
        await callback.answer(
            "Произошла ошибка при выборе времени мута.",
            show_alert=True
        )


# Обработчик кнопки "Назад" к выбору действий
@report.callback_query(lambda c: c.data.startswith("back_to_report:"))
@rate_limit_with_cleanup(limit=1)
async def _back_to_report_handler(callback: types.CallbackQuery):
    try:
        data = callback.data.split(':')[1]
        user_id_str, msg_id_str, chat_id_str = data.split('_')
        user_id = int(user_id_str)
        msg_id = int(msg_id_str)
        chat_id = int(chat_id_str)

        admin_link = await user_link_global(callback.from_user.id)
        user_link = await user_link_global(user_id)

        # Получаем причину из текущего сообщения
        reason = "Не указана"
        if callback.message.text:
            lines = callback.message.text.split('\n')
            for line in lines:
                if 'Причина:' in line:
                    reason = line.split('Причина:')[-1].strip()
                    break
                elif 'Причина жалобы:' in line:
                    reason = line.split('Причина жалобы:')[-1].strip()
                    break

        # Формируем текст заново
        try:
            chat_info = await bot.get_chat(chat_id)
            chat_name = chat_info.full_name
        except:
            chat_name = f"чат {chat_id}"

        # Получаем информацию о том, кто отправил репорт
        # Можно получить из оригинального сообщения или БД
        reporter_link = "неизвестно"

        # Формируем текст
        original_text = (
            f"\n<b> Новая жалоба из {chat_name}</b>\n\n"
            f"👤 На пользователя: {user_link}\n"
            f"📢 От: {reporter_link}"
        )

        # Добавляем причину, если она есть
        if reason != "Не указана":
            full_text = f"{original_text}\n📝 Причина жалобы: {reason}"
        else:
            full_text = original_text

        # Возвращаем исходную клавиатуру с действиями
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⛔️ Забанить",
                    callback_data=f"ban:{user_id}_{msg_id}_{chat_id}"
                ),
                InlineKeyboardButton(
                    text="👢 Кикнуть",
                    callback_data=f"kik:{user_id}_{msg_id}_{chat_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔇 Заглушить",
                    callback_data=f"mute:{user_id}_{msg_id}_{chat_id}"
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=f"del:{user_id}_{msg_id}_{chat_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Чек",
                    callback_data=f"check:{msg_id}_{chat_id}"
                ),
                InlineKeyboardButton(
                    text="➖ Игнор",
                    callback_data=f"ignore:{msg_id}_{chat_id}"
                )
            ]
        ])

        await callback.message.edit_text(
            full_text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )

        await callback.answer("Возврат к выбору действий")

    except Exception as e:
        logger.error(e, exc_info=True)
        await callback.answer(
            "Произошла ошибка при возврате.",
            show_alert=True
        )


# Обработчик для пустой callback_data (noop)
@report.callback_query(lambda c: c.data == "noop")
async def _noop_handler(callback: types.CallbackQuery):
    await callback.answer()







@report.message(F.text.split("\n", 1)[0].lower() == '!чат ид')
@report.message(F.text.split("\n", 1)[0].lower() == '.чат ид')
@report.message(F.text.split("\n", 1)[0].lower() == '/чат ид')
async def chat_id(msg: Message):
    chat_id = msg.chat.id
    await msg.reply(f'🆔 <b>чата:</b> <code>{chat_id}</>', parse_mode='HTML')