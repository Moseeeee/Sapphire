import re
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InputFile
from aiogram.exceptions import TelegramAPIError
from aiogram.utils.markdown import hcode, hlink
import logging

from handlers.BotAutomaticWork.Gonfig.config import sanor_ID
from handlers.BotAutomaticWork.universal_bot import bot

# Логирование (опционально)
logging.basicConfig(level=logging.INFO)
CPE = Router()  # CPE - CheckPremiumEmodji


@CPE.message(F.text, F.text.lower().startswith("!прем ид"))
@CPE.message(F.text, F.text.lower().startswith("/прем ид"))
@CPE.message(F.text, F.text.lower().startswith(".прем ид"))
async def handle_premium_emoji_info(message: Message):
    if message.from_user.id != sanor_ID:
        return

    # Получаем текст команды и аргументы
    text = message.text or message.caption or ""
    command_parts = text.strip().split()

    # Определяем, есть ли аргументы после "прем ид"
    has_args = False
    for i in range(len(command_parts) - 2):
        if command_parts[i].lower() in ["!прем", "/прем", ".прем"] and command_parts[i + 1].lower() == "ид":
            # Проверяем, есть ли что-то после "ид"
            if len(command_parts) > i + 2:
                has_args = True
            break

    # Определяем, откуда брать эмодзи для анализа
    if has_args:
        # Есть аргументы - используем текст команды, игнорируем reply
        source_message = message
        #await message.reply("⚙️ Использую эмодзи из аргументов команды (reply проигнорирован).")
    elif message.reply_to_message:
        # Нет аргументов, но есть reply - используем reply
        source_message = message.reply_to_message
        #await message.reply("↩️ Использую эмодзи из ответленного сообщения.")
    else:
        # Нет ни аргументов, ни reply - используем само сообщение
        source_message = message
        #await message.reply("📝 Использую эмодзи из текущего сообщения.")

    # Получаем html_text для парсинга
    html_text = source_message.html_text or source_message.html_caption or ""

    # Используем регулярку для поиска всех эмодзи в html_text
    # Формат: <tg-emoji emoji-id="123456789">😀</tg-emoji>
    emoji_matches = re.findall(r'<tg-emoji emoji-id="(\d+)">([^<]+)</tg-emoji>', html_text)

    if not emoji_matches:
        await message.reply("❌ Не найдено ни одного премиального эмодзи.")
        return

    # Собираем уникальные эмодзи (по ID)
    unique_emojis = {}  # {emoji_id: (emoji_char, count)}

    for emoji_id, emoji_char in emoji_matches:
        if emoji_id not in unique_emojis:
            # Считаем, сколько раз встречается этот эмодзи
            count = sum(1 for eid, _ in emoji_matches if eid == emoji_id)
            unique_emojis[emoji_id] = (emoji_char, count)

    # Ограничиваем до 10 уникальных эмодзи
    if len(unique_emojis) > 10:
        # Берем первые 10 уникальных ID
        limited_emojis = {}
        for i, (emoji_id, data) in enumerate(unique_emojis.items()):
            if i >= 100:
                break
            limited_emojis[emoji_id] = data
        unique_emojis = limited_emojis
        await message.reply("⚠️ Обрабатываю только первые 100 эмодзи.")

    # Получаем ID для запроса к API
    emoji_ids = list(unique_emojis.keys())

    if not emoji_ids:
        await message.reply("❌ Не найдено ID премиальных эмодзи.")
        return

    try:
        # Получаем информацию о стикерах
        stickers = await bot.get_custom_emoji_stickers(custom_emoji_ids=emoji_ids)
    except TelegramAPIError as e:
        await message.reply(f"❌ Ошибка Telegram API: {e}")
        return

    if not stickers:
        await message.reply("❌ Не удалось получить данные о премиальных эмодзи.")
        return

    # Создаем словарь для быстрого доступа к информации о стикерах по ID
    sticker_info = {}
    for sticker in stickers:
        emoji_id = str(sticker.custom_emoji_id)
        sticker_info[emoji_id] = sticker

    # Формируем ответ с использованием HTML разметки для отображения премиальных эмодзи
    lines = ["<tg-emoji emoji-id='5334890573281114250'>🆔</tg-emoji> <b>Премиальных эмодзи:</b>\n"]

    for emoji_id, (emoji_char, count) in unique_emojis.items():
        if emoji_id in sticker_info:
            sticker = sticker_info[emoji_id]

            # Используем HTML-тег для отображения премиального эмодзи
            # Формат: <tg-emoji emoji-id="123456789"></tg-emoji>
            premium_emoji_tag = f'<tg-emoji emoji-id="{emoji_id}">{emoji_char}</tg-emoji>'

            if sticker.set_name:
                pack_link = f"https://t.me/addstickers/{sticker.set_name}"
                link_text = hlink(sticker.set_name, pack_link)
            else:
                link_text = "неизвестен"
        else:
            premium_emoji_tag = emoji_char
            link_text = "неизвестен"

        # Формат: {премиальный_эмодзи}: {id} (ссылка на пак)
        lines.append(f"{premium_emoji_tag}: {hcode(emoji_id)} ({link_text})\n")

    # Показываем общую статистику
    total_count = len(emoji_matches)
    unique_count = len(unique_emojis)
    lines.append(
        f"\n<tg-emoji emoji-id='5231200819986047254'>📊</tg-emoji> {total_count} эмодзи ({unique_count} уникальных)\n")
    #lines.append("HTML ссылка: <code><tg-emoji emoji-id=''></tg-emoji></code>")

    response = "".join(lines).rstrip()
    await message.reply(response, parse_mode="HTML", disable_web_page_preview=True)