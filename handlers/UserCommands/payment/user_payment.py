import logging
import uuid
from aiogram import Router, F, Bot
from aiogram.types import Message, PreCheckoutQuery, LabeledPrice, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from BotAutomaticWork.users.checks.check_UserId.check_users_id import resolve_id
from UserCommands.payment.paymentDB import (
    add_to_bag,
    get_current_datetime,
    save_star_transaction,
    get_balance,
    get_bag_info,
    set_bag_visibility,
    get_bag_history
)
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_global

logger = logging.getLogger(__name__)
user_sapphires_router = Router()


def generate_receipt_code() -> str:
    return f"TX-{uuid.uuid4().hex[:8].upper()}"


async def parse_target_and_amount(msg: Message) -> tuple[int | None, int | None]:
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
# ⭐️ ПОКУПКА САПФИРОК
# ==========================================

@user_sapphires_router.message(F.text.lower().regexp(r'^купить\s+\d+'))
async def buy_sapphires_cmd(msg: Message, bot: Bot):
    try:
        if msg.chat.type != 'private':
            if not await auto_check_AccessLevel_for_rang(msg.from_user.id, msg.chat.id, 84):
                return

        parts = msg.text.split(maxsplit=1)
        sapphires_amount = int(parts[1])

        if sapphires_amount < 20:
            await msg.reply('🛒 Эй, по мелочи не работаем! Минимальная сумма покупки — 20 сапфирок.')
            return

        stars_price = int(sapphires_amount * 1.2)
        prices = [LabeledPrice(label=f"{sapphires_amount} Сапфирок", amount=stars_price)]
        payload = f"buy_sapphires_{sapphires_amount}"

        if msg.chat.type in ("group", "supergroup"):
            try:
                await bot.send_invoice(
                    chat_id=msg.from_user.id,
                    title="Пополнение мешка 💎",
                    description=f"Отсыпаем {sapphires_amount} сапфирок в твой мешок.",
                    payload=payload,
                    provider_token="",
                    currency="XTR",
                    prices=prices,
                    start_parameter="buy_sapphires"
                )

                bot_me = await bot.get_me()
                await msg.reply(
                    f"🛒 <b>Запрос на покупку принят!</b>\n"
                    f"Отправил счёт на покупку <code>{sapphires_amount}</code> сапфирок Вам в личные сообщения.\n"
                    f"🔗 Перейти к оплате: @{bot_me.username}",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except Exception as pm_err:
                logger.warning(f"Не удалось отправить инвойс в ЛС для {msg.from_user.id}: {pm_err}")
                await msg.reply(
                    "❌ <b>Я не могу написать Вам в ЛС!</b>\n"
                    "Пожалуйста, сначала перейди в диалог со мной, нажмите кнопку <b>Старт</b> и повтори команду там.",
                    parse_mode="HTML"
                )
        else:
            await msg.answer_invoice(
                title="Пополнение мешка 💎",
                description=f"Отсыпаем {sapphires_amount} сапфирок в твой мешок.",
                payload=payload,
                provider_token="",
                currency="XTR",
                prices=prices,
                start_parameter="buy_sapphires"
            )

    except (ValueError, IndexError):
        await msg.reply('❌ Что-то не так с цифрами. Напиши, например: <code>Купить 20</code>', parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error creating invoice: {e}", exc_info=True)
        await msg.reply('🛠 В кассе что-то сломалось. Попробуй чуть позже.')


@user_sapphires_router.pre_checkout_query(F.invoice_payload.startswith('buy_sapphires_'))
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@user_sapphires_router.message(F.successful_payment)
async def successful_payment_handler(msg: Message, bot: Bot):
    payment_info = msg.successful_payment
    payload = payment_info.invoice_payload

    if payload.startswith('buy_sapphires_'):
        try:
            sapphires_amount = int(payload.split('_')[2])
            user_id = msg.from_user.id
            charge_id = payment_info.telegram_payment_charge_id
            bot_me = await bot.get_me()
            receipt_code = generate_receipt_code()

            await save_star_transaction(receipt_code, user_id, charge_id, sapphires_amount)

            success, new_balance, db_msg = await add_to_bag(
                user_id=user_id,
                amount=sapphires_amount,
                agent_id=bot_me.id,
                date=get_current_datetime(),
                comment=f"Покупка сафирок [{receipt_code}]"
            )

            if success:
                await msg.answer(
                    f"🎉 <b>Ого, звон монет!</b>\n\n"
                    f"Твой мешок потяжелел на <code>+{sapphires_amount:,}</code> сапфов 💎\n"
                    f"🧾 Чек на всякий случай: <code>{receipt_code}</code>\n"
                    f"<i>(Сохрани его, если вдруг что-то пойдет не так)</i>",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            else:
                await msg.answer(
                    f"❌ Звезды ушли, но в базу не записалось: {db_msg}. Покажи этот код агентам: <code>{receipt_code}</code>. Их можно найти прописав: помощь",
                    parse_mode="HTML",
                disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Critical error in payment delivery: {e}", exc_info=True)
            await msg.answer("❌ Произошла ошибка при выдаче сапфиров. Зови агентов!")


# ==========================================
# ПРОСМОТР И УПРАВЛЕНИЕ МЕШКОМ
# ==========================================

@user_sapphires_router.message(F.text.lower().regexp(r'^(мой\s+)?мешок(\s|$)'))
async def smart_bag_handler(msg: Message):

    if msg.chat.type != 'private':
        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, msg.chat.id, 85):
            return

    parts = msg.text.split()
    target_id = None

    if msg.reply_to_message:
        target_id = msg.reply_to_message.from_user.id
    elif len(parts) > 1:
        args = [p for p in parts if p.lower() not in ["мой", "мешок"]]
        if args:
            target_raw = args[0]
            try:
                # ВПИХНУТО:
                target_id = await resolve_id(msg=msg, mention=target_raw)
            except Exception:
                target_id = None

            if not target_id:
                await msg.reply("🕵️‍♂️ Не могу найти такого пользователя. Вы точно правильно указали пользователя?")
                return

    if not target_id or target_id == msg.from_user.id:
        bag_info = await get_bag_info(msg.from_user.id)

        await msg.answer(
            f"💎 <b>Твой личный мешок</b>\n\n"
            f"<code>{bag_info['balance']:,}</code> сапфирок\n\n"
            f"<i>Команды: <code>-мешок</code> (спрятать), <code>+мешок</code> (показать), <code>история мешка</code> (только в лс)</i>",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    else:
        bag_info = await get_bag_info(target_id)
        user_link = await user_link_global(target_id)

        if bag_info['is_hidden']:
            await msg.reply("🤫 Владелец крепко завязал свой мешок. Заглянуть внутрь не получится!")
            return

        await msg.answer(
            f"💎 Мешок {user_link}\n\n"
            f"<code>{bag_info['balance']:,}</code> сапфирок",
            parse_mode="HTML",
            disable_web_page_preview=True
        )


@user_sapphires_router.message(F.text.lower() == "-мешок")
async def hide_bag_cmd(msg: Message):

    if msg.chat.type != 'private':
        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, msg.chat.id, 86):
            return

    await set_bag_visibility(msg.from_user.id, hide=True)
    await msg.reply("🥷 <b>Твой мешок теперь в тени.</b>\nНикто из игроков не узнает, сколько там сапфирок.")


@user_sapphires_router.message(F.text.lower() == "+мешок")
async def show_bag_cmd(msg: Message):

    if msg.chat.type != 'private':
        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, msg.chat.id, 86):
            return

    await set_bag_visibility(msg.from_user.id, hide=False)
    await msg.reply("🌍 <b>Мешок снова на виду!</b>\nТеперь другие игроки могут посмотреть твои запасы.")


# ==========================================
# ИСТОРИЯ НА КНОПКАХ
# ==========================================

def get_history_keyboard(user_id: int, page: int, has_next: bool):
    builder = InlineKeyboardBuilder()
    if page > 1:
        builder.button(text="⬅️ Назад", callback_data=f"hist:{user_id}:{page - 1}")
    if has_next:
        builder.button(text="Вперед ➡️", callback_data=f"hist:{user_id}:{page + 1}")
    return builder.as_markup()


@user_sapphires_router.message(F.text.lower().startswith("история мешка"))
async def text_history_cmd(msg: Message):
    if msg.chat.type != "private":
        return

    parts = msg.text.split()
    page = 1
    if len(parts) >= 3 and parts[-1].isdigit():
        page = int(parts[-1])

    user_id = msg.from_user.id
    history = await get_bag_history(user_id, page=page)

    if not history:
        await msg.reply(f"📜 Тут пусто! Либо ты еще ничего не тратил, либо страницы {page} не существует.")
        return

    text = f"📜 <b>Твои бухгалтерские записи</b>\n\n" + "\n".join(history)
    has_next = len(history) == 5
    kb = get_history_keyboard(user_id, page, has_next)

    await msg.answer(text,
                     parse_mode="HTML",
                     reply_markup=kb,
                     disable_web_page_preview=True)


@user_sapphires_router.callback_query(F.data.startswith("hist:"))
async def history_page_callback(call: CallbackQuery):
    parts = call.data.split(":")
    owner_id = int(parts[1])
    page = int(parts[2])

    if call.from_user.id != owner_id:
        await call.answer("❌ Это не твой мешок, ты не можешь листать чужую историю!", show_alert=True)
        return

    history = await get_bag_history(owner_id, page=page)
    if not history:
        await call.answer("📜 Больше записей нет!", show_alert=True)
        return

    text = f"📜 <b>Твои бухгалтерские записи (Стр. {page})</b>\n\n" + "\n".join(history)
    has_next = len(history) == 5
    kb = get_history_keyboard(owner_id, page, has_next)

    try:
        await call.message.edit_text(text,
                                     parse_mode="HTML",
                                     reply_markup=kb,
                                     disable_web_page_preview=True)
    except Exception:
        pass
    await call.answer()


# ==========================================
# ПЕРЕВОДЫ
# ==========================================

@user_sapphires_router.message(F.text.lower().startswith("передать "))
async def transfer_sapphires_simple_handler(msg: Message, bot: Bot):

    if msg.chat.type != 'private':
        if not await auto_check_AccessLevel_for_rang(msg.from_user.id, msg.chat.id, 87):
            return

    target_id, amount = await parse_target_and_amount(msg)

    if not target_id or not amount or amount <= 0:
        await msg.reply("🤔 Как-то непонятно... Напиши: `передать {юзер} {кол-во}`", parse_mode="Markdown")
        return

    if target_id == msg.from_user.id:
        await msg.reply("🌀 Перекладывать сапфирки из правого кармана в левый? Так баланс не вырастет!")
        return

    sender_balance = await get_balance(msg.from_user.id)
    if sender_balance < amount:
        await msg.reply("💸 В мешке пустовато... Не хватает сапфирок для такого щедрого перевода.")
        return

    await add_to_bag(msg.from_user.id, -amount, msg.from_user.id, get_current_datetime(), f"Перевод игроку {target_id}")
    await add_to_bag(target_id, amount, msg.from_user.id, get_current_datetime(), f"Подарок от {msg.from_user.id}")

    sender_link = await user_link_global(msg.from_user.id)
    target_link = await user_link_global(target_id)

    await msg.answer(
        f"🤝 <b>Перевод {target_link} прошёл успешно!</b>\n\n"
        f"От кого: {sender_link}\n"
        f"Передано {amount:,} сапфирок 💎",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

    try:
        await bot.send_message(
            target_id,
            f"🎁 <b>Тебе посылка!</b>\n{sender_link} только что перевел тебе <code>{amount:,}</code> сапфирок.",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception:
        pass