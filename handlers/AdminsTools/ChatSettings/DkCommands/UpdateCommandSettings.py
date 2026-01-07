import logging

from aiogram import types, Router
from handlers.AdminsTools.ChatSettings.DkCommands.UpdateCommandSettingsDB import (
    add_dk_for_chats,
    update_dk_for_chats,
    check_command_chat,
    get_section_info,
    get_under_section_info,
    get_commands_by_section,
    get_commands_by_under_section,
    get_command_info
)
from handlers.BotAutomaticWork.Gonfig.config import boss_agent
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

logger = logging.getLogger(__name__)

UpdateCommandsSetting = Router()

# ID команды, которую нельзя отключать
PROTECTED_COMMAND_ID = 61


async def update_command_access(chat_id: int, command_id: int, rang: int) -> None:
    # Проверяем, не пытаемся ли отключить защищенную команду
    if command_id == PROTECTED_COMMAND_ID and rang == 6:
        return  # Игнорируем попытку отключения защищенной команды

    CHECK = await check_command_chat(command_id, chat_id)
    if not CHECK:
        await add_dk_for_chats(chat_id, command_id, rang)
    else:
        await update_dk_for_chats(chat_id, command_id, rang)


async def bulk_update_commands(m: types.Message, chat_id: int, commands: list, rang: int, success_message: str) -> None:
    """Массовое обновление команд с одинаковым рангом (с исключением защищенной команды)"""
    if not commands:
        await m.answer('❌ Нет команд для обновления.', parse_mode='HTML')
        return

    updated_count = 0
    skipped_count = 0

    for command in commands:
        command_id = command['CommandId']  # Используем только ID команды

        if command_id == PROTECTED_COMMAND_ID and rang == 6:
            skipped_count += 1
            continue

        await update_command_access(chat_id, command_id, rang)
        updated_count += 1

    status_text = "выключены" if rang == 6 else f"установлен ранг {rang}"

    result_message = f'✅ {success_message} {status_text} (обновлено команд: {updated_count})'
    if skipped_count > 0:
        result_message += '\n⏩ Команду «настройка доступа команд» нельзя отключить.'

    await m.answer(result_message)


async def bulk_update_commands_individual(m: types.Message, chat_id: int, commands: list, success_message: str) -> None:
    """Массовое обновление команд с индивидуальными рангами (для включения)"""
    if not commands:
        await m.answer('❌ Нет команд для обновления.', parse_mode='HTML')
        return

    updated_count = 0
    for command in commands:
        command_id = command['CommandId']  # Используем только ID команды
        target_rang = command['AccessLevel']
        await update_command_access(chat_id, command_id, target_rang)
        updated_count += 1

    await m.answer(f'✅ {success_message} включены (обновлено команд: {updated_count})')


async def identify_target_type(target_value: str) -> tuple[str, int]:
    """Определяет тип цели (команда, раздел, подраздел) и возвращает ID"""

    # Сначала проверяем, является ли target_value числом (ID команды)
    if target_value.isdigit():
        command_id = int(target_value)
        command_info = await get_command_info(command_id=command_id)
        if command_info:
            return "command", command_info['CommandId']  # Возвращаем ID команды

    # Проверяем по названию команды
    command_info = await get_command_info(command_name=target_value)
    if command_info:
        return "command", command_info['CommandId']  # Возвращаем ID команды

    # Проверяем подразделы в формате "раздел.подраздел"
    if '.' in target_value:
        section_part, under_section_part = target_value.split('.', 1)

        if section_part.isdigit() and under_section_part.isdigit():
            under_section_info = await get_under_section_info(
                under_section_id=int(under_section_part),
                section_id=int(section_part)
            )
        else:
            under_section_info = await get_under_section_info(under_section_part, section_part)

        if under_section_info:
            return "under_section", under_section_info['UnderSectionId']

    # Проверяем подраздел по названию
    if under_section_info := await get_under_section_info(under_section_name=target_value):
        return "under_section", under_section_info['UnderSectionId']

    # Проверяем раздел по названию
    if section_info := await get_section_info(section_name=target_value):
        return "section", section_info['SectionId']

    # Проверяем раздел по ID
    if target_value.isdigit():
        if section_info := await get_section_info(section_id=int(target_value)):
            return "section", section_info['SectionId']

    return "not_found", None


async def show_help_message(m: types.Message, command_type: str):
    """Показать справку в зависимости от типа команды"""
    if command_type == "рк":
        help_text = (
            '⚠️ <b>Использование команды "рк":</b>\n\n'
            '<code>рк [команда/ID/раздел/подраздел] [ранг]</code>\n'
            '• <b>ранг</b> - число от 0 до 6 (6 - выключить)\n\n'
        )
    else:
        help_text = (
            '⚠️ <b>Использование команд включения/выключения:</b>\n\n'
            f'<code>{command_type} [команда/ID/раздел/подраздел]</code>\n\n'

        )

    await m.answer(help_text, parse_mode='HTML')


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
    # Проверяем, не пытаемся ли отключить защищенную команду
    if not is_enable and command_id == PROTECTED_COMMAND_ID:
        await m.answer('❌ Эту команду нельзя отключить!', parse_mode='HTML')
        return

    command_info = await get_command_info(command_id=command_id)
    if not command_info:
        await m.answer('❌ Команда не найдена!', parse_mode='HTML')
        return

    target_rang = command_info['AccessLevel'] if is_enable else 6
    await update_command_access(chat_id, command_id, target_rang)

    action_text = "включена" if is_enable else "выключена"
    await m.answer(f'✅ Команда «{command_info["CommandName"]}» {action_text} (ранг {target_rang})')


async def set_command_rang(m: types.Message, chat_id: int, command_id: int, rang: int):
    """Установка ранга для отдельной команды"""
    if command_id == PROTECTED_COMMAND_ID and rang == 6:
        await m.answer('❌ Эту команду нельзя отключить!', parse_mode='HTML')
        return

    command_info = await get_command_info(command_id=command_id)
    if not command_info:
        await m.answer('❌ Команда не найдена!', parse_mode='HTML')
        return

    await update_command_access(chat_id, command_id, rang)

    status_text = "выключена" if rang == 6 else f"установлен ранг {rang}"
    await m.answer(f'✅ Команда «{command_info["CommandName"]}» {status_text}')


async def enable_disable_under_section(m: types.Message, chat_id: int, under_section_id: int, is_enable: bool):
    """Включение/выключение всех команд подраздела"""
    under_section_info = await get_under_section_info(under_section_id=under_section_id)
    if not under_section_info:
        await m.answer('❌ Подраздел не найден!', parse_mode='HTML')
        return

    commands = await get_commands_by_under_section(under_section_id)
    success_message = f'Все команды подраздела «{under_section_info["UnderName"]}»'

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
    success_message = f'Все команды раздела «{section_info["SectionName"]}»'

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


async def set_under_section_rang(m: types.Message, chat_id: int, under_section_id: int, rang: int):
    """Установка ранга для всех команд подраздела"""
    under_section_info = await get_under_section_info(under_section_id=under_section_id)
    if not under_section_info:
        await m.answer('❌ Подраздел не найден!', parse_mode='HTML')
        return

    commands = await get_commands_by_under_section(under_section_id)
    success_message = f'Все команды подраздела «{under_section_info["UnderName"]}»'
    await bulk_update_commands(m, chat_id, commands, rang, success_message)


async def set_section_rang(m: types.Message, chat_id: int, section_id: int, rang: int):
    """Установка ранга для всех команд раздела"""
    section_info = await get_section_info(section_id=section_id)
    if not section_info:
        await m.answer('❌ Раздел не найден!', parse_mode='HTML')
        return

    commands = await get_commands_by_section(section_id)
    success_message = f'Все команды раздела «{section_info["SectionName"]}»'
    await bulk_update_commands(m, chat_id, commands, rang, success_message)


@UpdateCommandsSetting.message(lambda m: m.text and m.text.lower().startswith(('.рк', '!рк', '/рк', '+рк', '-рк')))
async def add_command_db_rang(m: types.Message) -> None:
    try:
        if m.chat.type == 'private':
            return
        ChatId = m.chat.id
        User_Id = m.from_user.id

        # Проверяем права доступа: босс-агенты пропускаются, остальные проходят проверку
        if User_Id not in boss_agent and not await auto_check_AccessLevel_for_rang(User_Id, ChatId, 61):
            return

        text = m.text.strip()
        # Получаем префикс команды (первое слово)
        command_parts = text.split(maxsplit=1)
        if not command_parts:
            return

        command_prefix = command_parts[0].lower()

        # Обработка команд +рк и -рк (включение/выключение)
        if command_prefix in ("+рк", "-рк"):
            if len(command_parts) < 2:
                await show_help_message(m, command_prefix)
                return

            target_value = command_parts[1].strip()
            if not target_value:
                await show_help_message(m, command_prefix)
                return

            target_type, target_id = await identify_target_type(target_value)
            if target_type == "not_found":
                await m.answer('❌ <b>Команда, раздел или подраздел не найдены!</b>\n'
                               'Используйте команды, ID или названия разделов.',
                               parse_mode='HTML')
                return

            await handle_enable_disable(m, m.chat.id, target_type, target_id, command_prefix == "+рк")

        # Обработка команд .рк, !рк, /рк (установка ранга)
        elif command_prefix in (".рк", "!рк", "/рк"):
            if len(command_parts) < 2:
                await show_help_message(m, command_prefix)
                return

            # Получаем аргументы после префикса
            args_text = command_parts[1].strip()
            if not args_text:
                await show_help_message(m, command_prefix)
                return

            # Разделяем на цель и ранг (берем последнее слово как ранг, остальное как цель)
            args_parts = args_text.rsplit(maxsplit=1)
            if len(args_parts) < 2:
                await show_help_message(m, command_prefix)
                return

            target_value = args_parts[0].strip()
            rang_str = args_parts[1].strip()

            if not rang_str.isdigit():
                await m.reply('❗ Ранг должен быть числом от 0 до 6.')
                return

            rang_int = int(rang_str)
            if rang_int not in range(0, 7):
                await m.reply('❌ <b>Такого ранга не существует.</b>\nВведите ранг от 0 до 6.', parse_mode='HTML')
                return

            # Идентификация цели
            target_type, target_id = await identify_target_type(target_value)
            if target_type == "not_found":
                await m.answer('❌ <b>Команда, раздел или подраздел не найдены!</b>\n'
                               'Используйте команды, ID или названия разделов/подразделов.',
                               parse_mode='HTML')
                return

            await set_target_rang(m, m.chat.id, target_type, target_id, rang_int)

    except Exception as e:
        logger.error(e, exc_info=True)