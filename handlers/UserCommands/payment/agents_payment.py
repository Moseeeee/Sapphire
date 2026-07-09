import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from BotAutomaticWork.users.checks.acces_commands.check_access_rang import check_user_access
from UserCommands.payment.paymentDB import (
    add_to_bag,
    get_current_datetime,
    get_star_transaction,
    mark_transaction_refunded,
    get_top_bags,
    get_agent_audit_info,
    get_bag_history
)
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global
from BotAutomaticWork.users.checks.check_UserId.check_users_id import resolve_id

logger = logging.getLogger(__name__)
agent_sapphires_router = Router()

async def parse_admin_args(msg: Message) -> tuple[int | None, int | None]:
    parts = msg.text.split()
    if msg.reply_to_message:
        try:
            amount = int(parts[1])
            return msg.reply_to_message.from_user.id, amount
        except (ValueError, IndexError):
            return None, None
    else:
        if len(parts) < 3:
            return None, None
        try:
            target_raw = parts[1]
            amount = int(parts[2])
            # ВПИХНУТО:
            target_id = await resolve_id(msg=msg, mention=target_raw)
            return target_id, amount
        except Exception:
            return None, None

# ==========================================
# 🛑 СИСТЕМА СТРОГОГО РЕФАУНДА STARS
# ==========================================

@agent_sapphires_router.message(F.text.lower().startswith('рефаунд '))
async def refund_stars_cmd(msg: Message, bot: Bot):
    try:
        if not await check_user_access(msg.from_user.id, 4):
            return

        parts = msg.text.split(maxsplit=1)
        if len(parts) < 2:
            await msg.reply("❌ Укажите код чека. Пример: `рефаунд TX-ABC12345`", parse_mode="Markdown")
            return

        receipt_code = parts[1].strip().upper()
        transaction = await get_star_transaction(receipt_code)

        if not transaction:
            await msg.reply(f"❌ Чек <code>{receipt_code}</code> не бьется по базе.", parse_mode="HTML")
            return

        if transaction.get('status') == 'refunded':
            await msg.reply("⚠️ Деньги по этому чеку уже возвращались ранее.")
            return

        user_id = transaction['user_id']
        charge_id = transaction['charge_id']
        sapphires_to_remove = transaction['sapphires']

        try:
            await bot.refund_star_payment(user_id=user_id, telegram_payment_charge_id=charge_id)
        except Exception as api_err:
            logger.error(f"Telegram API Refund Failure: {api_err}")
            await msg.reply(f"❌ Ошибка Telegram API. Либо прошло 21 день, либо возврат уже был.\nТекст: {api_err}")
            return

        success, new_balance, db_msg = await add_to_bag(
            user_id=user_id,
            amount=-sapphires_to_remove,
            agent_id=msg.from_user.id,
            date=get_current_datetime(),
            comment=f"Рефаунд транзакции {receipt_code}"
        )

        await mark_transaction_refunded(receipt_code)
        user_link = await user_link_global(user_id)

        await msg.reply(
            f"✅ <b>Возврат оформлен!</b>\n\n"
            f"🧾 Код: <code>{receipt_code}</code>\n"
            f"👤 Кому: {user_link}\n"
            f"📉 Изъято из мешка: <code>-{sapphires_to_remove}</code> (<code>{new_balance}</code>)\n",
            #f"🏦 Остаток: <code>{new_balance}</code>",
            parse_mode="HTML",
            disable_web_page_preview=True
        )

        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"⚠️ <b>Оформлен возврат средств!</b>\n\n"
                     f"Покупка по чеку <code>{receipt_code}</code> аннулирована.\n"
                     f"⭐️ Telegram звезды возвращены.\n"
                     f"💎 Из мешка списано: <code>{sapphires_to_remove}</code> сапфов.\n",
                     #f"🏦 Текущий баланс: <code>{new_balance}</code>",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Critical error in refund_stars_cmd: {e}", exc_info=True)
        await msg.reply("❌ Системный сбой при рефаунде.")

# ==========================================
# УПРАВЛЕНИЕ ЭКОНОМИКОЙ И АУДИТ
# ==========================================

@agent_sapphires_router.message(F.text.lower().startswith('!пополнить'))
async def add_sapphires_handler(msg: Message):

    if not await check_user_access(msg.from_user.id, 4):
        return

    target_id, amount = await parse_admin_args(msg)
    if not target_id or not amount or amount <= 0:
        await msg.reply("❌ Формат: `!пополнить {юзер} {кол-во}`")
        return

    _, new_balance, _ = await add_to_bag(target_id, amount, msg.from_user.id, get_current_datetime(), "Выдача агентом")
    user_link = await user_link_global(target_id)
    await msg.reply(f"🪄 <b>Наколдавано</b> <code>+{amount:,}</code> сапфирок для {user_link}.\nБаланс: <code>{new_balance:,}</code>",
                    parse_mode="HTML",
                    disable_web_page_preview=True)

@agent_sapphires_router.message(F.text.lower().startswith('!отнять'))
async def remove_sapphires_handler(msg: Message):

    if not await check_user_access(msg.from_user.id, 4):
        return

    target_id, amount = await parse_admin_args(msg)
    if not target_id or not amount or amount <= 0:
        await msg.reply("❌ Формат: `!отнять {юзер} {кол-во}`")
        return

    _, new_balance, _ = await add_to_bag(target_id, -amount, msg.from_user.id, get_current_datetime(), "Админ изъятие")
    user_link = await user_link_global(target_id)
    await msg.reply(f"🗑 <b>Изъято</b> <code>-{amount:,}</code> сапфирок у {user_link}.\nОстаток: <code>{new_balance:,}</code>",
                    parse_mode="HTML",
                    disable_web_page_preview=True)

@agent_sapphires_router.message(F.text.lower().startswith('!наказать'))
async def punish_sapphires_simple_handler(msg: Message):

    if not await check_user_access(msg.from_user.id, 3):
        return

    target_id, amount = await parse_admin_args(msg)
    if not target_id or not amount or amount <= 0:
        await msg.reply("❌ Формат: `!наказать {юзер} {кол-во}`")
        return

    _, new_balance, _ = await add_to_bag(target_id, -amount, msg.from_user.id, get_current_datetime(), "Штрафные санкции")
    user_link = await user_link_global(target_id)
    await msg.reply(f"🚨 <b>Штраф выписан!</b> {user_link} лишился <code>{amount:,}</code> сапфирок.\nОстаток: <code>{new_balance:,}</code>",
                    parse_mode="HTML",
                    disable_web_page_preview=True)

@agent_sapphires_router.message(F.text.lower().startswith('чек мешок'))
async def agent_check_bag_handler(msg: Message):

    if not await check_user_access(msg.from_user.id, 1):
        return

    parts = msg.text.split()
    target_id = None

    if msg.reply_to_message:
        target_id = msg.reply_to_message.from_user.id
    elif len(parts) >= 3:
        target_raw = parts[2]
        try:
            # ВПИХНУТО:
            target_id = await resolve_id(msg=msg, mention=target_raw)
        except Exception:
            target_id = None

    if not target_id:
        await msg.reply("❌ Укажите цель. Формат: `чек мешок {юзер}`", parse_mode="Markdown")
        return

    audit = await get_agent_audit_info(target_id)
    user_link = await user_link_global(target_id)
    status = "🔴 Скрыт" if audit['is_hidden'] else "🟢 Публичен"
    last_upd = audit['last_update'].strftime('%d.%m.%Y %H:%M') if audit['last_update'] else "Никогда"

    await msg.reply(
        f"🕵️‍♂️ <b>Секретное досье на мешок {user_link}</b>\n\n"
        f"💎 <code>{audit['balance']:,}</code> сапф.\n\n"
        #f"👁 Статус: {status}\n\n"
        f"📈 <b>Аудит активности:</b>\n"
        f"⭐️ Всего задоначено: <code>{audit['total_donated']:,}</code> сапф.\n"
        f"🚨 Получено штрафов: <code>{audit['punishments_count']}</code>\n"
        f"⏱ Последнее движение: <code>{last_upd}</code>",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

# ==========================================
# ГЛОБАЛЬНЫЙ ТОП НА КНОПКАХ
# ==========================================

def get_top_keyboard(page: int, has_next: bool):
    builder = InlineKeyboardBuilder()
    if page > 1:
        builder.button(text="⬅️ Назад", callback_data=f"top_page:{page-1}")
    if has_next:
        builder.button(text="Вперед ➡️", callback_data=f"top_page:{page+1}")
    return builder.as_markup()

#@agent_sapphires_router.message(F.text.lower().startswith('!топ всех мешков'))
async def top_all_bags_handler(msg: Message):
    parts = msg.text.split()
    page = 1
    if len(parts) >= 4 and parts[-1].isdigit():
        page = int(parts[-1])

    top_users = await get_top_bags(include_hidden=True, page=page)
    if not top_users:
        await msg.reply(f"Страница {page} пуста.")
        return

    text = f"👑 <b>Глобальный админ-топ (Стр. {page})</b>\n\n"
    for i, user in enumerate(top_users, 1 + (page - 1) * 10):
        user_link = await user_link_global(user['user_id'])
        hidden_tag = " 🥷 [СКРЫТ]" if user.get('is_hidden') else ""
        text += f"{i}. {user_link} — <code>{user['balance']:,}</code> сапф.{hidden_tag}\n"

    has_next = len(top_users) == 10
    kb = get_top_keyboard(page, has_next)

    await msg.answer(text, parse_mode="HTML", reply_markup=kb)

@agent_sapphires_router.callback_query(F.data.startswith("top_page:"))
async def top_page_callback(call: CallbackQuery):
    page = int(call.data.split(":")[1])

    top_users = await get_top_bags(include_hidden=True, page=page)
    if not top_users:
        await call.answer("👑 Это последняя страница топа!", show_alert=True)
        return

    text = f"👑 <b>Глобальный админ-топ (Стр. {page})</b>\n\n"
    for i, user in enumerate(top_users, 1 + (page - 1) * 10):
        user_link = await user_link_global(user['user_id'])
        hidden_tag = " 🥷 [СКРЫТ]" if user.get('is_hidden') else ""
        text += f"{i}. {user_link} — <code>{user['balance']:,}</code> сапф.{hidden_tag}\n"

    has_next = len(top_users) == 10
    kb = get_top_keyboard(page, has_next)

    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass
    await call.answer()


# ===================================================
# 🕵️‍♂️ АГЕНТСКИЙ ПРОСМОТР ИСТОРИИ (С ПАГИНАЦИЕЙ)
# ===================================================

def get_agent_history_keyboard(target_id: int, page: int, has_next: bool):
    builder = InlineKeyboardBuilder()
    if page > 1:
        builder.button(text="⬅️ Назад", callback_data=f"ag_hist:{target_id}:{page-1}")
    if has_next:
        builder.button(text="Вперед ➡️", callback_data=f"ag_hist:{target_id}:{page+1}")
    return builder.as_markup()


@agent_sapphires_router.message(F.text.lower().startswith('чек история'))
async def agent_check_history_handler(msg: Message):

    if not await check_user_access(msg.from_user.id, 2):
        return

    parts = msg.text.split()
    target_id = None
    page = 1

    # Вариант А: Сделан реплай на сообщение юзера ("чек история" или "чек история 2")
    if msg.reply_to_message:
        target_id = msg.reply_to_message.from_user.id
        if len(parts) >= 3 and parts[2].isdigit():
            page = int(parts[2])

    # Вариант Б: Передан ник/ID ("чек история @VIPERKV" или "чек история @VIPERKV 2")
    elif len(parts) >= 3:
        target_raw = parts[2]
        try:
            # Тот самый бронебойный вариант:
            target_id = await resolve_id(msg=msg, mention=target_raw)
        except Exception:
            target_id = None

        if len(parts) >= 4 and parts[3].isdigit():
            page = int(parts[3])

    if not target_id:
        await msg.reply(
            "❌ <b>Кого проверяем?</b>\n\n"
            "Формат: чек история {юзер}\n"
            "<i>(Либо просто отправь «чек история» в ответ на чужое сообщение)</i>",
            parse_mode="HTML"
        )
        return

    history = await get_bag_history(target_id, page=page)
    user_link = await user_link_global(target_id)

    if not history:
        await msg.reply(f"📜 Транзакций у {user_link} на странице {page} не найдено.",
                        parse_mode="HTML",
                        disable_web_page_preview=True)
        return

    text = f"🕵️‍♂️ <b>Финансовый след {user_link}</b>\n\n" + "\n".join(history)
    has_next = len(history) == 5  # Если вернулось 5 записей, значит возможно есть следующая страница
    kb = get_agent_history_keyboard(target_id, page, has_next)

    await msg.answer(text,
                     parse_mode="HTML",
                     reply_markup=kb,
                     disable_web_page_preview=True)


@agent_sapphires_router.callback_query(F.data.startswith("ag_hist:"))
async def agent_history_page_callback(call: CallbackQuery):
    parts = call.data.split(":")
    target_id = int(parts[1])
    page = int(parts[2])

    history = await get_bag_history(target_id, page=page)
    if not history:
        await call.answer("📜 Дальше бухгалтерских записей нет!", show_alert=True)
        return

    user_link = await user_link_global(target_id)
    text = f"🕵️‍♂️ <b>Финансовый след {user_link} (Стр. {page})</b>\n\n" + "\n".join(history)
    has_next = len(history) == 5
    kb = get_agent_history_keyboard(target_id, page, has_next)

    try:
        await call.message.edit_text(text,
                                     parse_mode="HTML",
                                     reply_markup=kb,
                                     disable_web_page_preview=True)
    except Exception:
        pass
    await call.answer()