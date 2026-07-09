from aiogram import Router, F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from handlers.AdminsTools.ChatSettings.catalog.catalog_db import (
    update_chat_catalog_draft,
    get_catalog_chat,
    set_catalog_param,
    CATALOG_CATEGORIES
)

catalog_settings = Router()


def get_settings_kb(chat_id: int, chat_data: dict):
    """Сборка главного меню настроек отображения чата на сайте."""
    kb = InlineKeyboardBuilder()

    selected_cats = chat_data.get("category_ids") or []
    cats_count = len(selected_cats)

    kb.row(
        types.InlineKeyboardButton(
            text=f"📂 Выбрать категории ({cats_count}/10)",
            callback_data=f"cat_list:{chat_id}"
        )
    )

    adm_label = "❌ Скрыты" if chat_data.get("hide_admins") else "👁 Видны"
    kb.row(
        types.InlineKeyboardButton(
            text=f"👤 Админы на сайте: {adm_label}",
            callback_data=f"cat_tgl:hide_admins:{chat_id}"
        )
    )

    link_label = "🔗 Личка владельца" if chat_data.get("is_private_link") else "🌐 Прямая ссылка"
    kb.row(
        types.InlineKeyboardButton(
            text=f"Тип ссылки: {link_label}",
            callback_data=f"cat_tgl:is_private_link:{chat_id}"
        )
    )

    stats_label = "❌ Скрыта" if chat_data.get("hide_stats") else "👁 Открыта"
    kb.row(
        types.InlineKeyboardButton(
            text=f"📊 Статистика на сайте: {stats_label}",
            callback_data=f"cat_tgl:hide_stats:{chat_id}"
        )
    )

    kb.row(
        types.InlineKeyboardButton(
            text="🚀 ОТПРАВИТЬ В КАТАЛОГ",
            callback_data=f"cat_sub:{chat_id}"
        )
    )
    return kb.as_markup()


@catalog_settings.message(F.text.regexp(r"(?i)^\+каталог(?:\s+(.+))?"))
async def cmd_add_catalog(message: types.Message):
    if message.chat.type == "private":
        return

    member = await message.chat.get_member(message.from_user.id)
    if member.status not in ["creator", "administrator"]:
        return await message.answer("❌ Добавлять чат в каталог могут только администраторы!")

    text = message.text.split(maxsplit=1)
    desc = text[1].strip() if len(text) > 1 else "Описание отсутствует"

    chat_title = message.chat.title
    chat_username = message.chat.username

    try:
        member_count = await message.bot.get_chat_member_count(message.chat.id)
    except Exception:
        member_count = 0

    invite_link = message.chat.invite_link or ""
    if not invite_link and chat_username:
        invite_link = f"https://t.me/{chat_username}"

    await update_chat_catalog_draft(
        chat_id=message.chat.id,
        owner_id=message.from_user.id,
        description=desc,
        title=chat_title,
        username=chat_username,
        member_count=member_count,
        invite_link=invite_link
    )

    chat = await get_catalog_chat(message.chat.id)
    chat_dict = dict(chat)

    st_status = "Скрыта" if chat_dict.get("hide_stats") else "Видна всем посетителям"
    adm_status = "Скрыты" if chat_dict.get("hide_admins") else "Отображаются"
    ln_status = "Личные сообщения владельца" if chat_dict.get("is_private_link") else (invite_link or "Не указана")

    preview_text = (
        f"⚙️ **Настройка отображения чата на сайте sapsp.site**\n\n"
        f"📋 *Название чата:* {chat_title}\n"
        f"👥 *Участников:* {member_count}\n"
        f"📊 *СМС-статистика:* {st_status}\n"
        f"👤 *Список admin:* {adm_status}\n"
        f"🔗 *Ссылка для входа:* {ln_status}\n"
    )

    await message.answer(
        preview_text,
        reply_markup=get_settings_kb(message.chat.id, chat_dict),
        parse_mode="Markdown"
    )


@catalog_settings.callback_query(F.data.startswith("cat_tgl:"))
async def cb_toggle(callback: types.CallbackQuery):
    _, col, c_id = callback.data.split(":")
    c_id = int(c_id)
    chat = await get_catalog_chat(c_id)

    if not chat:
        return await callback.answer("❌ Чат не найден.", show_alert=True)

    chat_dict = dict(chat)
    new_value = not chat_dict[col]

    await set_catalog_param(c_id, col, new_value)

    upd_chat = await get_catalog_chat(c_id)
    await callback.message.edit_reply_markup(reply_markup=get_settings_kb(c_id, dict(upd_chat)))
    await callback.answer("Изменения сохранены!")


@catalog_settings.callback_query(F.data.startswith("cat_list:"))
async def cb_list(callback: types.CallbackQuery):
    c_id = int(callback.data.split(":")[1])
    chat = await get_catalog_chat(c_id)

    if not chat:
        return await callback.answer("❌ Чат не найден.", show_alert=True)

    selected_cats = chat["category_ids"] or []
    kb = InlineKeyboardBuilder()

    for cat_id, c in CATALOG_CATEGORIES.items():
        is_selected = cat_id in selected_cats
        mark = " ✅" if is_selected else ""

        kb.add(
            types.InlineKeyboardButton(
                text=f"{c['emoji']} {c['name']}{mark}",
                callback_data=f"cat_toggle_id:{c_id}:{cat_id}"
            )
        )
    kb.adjust(2)
    kb.row(types.InlineKeyboardButton(text="🔙 Назад к настройкам", callback_data=f"cat_back:{c_id}"))

    await callback.message.edit_text(
        f"📂 **Выберите категории для сайта (выбрано {len(selected_cats)} из 10):**\n"
        f"_Пользователи смогут находить ваш чат по этим тегам._",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )
    await callback.answer()


@catalog_settings.callback_query(F.data.startswith("cat_toggle_id:"))
async def cb_toggle_category(callback: types.CallbackQuery):
    _, c_id, cat_id = callback.data.split(":")
    c_id, cat_id = int(c_id), int(cat_id)

    chat = await get_catalog_chat(c_id)
    if not chat:
        return await callback.answer("❌ Чат не найден.", show_alert=True)

    current_cats = list(chat["category_ids"] or [])

    if cat_id in current_cats:
        current_cats.remove(cat_id)
        await callback.answer("Категория убрана")
    else:
        if len(current_cats) >= 10:
            return await callback.answer("⚠️ Нельзя выбрать более 10 категорий!", show_alert=True)
        current_cats.append(cat_id)
        await callback.answer("Категория добавлена")

    await set_catalog_param(c_id, "category_ids", current_cats)
    await cb_list(callback)


@catalog_settings.callback_query(F.data.startswith("cat_back:"))
async def cb_back_to_main(callback: types.CallbackQuery):
    c_id = int(callback.data.split(":")[1])
    chat = await get_catalog_chat(c_id)
    chat_dict = dict(chat)

    invite_link = chat_dict.get("invite_link") or ""
    st_status = "Скрыта" if chat_dict.get("hide_stats") else "Видна всем посетителям"
    adm_status = "Скрыты" if chat_dict.get("hide_admins") else "Отображаются"
    ln_status = "Личные сообщения владельца" if chat_dict.get("is_private_link") else (invite_link or "Не указана")

    preview_text = (
        f"⚙️ **Настройка отображения чата на сайте sapsp.site**\n\n"
        f"📋 *Название чата:* {chat_dict.get('title')}\n"
        f"👥 *Участников:* {chat_dict.get('member_count', 0)}\n"
        f"📊 *СМС-статистика:* {st_status}\n"
        f"👤 *Список admin:* {adm_status}\n"
        f"🔗 *Ссылка для входа:* {ln_status}\n"
    )

    await callback.message.edit_text(
        preview_text,
        reply_markup=get_settings_kb(c_id, chat_dict),
        parse_mode="Markdown"
    )
    await callback.answer()


@catalog_settings.callback_query(F.data.startswith("cat_sub:"))
async def cb_sub(callback: types.CallbackQuery):
    c_id = int(callback.data.split(":")[1])
    chat = await get_catalog_chat(c_id)

    if not chat:
        return await callback.answer("❌ Чат не найден.", show_alert=True)

    if not chat["category_ids"] or len(chat["category_ids"]) == 0:
        return await callback.answer("❌ Выберите хотя бы одну категорию перед публикацией!", show_alert=True)

    await set_catalog_param(c_id, "status", "pending")
    await callback.message.edit_text(
        "🚀 **Заявка успешно отправлена!**\n\nМодераторы Sapphire проверят ваш чат, после чего он станет доступен в каталоге на сайте `sapsp.site`.",
        parse_mode="Markdown"
    )
    await callback.answer()