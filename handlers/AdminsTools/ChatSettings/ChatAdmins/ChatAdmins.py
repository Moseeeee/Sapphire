import logging

from aiogram import Router
from aiogram.types import *
from aiogram.filters import Command
from pytz import timezone
from datetime import datetime

from handlers.AdminsTools.ChatSettings.ChatAdmins.ChatAdminsDB import (
    add_admin_for_rang,
    check_admin_for_rang,
    update_admin_for_rang,
    add_history_admin_for_rang,
    del_admin_for_rang,
    check_history_admin_for_rang,
    get_all_chat_admins

)
from handlers.BotAutomaticWork.Gonfig.config import boss_agent

from typing import List, Tuple

from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import rate_limit_with_cleanup, get_random_text
from handlers.BotAutomaticWork.users.checks.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.checks.user_online_status import get_user_status
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_global
from handlers.UserCommands.GenderSettings.GenderSettingsDB import get_user_gender

chatadmin = Router()
user_pagination_data = {}

time_zona = timezone('Europe/Moscow')
moscow_time = datetime.now(time_zona)
mon = moscow_time.month
time = moscow_time.strftime(f'%d.{mon}.%Y в %H:%M')


logger = logging.getLogger(__name__)

async def is_telegram_owner(bot, chat_id, user_id):
    """Проверяет, является ли пользователь создателем чата в Telegram"""
    try:
        chat_member = await bot.get_chat_member(chat_id, user_id)
        return chat_member.status == "creator"
    except Exception:
        return False


@chatadmin.message(lambda m: m.text and m.text.lower().startswith("повысить"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("!повысить"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith(".повысить"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("/повысить"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("сап повысить"))
async def increase_chat_admin(m: Message):
    if m.chat.type == 'private':
        return
    ChatId = m.chat.id
    User_Id = m.from_user.id

    # Проверяем права доступа: босс-агенты пропускаются, остальные проходят проверку
    if User_Id not in boss_agent and not await auto_check_AccessLevel_for_rang(User_Id, ChatId, 41):
        return
    try:
        # Определяем UserId
        if m.reply_to_message:
            # Если ответ на сообщение
            UserId = m.reply_to_message.from_user.id
            rang_str = None
        else:
            # Если команда с упоминанием
            parts = m.text.split()
            if len(parts) < 2:
                await m.answer(
                    "❌ <b>Неверный формат команды!</b>\nИспользуйте: Повысить {@username} или ответьте на сообщение",
                    parse_mode='HTML')
                return

            # Проверяем, если последнее слово это число (ранг)
            if len(parts) >= 3 and parts[1].isdigit():
                # Формат: Повысить 3 @username
                rang_str = parts[1].strip()
                mention = parts[2]
            else:
                # Формат: Повысить @username (без ранга)
                rang_str = None
                mention = parts[-1]  # Берём последнее слово как упоминание

            UserId = await resolve_id(m, mention)

            if not UserId:
                await m.reply("⚠️ Не удалось определить пользователя. Укажите @username или ID.")
                return

        # Если ранг не указан, повышаем на 1 от текущего
        UserRang = await check_admin_for_rang(UserId, ChatId)

        if rang_str is None:
            # Если пользователь не админ, ставим 1 ранг
            if UserRang == 0:
                rang = 1
            else:
                # Повышаем на 1 ранг
                rang = UserRang + 1
        else:
            if not rang_str.isdigit():
                await m.reply('❗ Ранг должен быть числом от 1 до 5.')
                return
            rang = int(rang_str)

        ChatId = m.chat.id
        ManagementAdminId = m.from_user.id
        ManagementRang = await check_admin_for_rang(ManagementAdminId, ChatId)
        user_link = await user_link_global(UserId)

        # Проверяем, является ли управляющий Telegram-владельцем
        is_tg_owner = await is_telegram_owner(m.bot, ChatId, ManagementAdminId)

        # Проверяем, является ли целевой пользователь владельцем (ранг 5)
        if UserRang == 5 and not is_tg_owner:
            await m.answer('❌ <b>Нельзя изменять ранг владельца!</b>', parse_mode='HTML')
            return

        # Босс-агенты имеют полную власть
        if ManagementAdminId not in boss_agent:
            # Telegram-владелец может управлять любыми администраторами и повышать до 5 ранга
            if not is_tg_owner:
                if UserRang > ManagementRang:
                    await m.answer('❌ <b>Вы не можете управлять администраторами высшего ранга!</b>',
                                   parse_mode='HTML')
                    return

                # Проверяем, что новый ранг не выше ранга управляющего
                max_allowed_rang = ManagementRang
                if rang > max_allowed_rang:
                    await m.answer(
                        f'❌ <b>Вы не можете повысить до ранга {rang}, так как ваш ранг {ManagementRang}!</b>',
                        parse_mode='HTML')
                    return

        # Проверяем, не пытаемся ли повысить выше 5 ранга
        if rang > 5:
            await m.answer('❌ <b>Максимальный ранг - 5!</b>', parse_mode='HTML')
            return

        # Проверяем, не пытаемся ли понизить (если новый ранг ниже текущего)
        if rang < UserRang:
            await m.answer('❌ <b>Новый ранг должен быть выше текущего!</b>', parse_mode='HTML')
            return

        # Проверяем, не пытаемся ли оставить на том же ранге
        if rang == UserRang:
            await m.answer('❌ <b>Пользователь уже на этом ранге!</b>', parse_mode='HTML')
            return

        gender = await get_user_gender(UserId)
        rank_names = {
            5: "владельца",
            4: "старшего администратора",
            3: "администратора",
            2: "модератора",
            1: "помощника"
        }

        if UserRang == 0:
            # Добавляем нового администратора
            await m.answer(f'✅ {user_link} повыш{g("ен", gender)} до {rank_names[rang]}',
                           parse_mode='HTML',
                           disable_web_page_preview=True)
            await add_admin_for_rang(UserId, ChatId, rang, ManagementAdminId, ManagementRang, time)
            await add_history_admin_for_rang(UserId, ChatId, rang, UserRang, ManagementAdminId, ManagementRang, time)
        else:
            # Обновляем существующего администратора
            await m.answer(f'✅ {user_link} повыш{g("ен", gender)} до {rank_names[rang]}',
                           parse_mode='HTML',
                           disable_web_page_preview=True)
            await update_admin_for_rang(rang, ManagementAdminId, ManagementRang, time, UserId, ChatId)
            await add_history_admin_for_rang(UserId, ChatId, rang, UserRang, ManagementAdminId, ManagementRang, time)

    except Exception as e:
        logger.error(e, exc_info=True)


@chatadmin.message(lambda m: m.text and m.text.lower().startswith("понизить"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("!понизить"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith(".понизить"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("/понизить"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("сап понизить"))
async def decrease_chat_admin(m: Message):
    if m.chat.type == 'private':
        return
    ChatId = m.chat.id
    User_Id = m.from_user.id

    if User_Id not in boss_agent and not await auto_check_AccessLevel_for_rang(User_Id, ChatId, 41):
        return
    try:
        if m.reply_to_message:
            # Если ответ на сообщение
            UserId = m.reply_to_message.from_user.id
            rang_str = None
        else:
            # Если команда с упоминанием
            parts = m.text.split()
            if len(parts) < 2:
                await m.answer(
                    "❌ <b>Неверный формат команды!</b>\nИспользуйте: Понизить {@username} или ответьте на сообщение",
                    parse_mode='HTML')
                return

            # Извлекаем упоминание (последнее слово команды)
            mention = parts[-1]
            UserId = await resolve_id(m, mention)

            if not UserId:
                await m.reply("⚠️ Не удалось определить пользователя. Укажите @username или ID.")
                return
            rang_str = None

        ChatId = m.chat.id
        CheckUserRang = await check_admin_for_rang(UserId, ChatId)

        # Если ранг не указан, понижаем на 1 уровень
        if rang_str is None:
            if CheckUserRang > 0:
                rang = CheckUserRang - 1
            else:
                await m.answer("⚠️ Пользователь не является администратором.")
                return
        else:
            if not rang_str.isdigit():
                await m.reply('❗ Ранг должен быть числом.')
                return
            rang = int(rang_str)

        ManagementAdminId = m.from_user.id
        ManagementRang = await check_admin_for_rang(ManagementAdminId, ChatId)
        user_link = await user_link_global(UserId)

        is_tg_owner = await is_telegram_owner(m.bot, ChatId, ManagementAdminId)

        if CheckUserRang == 5 and not is_tg_owner:
            await m.answer('❌ <b>Нельзя понизить владельца!</b>', parse_mode='HTML')
            return

        if CheckUserRang == 0:
            await m.answer(f'⚠️ {user_link} не является администратором',
                           parse_mode='HTML',
                           disable_web_page_preview=True)
            return

        if ManagementAdminId not in boss_agent:
            if not is_tg_owner:
                if CheckUserRang >= ManagementRang:
                    await m.answer('❌ <b>Вы не можете управлять администраторами равного или высшего ранга!</b>',
                                   parse_mode='HTML')
                    return

        if rang < 0 or rang > 4:
            await m.reply('❌ <b>Ранг должен быть от 0 до 4.</b>', parse_mode='HTML')
            return

        if rang >= CheckUserRang:
            await m.reply('❌ <b>Целевой ранг должен быть ниже текущего!</b>', parse_mode='HTML')
            return

        if rang == 0:
            await m.answer(f'✅ {user_link} больше не администратор',
                           parse_mode='HTML',
                           disable_web_page_preview=True)
            await add_history_admin_for_rang(UserId, ChatId, 0, CheckUserRang, ManagementAdminId, ManagementRang, time)
            await del_admin_for_rang(UserId, ChatId)
        else:
            rank_names = {
                5: "владельца",
                4: "старшего администратора",
                3: "администратора",
                2: "модератора",
                1: "помощника"
            }
            gender = await get_user_gender(UserId)
            await m.answer(f'✅ {user_link} пониж{g("ен", gender)} до {rank_names[rang]}',
                           parse_mode='HTML',
                           disable_web_page_preview=True)
            await update_admin_for_rang(rang, ManagementAdminId, ManagementRang, time, UserId, ChatId)
            await add_history_admin_for_rang(UserId, ChatId, rang, CheckUserRang, ManagementAdminId, ManagementRang,
                                             time)

    except Exception as e:
        logger.error(e, exc_info=True)



@chatadmin.message(lambda m: m.text and m.text.lower().startswith("снять"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("!снять"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith(".снять"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("/снять"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("сап снять"))
async def remove_chat_admin(m: Message):
    global rank_names
    if m.chat.type == 'private':
        return
    ChatId = m.chat.id
    User_Id = m.from_user.id

    if not await auto_check_AccessLevel_for_rang(User_Id, ChatId, 41):
        return


    # Проверяем права доступа: босс-агенты пропускаются, остальные проходят проверку
    if User_Id not in boss_agent and not await auto_check_AccessLevel_for_rang(User_Id, ChatId, 17):
        return
    try:
        if m.reply_to_message:
            UserId = m.reply_to_message.from_user.id
        else:
            parts = m.text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                await m.answer("❌ <b>Неверный формат команды!</b>\nИспользуйте: Снять {@username} или ответьте на сообщение того, кого хотите снять",
                               parse_mode='HTML')
                return
            mention = parts[1].strip()
            UserId = await resolve_id(m, mention)

        if not UserId:
            await m.reply("⚠️ Не удалось определить пользователя.")
            return

        ChatId = m.chat.id
        ManagementAdminId = m.from_user.id
        ManagementRang = await check_admin_for_rang(ManagementAdminId, ChatId)
        CheckUserRang = await check_admin_for_rang(UserId, ChatId)
        user_link = await user_link_global(UserId)

        # Проверяем, является ли управляющий Telegram-владельцем
        is_tg_owner = await is_telegram_owner(m.bot, ChatId, ManagementAdminId)

        # Проверяем, является ли целевой пользователь владельцем (ранг 5)
        if CheckUserRang == 5 and not is_tg_owner:
            await m.answer('❌ <b>Нельзя снять владельца!</b>', parse_mode='HTML')
            return

        if CheckUserRang == 0:
            await m.answer(f'⚠️ {user_link} не является администратором',
                           parse_mode='HTML',
                           disable_web_page_preview=True)
            return

        # Босс-агенты имеют полную власть
        if ManagementAdminId not in boss_agent:
            # Telegram-владелец может управлять любыми администраторами
            if not is_tg_owner:
                if CheckUserRang > ManagementRang:
                    await m.answer('❌ <b>Вы не можете управлять администраторами высшего ранга!</b>', parse_mode='HTML')
                    return

        rank_names = {
            5: "владелец",
            4: "старший администратор",
            3: "администратор",
            2: "модератор",
            1: "помощник"
            }


        await m.answer(f'✅ {user_link} больше не {rank_names[CheckUserRang]}',
                       parse_mode='HTML',
                       disable_web_page_preview=True)
        await add_history_admin_for_rang(UserId, ChatId, 0, CheckUserRang, ManagementAdminId, ManagementRang, time)
        await del_admin_for_rang(UserId, ChatId)

    except Exception as e:
        logger.error(e, exc_info=True)



class LogPagination:
    def __init__(self, history_data: List[Tuple], items_per_page: int = 5):
        self.history_data = history_data
        self.items_per_page = items_per_page
        self.total_pages = max(1, (len(history_data) + items_per_page - 1) // items_per_page)
        self.current_page = 1

    def get_page_data(self, page: int = None) -> List[Tuple]:
        if page is not None:
            self.current_page = page

        if self.current_page < 1:
            self.current_page = 1
        elif self.current_page > self.total_pages:
            self.current_page = self.total_pages

        start_index = (self.current_page - 1) * self.items_per_page
        end_index = start_index + self.items_per_page

        return self.history_data[start_index:end_index]

    def create_pagination_keyboard(self, page: int = None, user_id: int = None) -> InlineKeyboardMarkup:
        if page is not None:
            self.current_page = page

        keyboard = []

        # Пагинация: Назад - Текущая страница - Вперед
        pagination_row = []

        # Кнопка "Назад"
        if self.current_page > 1:
            pagination_row.append(
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"log_prev_{user_id}_{self.current_page - 1}"
                )
            )

        # Текущая страница
        pagination_row.append(
            InlineKeyboardButton(
                text=f"{self.current_page}/{self.total_pages}",
                callback_data="log_current"
            )
        )

        # Кнопка "Вперед"
        if self.current_page < self.total_pages:
            pagination_row.append(
                InlineKeyboardButton(
                    text="Вперед ➡️",
                    callback_data=f"log_next_{user_id}_{self.current_page + 1}"
                )
            )

        keyboard.append(pagination_row)

        return InlineKeyboardMarkup(inline_keyboard=keyboard)


@chatadmin.message(lambda m: m.text and m.text.lower().startswith("логи"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("!логи"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith(".логи"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("/логи"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("сап логи"))
async def log_chat_admin(m: Message):
    if m.chat.type == 'private':
        return
    ChatId = m.chat.id
    User_Id = m.from_user.id

    if not await auto_check_AccessLevel_for_rang(User_Id, ChatId, 42):
        return


    # Проверяем права доступа: босс-агенты пропускаются, остальные проходят проверку
    if User_Id not in boss_agent and not await auto_check_AccessLevel_for_rang(User_Id, ChatId, 18):
        return

    try:
        if m.reply_to_message:
            UserId = m.reply_to_message.from_user.id
        else:
            parts = m.text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                await m.answer(
                    "❌ <b>Неверный формат команды!</b>\nИспользуйте: Лог {@username} или ответьте на сообщение",
                    parse_mode='HTML')
                return
            mention = parts[1].strip()
            UserId = await resolve_id(m, mention)

        if not UserId:
            await m.reply("⚠️ Не удалось определить пользователя.")
            return

        ChatId = m.chat.id
        HISTORY = await check_history_admin_for_rang(UserId, ChatId)
        user_link = await user_link_global(UserId)

        if not HISTORY:
            await m.answer(f"📭 <b>У {user_link} нет истории изменений административных прав.</b>",
                           parse_mode='HTML', disable_web_page_preview=True)
            return

        # Создаем пагинацию
        pagination = LogPagination(HISTORY, items_per_page=5)
        page_data = pagination.get_page_data()

        # Формируем текст для первой страницы
        text = f'🗃️ <b>Админ-лог {user_link}</b> (стр. {pagination.current_page}/{pagination.total_pages})\n\n'



        for i, AH in enumerate(page_data, start=1):
            rang, OldRang, ManagementAdminId, time = AH
            ManagementAdminLink = await user_link_global(ManagementAdminId)
            gender = await get_user_gender(UserId)
            gender_admin = await get_user_gender(ManagementAdminId)

            if OldRang > rang:
                t = f'🔴 пониж{g("ен", gender)} с {OldRang} до {rang}'
            elif OldRang < rang:
                t = f'🟢 повыш{g("ен", gender)} с {OldRang} до {rang}'
            else:
                t = '⚠️ ОШИБКА ПОДСЧЁТА'

            text += (f'{i}. '
                     f'{t} | {time}\n'
                     f'Назнач{g("ил", gender_admin)}: {ManagementAdminLink}\n\n')

        await m.reply(
            text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=pagination.create_pagination_keyboard(user_id=UserId)
        )

    except Exception as e:
        logger.error(e, exc_info=True)
        await m.answer("❌ <b>Произошла ошибка при получении лога.</b>", parse_mode='HTML')




@chatadmin.message(lambda m: m.text and m.text.lower().startswith("админы"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("!админы"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith(".админы"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("/админы"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("сап админы"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("кто админ"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("!кто админ"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith(".кто админ"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("/кто админ"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("сап кто админ"))
@chatadmin.message(Command("admins"))
async def list_admins(m: Message):
    if m.chat.type == 'private':
        return
    ChatId = m.chat.id
    User_Id = m.from_user.id

    # Проверяем права доступа: босс-агенты пропускаются, остальные проходят проверку
    if User_Id not in boss_agent and not await auto_check_AccessLevel_for_rang(User_Id, ChatId, 19):
        return

    try:
        ChatId = m.chat.id
        admins = await get_all_chat_admins(ChatId)

        if not admins:
            await m.answer("❌ <b>В этом чате нет администраторов.</b>", parse_mode='HTML')
            return

        admins_by_rank = {5: [], 4: [], 3: [], 2: [], 1: []}

        for admin in admins:
            user_id = admin['UserId']
            rank = admin['rang']
            user_link = await user_link_global(user_id)

            # АСИНХРОННО получаем статус для каждого администратора
            try:
                status = await get_user_status(int(user_id))
            except Exception as e:
                print(f"Error getting status for user {user_id}: {e}")
                status = '❓'  # Статус по умолчанию в случае ошибки

            admins_by_rank[rank].append((user_link, status))

        # Эмодзи и названия для каждого ранга
        rank_emojis = {
            5: "5️⃣",  # Владелец
            4: "4️⃣",  # Старший администратор
            3: "3️⃣",  # Администратор
            2: "2️⃣",  # Модератор
            1: "1️⃣"  # Помощник
        }

        rank_names = {
            5: "Владелец",
            4: "Старший администратор",
            3: "Администратор",
            2: "Модератор",
            1: "Помощник"
        }

        # Множественные числа для рангов
        rank_names_plural = {
            5: "Владельцы",
            4: "Старшие администраторы",
            3: "Администраторы",
            2: "Модераторы",
            1: "Помощники"
        }

        message_text = ""

        for rank in [5, 4, 3, 2, 1]:
            if admins_by_rank[rank]:
                # Выбираем правильную форму (единственное/множественное число)
                if len(admins_by_rank[rank]) == 1:
                    rank_name = rank_names[rank]
                else:
                    rank_name = rank_names_plural[rank]

                message_text += f"{rank_emojis[rank]} <b>{rank_name}:</b>\n"
                # Используем кортеж (user_link, status)
                message_text += "\n".join(
                    f"{status} {user_link}" for user_link, status in admins_by_rank[rank]) + "\n\n"

        await m.answer(message_text.strip(), parse_mode='HTML', disable_web_page_preview=True)

    except Exception as e:
        logger.error(e, exc_info=True)
        await m.answer("❌ <b>Произошла ошибка при получении списка администраторов.</b>", parse_mode='HTML')








@chatadmin.message(lambda m: m.text and m.text.lower().startswith("уйти с должности"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("!уйти с должности"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith(".уйти должности"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("/уйти с должности"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("сап уйти с должности"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("уйти в отставку"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("!уйти в отставку"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith(".уйти в отставку"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("/уйти в отставку"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("сап уйти в отставку"))
async def resign_admin(m: Message):
    try:
        UserId = m.from_user.id
        ChatId = m.chat.id

        # Проверяем, является ли пользователь администратором
        user_rang = await check_admin_for_rang(UserId, ChatId)

        if user_rang == 0:
            return

        # Получаем информацию о пользователе для истории
        user_link = await user_link_global(UserId)

        # Удаляем из администраторов
        await del_admin_for_rang(UserId, ChatId)
        await add_history_admin_for_rang(UserId, ChatId, 0, user_rang, UserId, user_rang, time)
        gender = await get_user_gender(UserId)

        rank_names = {
            5: "владелец",
            4: "старший администратор",
            3: "администратор",
            2: "модератор",
            1: "помощник"
        }

        await m.reply(
            f"ℹ️ {user_link} уш{g('ол', gender)} с должности {rank_names[user_rang]}.",
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(e, exc_info=True)
        await m.answer("❌ <b>Произошла ошибка при обработке запроса.</b>", parse_mode='HTML')






@chatadmin.message(lambda m: m.text and m.text.lower().startswith("вв"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("!вв"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith(".вв"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("/вв"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("сап вв"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("вернуть владельца"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("!вернуть владельца"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith(".вернуть владельца"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("/вернуть владельца"))
@chatadmin.message(lambda m: m.text and m.text.lower().startswith("сап вернуть владельца"))
async def restore_owner(m: Message):
    try:
        UserId = m.from_user.id
        ChatId = m.chat.id

        # Проверяем, является ли пользователь создателем чата в Telegram
        chat_member = await m.bot.get_chat_member(ChatId, UserId)

        if chat_member.status != "creator":
            return

        # Проверяем, является ли пользователь уже администратором в нашей системе
        current_rang = await check_admin_for_rang(UserId, ChatId)

        if current_rang == 5:
            await m.answer("✅ <b>Вы уже являетесь владельцем чата.</b>", parse_mode='HTML')
            return

        # Восстанавливаем владельца в должности (ранг 5)
        user_link = await user_link_global(UserId)
        gender = await get_user_gender(UserId)

        if current_rang == 0:
            # Если не был администратором - добавляем
            await add_admin_for_rang(UserId, ChatId, 5, UserId, 5, time)
            await add_history_admin_for_rang(UserId, ChatId, 5, 0, UserId, 5, time)
        else:
            # Если был администратором младшего ранга - обновляем до владельца
            await update_admin_for_rang(5, UserId, 5, time, UserId, ChatId)
            await add_history_admin_for_rang(UserId, ChatId, 5, current_rang, UserId, 5, time)

        # Уведомляем чат
        await m.reply(
            f"👑 {user_link} восстановл{g('ен', gender)} в должности владельца!",
            parse_mode='HTML',
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(e, exc_info=True)
        await m.answer("❌ <b>Произошла ошибка при восстановлении должности.</b>", parse_mode='HTML')


@chatadmin.callback_query(lambda c: c.data.startswith(('log_prev_', 'log_next_')))
@rate_limit_with_cleanup(limit=1)
async def handle_log_pagination(callback: CallbackQuery):
    try:

        if (not callback.message.reply_to_message or
            callback.from_user.id != callback.message.reply_to_message.from_user.id):
            random_text = get_random_text()
            await callback.answer(f"{random_text}", show_alert=True)
            return

        data_parts = callback.data.split('_')
        action = data_parts[1]  # prev или next
        user_id = int(data_parts[2])
        page_num = int(data_parts[3])

        # Получаем историю заново
        HISTORY = await check_history_admin_for_rang(user_id, callback.message.chat.id)

        if not HISTORY:
            await callback.answer("История не найдена")
            return

        # Создаем пагинацию
        pagination = LogPagination(HISTORY, items_per_page=5)
        page_data = pagination.get_page_data(page_num)

        user_link = await user_link_global(user_id)

        # Формируем текст для новой страницы
        text = f'🗃️ <b>Админ-лог {user_link}</b> (стр. {pagination.current_page}/{pagination.total_pages})\n\n'

        for i, AH in enumerate(page_data, start=(page_num - 1) * 5 + 1):
            rang, OldRang, ManagementAdminId, time = AH
            ManagementAdminLink = await user_link_global(ManagementAdminId)

            gender = await get_user_gender(user_id)
            gender_admin = await get_user_gender(ManagementAdminId)

            if OldRang > rang:
                t = f'🔴 пониж{g("ен", gender)} с {OldRang} до {rang}'
            elif OldRang < rang:
                t = f'🟢 повыш{g("ен", gender)} с {OldRang} до {rang}'
            else:
                t = '⚠️ ОШИБКА ПОДСЧЁТА'

            text += (f'{i}. '
                     f'{t} | {time}\n'
                     f'Назнач{g("ил", gender_admin)}: {ManagementAdminLink}\n\n')

        await callback.message.edit_text(
            text=text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=pagination.create_pagination_keyboard(page=page_num, user_id=user_id)
        )
        await callback.answer()

    except Exception as e:
        logger.error(e, exc_info=True)
        await callback.answer("❌ Ошибка при переключении страницы")


# Обработчик для кнопки текущей страницы
@chatadmin.callback_query(lambda c: c.data == "log_current")
@rate_limit_with_cleanup(limit=1)
async def handle_current_page(callback: CallbackQuery):
    await callback.answer(f"Текущая страница")