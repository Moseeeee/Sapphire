import re
from datetime import timedelta, datetime
import asyncio
import math

from aiogram import Router, Bot, F
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile, ChatPermissions,
    InlineKeyboardButton, InlineKeyboardMarkup, ChatMemberUpdated
)


from handlers.AdminsTools.ChatSettings.captcha.captchaDB import *
from handlers.AdminsTools.CommandsModerations.bans.ban import perform_ban
from handlers.AdminsTools.ChatSettings.captcha.captcha_generator import CaptchaGenerator
from handlers.AdminsTools.CommandsModerations.mute.mute import get_chat_permissions
from handlers.BotAutomaticWork.parse_time_auto import format_duration, parse_time_string
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang, \
    check_user_access
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import get_random_text, rate_limit_with_cleanup
from BotAutomaticWork.users.checks.check_UserId.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender

logger = logging.getLogger(__name__)

captcha_router = Router()
captcha_generator = CaptchaGenerator()

# Хранилище активных капч: ключ = (chat_id, user_id)
active_captchas = {}

# Константы для пагинации
USERS_PER_PAGE = 10
HISTORY_PER_PAGE = 10




async def handle_new_member(event: ChatMemberUpdated, bot: Bot):
    """Обработчик нового участника чата — отправляем ссылку на капчу в чате"""
    user = event.new_chat_member.user
    chat_id = event.chat.id

    # Игнорируем самого бота
    if user.id == bot.id:
        return

    # Проверяем, включена ли капча в чате
    if not await is_captcha_enabled(chat_id):
        return

    # Получаем текущие настройки капчи
    time_limit_str, current_difficulty, attempts_limit, _ = await get_captcha_settings(chat_id)
    time_limit = parse_time_string(time_limit_str) or timedelta(minutes=5)

    # Проверяем, проходил ли пользователь капчу ранее в этом чате
    last_successful_captcha = await get_user_last_successful_captcha(chat_id, user.id)

    if last_successful_captcha:
        difficulty_levels = {'легкая': 1, 'средняя': 2, 'тяжелая': 3, 'хардкорд': 4}
        current_level = difficulty_levels.get(current_difficulty, 1)
        previous_level = difficulty_levels.get(last_successful_captcha[0], 1)

        if current_level <= previous_level:
            # Текущая сложность такая же или проще — пропускаем капчу
            try:
                success = await perform_captcha_unmute(chat_id, user.id, bot)
                if success:
                    gender = await get_user_gender(user.id)
                    user_link = await user_link_global(user.id)
                    chat_message = await bot.send_message(
                        chat_id=chat_id,
                        text=f"✅ {user_link} уже проход{g('ил', gender)} капчу ({last_successful_captcha[0]}) и "
                             f"был автоматически допуще{g('ен', gender)} в чат.",
                        parse_mode="HTML"
                    )
                    asyncio.create_task(delete_message_after_delay(bot, chat_id, chat_message.message_id, 20))
                return
            except Exception as e:
                logger.error(e, exc_info=True)
        else:
            # Сложность повышена — требуем перепрохождение

            #chat_message = await bot.send_message(
                #chat_id=chat_id,
                #text=f"⚠️ {user_link}, сложность капчи в чате повышена. Требуется пройти капчу заново.",
                #parse_mode="HTML"
            #)
            print('ох блина')
            #asyncio.create_task(delete_message_after_delay(bot, chat_id, chat_message.message_id, 20))

    # Мьютим пользователя
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False
            )
        )
    except Exception as e:
        logger.error(f"Не удалось замутить {user.id} в {chat_id}: {e}", exc_info=True)
        return

    # Генерируем deep link для перехода в ЛС
    bot_info = await bot.get_me()
    payload = f"captcha_{chat_id}_{user.id}"
    deep_link = f"https://t.me/{bot_info.username}?start={payload}"
    tag_link = f'<a href="tg://user?id={user.id}">\u200e</a>'

    # Отправляем сообщение в чат с кнопкой
    try:
        user_link = await user_link_global(user.id)
        msg = await bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ <b>{user_link},{tag_link}сложность капчи в чате повышена. Требуется пройти капчу заново.</b>\nНажмите на кнопку ниже, чтобы пройти капчи",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔐 Перейти к прохождению капче", url=deep_link)]
            ]),
            parse_mode='HTML'
        )
        # Удалим сообщение через 5 минут
        asyncio.create_task(delete_message_after_delay(bot, chat_id, msg.message_id, 300))
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение с капчей: {e}", exc_info=True)
        # Опционально: банить, если не получилось уведомить
        try:
            await bot.ban_chat_member(chat_id, user.id)
            await bot.unban_chat_member(chat_id, user.id)
        except:
            pass




class CaptchaSession:
    def __init__(self, user_id: int, chat_id: int, answer: str, captcha_type: str, difficulty: str, attempts_limit: int):
        self.user_id = user_id
        self.chat_id = chat_id
        self.answer = answer
        self.captcha_type = captcha_type
        self.difficulty = difficulty
        self.start_time = datetime.now()
        self.attempts = 0
        self.attempts_limit = attempts_limit


async def delete_message_after_delay(bot: Bot, chat_id: int, message_id: int, delay: int):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def analyze_captcha_behavior(chat_id: int, user_id: int, total: int, success_count: int, success_rate: float) -> str:
    if total == 0:
        return "Никогда не проходил капчу"

    history = await get_user_captcha_history(chat_id, user_id, limit=20, offset=0)
    successes = [h for h in history if h[2]]
    sorted_history = sorted(history, key=lambda x: x[4])

    if total >= 10 and success_rate < 10:
        return "Автогенератор (спам-бот)"
    if total >= 5 and success_rate < 20:
        fast_auto = any(s[3] <= 1.5 and s[1] in ('средняя', 'тяжелая') for s in successes)
        if not fast_auto:
            return "ЮзерБот (автоматизация)"
    if any(s[3] <= 1.5 and s[1] in ('средняя', 'тяжелая') for s in successes):
        return "Автокликер / решатель"
    if total >= 4 and success_rate == 100.0:
        if all(s[3] <= 3 and s[1] in ('средняя', 'тяжелая') for s in successes):
            return "Скрытый бот? (идеальные результаты)"
    if any(s[3] >= 240 for s in successes):
        return "Затяжное прохождение (4+ минуты)"
    rapid_fails = 0
    for i in range(1, len(sorted_history)):
        prev, curr = sorted_history[i - 1], sorted_history[i]
        delta = (curr[4] - prev[4]).total_seconds()
        if not prev[2] and not curr[2] and delta < 5.0:
            rapid_fails += 1
    if rapid_fails >= 2:
        return "Много быстрых неудачных попыток"
    if total >= 3 and 20 <= success_rate < 50:
        return "Испытывает трудности с капчей"
    if total >= 3 and success_rate >= 80:
        if not any(s[3] <= 2 for s in successes if s[1] in ('средняя', 'тяжелая')):
            return "Стабильно проходит капчу"
    if total == 1:
        return "Успешная первая попытка" if success_count == 1 else "Неудачная первая попытка"
    return "ℹ️ Поведение не поддаётся однозначной классификации"


# === Внешний интерфейс: вызывается из /start или другого обработчика ===

async def send_captcha_to_user(bot: Bot, user_id: int, chat_id: int, difficulty: str, attempts_limit: int, time_limit: timedelta):
    """Отправляет капчу в ЛС и создаёт сессию. Вызывается ТОЛЬКО после начала диалога."""
    try:
        answer, image_buffer, captcha_type = await captcha_generator.generate_captcha(difficulty)
        caption = (
            f"🔐 <b>Капча для доступа к чату</b>\n\n"
            f"Время: {format_duration(time_limit)}\n"
            f"Сложность: {difficulty}\n"
            f"Попыток: {attempts_limit}\n\n"
            f"<i>Введите текст с картинки:</i>"
        )
        await bot.send_photo(
            chat_id=user_id,
            photo=BufferedInputFile(image_buffer.getvalue(), filename="captcha.png"),
            caption=caption,
            parse_mode="HTML"
        )

        session = CaptchaSession(
            user_id=user_id,
            chat_id=chat_id,
            answer=answer.lower(),
            captcha_type=captcha_type,
            difficulty=difficulty,
            attempts_limit=attempts_limit
        )
        active_captchas[(chat_id, user_id)] = session
        asyncio.create_task(captcha_timeout(chat_id, user_id, time_limit, bot, difficulty))

    except Exception as e:
        logger.error(f"Ошибка отправки капчи {user_id}: {e}", exc_info=True)


async def captcha_timeout(chat_id: int, user_id: int, timeout: timedelta, bot: Bot, difficulty: str):
    """Таймер капчи с гарантированным удалением из памяти."""
    try:
        await asyncio.sleep(timeout.total_seconds())

        if (chat_id, user_id) not in active_captchas:
            return

        session = active_captchas[(chat_id, user_id)]
        gender = await get_user_gender(user_id)

        ban_success, _ = await perform_ban(
            chat_id=chat_id,
            user_id=user_id,
            duration="навсегда",
            admin_id=bot.id,
            reason=f'Не прош{g("ол", gender)} капчу вовремя.'
        )

        if ban_success:
            try:
                await bot.send_message(user_id, "Время на прохождение капчи истекло. Вы были забанены.")
            except:
                pass

            try:
                user_link = await user_link_global(user_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"{user_link} не прош{g('ол', gender)} капчу вовремя и был забан{g('ен', gender)}.",
                    parse_mode="HTML"
                )
            except:
                pass

            time_taken = int((datetime.now() - session.start_time).total_seconds())
            await add_captcha_history(chat_id, user_id, session.captcha_type, session.difficulty, False, time_taken)

    except Exception as e:
        logger.error(f"Ошибка в captcha_timeout для {user_id}@{chat_id}: {e}", exc_info=True)
    finally:
        # 🔥 ГАРАНТИРОВАННОЕ УДАЛЕНИЕ — предотвращает утечку памяти
        active_captchas.pop((chat_id, user_id), None)


async def perform_captcha_unmute(chat_id: int, user_id: int, bot: Bot) -> bool:
    """Размут пользователя после успешного прохождения капчи."""
    try:
        chat_permissions = await get_chat_permissions(chat_id)
        await bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=chat_permissions)
        return True
    except Exception as e:
        logger.error(f"Ошибка размута {user_id}: {e}", exc_info=True)
        return False


# === Обработка ответов в ЛС (капча) ===

@captcha_router.message(F.chat.type == "private")
async def handle_private_message(message: Message, bot: Bot):
    user_id = message.from_user.id
    sessions = [sess for sess in active_captchas.values() if sess.user_id == user_id]

    if not sessions:
        return

    for session in sessions:
        user_answer = message.text.strip().lower()
        correct_answer = session.answer
        is_correct = user_answer == correct_answer
        session.attempts += 1
        time_taken = int((datetime.now() - session.start_time).total_seconds())
        gender = await get_user_gender(user_id)

        if is_correct:
            success = await perform_captcha_unmute(session.chat_id, user_id, bot)
            if success:
                await message.answer("✅ <b>Капча пройдена успешно!</b>\nТеперь вы полноправный участник чата.", parse_mode="HTML")
                try:
                    user_link = await user_link_global(user_id)
                    await bot.send_message(
                        chat_id=session.chat_id,
                        text=f"✅ {user_link} успешно прош{g('ел', gender)} капчу и допущен в чат!",
                        parse_mode="HTML"
                    )
                except:
                    pass
                await add_captcha_history(session.chat_id, user_id, session.captcha_type, session.difficulty, True, time_taken)
            else:
                await message.answer("Ошибка при размуте. Обратитесь к администратору.")
            active_captchas.pop((session.chat_id, user_id), None)

        else:
            remaining = session.attempts_limit - session.attempts
            if remaining > 0:
                await message.answer(f"Неправильный ответ! Осталось попыток: {remaining}")
            else:
                try:
                    await bot.ban_chat_member(chat_id=session.chat_id, user_id=user_id)
                    await message.answer("Превышено количество попыток. Вы были забанены в чате.")
                    try:
                        user_link = await user_link_global(user_id)
                        await bot.send_message(
                            chat_id=session.chat_id,
                            text=f"{user_link} превысил лимит попыток прохождения капчи и был забанен.",
                            parse_mode="HTML"
                        )
                    except:
                        pass
                    await add_captcha_history(session.chat_id, user_id, session.captcha_type, session.difficulty, False, time_taken)
                except Exception as e:
                    logger.error(f"Ошибка бана при превышении попыток: {e}", exc_info=True)
                    await message.answer("Ошибка при бане. Обратитесь к администратору.")
                active_captchas.pop((session.chat_id, user_id), None)


# === Команды управления капчей в чате ===

@captcha_router.message(F.text.regexp(re.compile(r'^\+капча$', re.IGNORECASE)))
async def enable_captcha_command_simple(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 44):
        return
    await enable_captcha(message.chat.id, 'средняя')
    time_limit_str, _, attempts_limit, _ = await get_captcha_settings(message.chat.id)
    time_limit = format_duration(parse_time_string(time_limit_str) or timedelta(minutes=5))
    await message.answer(
        f"✅ <b>Капча включена!</b>\n\n"
        f"Сложность: средняя (по умолчанию)\n"
        f"Время: {time_limit}\n"
        f"Попыток: {attempts_limit}\n\n"
        f"<i>Чтобы указать сложность, используйте:</i>\n"
        f"<code>+капча легкая</code>\n"
        f"<code>+капча тяжелая</code>\n"
        f"<code>+капча хардкорд</code>",
        parse_mode="HTML"
    )


@captcha_router.message(F.text.regexp(re.compile(r'^\+капча\s+', re.IGNORECASE)))
async def enable_captcha_command_with_args(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 44):
        return
    args = message.text[7:].strip()
    if not args:
        await message.answer("Укажите сложность капчи.", parse_mode="HTML")
        return
    difficulty = args.lower()
    if difficulty not in ['легкая', 'средняя', 'тяжелая', 'хардкорд']:
        await message.answer("Неверная сложность.", parse_mode="HTML")
        return
    await enable_captcha(message.chat.id, difficulty)
    time_limit_str, _, attempts_limit, _ = await get_captcha_settings(message.chat.id)
    time_limit = format_duration(parse_time_string(time_limit_str) or timedelta(minutes=5))
    await message.answer(
        f"✅ <b>Капча включена!</b>\n\n"
        f"Сложность: {difficulty}\n"
        f"Время: {time_limit}\n"
        f"Попыток: {attempts_limit}",
        parse_mode="HTML"
    )


@captcha_router.message(F.text.split("\n", 1)[0].lower() == '-капча')
async def disable_captcha_command(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 44):
        return
    await disable_captcha(message.chat.id)
    await message.answer(
        "✅ <b>Капча выключена!</b>\n"
        "Теперь новые участники смогут свободно писать в чате без прохождения капчи.",
        parse_mode="HTML"
    )


@captcha_router.message(F.text.func(lambda text: text and text.split("\n", 1)[0].lower() in ['.капча', '/капча', '!капча']))
async def captcha_status(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 44):
        return
    time_limit_str, difficulty, attempts_limit, enabled = await get_captcha_settings(message.chat.id)
    time_limit = format_duration(parse_time_string(time_limit_str) or timedelta(minutes=5))
    status = "включена" if enabled else "выключена"
    response = (
        f"🔐 <b>Статус капчи в чате</b>\n\n"
        f"Статус: {status}\n"
        f"Сложность: {difficulty}\n"
        f"Время: {time_limit}\n"
        f"Попыток: {attempts_limit}\n\n"
    )
    if enabled:
        response += (
            f"<i>Команды управления:</i>\n"
            f"<code>+капча [сложность]</code> - включить капчу\n"
            f"<code>-капча</code> - выключить капчу\n"
            f"<code>капча период</code> - установить время\n"
            f"<code>капча лимит</code> - установить попытки\n"
            f"<code>капча инфо @user</code> - прошёл ли юзер капчу в чате"
        )
    else:
        response += (
            f"<i>Чтобы включить капчу, используйте:</i>\n"
            f"<code>+капча [сложность]</code>\n"
            f"<i>Сложности:</i> легкая, средняя, тяжелая, хардкорд"
        )
    await message.answer(response, parse_mode="HTML")


@captcha_router.message(F.text.regexp(re.compile(r'^(?:[!./]:?)?капча период', re.IGNORECASE)))
async def set_captcha_period(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 44):
        return
    text = message.text.strip()
    if text and text[0] in '!./':
        text = text[1:].strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Укажите время для капчи. Пример: <code>капча период 5 минут</code>", parse_mode="HTML")
        return
    time_input = parts[2].strip()
    parsed_duration = parse_time_string(time_input)
    if parsed_duration is None:
        await message.answer("Не удалось распознать время.", parse_mode="HTML")
        return
    await update_captcha_settings(message.chat.id, time_limit=time_input)
    formatted = format_duration(parsed_duration)
    await message.answer(f"✅ Время для капчи установлено: <b>{formatted}</b>", parse_mode="HTML")


@captcha_router.message(F.text.regexp(re.compile(r'^(?:[!./]:?)?капча сложность', re.IGNORECASE)))
async def set_captcha_difficulty(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 44):
        return
    text = message.text.strip()
    if text and text[0] in '!./':
        text = text[1:].strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Укажите сложность капчи.", parse_mode="HTML")
        return
    difficulty = parts[2].strip().lower()
    if difficulty not in ['легкая', 'средняя', 'тяжелая', 'хардкорд']:
        await message.answer("Неверная сложность.", parse_mode="HTML")
        return
    await update_captcha_settings(message.chat.id, difficulty=difficulty)
    await message.answer(f"✅ Сложность капчи установлена: <b>{difficulty}</b>", parse_mode="HTML")


@captcha_router.message(F.text.regexp(re.compile(r'^(?:[!./]:?)?капча лимит', re.IGNORECASE)))
async def set_captcha_attempts(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 44):
        return
    text = message.text.strip()
    if text and text[0] in '!./':
        text = text[1:].strip()
    parts = text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Укажите количество попыток (1–10).", parse_mode="HTML")
        return
    try:
        attempts = int(parts[2].strip())
        if not (1 <= attempts <= 10):
            raise ValueError
    except ValueError:
        await message.answer("Укажите число от 1 до 10.", parse_mode="HTML")
        return
    await update_captcha_settings(message.chat.id, attempts_limit=attempts)
    await message.answer(f"✅ Лимит попыток для капчи установлен: <b>{attempts}</b>", parse_mode="HTML")


@captcha_router.message(F.text.regexp(re.compile(r'^(?:[!./]:?)?капча история', re.IGNORECASE)))
async def check_captcha_history(message: Message):
    """Показать историю капчи пользователя"""

    # Проверка доступа
    if not await check_user_access(message.from_user.id, 1):
        return

    user_id = None
    user_info = ""

    # 1. Проверяем ответ на сообщение (самый простой способ)
    if message.reply_to_message and message.reply_to_message.from_user:
        user_id = message.reply_to_message.from_user.id
        user_info = f"@{message.reply_to_message.from_user.username}" if message.reply_to_message.from_user.username else f"ID: {user_id}"

    # 2. Ищем упоминание/ссылку в тексте команды
    if not user_id:
        # Получаем текст после команды
        command_text = message.text.strip()

        # Убираем команду из начала
        for prefix in ['капча история', 'капча', 'история']:
            if command_text.lower().startswith(prefix):
                command_text = command_text[len(prefix):].strip()
                break

        # Убираем лишние символы команд
        command_text = command_text.lstrip('!./: ')


        # Пробуем разрешить ID/username/ссылку
        user_id = await resolve_id(message, command_text)

        if user_id:
            user_info = command_text

    # Если user_id не найден
    if not user_id:
        await message.answer(
            "Пользователь не найден."
        )
        return

    try:
        # Показываем историю капчи
        await show_user_captcha_history(message, user_id, page=0)

        # Логируем действие
        logger.info(f"User {message.from_user.id} checked captcha history for {user_id} ({user_info})")

    except Exception as e:
        logger.error(f"Error showing captcha history for {user_id}: {e}")
        await message.answer(
            "❌ Не удалось получить историю капчи.\n"
            "Возможно, у пользователя нет истории или произошла ошибка."
        )

async def show_user_captcha_history(message: Message, user_id: int, page: int = 0):
    chat_id = message.chat.id
    gender = await get_user_gender(user_id)
    offset = page * HISTORY_PER_PAGE
    history = await get_user_captcha_history(chat_id, user_id, HISTORY_PER_PAGE, offset)
    total, success_count, success_rate = await get_user_captcha_stats(chat_id, user_id)
    user_link = await user_link_global(user_id)

    response = f"📊 <b>История прохождения капчей {user_link}:</b>\n\n"
    diagnostic = await analyze_captcha_behavior(chat_id, user_id, total, success_count, success_rate)
    response += f"<b>{diagnostic}</b>\n\n"

    if not history:
        response += "📝 История капчи пуста."
    else:
        for i, (captcha_type, difficulty, success, time_taken, timestamp) in enumerate(history, start=offset + 1):
            status = f"✅ прош{g('ел', gender)}" if success else f"❌ не прош{g('ел', gender)}"
            time_str = format_duration(timedelta(seconds=time_taken))
            response += f"{i}. {status} {difficulty} за {time_str}\n"

    response += f"\n📈 Статистика: {success_count}/{total} ({success_rate:.1f}%)"

    keyboard = []
    total_pages = math.ceil(total / HISTORY_PER_PAGE)
    if total_pages > 1:
        row = []
        if page > 0:
            row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"captcha_history_{user_id}_{page - 1}"))
        if page < total_pages - 1:
            row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"captcha_history_{user_id}_{page + 1}"))
        if row:
            keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
    await message.reply(response, parse_mode="HTML", disable_web_page_preview=True, reply_markup=reply_markup)


@captcha_router.message(F.text.regexp(re.compile(r'^(?:[!./]:?)?капча инфо', re.IGNORECASE)))
async def show_captcha_info(message: Message):
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 45):
        return

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        user_specified = True
    else:
        text = message.text
        prefixes = ['.капча инфо', '/капча инфо', '!капча инфо', 'капча инфо']
        arg_text = None
        for prefix in sorted(prefixes, key=len, reverse=True):
            if text.lower().startswith(prefix.lower()):
                arg_text = text[len(prefix):].strip()
                break
        if arg_text:
            user_id = await resolve_id(message, arg_text)
            user_specified = True
        else:
            user_id = None
            user_specified = False

    chat_id = message.chat.id

    if user_id and user_specified:
        recent_captcha = await get_user_recent_captcha(chat_id, user_id)
        user_link = await user_link_global(user_id)
        gender = await get_user_gender(user_id)

        if not recent_captcha:
            await message.answer(f"ℹ️ {user_link} еще не проход{g('ел', gender)} капчу в этом чате.", parse_mode="HTML")
            return

        difficulty, time_taken, timestamp, success = recent_captcha
        status = f"прош{g('ел', gender)}" if success else f"не прош{g('ел', gender)}"
        time_str = format_duration(timedelta(seconds=time_taken))
        date_str = timestamp.strftime("%d.%m.%Y %H:%M")

        response = (
            f"ℹ️ <b>Информация о капче</b>\n\n"
            f"Пользователь: {user_link}\n"
            f"Статус: {status}\n"
            f"Сложность: {difficulty}\n"
            f"Время: {time_str}\n"
            f"Дата: {date_str}"
        )
        await message.reply(response, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await show_all_captcha_users(message, page=0)


async def show_all_captcha_users(message: Message, page: int = 0):
    chat_id = message.chat.id
    offset = page * USERS_PER_PAGE
    users = await get_all_captcha_users(chat_id, USERS_PER_PAGE, offset)
    total_users = await get_total_captcha_users_count(chat_id)

    if not users:
        await message.reply("В этом чате еще никто не проходил капчу.", parse_mode="HTML")
        return

    response = "📋 <b>Пользователи, проходившие капчу:</b>\n\n"
    for i, (user_id,) in enumerate(users, start=offset + 1):
        recent_captcha = await get_user_recent_captcha(chat_id, user_id)
        user_link = await user_link_global(user_id)
        gender = await get_user_gender(user_id)

        if recent_captcha:
            difficulty, time_taken, timestamp, success = recent_captcha
            status = f"прош{g('ел', gender)}" if success else f"не прош{g('ел', gender)}"
            time_str = format_duration(timedelta(seconds=time_taken))
            response += f"{i}. {user_link} - {status} {difficulty} за {time_str}\n"
        else:
            response += f"{i}. {user_link} - нет данных\n"

    total_pages = max(1, math.ceil(total_users / USERS_PER_PAGE))
    if total_pages > 1:
        response += f"\n📄 Страница {page + 1} из {total_pages}"
    response += f"\nВсего пользователей: {total_users}"

    keyboard = []
    if total_pages > 1:
        row = []
        if page > 0:
            row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"captcha_users_{page - 1}"))
        start_page = max(0, page - 2)
        end_page = min(total_pages, page + 3)
        for p in range(start_page, end_page):
            if p == page:
                row.append(InlineKeyboardButton(text=f"•{p + 1}•", callback_data=f"captcha_users_{p}"))
            else:
                row.append(InlineKeyboardButton(text=str(p + 1), callback_data=f"captcha_users_{p}"))
        if page < total_pages - 1:
            row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"captcha_users_{page + 1}"))
        if row:
            keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
    await message.reply(response, parse_mode="HTML", disable_web_page_preview=True, reply_markup=reply_markup)


@captcha_router.callback_query(F.data.startswith('captcha_history_'))
@rate_limit_with_cleanup(limit=1)
async def handle_captcha_history_pagination(c: CallbackQuery):
    if not c.message.reply_to_message or c.from_user.id != c.message.reply_to_message.from_user.id:
        random_text = get_random_text()
        await c.answer(f"{random_text}", show_alert=True)
        return
    data_parts = c.data.split('_')
    user_id = int(data_parts[2])
    page = int(data_parts[3])
    await show_user_captcha_history(c.message, user_id, page)
    await c.answer()


@captcha_router.callback_query(F.data.startswith('captcha_users_'))
@rate_limit_with_cleanup(limit=1)
async def handle_captcha_users_pagination(c: CallbackQuery):
    if not c.message.reply_to_message or c.from_user.id != c.message.reply_to_message.from_user.id:
        random_text = get_random_text()
        await c.answer(f"{random_text}", show_alert=True)
        return
    page = int(c.data.split('_')[2])
    await show_all_captcha_users(c.message, page)
    await c.answer()