import logging

from aiogram import Router, F
from aiogram.types import *
from aiogram.filters import *
from aiogram.enums import ChatMemberStatus
import pytz
import asyncio
from pytz import timezone
from datetime import datetime
from typing import Optional
from handlers.BotAutomaticWork.AddChatsBot.AddChatBotDB import add_chat_info, update_chat_leave_time
from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdminsDB import add_admin_for_rang, check_admin_for_rang
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup

logger = logging.getLogger(__name__)

chats = Router()

time_zona = timezone('Europe/Moscow')
moscow_time = datetime.now(time_zona)
mon = moscow_time.month
time = moscow_time.strftime(f'%d.{mon}.%Y в %H:%M')


def get_moscow_time() -> datetime:
    """Возвращает текущее время в московском часовом поясе"""
    moscow = pytz.timezone('Europe/Moscow')
    return datetime.now(moscow)


def get_greeting(moscow_time: datetime) -> str:
    """Возвращает приветствие в зависимости от времени суток"""
    hour = moscow_time.hour
    if 6 <= hour < 12:
        return '🌄 Доброе утро'
    elif 12 <= hour < 18:
        return '👋🏻 Доброго времени суток'
    elif 18 <= hour < 21:
        return '🌆 Добрый вечер'
    return '🌃 Доброй ночи'


def format_time(time: datetime) -> str:
    """Форматирует время в строку"""
    return time.strftime(f'%d.{time.month}.%Y в %H:%M')


async def get_chat_owner(chat_id: int) -> Optional[ChatMemberOwner]:
    """Возвращает владельца чата"""
    admins = await bot.get_chat_administrators(chat_id)
    return next((admin.user for admin in admins if isinstance(admin, ChatMemberOwner)), None)


async def is_chat_owner(user_id: int, chat_id: int) -> bool:
    """Проверяет, является ли пользователь владельцем чата"""
    owner = await get_chat_owner(chat_id)
    return owner and owner.id == user_id


@chats.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def bot_added_to_chat(event: ChatMemberUpdated) -> None:
    if not event.chat.type == 'private':

        bot_info = await bot.get_me()

        if not str(event.chat.id).startswith("-100"):
            await event.answer(
                '<b><tg-emoji emoji-id="5447644880824181073">⚠️</tg-emoji> Чат не является супер-чатом.</b>\n'
                'Обновите статус группы с обычного чата на супер-чат.\n\n'
                '<i>Один из способов:</i>\n'
                'Включите анонимность и сохраните настройки, после отключите и добавьте бота.\n\n'
                '💬 Или же обратитесь в чат для получения для получения помощи: @sap_sp_chat')
            await bot.leave_chat(event.chat.id)
            return

        moscow_time = get_moscow_time()
        greeting = get_greeting(moscow_time)

        chat_id = event.chat.id
        chat_title = event.chat.title
        chat_username = event.chat.username

        try:
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text='💫 Как выдать права боту', callback_data='install_chats_bot')]
            ])

            start_markup = InlineKeyboardMarkup(inline_keyboard=[
                #[InlineKeyboardButton(text='📖 Пользовательское соглашение', callback_data='ToS')],
                [
                    InlineKeyboardButton(text='🗃️ Команды', url='https://teletype.in/@sap_sp/commands'),
                    #InlineKeyboardButton(text='🔍 С чего начать?', callback_data='HowToStart')
                ]
            ])

            owner = await get_chat_owner(chat_id)
            await add_chat_info(
                chat_id=chat_id,
                chat_title=chat_title,
                chat_username=chat_username,
                bot_chat_status='join',
                owner_id=owner.id if owner else None
            )

            if owner:
                current_rang = await check_admin_for_rang(owner.id, chat_id)

                if current_rang != 5:
                    await add_admin_for_rang(owner.id, chat_id, 5, owner.id, 5, time)

            chat_member = await bot.get_chat_member(chat_id, bot_info.id)
            if chat_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f'<b>{greeting}, {chat_title}!</b>\n'
                         'Вы добавили меня сразу администратором чата, поэтому я готов приступить к работе!\n\n'
                         '<a href="https://t.me/+iwWRkgyHOwQ3ZjMy">Официальный канал</a> | '
                         '<a href="https://teletype.in/@sap_sp/commands">Мой функционал</a>\n'
                         '<blockquote><tg-emoji emoji-id="5447644880824181073">⚠️</tg-emoji> Бот только-только запустился, поэтому есть некоторые неточности.\n'
                         'Большая просьба сообщать о найденных ошибках в <a href="https://t.me/sap_sp_chat">Sapphire | Chat</a></blockquote>',
                    disable_web_page_preview=True,
                    parse_mode='HTML',
                    reply_markup=start_markup
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f'<b>{greeting}, {chat_title}!</b>\n'
                    'К сожалению, я не могу начать модерировать чат, пока у меня не будет прав администратора. Мне нужны все права кроме анонимности и управлением видеочатом.\n\n'
                    '<blockquote><tg-emoji emoji-id="5447644880824181073">⚠️</tg-emoji> Бот только-только запустился, поэтому есть некоторые неточности.\n'
                    'Большая просьба сообщать о найденных ошибках в <a href="https://t.me/sap_sp_chat">Sapphire | Chat</a></blockquote>',
                    disable_web_page_preview=True,
                    parse_mode='HTML',
                    reply_markup=markup
                )

        except Exception as e:
            logging.error(e)
            await bot.send_message(chat_id, f"⚠️ <b>Произошла ошибка:</b> \n<blockquote>{e}</blockquote>")
            await bot.leave_chat(chat_id)


@chats.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=LEAVE_TRANSITION))
async def bot_removed_from_chat(event: ChatMemberUpdated) -> None:
    chat_id = event.chat.id

    try:
        await update_chat_leave_time(chat_id)
    except Exception as e:
        logger.error(e, exc_info=True)


@chats.my_chat_member(
    ChatMemberUpdatedFilter(
        member_status_changed=IS_MEMBER >> ADMINISTRATOR
    )
)
async def adminka(event: ChatMemberUpdated):
    """Обработчик получения прав администратора"""

    # Проверяем, был ли бот ранее администратором
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    # Если бот уже был администратором - игнорируем
    if old_status in ["administrator", "creator"]:
        return

    start_markup = InlineKeyboardMarkup(inline_keyboard=[
        #[InlineKeyboardButton(text='📖 Пользовательское соглашение', callback_data='ToS')],
        [
            InlineKeyboardButton(text='🗃️ Команды бота', url='https://teletype.in/@sap_sp/commands'),
           # InlineKeyboardButton(text='🔍 С чего начать?', callback_data='HowToStart')
        ]
    ])


    await bot.send_message(
        chat_id=event.chat.id,
        text='<tg-emoji emoji-id="5190763359296826599">🤩</tg-emoji> <b>Спасибо за права администратора!</b>\n'
             'Теперь весь мой функционал доступен.\n\n'
             '<blockquote><tg-emoji emoji-id="5447644880824181073">⚠️</tg-emoji> Бот только-только запустился, поэтому есть некоторые неточности.\n'
             'Большая просьба сообщать о найденных ошибках в <a href="https://t.me/sap_sp_chat">Sapphire | Chat</a></blockquote>',
        parse_mode='HTML',
        reply_markup=start_markup
    )

@chats.my_chat_member(
    ChatMemberUpdatedFilter(
        member_status_changed=ADMINISTRATOR >> IS_MEMBER
    )
)
async def not_adminka(event: ChatMemberUpdated):
    bot_info = await bot.get_me()
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💫 Вернуть статус администратора', callback_data='install_chats_bot')]
    ])

    await bot.send_message(
        chat_id=event.chat.id,
        text="""<tg-emoji emoji-id="5345805601303700386">☹️</tg-emoji> <b>К сожалению, меня сняли с должности администратора!</b>\nБез прав администратора я как рыба на суше. <tg-emoji emoji-id="5382210409824525356">🐟</tg-emoji>""",
        parse_mode='HTML',
        reply_markup=markup
    )
    await asyncio.sleep(100.0)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💫 Вернуть бота в чат',
                              url=f'https://t.me/{bot_info.username}?startgroup=sap&admin=change_info+delete_messages+invite_users+restrict_members+pin_messages+promote_members')]
    ])
    await bot.send_message(
        chat_id=event.chat.id,
        text='<tg-emoji emoji-id="5248987078422706914">😢</tg-emoji> Прощайте, без прав администратора я бесполезен.',
        reply_markup=markup
    )
    await bot.leave_chat(event.chat.id)


@chats.callback_query(F.data == 'install_chats_bot')
@rate_limit_with_cleanup(limit=1)
async def install_chats_bot(call: CallbackQuery):
    bot_info = await bot.get_me()
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🪄 Выдать права доступа',
                              url=f'https://t.me/{bot_info.username}?startgroup=sap&admin=change_info+delete_messages+invite_users+restrict_members+pin_messages+promote_members')]
    ])
    await call.message.edit_text(
        f"""❔<b> Туториал как выдать права администратора боту:</b>
<i>Заходим в профиль чата -> Android: нажимаем на карандаш | Пк: ︙ -> управление группой | Ios: изм. -> администраторы -> добавить администратора -> выбираете @{bot_info.username}</i>

<tg-emoji emoji-id="5470177992950946662">👇</tg-emoji> Или просто нажмите на кнопку ниже и в появившемся списке выберите этот чат.""",
        parse_mode='HTML',
        disable_web_page_preview=True,
        reply_markup=markup
    )


@chats.callback_query(F.data == 'ToS')
@rate_limit_with_cleanup(limit=1)
async def send_chats_ToS(call: CallbackQuery):
    if not await is_chat_owner(call.from_user.id, call.message.chat.id):
        try:
            await bot.send_message(
                chat_id=call.from_user.id,
                text="Пользовательское соглашение важно для прочтения."
            )
            await call.answer("Загляните в личные сообщения с ботом :)", show_alert=True)
        except Exception as e:
            await call.answer("Не удалось отправить сообщение в ЛС. Проверьте, что вы начали диалог с ботом.",
                              show_alert=True)
        return

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='back_to_main')]
    ])
    await call.message.edit_text('Пользовательское соглашение важно для прочтения.',
                                 reply_markup=markup)


@chats.callback_query(F.data == 'commands')
@rate_limit_with_cleanup(limit=1)
async def send_chats_commands(call: CallbackQuery):
    if not await is_chat_owner(call.from_user.id, call.message.chat.id):
        try:
            await bot.send_message(
                chat_id=call.from_user.id,
                text="Команды бота тут"
            )
            await call.answer("Загляните в личные сообщения с ботом :)", show_alert=True)
        except Exception as e:
            await call.answer("Не удалось отправить сообщение в ЛС. Проверьте, что вы начали диалог с ботом.",
                              show_alert=True)
        return

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='back_to_main')]
    ])
    await call.message.edit_text('Команды бота тут',
                                 reply_markup=markup)


@chats.callback_query(F.data == 'HowToStart')
@rate_limit_with_cleanup(limit=1)
async def send_HowToStart(call: CallbackQuery):
    if not await is_chat_owner(call.from_user.id, call.message.chat.id):
        try:
            await bot.send_message(
                chat_id=call.from_user.id,
                text="Надо будет как нибудь заполнить"
            )
            await call.answer("Загляните в личные сообщения с ботом :)", show_alert=True)
        except Exception as e:
            await call.answer("Не удалось отправить сообщение в ЛС. Проверьте, что вы начали диалог с ботом.",
                              show_alert=True)
        return

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='⬅️ Назад', callback_data='back_to_main')]
    ])
    await call.message.edit_text('Надо будет как нибудь заполнить',
                                 reply_markup=markup)


@chats.callback_query(F.data == 'back_to_main')
@rate_limit_with_cleanup(limit=1)
async def back_to_main(call: CallbackQuery):
    moscow_time = get_moscow_time()
    greeting = get_greeting(moscow_time)

    start_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📖 Пользовательское соглашение', callback_data='ToS')],
        [
            InlineKeyboardButton(text='🗃️ Команды', callback_data='commands'),
            InlineKeyboardButton(text='🔍 С чего начать?', callback_data='HowToStart')
        ]
    ])

    await call.message.edit_text(
        text=f'<b>{greeting}, {call.message.chat.title if call.message.chat else "участники чата"}!</b>\n'
             '\n\n'
             '<tg-emoji emoji-id="5470177992950946662">👇</tg-emoji> Может быть полезно тем, кто пользуется ботом в первый раз\n',
        disable_web_page_preview=True,
        parse_mode='HTML',
        reply_markup=start_markup
    )