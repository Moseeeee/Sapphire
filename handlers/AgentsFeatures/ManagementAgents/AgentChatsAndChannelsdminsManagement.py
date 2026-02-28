import asyncio
import time
from typing import OrderedDict

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    Message,
    ChatMemberAdministrator, ChatMemberOwner
)

from handlers.BotAutomaticWork.Gonfig.config import sanor_ID
from handlers.BotAutomaticWork.universal_bot import bot
from handlers.BotAutomaticWork.users.checks.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global

agent_admin_management = Router()

# === РУЧНАЯ КОНФИГУРАЦИЯ ПРАВ ===
CHAT_RIGHTS_CONFIG = {
    -1002279817519: {
        "name": "Sapphire | Bugs and ideas",
        "rights": {
            "can_post_messages": True
        },
        "required_membership": True,
        "welcome_message": "📢 Для получения прав необходимо <a href='https://t.me/+MW1MFH6HolEzNjJi'>подписаться</a> на канал!\n\nОбязательно прочитайте закреп: https://t.me/c/2279817519/3",
        "success_message": "🎉 Вы назначены администратором канала!\n\n📌 <b>Обязательно прочитайте закреп:</b> https://t.me/c/2279817519/3\n\n⚠️ Обратите внимание на правила и обязанности администратора.",
        "send_success_message": True
    },

    -1002413177765: {
        "name": "Sapphire | Поддержка",
        "rights": {
            "can_delete_messages": True,
            "can_restrict_members": True,
            "can_invite_users": True,
        },
        "required_membership": True,
        "welcome_message": "👥 Для получения прав необходимо <a href='https://t.me/sapphire_sp_chat'>вступить</a> в чат!\n\n",
        "success_message": "🎉 Вы назначены администратором чата!\n\n📌 <b>Важные правила администрирования:</b>\n• Не злоупотребляйте правами\n• Соблюдайте правила сообщества\n• Помогайте новым участникам\n\nПо всем вопросам обращайтесь к главным администраторам.",
        "send_success_message": True
    },
}

# === ВСЕ ВОЗМОЖНЫЕ ПРАВА ===
ALL_PERMISSIONS = {
    # Основные права
    "can_change_info": "Изменить инфо",
    "can_delete_messages": "Удалять сообщения",
    "can_manage_video_chats": "Управлять видеочатами",
    "can_restrict_members": "Блокировать пользователей",
    "can_promote_members": "Назначать админов",
    "can_invite_users": "Приглашать пользователей",
    "can_pin_messages": "Закреплять сообщения",
    "can_manage_topics": "Управлять темами (форум)",
    "is_anonymous": "Анонимность",

    # Права для историй
    "can_post_stories": "Публиковать истории",
    "can_edit_stories": "Редактировать истории",
    "can_delete_stories": "Удалять истории",

    # Права для каналов
    "can_post_messages": "Отправлять сообщения (каналы)",
    "can_edit_messages": "Редактировать сообщения (каналы)",
}

# === УПРАВЛЕНИЕ СЕССИЯМИ ===
admin_sessions = OrderedDict()
MAX_SESSIONS = 50
SESSION_TIMEOUT = 600


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
async def cleanup_session(chat_id: int, user_id: int):
    await asyncio.sleep(SESSION_TIMEOUT)
    key = (chat_id, user_id)
    if key in admin_sessions:
        admin_sessions.pop(key, None)


def cleanup_old_sessions():
    while len(admin_sessions) > MAX_SESSIONS:
        key, session = admin_sessions.popitem(last=False)
        if "task" in session:
            session["task"].cancel()


async def is_user_admin(chat_id: int, user_id: int) -> bool:
    """Проверка, является ли пользователь админом"""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except:
        return False


async def check_membership(chat_id: int, user_id: int) -> bool:
    """Проверка, состоит ли пользователь в чате"""
    try:
        await bot.get_chat_member(chat_id, user_id)
        return True
    except:
        return False


async def notify_user_about_chat(user_id: int, chat_info: dict):
    """Уведомить пользователя о необходимости вступить в чат"""
    welcome = chat_info.get("welcome_message")
    if not welcome:
        return False

    try:
        await bot.send_message(user_id, welcome, parse_mode='HTML')
        return True
    except:
        return False


async def send_success_notification(user_id: int, chat_info: dict, chat_name: str):
    """
    Отправляет пользователю сообщение об успешном назначении
    """
    try:
        # Проверяем, нужно ли отправлять сообщение
        if not chat_info.get("send_success_message", True):
            return False, None

        # Получаем текст сообщения
        success_message = chat_info.get("success_message")
        if not success_message:
            # Если сообщение не указано, используем шаблон по умолчанию
            success_message = f"🎉 Вы назначены администратором в чате '{chat_name}'!\n\nПожалуйста, ознакомьтесь с правилами и обязанностями администратора."

        # Отправляем сообщение
        await bot.send_message(
            user_id,
            success_message,
            parse_mode='HTML',
            disable_web_page_preview=False
        )
        return True, success_message

    except Exception as e:
        # Если пользователь заблокировал бота или другая ошибка
        return False, str(e)


async def get_target_id(message: Message) -> int | None:
    """Получить ID целевого пользователя из сообщения"""
    # 1. Проверяем reply_to_message
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id

    # 2. Пытаемся получить ID из текста команды
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        mention = args[1]
        return await resolve_id(message, mention)

    return None


def format_chat_config() -> str:
    """Форматирование текущей конфигурации для отображения"""
    if not CHAT_RIGHTS_CONFIG:
        return "📭 Конфигурация пуста. Добавьте чаты в код."

    result = "📋 <b>Текущая конфигурация:</b>\n\n"

    for chat_id, config in CHAT_RIGHTS_CONFIG.items():
        result += f"<b>{config.get('name', 'Без названия')}</b> (ID: {chat_id})\n"

        # Права
        rights = config.get("rights", {})
        if rights:
            active_rights = [ALL_PERMISSIONS.get(k, k) for k, v in rights.items() if v]
            if active_rights:
                result += f"  🔹 Права: {', '.join(active_rights)}\n"

        # Требования
        if config.get("required_membership", True):
            result += f"  🔸 Требуется членство: Да\n"
        else:
            result += f"  🔸 Требуется членство: Нет\n"

        # Уведомления
        if config.get("send_success_message", False):
            result += f"  🔹 Уведомление при назначении: <b>Да</b>\n"
            success_msg = config.get("success_message", "")
            if success_msg:
                # Обрезаем длинное сообщение для отображения
                preview = success_msg[:50] + "..." if len(success_msg) > 50 else success_msg
                result += f"    📝 Текст: \"{preview}\"\n"
        else:
            result += f"  🔹 Уведомление при назначении: Нет\n"

        result += "\n"

    return result


# === КОМАНДА ПРОСМОТРА КОНФИГУРАЦИИ ===
@agent_admin_management.message(lambda m: m.text and m.text.lower() in ["права", "конфиг", "конфигурация"])
async def cmd_show_config(message: Message):
    """Показать текущую конфигурацию прав"""
    if message.from_user.id != sanor_ID:
        return

    config_text = format_chat_config()
    await message.reply(config_text, parse_mode='HTML', disable_web_page_preview=True)


# === ОСНОВНАЯ КОМАНДА +АДМИН ===
@agent_admin_management.message(lambda m: m.text and m.text.lower().startswith("+агентик"))
async def cmd_promote_admin(message: Message):

    if message.from_user.id != sanor_ID:
        return

    # Получаем ID целевого пользователя
    target_id = await get_target_id(message)
    if not target_id:
        await message.reply('❌ Пользователь не указан. Ответьте на сообщение пользователя или укажите его ID/юзернейм.')
        return

    requester = message.from_user
    chat_id = message.chat.id

    # Проверки
    if target_id == bot.id:
        return await message.reply("❌ Не могу назначить себя.")



    user_link = await user_link_global(target_id)

    # Если конфигурация пуста
    if not CHAT_RIGHTS_CONFIG:
        return await message.reply(
            "❌ Конфигурация прав не настроена.\n"
            "Добавьте чаты в переменную CHAT_RIGHTS_CONFIG в коде бота."
        )

    results = []
    detailed_results = []
    notification_results = []

    # Собираем статистику по уведомлениям
    notifications_sent = 0
    notifications_failed = 0

    # Применяем права для каждого настроенного чата
    for config_chat_id, chat_info in CHAT_RIGHTS_CONFIG.items():
        chat_name = chat_info.get("name", f"Чат {config_chat_id}")

        try:
            # 1. Проверка прав бота
            bot_member = await bot.get_chat_member(config_chat_id, bot.id)
            if not isinstance(bot_member, ChatMemberAdministrator):
                results.append(f"❌ {chat_name}: бот не админ")
                detailed_results.append(f"❌ <b>{chat_name}</b> - бот не является администратором")
                continue

            # 2. Проверка членства пользователя (если требуется)
            if chat_info.get("required_membership", True):
                if not await check_membership(config_chat_id, target_id):
                    results.append(f"⏳ {chat_name}: нет в чате")
                    detailed_results.append(f"⏳ <b>{chat_name}</b> - пользователь не состоит в чате")

                    # Отправляем уведомление в ЛС
                    notified = await notify_user_about_chat(target_id, chat_info)
                    if notified:
                        detailed_results[-1] += " (отправлено приглашение в ЛС)"

                    continue

            # 3. Проверка цели
            target_member = await bot.get_chat_member(config_chat_id, target_id)

            if isinstance(target_member, ChatMemberOwner):
                results.append(f"👑 {chat_name}: владелец")
                detailed_results.append(f"👑 <b>{chat_name}</b> - пользователь является владельцем")
                continue

            # 4. Получаем права для выдачи
            rights_to_grant = chat_info.get("rights", {})

            # Если пользователь уже админ, проверяем нужны ли изменения
            if isinstance(target_member, ChatMemberAdministrator):
                need_update = False
                current_rights = {}

                # Собираем текущие права
                for perm in rights_to_grant.keys():
                    if hasattr(target_member, perm):
                        current_rights[perm] = getattr(target_member, perm)

                # Сравниваем с требуемыми
                for perm, required_value in rights_to_grant.items():
                    if perm in current_rights and current_rights[perm] != required_value:
                        need_update = True
                        break

                if not need_update:
                    results.append(f"✅ {chat_name}: права уже выданы")
                    detailed_results.append(f"✅ <b>{chat_name}</b> - права уже установлены правильно")

                    # Даже если права уже были, можно отправить уведомление
                    if chat_info.get("send_success_message", False):
                        success, result = await send_success_notification(target_id, chat_info, chat_name)
                        if success:
                            notification_results.append(f"📨 {chat_name}: отправлено напоминание")
                            notifications_sent += 1
                        elif result:
                            notification_results.append(f"⚠️ {chat_name}: не удалось отправить ({result})")
                            notifications_failed += 1

                    continue

            # 5. Выдача/обновление прав
            promote_params = {
                "chat_id": config_chat_id,
                "user_id": target_id,
            }

            # Добавляем только те права, которые есть в конфигурации
            for perm, value in rights_to_grant.items():
                if perm in ALL_PERMISSIONS:
                    promote_params[perm] = value

            # Для каналов добавляем специальные параметры
            chat = await bot.get_chat(config_chat_id)
            if chat.type == "channel":
                if "can_post_messages" not in promote_params:
                    promote_params["can_post_messages"] = False
                if "can_edit_messages" not in promote_params:
                    promote_params["can_edit_messages"] = False

            await bot.promote_chat_member(**promote_params)
            results.append(f"✅ {chat_name}: права выданы")

            granted_rights = [ALL_PERMISSIONS.get(k, k) for k, v in rights_to_grant.items() if v]
            if granted_rights:
                detailed_results.append(f"✅ <b>{chat_name}</b> - выданы права: {', '.join(granted_rights)}")
            else:
                detailed_results.append(f"✅ <b>{chat_name}</b> - выданы стандартные права")

            # 6. Отправляем уведомление пользователю
            success, result = await send_success_notification(target_id, chat_info, chat_name)
            if success:
                notification_results.append(f"📨 {chat_name}: уведомление отправлено")
                notifications_sent += 1
            elif result:
                notification_results.append(f"⚠️ {chat_name}: уведомление не отправлено ({result})")
                notifications_failed += 1

        except TelegramAPIError as e:
            error_msg = str(e)
            if "not enough rights" in error_msg.lower():
                results.append(f"🚫 {chat_name}: недостаточно прав")
                detailed_results.append(f"🚫 <b>{chat_name}</b> - у бота недостаточно прав")
            else:
                results.append(f"❌ {chat_name}: ошибка API")
                detailed_results.append(f"❌ <b>{chat_name}</b> - ошибка Telegram: {error_msg}")

        except Exception as e:
            results.append(f"⚠️ {chat_name}: ошибка")
            detailed_results.append(f"⚠️ <b>{chat_name}</b> - ошибка: {str(e)}")

    # Формируем итоговое сообщение
    summary = "\n".join(results)
    details = "\n".join(detailed_results)

    # Добавляем информацию об уведомлениях
    notification_info = ""
    if notification_results:
        notification_info = f"\n\n<b>📨 Уведомления пользователю:</b>\n" + "\n".join(notification_results)

    # Общая статистика
    stats = f"\n\n📊 <b>Статистика:</b> Уведомлений отправлено: {notifications_sent} | Не отправлено: {notifications_failed}"

    result_message = (
        f"📊 <b>Результат выдачи прав для {user_link}:</b>\n\n"
        f"{summary}"
        f"{notification_info}"
        f"{stats}\n\n"
        f"<b>Подробно:</b>\n{details}"
    )

    await message.reply(result_message, parse_mode='HTML', disable_web_page_preview=True)


# === КОМАНДА -АДМИН ===
@agent_admin_management.message(lambda m: m.text and m.text.lower().startswith("-агентик"))
async def cmd_demote_admin(message: Message):

    if message.from_user.id != sanor_ID:
        return

    target_id = await get_target_id(message)
    if not target_id:
        await message.reply('❌ Пользователь не указан. Ответьте на сообщение пользователя или укажите его ID/юзернейм.')
        return

    requester = message.from_user
    chat_id = message.chat.id

    # Проверки
    if target_id == bot.id:
        return await message.reply("❌ Не могу снять с себя права.")

    if not await is_user_admin(chat_id, requester.id):
        return await message.reply("❌ Только админы могут снимать админов.")

    user_link = await user_link_global(target_id)

    # Если конфигурация пуста
    if not CHAT_RIGHTS_CONFIG:
        return await message.reply(
            "❌ Конфигурация прав не настроена.\n"
            "Добавьте чаты в переменную CHAT_RIGHTS_CONFIG в коде бота."
        )

    results = []
    detailed_results = []

    # Снимаем права во всех настроенных чатах
    for config_chat_id, chat_info in CHAT_RIGHTS_CONFIG.items():
        chat_name = chat_info.get("name", f"Чат {config_chat_id}")

        try:
            # 1. Проверка прав бота
            bot_member = await bot.get_chat_member(config_chat_id, bot.id)
            if not isinstance(bot_member, ChatMemberAdministrator):
                results.append(f"❌ {chat_name}: бот не админ")
                detailed_results.append(f"❌ <b>{chat_name}</b> - бот не является администратором")
                continue

            # 2. Проверка цели
            target_member = await bot.get_chat_member(config_chat_id, target_id)

            if isinstance(target_member, ChatMemberOwner):
                results.append(f"👑 {chat_name}: владелец")
                detailed_results.append(f"👑 <b>{chat_name}</b> - пользователь является владельцем")
                continue

            if not isinstance(target_member, ChatMemberAdministrator):
                results.append(f"✅ {chat_name}: не админ")
                detailed_results.append(f"✅ <b>{chat_name}</b> - пользователь не является администратором")
                continue

            # 3. Снимаем права
            await bot.ban_chat_member(
                chat_id=config_chat_id,
                user_id=target_id
            )

            results.append(f"✅ {chat_name}: права сняты")
            detailed_results.append(f"✅ <b>{chat_name}</b> - все права сняты")

        except TelegramAPIError as e:
            error_msg = str(e)
            if "not enough rights" in error_msg.lower():
                results.append(f"🚫 {chat_name}: недостаточно прав")
                detailed_results.append(f"🚫 <b>{chat_name}</b> - у бота недостаточно прав")
            else:
                results.append(f"❌ {chat_name}: ошибка API")
                detailed_results.append(f"❌ <b>{chat_name}</b> - ошибка Telegram: {error_msg}")

        except Exception as e:
            results.append(f"⚠️ {chat_name}: ошибка")
            detailed_results.append(f"⚠️ <b>{chat_name}</b> - ошибка: {str(e)}")

    # Формируем итоговое сообщение
    summary = "\n".join(results)
    details = "\n".join(detailed_results)

    result_message = (
        f"📊 <b>Результат блокировок {user_link}:</b>\n\n"
        f"{summary}\n\n"
        f"<b>Подробно:</b>\n{details}"
    )

    await message.reply(result_message, parse_mode='HTML', disable_web_page_preview=True)


# === КОМАНДА ДЛЯ ПРОВЕРКИ ===
@agent_admin_management.message(lambda m: m.text and m.text.lower().startswith("проверить права"))
async def cmd_check_rights(message: Message):

    if message.from_user.id != sanor_ID:
        return

    """Проверить права пользователя в настроенных чатах"""
    target_id = await get_target_id(message)
    if not target_id:
        await message.reply('❌ Пользователь не указан. Ответьте на сообщение пользователя или укажите его ID/юзернейм.')
        return



    user_link = await user_link_global(target_id)

    if not CHAT_RIGHTS_CONFIG:
        return await message.reply("❌ Конфигурация не настроена.")

    results = []

    for config_chat_id, chat_info in CHAT_RIGHTS_CONFIG.items():
        chat_name = chat_info.get("name", f"Чат {config_chat_id}")

        try:
            target_member = await bot.get_chat_member(config_chat_id, target_id)

            if isinstance(target_member, ChatMemberOwner):
                results.append(f"👑 {chat_name}: Владелец")
            elif isinstance(target_member, ChatMemberAdministrator):
                # Проверяем какие права есть
                admin_rights = []
                for perm, label in ALL_PERMISSIONS.items():
                    if hasattr(target_member, perm) and getattr(target_member, perm):
                        admin_rights.append(label)

                if admin_rights:
                    results.append(f"✅ {chat_name}: Админ ({', '.join(admin_rights[:3])})")
                else:
                    results.append(f"⚠️ {chat_name}: Админ без прав")
            else:
                results.append(f"❌ {chat_name}: Не админ")

        except Exception as e:
            results.append(f"🚫 {chat_name}: Ошибка ({str(e)})")

    result_text = f"🔍 <b>Права {user_link}:</b>\n\n" + "\n".join(results)
    await message.reply(result_text, parse_mode='HTML', disable_web_page_preview=True)


# === КОМАНДА ДЛЯ УПРАВЛЕНИЯ УВЕДОМЛЕНИЯМИ ===
@agent_admin_management.message(lambda m: m.text and m.text.lower().startswith("уведомления"))
async def cmd_notifications_info(message: Message):
    """Показать информацию о настройках уведомлений"""
    if message.from_user.id != sanor_ID:
        return

    result = "🔔 <b>Настройки уведомлений:</b>\n\n"

    for chat_id, config in CHAT_RIGHTS_CONFIG.items():
        chat_name = config.get("name", f"Чат {chat_id}")
        send_msg = config.get("send_success_message", False)

        if send_msg:
            result += f"✅ <b>{chat_name}</b>: уведомления ВКЛ\n"
            msg = config.get("success_message", "Стандартное сообщение")
            preview = msg[:80] + "..." if len(msg) > 80 else msg
            result += f"   📄 {preview}\n\n"
        else:
            result += f"❌ <b>{chat_name}</b>: уведомления ВЫКЛ\n\n"

    result += "\n<i>Для изменения текста уведомлений отредактируйте конфигурацию в коде бота.</i>"

    await message.reply(result, parse_mode='HTML')


# === КОМАНДА ДЛЯ ТЕСТА ОТПРАВКИ УВЕДОМЛЕНИЙ ===
@agent_admin_management.message(lambda m: m.text and m.text.lower().startswith("тест уведомления"))
async def cmd_test_notification(message: Message):
    """Тестовая отправка уведомления себе"""
    if message.from_user.id != sanor_ID:
        return

    user_id = message.from_user.id

    result = "🧪 <b>Тест отправки уведомлений:</b>\n\n"

    for chat_id, config in CHAT_RIGHTS_CONFIG.items():
        chat_name = config.get("name", f"Чат {chat_id}")

        if not config.get("send_success_message", False):
            result += f"❌ <b>{chat_name}</b>: уведомления отключены\n"
            continue

        try:
            success, msg = await send_success_notification(user_id, config, chat_name)
            if success:
                result += f"✅ <b>{chat_name}</b>: тестовое уведомление отправлено\n"
            else:
                result += f"❌ <b>{chat_name}</b>: ошибка: {msg}\n"
        except Exception as e:
            result += f"⚠️ <b>{chat_name}</b>: исключение: {str(e)}\n"

    await message.reply(result, parse_mode='HTML')


# === ФОНОВЫЙ СБОРЩИК МУСОРА ===
async def garbage_collector():
    """Фоновая очистка старых сессий"""
    while True:
        await asyncio.sleep(300)  # каждые 5 минут
        now = time.time()
        to_remove = [
            key for key, sess in admin_sessions.items()
            if now - sess.get("created_at", 0) > SESSION_TIMEOUT
        ]
        for key in to_remove:
            if key in admin_sessions:
                admin_sessions[key]["task"].cancel()
                admin_sessions.pop(key, None)


# === СТАРТ СБОРЩИКА ПРИ ЗАПУСКЕ ===
@agent_admin_management.startup()
async def start_garbage_collector():
    asyncio.create_task(garbage_collector())