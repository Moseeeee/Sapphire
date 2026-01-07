
import re

from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile, ChatPermissions, InlineKeyboardButton, \
    InlineKeyboardMarkup

from aiogram.filters.chat_member_updated import ChatMemberUpdated

from datetime import timedelta, datetime
import asyncio
import math

from handlers.AgentsFeatures.payment.payment import check_user_access
from handlers.BotAutomaticWork.Gonfig.config import boss_agent
from handlers.AdminsTools.ChatSettings.captcha.captchaDB import *
from handlers.AdminsTools.CommandsModerations.bans.ban import perform_ban
from handlers.AdminsTools.ChatSettings.captcha.captcha_generator import CaptchaGenerator
from handlers.AdminsTools.CommandsModerations.mute.mute import get_chat_permissions
from handlers.BotAutomaticWork.parse_time_auto import format_duration, parse_time_string
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_flood_inline_and_text import get_random_text, rate_limit_with_cleanup
from handlers.BotAutomaticWork.users.checks.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.users_global_link import user_link_global
from handlers.UserCommands.GenderSettings.GenderSettingsDB import get_user_gender

captcha_router = Router()
captcha_generator = CaptchaGenerator()

# Хранилище активных капч
active_captchas = {}

# Константы для пагинации
USERS_PER_PAGE = 10
HISTORY_PER_PAGE = 10


class CaptchaSession:
    def __init__(self, user_id: int, chat_id: int, answer: str, captcha_type: str, difficulty: str,
                 attempts_limit: int):
        self.user_id = user_id
        self.chat_id = chat_id
        self.answer = answer
        self.captcha_type = captcha_type
        self.difficulty = difficulty
        self.start_time = datetime.now()
        self.attempts = 0
        self.attempts_limit = attempts_limit


async def handle_new_member(event: ChatMemberUpdated, bot: Bot):
    """Обработчик нового участника чата - отправляем капчу в ЛС"""
    user = event.new_chat_member.user
    chat_id = event.chat.id

    # Игнорируем самого бота
    if user.id == bot.id:
        return

    # Проверяем, включена ли капча в чате
    if not await is_captcha_enabled(chat_id):
        return

    # Получаем текущие настройки капчи в чате
    time_limit_str, current_difficulty, attempts_limit, _ = await get_captcha_settings(chat_id)
    time_limit = parse_time_string(time_limit_str) or timedelta(minutes=5)

    # Проверяем, проходил ли пользователь капчу ранее в этом чате
    last_successful_captcha = await get_user_last_successful_captcha(chat_id, user.id)

    if last_successful_captcha:
        # Пользователь уже проходил капчу в этом чате
        previous_difficulty, previous_time_taken, previous_timestamp = last_successful_captcha

        # Сравниваем сложности
        difficulty_levels = {
            'легкая': 1,
            'средняя': 2,
            'тяжелая': 3,
            'хардкорд': 4
        }

        current_level = difficulty_levels.get(current_difficulty, 1)
        previous_level = difficulty_levels.get(previous_difficulty, 1)

        if current_level <= previous_level:
            # Текущая сложность такая же или проще - пропускаем капчу
            try:
                # Размучиваем пользователя сразу
                success = await perform_captcha_unmute(chat_id, user.id, bot)

                if success:
                    gender = await get_user_gender(user.id)

                    user_link = await user_link_global(user.id)
                    chat_message = await bot.send_message(
                        chat_id=chat_id,
                        text=f"✅ {user_link} уже проход{g('ил', gender)} капчу ({previous_difficulty}) и {g('был', gender)} автоматически допуще{g('ен', gender)} в чат.",
                        parse_mode="HTML"
                    )

                    # Уведомляем в ЛС
                    try:
                        pm_message = await bot.send_message(
                            chat_id=user.id,
                            text=f"✅ Вы уже проходили капчу в этом чате и были автоматически допущены.",
                            parse_mode="HTML"
                        )
                        await asyncio.sleep(20)
                        await bot.delete_message(user.id, pm_message.message_id)
                    except:
                        pass

                    # Удаляем сообщение из чата через 5 секунд
                    await asyncio.sleep(20)
                    try:
                        await bot.delete_message(chat_id, chat_message.message_id)
                    except:
                        pass

                    return  # Выходим - капча не требуется
                else:
                    await bot.send_message(
                        chat_id=user.id,
                        text=f"⚠️ Не удалось снять мут с пользователя.",
                        parse_mode="HTML"
                    )

            except Exception as e:
                logger.error(e, exc_info=True)
        else:
            # Текущая сложность выше - требуем перепрохождение
            user_link = await user_link_global(user.id)
            chat_message = await bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ {user_link}, сложность капчи в чате повышена. Требуется пройти капчу заново.",
                parse_mode="HTML"
            )

            await asyncio.sleep(20)
            try:
                await bot.delete_message(chat_id, chat_message.message_id)
            except:
                pass

    # Мьютим пользователя навсегда в чате (если требуется капча)
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
        logger.error(e, exc_info=True)
        return

    try:
        # Отправляем капчу в ЛС
        await send_captcha_to_user(bot, user.id, chat_id, current_difficulty, attempts_limit, time_limit)

    except Exception:
        try:
            await bot.ban_chat_member(chat_id=chat_id, user_id=user.id)
            await bot.unban_chat_member(chat_id=chat_id, user_id=user.id)
            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ Не удалось отправить капчу пользователю {user.first_name}. Пользователь исключен."
            )
        except:
            pass



async def analyze_captcha_behavior(chat_id: int, user_id: int, total: int, success_count: int, success_rate: float) -> str:
    """Расширенный анализ поведения пользователя по капче."""
    if total == 0:
        return "🔒 Никогда не проходил капчу"

    history = await get_user_captcha_history(chat_id, user_id, limit=20, offset=0)  # Берём больше данных для анализа
    successes = [h for h in history if h[2]]  # h[2] = success
    fails = [h for h in history if not h[2]]

    # Сортируем по времени для анализа интервалов
    sorted_history = sorted(history, key=lambda x: x[4])  # x[4] = timestamp

    # === 1. 🔥 Автогенератор (спам-бот)
    if total >= 10 and success_rate < 10:
        return "🔥 Автогенератор (спам-бот)"

    # === 2. 🤖 ЮзерБот
    if total >= 5 and success_rate < 20:
        # Исключаем автокликеры (они обрабатываются позже)
        fast_auto = any(
            s[3] <= 1.5 and s[1] in ('средняя', 'сложная')
            for s in successes
        )
        if not fast_auto:
            return "🤖 ЮзерБот (автоматизация)"

    # === 3. ⚡ Автокликер / решатель
    if any(
        s[3] <= 1.5 and s[1] in ('средняя', 'сложная')
        for s in successes
    ):
        return "⚡ Автокликер / решатель"

    # === 4. 🕵️‍♂️ Скрытый бот?
    if total >= 4 and success_rate == 100.0:
        if all(s[3] <= 3 and s[1] in ('средняя', 'сложная') for s in successes):
            return "🕵️‍♂️ Скрытый бот? (идеальные результаты)"

    # === 5. 🕐 Затяжное прохождение
    if any(s[3] >= 240 for s in successes):
        return "⏳ Затяжное прохождение (4+ минуты)"

    # === 6. 🔄 Много попыток подряд (интервал < 5 сек)
    rapid_fails = 0
    for i in range(1, len(sorted_history)):
        prev = sorted_history[i - 1]
        curr = sorted_history[i]
        delta = (curr[4] - prev[4]).total_seconds()
        if not prev[2] and not curr[2] and delta < 5.0:
            rapid_fails += 1
    if rapid_fails >= 2:  # т.е. минимум 3 попытки за <10 сек
        return "🔄 Много быстрых неудачных попыток"

    # === 7. 📉 Сложности с капчей
    if total >= 3 and 20 <= success_rate < 50:
        return "📉 Испытывает трудности с капчей"

    # === 8. ✅ Стабильно проходит
    if total >= 3 and success_rate >= 80:
        # Проверка, что нет подозрительно быстрых решений
        if not any(s[3] <= 2 for s in successes if s[1] in ('средняя', 'сложная')):
            return "✅ Стабильно проходит капчу"

    # === 9. 🥱 Единичная попытка
    if total == 1:
        if success_count == 1:
            return "🥱 Успешная первая попытка"
        else:
            return "🥱 Неудачная первая попытка"

    # === Запасной вариант
    return "ℹ️ Поведение не поддаётся однозначной классификации"

@captcha_router.message(F.text.regexp(re.compile(r'^\+капча$', re.IGNORECASE)))
async def enable_captcha_command_simple(message: Message):
    """Включить капчу в чате - команда +капча (без аргументов)"""
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 44):
        return

    await enable_captcha(message.chat.id, 'средняя')

    # Получаем полные настройки для отображения
    time_limit_str, _, attempts_limit, _ = await get_captcha_settings(message.chat.id)
    time_limit = format_duration(parse_time_string(time_limit_str) or timedelta(minutes=5))

    await message.answer(
        f"✅ <b>Капча включена!</b>\n\n"
        f"🎯 Сложность: <b>средняя</b> (по умолчанию)\n"
        f"⏰ Время: <b>{time_limit}</b>\n"
        f"🔢 Попыток: <b>{attempts_limit}</b>\n\n"
        f"<i>Чтобы указать сложность, используйте:</i>\n"
        f"<code>+капча легкая</code>\n"
        f"<code>+капча тяжелая</code>\n"
        f"<code>+капча хардкорд</code>",
        parse_mode="HTML"
    )


@captcha_router.message(F.text.regexp(re.compile(r'^\+капча\s+', re.IGNORECASE)))
async def enable_captcha_command_with_args(message: Message):
    """Включить капчу в чате - команда +капча [сложность]"""
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 44):
        return

    text = message.text.strip()
    # Извлекаем аргумент после +капча
    args = text[7:].strip()  # +капча = 7 символов

    if not args:
        await message.answer(
            "❌ Укажите сложность капчи.\n"
            "Используйте: <code>+капча легкая</code>, <code>+капча средняя</code>, etc.",
            parse_mode="HTML"
        )
        return

    difficulty = args.lower()
    if difficulty not in ['легкая', 'средняя', 'тяжелая', 'хардкорд']:
        await message.answer(
            "❌ Неверная сложность. Используйте: <code>легкая</code>, <code>средняя</code>, "
            "<code>тяжелая</code> или <code>хардкорд</code>",
            parse_mode="HTML"
        )
        return

    await enable_captcha(message.chat.id, difficulty)

    time_limit_str, _, attempts_limit, _ = await get_captcha_settings(message.chat.id)
    time_limit = format_duration(parse_time_string(time_limit_str) or timedelta(minutes=5))

    await message.answer(
        f"✅ <b>Капча включена!</b>\n\n"
        f"🎯 Сложность: <b>{difficulty}</b>\n"
        f"⏰ Время: <b>{time_limit}</b>\n"
        f"🔢 Попыток: <b>{attempts_limit}</b>",
        parse_mode="HTML"
    )


@captcha_router.message(F.text.split("\n", 1)[0].lower() == '-капча')
async def disable_captcha_command(message: Message):
    """Выключить капчу в чате - команда -капча"""
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 44):
        return

    await disable_captcha(message.chat.id)
    await message.answer(
        "✅ <b>Капча выключена!</b>\n\n"
        "Теперь новые участники смогут свободно писать в чате без прохождения капчи.",
        parse_mode="HTML"
    )


@captcha_router.message(F.text.func(lambda text: text.split("\n", 1)[0].lower() in ['.капча', '/капча', '!капча']))
async def captcha_status(message: Message):
    """Показать статус капчи в чате - команда /капча"""
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 44):
        return

    time_limit_str, difficulty, attempts_limit, enabled = await get_captcha_settings(message.chat.id)
    time_limit = format_duration(parse_time_string(time_limit_str) or timedelta(minutes=5))

    status = "🟢 ВКЛЮЧЕНА" if enabled else "🔴 ВЫКЛЮЧЕНА"

    response = (
        f"🔐 <b>Статус капчи в чате</b>\n\n"
        f"📊 Статус: <b>{status}</b>\n"
        f"🎯 Сложность: <b>{difficulty}</b>\n"
        f"⏰ Время: <b>{time_limit}</b>\n"
        f"🔢 Попыток: <b>{attempts_limit}</b>\n\n"
    )

    if enabled:
        response += (
            f"<i>Команды управления:</i>\n"
            f"<code>+капча [сложность]</code> - включить капчу\n"
            f"<code>-капча</code> - выключить капчу\n"
            f"<code>капча период</code> - установить время\n"
            f"<code>капча лимит</code> - установить попытки\n"
            f"<code>чек капча @user</code> - история пользователя"
        )
    else:
        response += (
            f"<i>Чтобы включить капчу, используйте:</i>\n"
            f"<code>+капча [сложность]</code>\n"
            f"<i>Сложности:</i> легкая, средняя, тяжелая, хардкорд"
        )

    await message.answer(response, parse_mode="HTML")


async def send_captcha_to_user(bot: Bot, user_id: int, chat_id: int, difficulty: str, attempts_limit: int,
                               time_limit: timedelta):
    """Отправляет капчу пользователю в ЛС"""
    try:
        # Генерируем капчу
        answer, image_buffer, captcha_type = await captcha_generator.generate_captcha(difficulty)

        # Создаем сообщение с капчей
        caption = (f"🔐 <b>Капча для доступа к чату</b>\n\n"
                   f"⏰ Время: <b>{format_duration(time_limit)}</b>\n"
                   f"🎯 Сложность: <b>{difficulty}</b>\n"
                   f"🔢 Попыток: <b>{attempts_limit}</b>\n\n"
                   f"<i>Введите текст с картинки:</i>")

        # Отправляем капчу в ЛС
        await bot.send_photo(
            chat_id=user_id,
            photo=BufferedInputFile(image_buffer.getvalue(), filename="captcha.png"),
            caption=caption,
            parse_mode="HTML"
        )

        # Сохраняем сессию капчи
        session = CaptchaSession(
            user_id=user_id,
            chat_id=chat_id,
            answer=answer.lower(),
            captcha_type=captcha_type,
            difficulty=difficulty,
            attempts_limit=attempts_limit
        )

        active_captchas[(chat_id, user_id)] = session

        # Устанавливаем таймер
        asyncio.create_task(captcha_timeout(chat_id, user_id, time_limit, bot, difficulty))

    except Exception as e:
        logging.error(e)
        # Если не удалось отправить в ЛС, уведомляем в чат
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ Не удалось отправить капчу пользователю. Убедитесь, что он начал диалог с ботом.\n\nℹ️ Начните диалог с ботом и перезайдите в чат."
            )
        except:
            pass


async def captcha_timeout(chat_id: int, user_id: int, timeout: timedelta, bot: Bot, difficulty: str):
    """Таймаут для капчи"""
    await asyncio.sleep(timeout.total_seconds())

    session = active_captchas.get((chat_id, user_id))
    if session:
        # Время вышло - баним пользователя
        try:

            gender = await get_user_gender(user_id)
            ban_success, ban_result = await perform_ban(
                chat_id=chat_id,
                user_id=user_id,
                duration="навсегда",
                admin_id=bot.id,
                reason=f'Не прош{g("ол", gender)} капчу вовремя.'
            )

            if not ban_success:
                pass
            # Уведомляем в ЛС
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text="❌ Время на прохождение капчи истекло. Вы были забанены в чате."
                )
            except:
                pass

            # Уведомляем в чат
            try:
                user_link = await user_link_global(user_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ {user_link} не прош{g('ол', gender)} капчу вовремя и был забан{g('ен', gender)}.",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except:
                pass

            # Добавляем в историю
            time_taken = int((datetime.now() - session.start_time).total_seconds())
            await add_captcha_history(chat_id, user_id, session.captcha_type, session.difficulty, False, time_taken)

            # Удаляем сессию
            del active_captchas[(chat_id, user_id)]

        except Exception as e:
            logger.error(e, exc_info=True)


@captcha_router.message(F.chat.type == "private")
async def handle_private_message(message: Message, bot: Bot):
    """Обработка сообщений в ЛС (ответы на капчу)"""
    user_id = message.from_user.id

    # Ищем активные капчи для этого пользователя
    user_sessions = []
    for key, session in active_captchas.items():
        if session.user_id == user_id:
            user_sessions.append(session)

    if not user_sessions:
        return

    # Обрабатываем каждую активную капчу
    for session in user_sessions:
        user_answer = message.text.strip().lower()
        correct_answer = session.answer

        is_correct = user_answer == correct_answer
        session.attempts += 1
        time_taken = int((datetime.now() - session.start_time).total_seconds())
        gender = await get_user_gender(user_id)

        if is_correct:
            # Капча пройдена
            success = await perform_captcha_unmute(session.chat_id, user_id, bot)

            if success:
                await message.answer(
                    "✅ <b>Капча пройдена успешно!</b>\n"
                    "Теперь вы полноправный участник чата.",
                    parse_mode="HTML"
                )

                # Уведомляем в чат
                try:

                    user_link = await user_link_global(user_id)
                    await bot.send_message(
                        chat_id=session.chat_id,
                        text=f"✅ {user_link} успешно прош{g('ел', gender)} капчу и допущен в чат!",
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                except:
                    pass

                # Добавляем в историю
                await add_captcha_history(session.chat_id, user_id, session.captcha_type, session.difficulty, True,
                                          time_taken)
            else:
                await message.answer("❌ Ошибка при размуте. Обратитесь к администратору.")

            # Удаляем сессию
            del active_captchas[(session.chat_id, user_id)]

        else:
            # Неправильный ответ
            remaining_attempts = session.attempts_limit - session.attempts

            if remaining_attempts > 0:
                await message.answer(
                    f"❌ Неправильный ответ! Осталось попыток: {remaining_attempts}"
                )
            else:
                # Превышено количество попыток - баним
                try:
                    await bot.ban_chat_member(
                        chat_id=session.chat_id,
                        user_id=user_id
                    )

                    await message.answer(
                        "❌ Превышено количество попыток. Вы были забанены в чате."
                    )

                    # Уведомляем в чат
                    try:
                        user_link = await user_link_global(user_id)
                        await bot.send_message(
                            chat_id=session.chat_id,
                            text=f"❌ {user_link} превысил лимит попыток прохождения капчи и был забанен.",
                            parse_mode="HTML",
                            disable_web_page_preview=True
                        )
                    except:
                        pass

                    # Добавляем в историю
                    await add_captcha_history(session.chat_id, user_id, session.captcha_type, session.difficulty, False,
                                              time_taken)

                except Exception as e:
                    logger.error(e, exc_info=True)
                    await message.answer("❌ Ошибка при бане. Обратитесь к администратору.")

                # Удаляем сессию
                del active_captchas[(session.chat_id, user_id)]


async def perform_captcha_unmute(chat_id: int, user_id: int, bot: Bot) -> bool:
    """Размут пользователя после прохождения капчи"""
    try:
        # Получаем текущие права чата по умолчанию
        chat_permissions = await get_chat_permissions(chat_id)

        # Восстановление прав согласно настройкам чата
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=chat_permissions
        )
        return True
    except Exception as e:
        logger.error(e, exc_info=True)
        return False


@captcha_router.message(F.text.regexp(re.compile(r'^[!./]?капча период\s+', re.IGNORECASE)))
async def set_captcha_period(message: Message):
    """Установка периода времени для капчи - команда 'капча период'"""
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 44):
        return

    # Извлекаем текст после "капча период "
    time_input = message.text[14:].strip()  # "капча период " = 14 символов

    if not time_input:
        await message.answer(
            "❌ Укажите время для капчи.\n"
            "Пример: <code>капча период 5 минут</code>\n"
            "Или: <code>капча период 1 час 30 минут</code>",
            parse_mode="HTML"
        )
        return

    parsed_duration = parse_time_string(time_input)

    if parsed_duration is None:
        await message.answer(
            "❌ Не удалось распознать время. Используйте формат: <code>5 минут</code> или <code>1 час 30 минут</code>",
            parse_mode="HTML"
        )
        return

    await update_captcha_settings(message.chat.id, time_limit=time_input)
    formatted = format_duration(parsed_duration)
    await message.answer(f"✅ Время для капчи установлено: <b>{formatted}</b>", parse_mode="HTML")


@captcha_router.message(F.text.regexp(re.compile(r'^[!./]?капча сложность\s+', re.IGNORECASE)))
async def set_captcha_difficulty(message: Message):
    """Установка сложности капчи - команда 'капча сложность'"""
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 44):
        return

    # Извлекаем текст после "капча сложность "
    difficulty = message.text[17:].strip().lower()  # "капча сложность " = 17 символов

    if not difficulty:
        await message.answer(
            "❌ Укажите сложность капчи.\n"
            "Доступные уровни: <code>легкая</code>, <code>средняя</code>, <code>тяжелая</code>, <code>хардкорд</code>",
            parse_mode="HTML"
        )
        return

    if difficulty not in ['легкая', 'средняя', 'тяжелая', 'хардкорд']:
        await message.answer(
            "❌ Неверная сложность. Используйте: <code>легкая</code>, <code>средняя</code>, "
            "<code>тяжелая</code> или <code>хардкорд</code>",
            parse_mode="HTML"
        )
        return

    await update_captcha_settings(message.chat.id, difficulty=difficulty)
    await message.answer(f"✅ Сложность капчи установлена: <b>{difficulty}</b>", parse_mode="HTML")


@captcha_router.message(F.text.regexp(re.compile(r'^[!./]капча лимит\s+', re.IGNORECASE)))
async def set_captcha_attempts(message: Message):
    """Установка лимита попыток для капчи - команда 'капча лимит'"""
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 44):
        return

    # Извлекаем текст после "капча лимит "
    attempts_text = message.text[13:].strip().lower()  # "капча лимит " = 13 символов

    if not attempts_text:
        await message.answer(
            "❌ Укажите количество попыток.\n"
            "Пример: <code>капча лимит 5</code>\n"
            "Минимум: 1, Максимум: 10",
            parse_mode="HTML"
        )
        return

    try:
        attempts = int(attempts_text)
        if attempts < 1 or attempts > 10:
            await message.answer(
                "❌ Количество попыток должно быть от 1 до 10",
                parse_mode="HTML"
            )
            return
    except ValueError:
        await message.answer(
            "❌ Укажите число от 1 до 10",
            parse_mode="HTML"
        )
        return

    await update_captcha_settings(message.chat.id, attempts_limit=attempts)
    await message.answer(f"✅ Лимит попыток для капчи установлен: <b>{attempts}</b>", parse_mode="HTML")


@captcha_router.message(F.text.regexp(re.compile(r'^[!./]?капча история', re.IGNORECASE)))
async def check_captcha_history(message: Message):
    """Проверка истории капчи пользователя - команда 'чек капча'"""

    if not await check_user_access(message.from_user.id, 1):
        return

    text = message.text.lower()

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        # Извлекаем аргумент после "чек капча "
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer(
                "❌ <b>Неверный формат команды!</b>\nИспользуйте: чек капча {@username} или ответьте на сообщение",
                parse_mode='HTML'
            )
            return

        mention = parts[2]
        user_id = await resolve_id(message, mention)

    if not user_id:
        await message.answer('❌ Укажите пользователя.')
        return

    await show_user_captcha_history(message, user_id, page=0)


async def show_user_captcha_history(message: Message, user_id: int, page: int = 0):
    """Показать историю капчи пользователя"""
    chat_id = message.chat.id

    # Получаем историю с пагинацией
    gender = await get_user_gender(user_id)
    offset = page * HISTORY_PER_PAGE
    history = await get_user_captcha_history(chat_id, user_id, HISTORY_PER_PAGE, offset)
    total, success_count, success_rate = await get_user_captcha_stats(chat_id, user_id)

    user_link = await user_link_global(user_id)

    response = f"📊 <b>История прохождения капчей {user_link}:</b>\n\n"

    # Проверяем на юзербота
    diagnostic = await analyze_captcha_behavior(chat_id, user_id, total, success_count, success_rate)
    response += f"<b>{diagnostic}</b>\n\n"

    if not history:
        response += "📝 История капчи пуста."
    else:
        for i, (captcha_type, difficulty, success, time_taken, timestamp) in enumerate(history, start=offset + 1):
            status = f"✅ прош{g('ел', gender)}" if success else f"❌ не прош{g('ел', gender)}"
            time_str = format_duration(timedelta(seconds=time_taken))
            response += f"{i}. {status} {difficulty} за {time_str}\n"

    # Добавляем статистику
    response += f"\n📈 Статистика: {success_count}/{total} ({success_rate:.1f}%)"

    # Создаем клавиатуру пагинации
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


@captcha_router.message(F.text.regexp(re.compile(r'^[!./]?капча инфо', re.IGNORECASE)))
async def show_captcha_info(message: Message):
    """Показать информацию о капчах в чате - команда 'капча инфо'"""
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 45):
        return

    text = message.text.lower()

    # Если указан пользователь
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        user_specified = True
    else:
        # Убираем команду из текста
        if text.startswith('.капча инфо'):
            command_len = len('.капча инфо')
        elif text.startswith('/капча инфо'):
            command_len = len('/капча инфо')
        elif text.startswith('!капча инфо'):
            command_len = len('!капча инфо')
        else:
            command_len = len('капча инфо')

        # Получаем аргумент после команды
        arg_text = message.text[command_len:].strip()

        if arg_text:
            user_id = await resolve_id(message, arg_text)
            user_specified = True
        else:
            user_id = None
            user_specified = False

    chat_id = message.chat.id

    if user_id and user_specified:
        # Показываем информацию о конкретном пользователе
        recent_captcha = await get_user_recent_captcha(chat_id, user_id)
        user_link = await user_link_global(user_id)
        gender = await get_user_gender(user_id)

        if not recent_captcha:
            await message.answer(f"ℹ️ {user_link} еще не проход{g('ел', gender)} капчу в этом чате.",
                                 parse_mode="HTML")
            return

        difficulty, time_taken, timestamp, success = recent_captcha
        status = f"прош{g('ел', gender)}" if success else f"не прош{g('ел', gender)}"
        time_str = format_duration(timedelta(seconds=time_taken))

        # Форматируем дату
        date_str = timestamp.strftime("%d.%m.%Y %H:%M")

        # Добавляем эмодзи сложности
        difficulty_emoji = {
            "легкая": "🟢",
            "средняя": "🟡",
            "тяжелая": "🔴",
            "хардкорд": "⚫"
        }.get(difficulty, "⚪")

        response = (f"ℹ️ <b>Информация о капче</b>\n\n"
                    f"👤 Пользователь: {user_link}\n"
                    f"📊 Статус: {status}\n"
                    f"⚡ Сложность: {difficulty_emoji} {difficulty}\n"
                    f"⏱️ Время: {time_str}\n"
                    f"📅 Дата: {date_str}")

        await message.reply(response, parse_mode="HTML", disable_web_page_preview=True)
    else:
        # Показываем всех пользователей
        await show_all_captcha_users(message, page=0)


async def show_all_captcha_users(message: Message, page: int = 0):
    """Показать всех пользователей, проходивших капчу"""
    chat_id = message.chat.id

    offset = page * USERS_PER_PAGE
    users = await get_all_captcha_users(chat_id, USERS_PER_PAGE, offset)
    total_users = await get_total_captcha_users_count(chat_id)

    if not users:
        await message.reply("📝 В этом чате еще никто не проходил капчу.",
                            parse_mode="HTML")
        return

    # Собираем данные для всех пользователей на странице
    response = "📋 <b>Пользователи, проходившие капчу:</b>\n\n"

    for i, (user_id,) in enumerate(users, start=offset + 1):
        # Параллельно получаем данные
        recent_captcha = await get_user_recent_captcha(chat_id, user_id)
        user_link = await user_link_global(user_id)
        gender = await get_user_gender(user_id)

        if recent_captcha:
            difficulty, time_taken, timestamp, success = recent_captcha
            status = f"✅ прош{g('ел', gender)}" if success else f"❌ не прош{g('ел', gender)}"
            time_str = format_duration(timedelta(seconds=time_taken))

            # Добавляем эмодзи сложности
            difficulty_emoji = {
                "легкая": "🟢",
                "средняя": "🟡",
                "тяжелая": "🔴",
                "хардкорд": "⚫"
            }.get(difficulty, "⚪")

            # Форматируем дату
            date_str = timestamp.strftime("%d.%m.%Y %H:%M")

            response += f"{i}. {user_link} - {status} {difficulty_emoji} {difficulty} за {time_str}\n"
        else:
            response += f"{i}. {user_link} - нет данных\n"

    # Добавляем информацию о пагинации
    total_pages = max(1, math.ceil(total_users / USERS_PER_PAGE))

    if total_pages > 1:
        response += f"\n📄 Страница {page + 1} из {total_pages}"

    response += f"\n👥 Всего пользователей: {total_users}"

    # Создаем клавиатуру пагинации
    keyboard = []

    if total_pages > 1:
        row = []
        if page > 0:
            row.append(InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"captcha_users_{page - 1}"
            ))

        # Добавляем кнопки для навигации по страницам
        start_page = max(0, page - 2)
        end_page = min(total_pages, page + 3)

        for p in range(start_page, end_page):
            if p == page:
                row.append(InlineKeyboardButton(
                    text=f"•{p + 1}•",
                    callback_data=f"captcha_users_{p}"
                ))
            else:
                row.append(InlineKeyboardButton(
                    text=str(p + 1),
                    callback_data=f"captcha_users_{p}"
                ))

        if page < total_pages - 1:
            row.append(InlineKeyboardButton(
                text="Вперед ➡️",
                callback_data=f"captcha_users_{page + 1}"
            ))

        if row:
            keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None

    await message.reply(response, parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=reply_markup)


@captcha_router.callback_query(F.data.startswith('captcha_history_'))
@rate_limit_with_cleanup(limit=1)
async def handle_captcha_history_pagination(c: CallbackQuery):
    """Обработка пагинации истории капчи"""
    if (not c.message.reply_to_message or
            c.from_user.id != c.message.reply_to_message.from_user.id):
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
    """Обработка пагинации списка пользователей"""
    if (not c.message.reply_to_message or
            c.from_user.id != c.message.reply_to_message.from_user.id):
        random_text = get_random_text()
        await c.answer(f"{random_text}", show_alert=True)
        return

    page = int(c.data.split('_')[2])

    await show_all_captcha_users(c.message, page)
    await c.answer()