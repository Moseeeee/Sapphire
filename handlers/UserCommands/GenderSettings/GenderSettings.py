from aiogram import Router, F
from aiogram.types import Message

from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.UserCommands.GenderSettings.GenderSettingsDB import update_user_gender

GenderSettings = Router()


@GenderSettings.message(F.text.lower().startswith('+мой пол'))
async def set_gender_command(message: Message):
    user_id = message.from_user.id
    command_text = message.text or ""

    # Если не private чат, проверяем права
    if message.chat.type != 'private':
        if not await auto_check_AccessLevel_for_rang(user_id, message.chat.id, 58):
            return

    # Общая обработка команды
    parts = command_text.split()
    if len(parts) < 3:
        await message.reply(
            "❌ <b>Использование команды:</b>\n"
            "+мой пол <b>ж</b> - женский\n"
            "+мой пол <b>м</b> - мужской\n"
            "+мой пол <b>оно</b> - оно\n\n"
            "Пример: <code>+мой пол ж</code>",
            parse_mode='HTML'
        )
        return

    gender_param = parts[2].lower().strip()
    valid_genders = {'ж', 'м', 'оно'}

    if gender_param not in valid_genders:
        await message.reply(
            "❌ <b>Неверный параметр пола!</b>\n"
            "Допустимые значения: <b>ж</b>, <b>м</b>, <b>оно</b>\n\n"
            "Пример: <code>+мой пол ж</code>",
            parse_mode='HTML'
        )
        return

    # Обновляем пол в базе данных
    await update_user_gender(user_id, gender_param)

    gender_display = {
        'ж': 'женский ♀️',
        'м': 'мужской ♂️',
        'оно': 'оно ⚧'
    }

    await message.reply(
        f"✅ Пол успешно обновлён на {gender_display[gender_param]}\n",
        parse_mode='HTML'
    )


@GenderSettings.message(F.text.lower().startswith('-мой пол'))
@GenderSettings.message(F.text.lower().startswith('!сбросить мой пол'))
@GenderSettings.message(F.text.lower().startswith('.сбросить мой пол'))
@GenderSettings.message(F.text.lower().startswith('/сбросить мой пол'))
async def reset_gender_command(message: Message):

    if message.chat.type != 'private':
        if not await auto_check_AccessLevel_for_rang(message.from_user.id, message.chat.id, 58):
            return

    """Команда для сброса пола на 'он'"""
    user_id = message.from_user.id

    # Сбрасываем пол на "не указан"
    await update_user_gender(user_id, 'не указан')

    await message.reply(
        "✅ Пол сброшен!\n",
        parse_mode='HTML'
    )


