import logging

from aiogram import types, Router
from handlers.AdminsTools.ChatSettings.DkCommands.UpdateCommandSettingsDB import (
    add_dk_for_chats,
    update_dk_for_chats,
    check_command_chat,
    check_command_for_bd_int,
    check_command_for_bd_str,
    get_section_info,
    get_under_section_info,
    get_commands_by_section,
    get_commands_by_under_section,
    get_command_info,
    get_all_sections,
    get_under_sections_by_section, get_command_access_level
)

from handlers.BotAutomaticWork.Gonfig.config import boss_agent
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

CheckDk = Router()

logger = logging.getLogger(__name__)

# Эмодзи для рангов
RANG_EMOJIS = {
    0: "0️⃣", 1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "⛔"
}




async def update_command_access(chat_id: int, command_id: int, rang: int) -> None:
    """Универсальная функция для обновления доступа к команде"""
    CHECK = await check_command_chat(command_id, chat_id)
    if not CHECK:
        await add_dk_for_chats(chat_id, command_id, rang)
    else:
        await update_dk_for_chats(chat_id, command_id, rang)


async def bulk_update_commands(m: types.Message, chat_id: int, commands: list, rang: int, success_message: str) -> None:
    """Массовое обновление команд с одинаковым рангом"""
    if not commands:
        await m.answer('❌ Нет команд для обновления.', parse_mode='HTML')
        return

    updated_count = 0
    for command in commands:
        await update_command_access(chat_id, command['CommandId'], rang)
        updated_count += 1

    status_text = "выключены" if rang == 6 else f"установлен ранг {rang}"
    await m.answer(f'✅ {success_message} {status_text} (обновлено команд: {updated_count})')


async def bulk_update_commands_individual(m: types.Message, chat_id: int, commands: list, success_message: str) -> None:
    """Массовое обновление команд с индивидуальными рангами (для включения)"""
    if not commands:
        await m.answer('❌ Нет команд для обновления.', parse_mode='HTML')
        return

    updated_count = 0
    for command in commands:
        # При включении используем уровень доступа из основной таблицы commands
        target_rang = command['AccessLevel']
        await update_command_access(chat_id, command['CommandId'], target_rang)
        updated_count += 1

    await m.answer(f'✅ {success_message} включены (обновлено команд: {updated_count})')


async def identify_target_type(target_value: str) -> tuple[str, int]:
    """Определяет тип цели (команда, раздел, подраздел) и возвращает ID"""

    # Проверяем, является ли числом (ID команды)
    if target_value.isdigit():
        command_id = int(target_value)
        if (db_id := await check_command_for_bd_int(command_id)) is not None:
            return "command", db_id

    # Проверяем как строковую команду
    if (db_id := await check_command_for_bd_str(target_value)) is not None:
        return "command", db_id

    # Проверяем как подраздел (формат: раздел.подраздел)
    if '.' in target_value:
        section_part, under_section_part = target_value.split('.', 1)
        if under_section_info := await get_under_section_info(under_section_part, section_part):
            return "under_section", under_section_info['UnderSectionId']

    # Проверяем как подраздел по имени
    if under_section_info := await get_under_section_info(target_value):
        return "under_section", under_section_info['UnderSectionId']

    # Проверяем как раздел
    if section_info := await get_section_info(target_value):
        return "section", section_info['SectionId']

    return "not_found", None


async def show_help_message(m: types.Message, command_type: str):
    """Показать справку в зависимости от типа команды"""
    if command_type == "рк":
        await m.answer('⚠️ Не указаны аргументы.',
                       parse_mode='HTML')
    else:
        await m.answer('⚠️ <b>Не указана команда/раздел/подраздел для включения/выключения.</b>',
                       parse_mode='HTML')


async def handle_enable_disable(m: types.Message, chat_id: int, target_type: str, target_id: int, is_enable: bool):
    """Обработка включения/выключения команд, разделов, подразделов"""

    if target_type == "command":
        await enable_disable_command(m, chat_id, target_id, is_enable)
    elif target_type == "under_section":
        await enable_disable_under_section(m, chat_id, target_id, is_enable)
    elif target_type == "section":
        await enable_disable_section(m, chat_id, target_id, is_enable)


async def enable_disable_command(m: types.Message, chat_id: int, command_id: int, is_enable: bool):
    """Включение/выключение отдельной команды"""
    command_info = await get_command_info(command_id)
    if not command_info:
        await m.answer('❌ Информация о команде не найдена!', parse_mode='HTML')
        return

    # При включении используем уровень доступа из основной таблицы commands
    # При выключении устанавливаем ранг 6
    target_rang = command_info['AccessLevel'] if is_enable else 6
    await update_command_access(chat_id, command_id, target_rang)

    action_text = "включена" if is_enable else "выключена"
    await m.answer(f'✅ Команда «<code>{command_info["CommandName"]}</code>» {action_text} (ранг {target_rang})')


async def enable_disable_under_section(m: types.Message, chat_id: int, under_section_id: int, is_enable: bool):
    """Включение/выключение всех команд подраздела"""
    under_section_info = await get_under_section_info(under_section_id=under_section_id)
    if not under_section_info:
        await m.answer('❌ Подраздел не найден!', parse_mode='HTML')
        return

    commands = await get_commands_by_under_section(under_section_id)
    success_message = f'🔽 Все команды подраздела «{under_section_info["UnderName"]}»'

    if is_enable:
        await bulk_update_commands_individual(m, chat_id, commands, success_message)
    else:
        await bulk_update_commands(m, chat_id, commands, 6, success_message)


async def enable_disable_section(m: types.Message, chat_id: int, section_id: int, is_enable: bool):
    """Включение/выключение всех команд раздела"""
    section_info = await get_section_info(section_id=section_id)
    if not section_info:
        await m.answer('❌ Раздел не найден!', parse_mode='HTML')
        return

    commands = await get_commands_by_section(section_id)
    success_message = f'🔽 Все команды раздела «{section_info["SectionName"]}»'

    if is_enable:
        await bulk_update_commands_individual(m, chat_id, commands, success_message)
    else:
        await bulk_update_commands(m, chat_id, commands, 6, success_message)


async def set_target_rang(m: types.Message, chat_id: int, target_type: str, target_id: int, rang: int):
    """Установка конкретного ранга для команды/раздела/подраздела"""

    if target_type == "command":
        await set_command_rang(m, chat_id, target_id, rang)
    elif target_type == "under_section":
        await set_under_section_rang(m, chat_id, target_id, rang)
    elif target_type == "section":
        await set_section_rang(m, chat_id, target_id, rang)


async def set_command_rang(m: types.Message, chat_id: int, command_id: int, rang: int):
    """Установка ранга для отдельной команды"""
    command_info = await get_command_info(command_id)
    if not command_info:
        await m.answer('❌ Команда не найдена!', parse_mode='HTML')
        return

    await update_command_access(chat_id, command_id, rang)

    status_text = "выключена" if rang == 6 else f"установлен ранг {rang}"
    await m.answer(f'✅ Команда {command_info["CommandName"]} {status_text}')


async def set_under_section_rang(m: types.Message, chat_id: int, under_section_id: int, rang: int):
    """Установка ранга для всех команд подраздела"""
    under_section_info = await get_under_section_info(under_section_id=under_section_id)
    if not under_section_info:
        await m.answer('❌ Подраздел не найден!', parse_mode='HTML')
        return

    commands = await get_commands_by_under_section(under_section_id)
    success_message = f'🔽 Все команды подраздела «{under_section_info["UnderName"]}»'
    await bulk_update_commands(m, chat_id, commands, rang, success_message)


async def set_section_rang(m: types.Message, chat_id: int, section_id: int, rang: int):
    """Установка ранга для всех команд раздела"""
    section_info = await get_section_info(section_id=section_id)
    if not section_info:
        await m.answer('❌ Раздел не найден!', parse_mode='HTML')
        return

    commands = await get_commands_by_section(section_id)
    success_message = f'🔽 Все команды раздела "{section_info["SectionName"]}"'
    await bulk_update_commands(m, chat_id, commands, rang, success_message)


# ========== СИСТЕМА ПРОСМОТРА КОМАНД ==========

async def show_all_sections(m: types.Message):
    """Показать все разделы"""
    sections = await get_all_sections()

    if not sections:
        await m.answer('Ничего не найдено.', parse_mode='HTML')
        return

    sections_text = "▶️ Доступы команд:\n"
    for section in sections:
        sections_text += f"{section['SectionId']}. {section['SectionName']}\n"

    await m.answer(sections_text, parse_mode='HTML')


async def show_command_by_id(m: types.Message, command_id: int | str, chat_id: int = None):
    """Показать информацию о команде по ID или имени с учетом приоритета commands_chats"""
    try:
        command_info = await get_command_info(command_id=command_id)

        if not command_info:
            await m.answer(f'❌ Команда «<code>{command_id}</code>» не найдена!', parse_mode='HTML')
            return

        # Получаем актуальный уровень доступа с приоритетом commands_chats
        if chat_id:
            access_level = await get_command_access_level(chat_id, command_info['CommandId'])
        else:
            access_level = command_info['AccessLevel']

        # Получаем информацию о подразделе
        under_section_info = await get_under_section_info(under_section_id=command_info['UnderSectionId'])

        rang_emoji = RANG_EMOJIS.get(access_level, '❓')
        command_name = command_info.get('CommandName', f'Команда #{command_info["CommandId"]}')

        command_text = (
            f'<b>🔽 Раздел {under_section_info["UnderName"]}:</b>\n\n'
            f'{rang_emoji} {command_info["CommandId"]}. {command_name} (ранг {access_level})'
        )

        await m.answer(command_text, parse_mode='HTML')

    except Exception as e:
        logger.error(e, exc_info=True)
        await m.answer('❌ Произошла ошибка при получении информации о команде!', parse_mode='HTML')


async def identify_and_show_target(m: types.Message, target: str):
    """Идентифицировать цель и показать соответствующую информацию с учетом commands_chats"""

    #print(f"🔍 Поиск цели: '{target}'")  # Отладка
    chat_id = m.chat.id

    # 1. Сначала ищем команду по имени (регистронезависимо)
    #print(f"📝 Ищем команду по имени: '{target}'")
    command_info = await get_command_info(command_name=target)
    if command_info:
        #print(f"✅ Найдена команда по имени: {command_info['CommandName']} (ID: {command_info['CommandId']})")
        await show_command_by_id(m, command_info['CommandId'], chat_id)
        return

    # 2. Проверяем, является ли target числом (ID)
    if target.isdigit():
        target_id = int(target)
        #print(f"🔢 Цель является числом: {target_id}")

        # Ищем команду по ID
        command_info = await get_command_info(command_id=target_id)
        if command_info:
            #print(f"✅ Найдена команда по ID: {command_info}")
            await show_command_by_id(m, target_id, chat_id)
            return

        # Ищем раздел по ID
        section_info = await get_section_info(section_id=target_id)
        if section_info:
            #print(f"✅ Найден раздел по ID: {section_info}")
            await show_under_sections(m, section_info, chat_id)
            return

        # Ищем подраздел по ID
        under_section_info = await get_under_section_info(under_section_id=target_id)
        if under_section_info:
            #print(f"✅ Найден подраздел по ID: {under_section_info}")
            await show_commands_in_under_section(m, under_section_info, chat_id)
            return

    # 3. Проверяем формат "раздел.подраздел" (регистронезависимо)
    if '.' in target:
        #print(f"🔗 Проверяем формат раздел.подраздел: {target}")
        section_part, under_section_part = target.split('.', 1)

        if section_part.isdigit() and under_section_part.isdigit():
            under_section_info = await get_under_section_info(
                under_section_id=int(under_section_part),
                section_id=int(section_part)
            )
        else:
            # Регистронезависимый поиск по именам
            under_section_info = await get_under_section_info(
                under_section_name=under_section_part,
                section_name=section_part
            )

        if under_section_info:
            #print(f"✅ Найден подраздел по формату: {under_section_info}")
            await show_commands_in_under_section(m, under_section_info, chat_id)
            return

    # 4. Ищем раздел по имени (регистронезависимо)
    #print(f"📁 Ищем раздел по имени: '{target}'")
    section_info = await get_section_info(section_name=target)
    if section_info:
        #print(f"✅ Найден раздел по имени: {section_info}")
        await show_under_sections(m, section_info, chat_id)
        return

    # 5. Ищем подраздел по имени (регистронезависимо)
    #print(f"📂 Ищем подраздел по имени: '{target}'")
    under_section_info = await get_under_section_info(under_section_name=target)
    if under_section_info:
        #print(f"✅ Найден подраздел по имени: {under_section_info}")
        await show_commands_in_under_section(m, under_section_info, chat_id)
        return

    # Если ничего не найдено
    #print(f"❌ Ничего не найдено для: '{target}'")
    await m.answer('❌ Команда, раздел или подраздел не найден!', parse_mode='HTML')


async def show_under_sections(m: types.Message, section_info: dict, chat_id: int = None):
    """Показать подразделы раздела"""
    under_sections = await get_under_sections_by_section(section_info['SectionId'])

    if not under_sections:
        await m.answer(f'{section_info["SectionName"]}\n\n'
                       '❌ В разделе нет подразделов',
                       parse_mode='HTML')
        return

    under_sections_text = f'🔽 Раздел {section_info["SectionName"]}\n\n'

    for under_section in under_sections:
        # Используем реальный UnderSectionId из базы данных
        under_sections_text += f"{under_section['UnderSectionId']}. {under_section['UnderName']}\n"

    await m.answer(under_sections_text, parse_mode='HTML')


async def show_commands_in_under_section(m: types.Message, under_section_info: dict, chat_id: int = None):
    """Показать все команды в подразделе с их рангами (с учетом commands_chats)"""
    commands = await get_commands_by_under_section(under_section_info['UnderSectionId'])

    if not commands:
        await m.answer(f'🔽 Раздел {under_section_info["UnderName"]}\n\n'
                       '❌ <b>В подразделе нет команд</b>',
                       parse_mode='HTML')
        return

    commands_text = f'🔽 <b>Раздел</b> {under_section_info["UnderName"]}\n\n'

    for command in commands:
        # Получаем актуальный уровень доступа с приоритетом commands_chats
        if chat_id:
            access_level = await get_command_access_level(chat_id, command['CommandId'])
        else:
            access_level = command['AccessLevel']

        rang_emoji = RANG_EMOJIS.get(access_level, '❓')
        command_name = command.get('CommandName', f'Команда #{command["CommandId"]}')

        # Добавляем CommandId перед названием команды
        commands_text += f"{rang_emoji} {command['CommandId']}. <code>{command_name}</code>\n"

    await m.answer(commands_text, parse_mode='HTML')


async def check_commands_structure(m: types.Message):
    """Основной обработчик команды !чек рк"""
    try:
        parts = m.text.split(maxsplit=2)

        # Если команда просто "!чек дк" - показываем все разделы
        if len(parts) == 2:
            await show_all_sections(m)
            return

        target = parts[2].strip()
        await identify_and_show_target(m, target)

    except Exception as e:
        logger.error(e, exc_info=True)
        await m.answer('❌ <b>Произошла ошибка при выполнении команды.</b>', parse_mode='HTML')


@CheckDk.message(lambda m: m.text and m.text.lower().startswith('!чек рк'))
@CheckDk.message(lambda m: m.text and m.text.lower().startswith('.чек рк'))
@CheckDk.message(lambda m: m.text and m.text.lower().startswith('/чек рк'))
async def check_commands_handler(m: types.Message):
    if m.chat.type == 'private':
        return

    ChatId = m.chat.id
    User_Id = m.from_user.id

    # Проверяем права доступа: босс-агенты пропускаются, остальные проходят проверку
    if User_Id not in boss_agent and not await auto_check_AccessLevel_for_rang(User_Id, ChatId, 62):
        return

    await check_commands_structure(m)