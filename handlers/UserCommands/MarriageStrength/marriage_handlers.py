# marriage_handlers.py
import logging
import re
import asyncio
from datetime import timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from BotAutomaticWork.parse_time_auto import format_time_ago, format_duration
from BotAutomaticWork.users.GenderUtils import g
from BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender
from UserCommands.SettingsUsersProfile.PseudonymsUsers.PseudonymSettings import user_link_global, \
    user_link_with_pseudonym
from BotAutomaticWork.users.checks.check_UserId.check_users_id import resolve_id

# ИМПОРТЫ ЗАВИСЯТ ОТ ТВОЕЙ СТРУКТУРЫ:
from UserCommands.MarriageStrength.actions import ACTIONS
from UserCommands.MarriageStrength.db import (
    get_marriage_by_user, create_marriage, update_points, get_level_by_points,
    get_next_level_info,  is_action_on_cooldown, update_cascade_cooldowns,
    is_epic_action_used, mark_epic_action_used, add_gift, increment_action_counter,
    delete_marriage, get_all_marriages, now_utc
)
from UserCommands.MarriageStrength.keyboards import marriage_proposal_keyboard, buy_action_keyboard
from UserCommands.payment.paymentDB import process_sapphire_purchase
from handlers.BotAutomaticWork.Middleware.SmartIntRefreshed import SmartInt


logger = logging.getLogger(__name__)
marriage = Router()

# Константа для пагинации списка браков
MARRIAGES_PER_PAGE = 15


# ==================== ВСПОМОГАТЕЛЬНЫЕ ХЕЛПЕРЫ И ФИЛЬТРЫ ====================

def parse_gender_text(template: str, gender: str) -> str:
    """Преобразует строку вида 'обнял{ал}' в правильную форму из GenderUtils."""
    found = re.findall(r"\{(.*?)\}", template)
    result = template
    for key in found:
        gender_ending = g(key, gender)
        result = result.replace(f"{{{key}}}", gender_ending)
    return result


def match_dynamic_action_filter(message: Message) -> bool:
    if not message.text:
        return False
    text = message.text.lower().strip()

    action_text = ""
    for prefix in ("брак ", "!брак ", ".брак ", "/брак "):
        if text.startswith(prefix):
            action_text = text[len(prefix):].strip()
            break

    if not action_text:
        return False

    all_acts = list(ACTIONS.keys())
    return any(action_text.startswith(act) for act in all_acts)


def get_marriages_kb(total_items: int, page: int) -> InlineKeyboardMarkup | None:
    builder = InlineKeyboardBuilder()
    total_pages = (total_items + MARRIAGES_PER_PAGE - 1) // MARRIAGES_PER_PAGE

    if total_pages <= 1:
        return None

    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"mar_page:{page - 1}"))

    buttons.append(InlineKeyboardButton(text=f"• {page}/{total_pages} •", callback_data="noop"))

    if page < total_pages:
        buttons.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"mar_page:{page + 1}"))

    builder.row(*buttons)
    return builder.as_markup()


async def generate_marriages_text(marriages: list, page: int, chat_id: int) -> str:
    start = (page - 1) * MARRIAGES_PER_PAGE
    end = start + MARRIAGES_PER_PAGE
    page_items = marriages[start:end]

    text = f"<b>💖 Список браков данного чата (Страница {page}):</b>\n\n"

    for idx, m in enumerate(page_items, start=start + 1):
        # Получаем актуальные данные брака - ИСПРАВЛЕН ПОРЯДОК АРГУМЕНТОВ
        marriage_data = await get_marriage_by_user(chat_id, m["user1_id"])

        # Проверяем, существует ли брак
        if marriage_data is None:
            # Пропускаем несуществующий брак или выводим сообщение
            text += f"{idx}. ❌ Брак не найден (пользователь {m['user1_id']})\n"
            continue

        level, level_name = get_level_by_points(marriage_data["points"])
        current_fmt = SmartInt(marriage_data["points"])

        # Получаем красивые ссылки на обоих участников брака
        u1_link = await user_link_with_pseudonym(int(m["user1_id"]), int(chat_id))
        u2_link = await user_link_with_pseudonym(int(m["user2_id"]), int(chat_id))

        text += f"{idx}. {u1_link} ❤️ {u2_link} ({current_fmt} | {level_name})\n"

    return text

# ==================== ФОНОВАЯ ЗАДАЧА СНИЖЕНИЯ ОЧКОВ ====================

async def check_any_action_available(marriage_data: dict) -> bool:
    level, _ = get_level_by_points(marriage_data["points"])
    cooldowns = marriage_data.get("cooldowns", {})
    now_ts = now_utc().timestamp()

    for action, cfg in ACTIONS.items():
        if cfg["level"] <= level:
            if cfg["cooldown"] == -1:
                used = await is_epic_action_used(marriage_data["id"], action)
                if not used:
                    return True
            else:
                expiry = cooldowns.get(action, 0)
                if expiry <= now_ts:
                    return True
    return False


async def decay_marriage_points_task():
    check_interval = 3600
    while True:
        await asyncio.sleep(check_interval)
        try:
            marriages = await get_all_marriages()
            now = now_utc().replace(tzinfo=None)

            for m in marriages:
                if m["points"] <= 0: continue
                level, _ = get_level_by_points(m["points"])
                if level < 2: continue

                last_interaction = m.get("last_interaction") or m.get("married_at")
                if not last_interaction: continue

                last_interaction = last_interaction.replace(tzinfo=None)
                inactive_hours = (now - last_interaction).total_seconds() / 3600

                if inactive_hours < 24: continue

                if await check_any_action_available(m):
                    base_penalty = level
                    inactive_days = inactive_hours / 24

                    if inactive_days >= 7:
                        multiplier = 10.0
                    elif inactive_days >= 4:
                        multiplier = 5.0
                    elif inactive_days >= 2:
                        multiplier = 2.0
                    else:
                        multiplier = 1.0

                    decay_points = int(-(base_penalty * multiplier))
                    await update_points(m["id"], decay_points)
        except Exception as e:
            logger.error(f"Ошибка в фоновом цикле деградации браков: {e}")


@marriage.startup()
async def on_marriage_startup():
    logger.info("Запуск фоновой задачи контроля браков...")
    asyncio.create_task(decay_marriage_points_task())


# ==================== 1. ВЫСШИЙ ПРИОРИТЕТ: СТАТИЧЕСКИЕ И АДМИН-КОМАНДЫ ====================

@marriage.message(F.text.lower().startswith(("браки", "!браки", ".браки", "/браки")))
async def list_chat_marriages(message: Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 91):
        return

    all_marriages = await get_all_marriages()
    marriages = [m for m in all_marriages if m["chat_id"] == message.chat.id]

    if not marriages:
        await message.answer("😔 В этом чате пока никто не заключил брак.")
        return

    text = await generate_marriages_text(marriages, page=1, chat_id=message.chat.id)
    kb = get_marriages_kb(len(marriages), page=1)
    await message.answer(text,
                         reply_markup=kb,
                         parse_mode="HTML",
                         disable_web_page_preview=True)


@marriage.message(F.text.lower().startswith((
        "брак поженить", "!брак поженить", ".брак поженить", "/брак поженить"
)))
async def admin_force_marriage(message: Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 96):
        return

    args = message.text.split()

    if len(args) < 3:
        await message.answer("❌ Укажите двух пользователей.\nПример: <code>брак поженить @user1 @user2</code>")
        return

    u1_mention = args[2]
    u2_mention = args[3] if len(args) > 3 else None

    if not u2_mention:
        await message.answer("❌ Укажите второго пользователя для заключения брака.")
        return

    user1_id = await resolve_id(message, u1_mention)
    user2_id = await resolve_id(message, u2_mention)

    if not user1_id or not user2_id:
        await message.answer("❌ Не удалось найти одного или обоих указанных пользователей.")
        return

    if user1_id == user2_id:
        await message.answer("❌ Нельзя женить пользователя на самом себе!")
        return

    if await get_marriage_by_user(message.chat.id, user1_id) or await get_marriage_by_user(message.chat.id, user2_id):
        await message.answer("❌ Один из указанных пользователей уже состоит в браке!")
        return

    marriage_id = await create_marriage(message.chat.id, user1_id, user2_id)
    await update_points(marriage_id, 0)

    user1_link = await user_link_global(user1_id)
    user2_link = await user_link_global(user2_id)

    await message.answer(
        f"💍 <b>Административное решение!</b>\n"
        f"Брак между {user1_link} и {user2_link} был успешно заключен в принудительном порядке! ",
        parse_mode="HTML",
        disable_web_page_preview=True
    )


@marriage.message(F.text.lower().startswith((
        "брак развести", "!брак развести", ".брак развести", "/брак развести"
)))
async def admin_force_divorce(message: Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 96):
        return

    args = message.text.split()
    target_mention = args[2] if len(args) > 2 else None

    if not target_mention and not message.reply_to_message:
        await message.answer("❌ Укажите пользователя, чей брак нужно расторгнуть (ответом или через @username).")
        return

    target_user_id = await resolve_id(message, target_mention) if target_mention else message.reply_to_message.from_user.id

    if not target_user_id:
        await message.answer("❌ Не удалось распознать указанного пользователя.")
        return

    marriage_data = await get_marriage_by_user(message.chat.id, target_user_id)
    if not marriage_data:
        await message.answer("❌ Данный пользователь не состоит в семейных отношениях в этом чате.")
        return

    await delete_marriage(marriage_data["id"])

    u1_link = await user_link_global(marriage_data["user1_id"])
    u2_link = await user_link_global(marriage_data["user2_id"])

    await message.answer(
        f"💔 Брак между {u1_link} и {u2_link} принудительно аннулирован администрацией чата.",
        parse_mode="HTML",
        disable_web_page_preview=True
    )


@marriage.message(F.text.lower().startswith((
        "брак действия", "!брак действия", ".брак действия", "/брак действия",
        "брак действие", "!брак действия", ".брак действие", "/брак действие"
)))
async def list_available_actions(message: Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 93):
        return

    marriage_data = await get_marriage_by_user(message.chat.id, message.from_user.id)
    if not marriage_data:
        await message.answer("❌ Вы не в браке.")
        return

    level, _ = get_level_by_points(marriage_data["points"])
    text = "📋 <b>Интерактивное меню действий</b>\n"
    has_actions = False

    for action, cfg in sorted(ACTIONS.items(), key=lambda item: item[1]['points'], reverse=True):
        if cfg["level"] <= level:
            if cfg["cooldown"] == -1:
                used = await is_epic_action_used(marriage_data["id"], action)
                if used: continue
                status_emoji = "✨"
            else:
                on_cd, secs = await is_action_on_cooldown(marriage_data["id"], action)
                status_emoji = "💔" if on_cd else "💚"

            cost_text = f"- <code>{cfg['cost']} сапф.</code>" if cfg.get('cost') else ""
            text += f"{status_emoji} <code>брак {action}</code>, +{cfg['points']} очков {cost_text}\n"
            has_actions = True

    if not has_actions:
        text += "<i>Пока что вам недоступны новые действия. </i>"

    await message.answer(text,
                         parse_mode="HTML",
                         disable_web_page_preview=True)


@marriage.message(F.text.lower().startswith((
        "брак статус", "!брак статус", ".брак статус", "/брак статус",
        "мой брак", ".мой брак", "!мой брак", "/мой брак"
)))
async def show_user_marriage_status(message: Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 92):
        return

    args = message.text.split()
    target_mention = args[2] if len(args) > 2 else None

    if target_mention:
        target_user_id = await resolve_id(message, target_mention)
    elif message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
    else:
        target_user_id = message.from_user.id

    if not target_user_id:
        await message.answer("❌ Не удалось найти указанного пользователя.")
        return

    marriage_data = await get_marriage_by_user(message.chat.id, target_user_id)
    if not marriage_data:
        msg_owner = "Вы не состоите" if target_user_id == message.from_user.id else "Этот пользователь не состоит"
        await message.answer(f"❌ {msg_owner} в браке.")
        return

    points = marriage_data["points"]
    level, level_name = get_level_by_points(points)
    next_level, next_name, need = get_next_level_info(points)

    current_fmt = SmartInt(points)
    next_fmt = SmartInt(points + need) if need > 0 else current_fmt

    other_id = marriage_data["user1_id"] if marriage_data["user2_id"] == target_user_id else marriage_data["user2_id"]
    other_gender = await get_user_gender(other_id)
    other_emoji = g('пол_эмод', other_gender)
    partner_link = await user_link_global(other_id)

    target_link = await user_link_global(target_user_id)
    married_time_str = format_time_ago(marriage_data["married_at"])

    text = (
        f"📊 <b>Статус брака для {target_link}</b>\n\n"
        f"💍 <b>Вторая половинка:</b> {other_emoji} {partner_link}\n"
        f"⏳ <b>Поженились:</b> {married_time_str}\n"
        f"💌 <b>Уровень любви:</b> {level_name} [{level} ур.]\n"
        f"💖 <b>Прочность отношений:</b> {current_fmt} / {next_fmt}\n"
    )
    if need <= 0:
        text += f"👑 Достигнут максимальный предел чувств!\n"

    await message.answer(text,
                         parse_mode="HTML",
                         disable_web_page_preview=True)


@marriage.message(F.text.lower().in_({"брак история", "!брак история", "/брак история", ".брак история"}))
async def show_marriage_history(message: Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 94):
        return

    marriage_data = await get_marriage_by_user(message.chat.id, message.from_user.id)
    if not marriage_data:
        await message.answer("❌ Вы не в браке.")
        return

    counters = marriage_data.get("action_counters", {})
    if not counters:
        await message.answer("📜 <b>Статистика вашей любви</b>\n\n<i>История действий пуста.</i>", parse_mode="HTML")
        return

    all_actions = {**ACTIONS}
    stats_lines = []
    for act, count in counters.items():
        emoji = all_actions.get(act, {}).get("emoji", "❓")
        stats_lines.append(f"{emoji} <code>{act}</code> - {count}")

    stats = "\n".join(stats_lines)
    await message.answer(f"📜 <b>Статистика действий вашей пары</b>\n\n{stats}",
                         parse_mode="HTML",
                         disable_web_page_preview=True)


@marriage.message(F.text.lower().startswith((
        "брак подтвердить развод", "!брак подтвердить развод",
        ".брак подтвердить развод", "/брак подтвердить развод"
)))
async def divorce_confirm(message: Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 95):
        return

    marriage_data = await get_marriage_by_user(message.chat.id, message.from_user.id)
    if not marriage_data:
        await message.answer("❌ Ошибочка, вы уже свободны.")
        return

    await delete_marriage(marriage_data["id"])
    await message.answer("💥 <b>Эпоха подошла к концу.</b> Брак официально расторгнут. Вы оба теперь свободные люди...",
                         parse_mode="HTML",
                         disable_web_page_preview=True)


@marriage.message(F.text.lower().startswith(("брак развод", "!брак развод", "/брак развод", ".брак развод")))
async def divorce_command(message: Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 95):
        return

    marriage_data = await get_marriage_by_user(message.chat.id, message.from_user.id)
    if not marriage_data:
        await message.answer("❌ Вы не можете развестись, так как не состоите в семейных отношениях.")
        return

    await message.answer(
        "💔 <b>Вы уверены, что хотите разрушить семью?</b>\n"
        "Все набранные очки близости и эпические достижения будут стерты навсегда.\n\n"
        "Если решение взвешенное, введите команду: <code>брак подтвердить развод</code>",
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# ==================== 2. СРЕДНИЙ ПРИОРИТЕТ: ДИНАМИЧЕСКИЕ ДЕЙСТВИЯ БРАКА ====================

async def handle_marriage_action(message: Message, action_key: str, is_conflict: bool = False):
    marriage_data = await get_marriage_by_user(message.chat.id, message.from_user.id)
    if not marriage_data:
        await message.answer("❌ Вы еще даже не сыграли свадьбу! Введите <code>жениться @user</code>.")
        return

    level, _ = get_level_by_points(marriage_data["points"])
    cfg = ACTIONS.get(action_key)
    if not cfg: return

    if cfg["level"] > level:
        await message.answer(
            f"🔒 <b>Недостаточный уровень!</b> Это действие откроется только на <b>{cfg['level']} уровне</b> брака.",
        parse_mode="HTML")
        return

    cost = cfg.get("cost", 0)

    if cfg["cooldown"] == -1:
        if await is_epic_action_used(marriage_data["id"], action_key):
            await message.answer(
                f"❌ Легендарное событие «{cfg['emoji']} {action_key}» уже однажды произошло. Повторить невозможно!")
            return

    on_cd, remaining = await is_action_on_cooldown(marriage_data["id"], action_key)
    time_left_str = format_duration(timedelta(seconds=remaining))

    if on_cd:
        if cost > 0:
            kb = buy_action_keyboard(message.from_user.id, action_key, cost)
            await message.reply(
                f"⏳ <b>Не торопитесь!</b> Действие «{action_key}» пока недоступно.\n"
                f"Попробуйте снова через: <b>{time_left_str}</b> или купите это действие за <b>{cost} сапфирок</b>.",
                reply_markup=kb,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            return
        else:
            await message.answer(
                f"⏳ <b>Не торопитесь!</b> Действие «{action_key}» пока недоступно через <b>{time_left_str}</b>.",
            parse_mode="HTML",)
            return

    await execute_action_logic(message, action_key, is_conflict)


async def execute_action_logic(message: Message, action_key: str, is_conflict: bool):
    marriage_data = await get_marriage_by_user(message.chat.id, message.from_user.id)
    if not marriage_data: return

    level, _ = get_level_by_points(marriage_data["points"])
    cfg = ACTIONS.get(action_key)
    if not cfg: return

    user_gender = await get_user_gender(message.from_user.id)
    action_desc = parse_gender_text(cfg["desc_tpl"], user_gender)

    new_points, new_level = await update_points(marriage_data["id"], cfg["points"])

    if cfg["cooldown"] != -1:
        cooldowns_to_apply = {}
        target_weight = cfg["points"]
        for act_name, act_cfg in ACTIONS.items():
            if act_cfg["points"] <= target_weight and act_cfg["cooldown"] > 0:
                cooldowns_to_apply[act_name] = act_cfg["cooldown"]
        await update_cascade_cooldowns(marriage_data["id"], cooldowns_to_apply)
    else:
        await mark_epic_action_used(marriage_data["id"], action_key)

    if action_key == "подарок":
        await add_gift(marriage_data["id"], action_key, message.from_user.id, cfg["points"])

    await increment_action_counter(marriage_data["id"], action_key)

    other_id = marriage_data["user1_id"] if marriage_data["user2_id"] == message.from_user.id else marriage_data[
        "user2_id"]
    user1_link = await user_link_with_pseudonym(int(message.from_user.id), int(message.chat.id))
    user2_link = await user_link_with_pseudonym(int(other_id), int(message.chat.id))

    evalishion = ""

    if new_level > level:
        _, new_name = get_level_by_points(new_points)
        evalishion = f"🎉 <b>УРА-А-А! Эволюция любви!</b> 🎉\nВаше гнездышко переходит на новый этап!\n💖 Ваш брак достиг <b>{new_level}-го уровня «{new_name}»</b>!"

    await message.reply(
        f"{cfg['emoji']} {user1_link} {action_desc} {user2_link}!\n{cfg['points']} очков прочности отношений.\n\n{evalishion}",
        parse_mode="HTML",
        disable_web_page_preview=True)


@marriage.message(match_dynamic_action_filter)
async def universal_action_handler(message: Message):
    text = message.text.lower()
    action_text = ""
    for prefix in ("брак ", "!брак ", ".брак ", "/брак "):
        if text.startswith(prefix):
            action_text = text[len(prefix):].strip()
            break

    matched_action = None
    is_conflict = False

    all_acts = list(ACTIONS.keys())
    all_acts.sort(key=len, reverse=True)

    for act in all_acts:
        if action_text.startswith(act):
            matched_action = act
            break

    if matched_action:
        await handle_marriage_action(message, matched_action)


# ==================== 3. НИЗШИЙ ПРИОРИТЕТ: РЕГИСТРАЦИЯ БРАКА (FALLBACK) ====================

@marriage.message(F.text.lower().startswith((
        "жениться", "брак жениться", ".жениться", ".брак жениться",
        "!жениться", "!брак жениться", "/жениться", "/брак жениться",
        "брак", "предложить брак", ".брак", ".предложить брак",
        "!брак", "!предложить брак", "/брак", "/предложить брак"
)))
async def marry_command(message: Message):

    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 95):
        return

    if message.chat.type == "private": return

    user1 = message.from_user.id
    chat_id = message.chat.id

    user2 = None
    if message.reply_to_message:
        user2 = message.reply_to_message.from_user.id
    else:
        args = message.text.split(maxsplit=2)
        text_lower = message.text.lower()

        multi_word_prefixes = (
            "брак жениться", ".брак жениться", "!брак жениться", "/брак жениться",
            "предложить брак", ".предложить брак", "!предложить брак", "/предложить брак"
        )
        mention_idx = 2 if text_lower.startswith(multi_word_prefixes) else 1

        if len(args) > mention_idx:
            mention = args[mention_idx].strip()
            user2 = await resolve_id(message, mention)

    if not user2 or user1 == user2:
        await message.answer(
            "⚠️ <b>Ошибка:</b> Кого вы хотите взять в супруги? Укажите пользователя ответом на сообщение или через @username.",
        parse_mode="HTML")
        return

    if await get_marriage_by_user(chat_id, user1) or await get_marriage_by_user(chat_id, user2):
        await message.answer("❌ Свадьба невозможна! Один из участников уже состоит в официальном браке.")
        return

    user1_link = await user_link_global(user1)
    user2_link = await user_link_global(user2)
    await message.answer(
        f"👑 <b>Романтическое предложение!</b>\n\n{user1_link} делает предложение руки и сердца {user2_link}! ❤️\nВы готовы связать свои узы судьбы в крепкий союз?",
        reply_markup=marriage_proposal_keyboard(user2, user1),
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# ==================== 4. CALLBACK QUERY ОБРАБОТЧИКИ ====================

@marriage.callback_query(F.data.startswith("buy_act:"))
async def confirm_action_purchase(call: CallbackQuery):
    parts = call.data.split(":")
    user_id, action_key = int(parts[1]), parts[2]

    if call.from_user.id != user_id:
        await call.answer("Это не ваша кнопка!", show_alert=True)
        return

    cfg = ACTIONS.get(action_key)
    if not cfg: return

    cost = cfg.get("cost", 0)
    payment_result = await process_sapphire_purchase(user_id=user_id, amount=cost,
                                                     item_name=f"Семейное действие: {action_key}")

    if payment_result is not True:
        await call.answer(f"❌ Ошибка: {payment_result}", show_alert=True)
        await call.message.edit_text(f"❌ <b>Покупка отменена</b>\nПричина: <i>{payment_result}</i>", parse_mode="HTML")
        return

    await call.answer("Оплата прошла успешно!")
    await call.message.edit_text(f"✅ Оплата в размере <b>{cost} сапфирок</b> прошла успешно!", parse_mode="HTML")

    target_message = call.message.reply_to_message if call.message.reply_to_message else call.message
    await execute_action_logic(target_message, action_key, is_conflict=False)


@marriage.callback_query(F.data.startswith("marry_accept:"))
async def marry_accept(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3: return
    try:
        user2_id, user1_id = int(parts[1]), int(parts[2])
    except ValueError:
        return

    if callback.from_user.id != user2_id:
        await callback.answer("❌ Это предложение сделано не вам!", show_alert=True)
        return

    chat_id = callback.message.chat.id
    if await get_marriage_by_user(chat_id, user1_id) or await get_marriage_by_user(chat_id, user2_id):
        await callback.answer("❌ Увы, кто-то уже успел окольцеваться.", show_alert=True)
        return

    marriage_id = await create_marriage(chat_id, user1_id, user2_id)
    await update_points(marriage_id, 0)

    user1_link = await user_link_global(user1_id)
    user2_link = await user_link_global(user2_id)

    await callback.message.edit_text(
        f"🎉 <b>Горько! У нас новая семья!</b>\n\n💍 Брак между {user1_link} и {user2_link} официально зарегистрирован церковью Сапфира!\n\n📈 <b>Стартовый статус:</b> Уровень 1 — <i>Знакомство</i>.\n✨ Используйте <code>брак действия</code>, чтобы развивать ваши узы!",
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await callback.answer("✨ Поздравляем, вы в браке!")


@marriage.callback_query(F.data.startswith("marry_decline:"))
async def marry_decline(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3: return
    try:
        user2_id, user1_id = int(parts[1]), int(parts[2])
    except ValueError:
        return

    if callback.from_user.id != user2_id:
        await callback.answer("❌ Это предложение сделано не вам!", show_alert=True)
        return
    await callback.message.edit_text("💔 Увы! Предложение руки и сердца было холодно отвергнуто...")
    await callback.answer()


@marriage.callback_query(F.data.startswith("mar_page:"))
async def process_marriages_pagination(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    all_marriages = await get_all_marriages()
    marriages = [m for m in all_marriages if m["chat_id"] == callback.message.chat.id]

    if not marriages:
        await callback.message.edit_text("😔 Список браков пуст.")
        return

    text = await generate_marriages_text(marriages, page=page, chat_id=callback.message.chat.id)
    kb = get_marriages_kb(len(marriages), page=page)

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        pass
    await callback.answer()