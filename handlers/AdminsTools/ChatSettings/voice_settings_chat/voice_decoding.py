import os
import asyncio
import tempfile
import logging
import gc
from aiogram import types, F, Router
from aiogram.filters import Command
from aiogram.types import ReplyParameters
from faster_whisper import WhisperModel

from handlers.AdminsTools.ChatSettings.voice_settings_chat.voice_settingsDB import check_status_voice_settings
from handlers.BotAutomaticWork.Gonfig.config import sanor_ID
from handlers.BotAutomaticWork.universal_bot import bot  # Импортируем функцию проверки
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

# ================= КОНФИГУРАЦИЯ =================
MODEL_SIZE = "small"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

MAX_CONCURRENT_TASKS = 1

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

decoding = Router()

model = None


def load_model():
    global model
    logger.info(f"🚀 Загрузка модели {MODEL_SIZE} (режим {COMPUTE_TYPE})...")
    try:
        model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        logger.info("✅ Модель успешно загружена!")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка загрузки модели: {e}")
        raise e


#load_model()

semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)


def transcribe_audio(file_path: str) -> str:
    """Функция распознавания речи (синхронная)."""
    if model is None:
        raise RuntimeError("Модель не инициализирована!")

    segments, info = model.transcribe(
        file_path,
        beam_size=1,
        language="ru",
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500)
    )

    text_parts = [segment.text for segment in segments]
    return " ".join(text_parts).strip()


async def send_long_text_chain(message: types.Message, full_text: str, reply_to_message_id: int,
                               edit_message_id: int = None):
    """
    Отправляет длинный текст цепочкой.
    Если передан edit_message_id, первое сообщение будет отредактировано, а не отправлено новое.
    """
    MAX_LEN = 4000
    HEADER_RESERVED = 70

    chunks = []
    current_pos = 0
    total_len = len(full_text)
    part_index = 0

    # Разбивка текста на части
    while current_pos < total_len:
        part_index += 1
        limit = MAX_LEN - HEADER_RESERVED if part_index == 1 else MAX_LEN - 40

        chunk_end = min(current_pos + limit, total_len)
        text_chunk = full_text[current_pos:chunk_end]

        if chunk_end < total_len:
            last_space = text_chunk.rfind(' ')
            if last_space != -1 and last_space > len(text_chunk) * 0.8:
                text_chunk = text_chunk[:last_space]
                chunk_end = current_pos + last_space

        chunks.append(text_chunk)
        current_pos = chunk_end

    total_parts = len(chunks)
    last_sent_message_id = reply_to_message_id

    for index, chunk in enumerate(chunks):
        text_to_send = ""

        if index == 0:
            header = "💬 <b>Расшифровка голосового сообщения:</b>\n\n"
            footer = "\n\n<i>(Продолжение ниже 👇)</i>" if total_parts > 1 else ""
            text_to_send = f"{header}<code>{chunk}</code>{footer}"

            # ЛОГИКА РЕДАКТИРОВАНИЯ ПЕРВОГО СООБЩЕНИЯ
            if edit_message_id:
                try:
                    await bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=edit_message_id,
                        text=text_to_send,
                        parse_mode="HTML"
                    )
                    last_sent_message_id = edit_message_id
                    continue  # Переходим к следующей части, первое уже обработано
                except Exception as e:
                    logger.warning(
                        f"Не удалось отредактировать сообщение (возможно, текст слишком длинный для одного сообщения или изменился контент): {e}")
                    await message.reply('Произошла ошибка')
                    # Если редактирование не удалось (например, текст стал слишком длинным при добавлении заголовка),
                    # просто отправим новое сообщение следом, чтобы не ломать поток.

        else:
            header = f"📝 <b>Часть {index + 1}/{total_parts}:</b>\n\n"
            text_to_send = f"{header}<code>{chunk}</code>"

        # Отправка последующих частей (или первой, если редактирование не сработало)
        try:
            sent_msg = await message.answer(
                text=text_to_send,
                parse_mode="HTML",
                reply_parameters=ReplyParameters(message_id=last_sent_message_id)
            )
            last_sent_message_id = sent_msg.message_id

            if index < total_parts - 1:
                await asyncio.sleep(0.2)

        except Exception as e:
            logger.error(f"Ошибка при отправке части текста #{index}: {e}")
            break


async def process_voice(voice: types.Voice, message: types.Message):
    """Обработка голосового сообщения"""
    file_id = voice.file_id
    temp_path = None
    status_message = None

    try:
        # 1. ОТПРАВЛЯЕМ СТАТУСНОЕ СООБЩЕНИЕ
        status_text = "🎙 Распознаю . . ."
        status_message = await message.answer(status_text)
        #logger.info(f"Статус отправлен user_{message.from_user.id}, msg_id={status_message.message_id}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp_file:
            temp_path = tmp_file.name

        await bot.download(file_id, destination=temp_path)
        #logger.info(f"Файл скачан: {temp_path}")

        async with semaphore:
         #   logger.info(f"Начало обработки файла от user_{message.from_user.id}")
            loop = asyncio.get_event_loop()

            # 2. ЗАПУСКАЕМ РАСПОЗНАВАНИЕ (блокирующая операция в потоке)
            text = await loop.run_in_executor(None, transcribe_audio, temp_path)

            if not text:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=status_message.message_id,
                    text="⚠️ Не удалось распознать речь (возможно, там тишина или сильный шум)."
                )
            else:
                #logger.info(f"Успешная расшифровка ({len(text)} симв.) для user_{message.from_user.id}")
                # 3. ОБНОВЛЯЕМ СООБЩЕНИЕ ИЛИ ОТПРАВЛЯЕМ ЦЕПОЧКУ
                await send_long_text_chain(
                    message,
                    text,
                    reply_to_message_id=message.message_id,
                    edit_message_id=status_message.message_id
                )

            gc.collect()

    except Exception as e:
        #logger.error(f"Критическая ошибка в process_voice: {e}", exc_info=True)
        error_text = "❌ Произошла ошибка при обработке. Попробуйте позже."
        try:
            if status_message:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=status_message.message_id,
                    text=error_text
                )
            else:
                await message.answer(error_text)
        except:
            pass
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
       #         logger.debug(f"Временный файл удален: {temp_path}")
            except Exception as e:
                logger.warning(f"Не удалось удалить файл {temp_path}: {e}")


@decoding.message(F.text.split("\n", 1)[0].lower() == '.гс')
@decoding.message(F.text.split("\n", 1)[0].lower() == '!гс')
@decoding.message(F.text.split("\n", 1)[0].lower() == '/гс')
async def cmd_transcribe_reply(message: types.Message):
    """Обработка команды /гс в ответ на сообщение"""
    if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 80):
        return

    if not message.reply_to_message:
        await message.answer("Пожалуйста, используйте эту команду как <b>ответ</b> на голосовое сообщение.")
        return

    # Проверяем включены ли голосовые в чате
    voice_settings = await check_status_voice_settings(message.chat.id)

    # Handle both dictionary and string return types
    is_enabled = False
    if voice_settings:
        if isinstance(voice_settings, dict):
            is_enabled = voice_settings.get('voice') == "yes"
        else:
            # If it's a string, assume it's the status directly
            is_enabled = voice_settings == "yes"

    # Если функция отключена - сообщаем пользователю
    if not is_enabled:
        return

    if message.reply_to_message.voice:
        await process_voice(message.reply_to_message.voice, message)
    elif message.reply_to_message.video_note:
        await message.answer("Кружочки (видеосообщения) пока не поддерживаются, только аудио 🎙")
    else:
        await message.answer("В ответном сообщении нет голосового аудио 🤷‍♂️")


@decoding.message(F.voice)
async def handle_voice_direct(message: types.Message):
    """Автоматическая обработка голосовых сообщений"""
    # Проверяем включены ли голосовые в чате
    voice_settings = await check_status_voice_settings(message.chat.id)

    # Handle both dictionary and string return types
    is_enabled = False
    if voice_settings:
        if isinstance(voice_settings, dict):
            is_enabled = voice_settings.get('voice') == "yes"
        else:
            # If it's a string, assume it's the status directly
            is_enabled = voice_settings == "yes"

    # If disabled, silently ignore (no response for auto-handler)
    if not is_enabled:
        return

    await process_voice(message.voice, message)