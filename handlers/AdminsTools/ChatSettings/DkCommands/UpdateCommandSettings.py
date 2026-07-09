import logging
from aiogram import types, Router

from BotAutomaticWork.DataBase.CreateBD.CreateCommandBase import sections, under_sections, commands
# Импортируем массивы напрямую из конфигурационного файла базы данных
from handlers.AdminsTools.ChatSettings.DkCommands.UpdateCommandSettingsDB import (
    add_dk_for_chats,
    get_command_access_level
)
from handlers.BotAutomaticWork.Gonfig.config import boss_agent
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang

logger = logging.getLogger(__name__)

DkCommandsRouter = Router()

PROTECTED_COMMAND_ID = 61
RANG_EMOJIS = {
    0: "0️⃣", 1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "⛔"
}

# ==========================================
#   МГНОВЕННАЯ СИНХРОННАЯ СБОРКА ИНДЕКСОВ
# ==========================================

SECTIONS_BY_ID = {s["SectionId"]: s for s in sections}
SECTIONS_BY_NAME = {s["SectionName"].lower(): s for s in sections}

UNDER_SECTIONS_BY_ID = {us["UnderSectionId"]: us for us in under_sections}
UNDER_SECTIONS_BY_NAME = {us["UnderName"].lower(): us for us in under_sections}
UNDER_SECTIONS_BY_COMPOSITE = {}

for us in under_sections:
    s_info = SECTIONS_BY_ID.get(us["SectionId"])
    if s_info:
        UNDER_SECTIONS_BY_COMPOSITE[(us["UnderName"].lower(), s_info["SectionName"].lower())] = us

COMMANDS_BY_ID = {}
COMMANDS_BY_NAME = {}
COMMANDS_BY_UNDER_SECTION = {us["UnderSectionId"]: [] for us in under_sections}
COMMANDS_BY_SECTION = {s["SectionId"]: [] for s in sections}
UNDER_SECTIONS_BY_SECTION = {s["SectionId"]: [] for s in sections}

for us in under_sections:
    s_id = us["SectionId"]
    if s_id in UNDER_SECTIONS_BY_SECTION:
        UNDER_SECTIONS_BY_SECTION[s_id].append(us)

for c in commands:
    cmd_name = c["names"][0] if c["names"] else "Без названия"
    c_fixed = {
        "CommandId": c["CommandId"],
        "CommandName": cmd_name,
        "AccessLevel": c["AccessLevel"],
        "UnderSectionId": c["UnderSectionId"]
    }

    COMMANDS_BY_ID[c["CommandId"]] = c_fixed
    for name in c["names"]:
        COMMANDS_BY_NAME[name.lower()] = c_fixed

    us_id = c["UnderSectionId"]
    if us_id in COMMANDS_BY_UNDER_SECTION:
        COMMANDS_BY_UNDER_SECTION[us_id].append(c_fixed)

    s_id = UNDER_SECTIONS_BY_ID.get(us_id, {}).get("SectionId")
    if s_id in COMMANDS_BY_SECTION:
        COMMANDS_BY_SECTION[s_id].append(c_fixed)


# ==========================================
#      ОБЩИЕ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

async def update_command_access(chat_id: int, command_id: int, rang: int) -> None:
    if command_id == PROTECTED_COMMAND_ID and rang == 6:
        return
    await add_dk_for_chats(chat_id, command_id, rang)


async def bulk_update_commands(m: types.Message, chat_id: int, commands_list: list, rang: int,
                               success_message: str) -> None:
    if not commands_list:
        await m.answer('❌ Нет команд для обновления.', parse_mode='HTML')
        return

    updated_count = 0
    skipped_count = 0

    for command in commands_list:
        command_id = command['CommandId']
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


async def identify_target_type(target_value: str) -> tuple[str, int]:
    target_lower = target_value.lower()

    if target_value.isdigit():
        val_int = int(target_value)
        if val_int in COMMANDS_BY_ID:
            return "command", val_int
        if val_int in SECTIONS_BY_ID:
            return "section", val_int
        if val_int in UNDER_SECTIONS_BY_ID:
            return "under_section", val_int

    if target_lower in COMMANDS_BY_NAME:
        return "command", COMMANDS_BY_NAME[target_lower]['CommandId']

    if '.' in target_value:
        section_part, under_section_part = target_value.split('.', 1)
        if section_part.isdigit() and under_section_part.isdigit():
            us_id = int(under_section_part)
            s_id = int(section_part)
            if us_id in UNDER_SECTIONS_BY_ID and UNDER_SECTIONS_BY_ID[us_id]['SectionId'] == s_id:
                return "under_section", us_id
        else:
            composite_key = (under_section_part.lower(), section_part.lower())
            if composite_key in UNDER_SECTIONS_BY_COMPOSITE:
                return "under_section", UNDER_SECTIONS_BY_COMPOSITE[composite_key]['UnderSectionId']

    if target_lower in UNDER_SECTIONS_BY_NAME:
        return "under_section", UNDER_SECTIONS_BY_NAME[target_lower]['UnderSectionId']

    if target_lower in SECTIONS_BY_NAME:
        return "section", SECTIONS_BY_NAME[target_lower]['SectionId']

    return "not_found", None


async def show_help_message(m: types.Message, command_type: str):
    help_text = f'⚠️ <b>Использование команд включения/выключения:</b>\n\n<code>{command_type} [раздел/подраздел/команда]</code>\n'
    await m.answer(help_text, parse_mode='HTML')


# ==========================================
#          ЛОГИКА ИЗМЕНЕНИЯ РАНГОВ
# ==========================================

async def handle_enable_disable(m: types.Message, chat_id: int, target_type: str, target_id: int, is_enable: bool):
    target_rang = 0 if is_enable else 6

    if target_type == "command":
        if not is_enable and target_id == PROTECTED_COMMAND_ID:
            await m.answer('❌ Эту команду нельзя отключить!', parse_mode='HTML')
            return
        command_info = COMMANDS_BY_ID.get(target_id)
        await update_command_access(chat_id, target_id, target_rang)
        action_text = "включена" if is_enable else "выключена"
        await m.answer(f'✅ Команда «{command_info["CommandName"]}» {action_text} (установлен ранг {target_rang})')

    elif target_type == "under_section":
        under_section_info = UNDER_SECTIONS_BY_ID.get(target_id)
        commands_list = COMMANDS_BY_UNDER_SECTION.get(target_id, [])
        await bulk_update_commands(m, chat_id, commands_list, target_rang,
                                   f'Все команды подраздела «{under_section_info["UnderName"]}»')

    elif target_type == "section":
        section_info = SECTIONS_BY_ID.get(target_id)
        commands_list = COMMANDS_BY_SECTION.get(target_id, [])
        await bulk_update_commands(m, chat_id, commands_list, target_rang,
                                   f'Все команды раздела «{section_info["SectionName"]}»')


async def set_target_rang(m: types.Message, chat_id: int, target_type: str, target_id: int, rang: int):
    if target_type == "command":
        if target_id == PROTECTED_COMMAND_ID and rang == 6:
            await m.answer('❌ Эту команду нельзя отключить!', parse_mode='HTML')
            return
        command_info = COMMANDS_BY_ID.get(target_id)
        await update_command_access(chat_id, target_id, rang)
        status_text = "выключена" if rang == 6 else f"установлен ранг {rang}"
        await m.answer(f'✅ Команда «{command_info["CommandName"]}» {status_text}')

    elif target_type == "under_section":
        under_section_info = UNDER_SECTIONS_BY_ID.get(target_id)
        commands_list = COMMANDS_BY_UNDER_SECTION.get(target_id, [])
        await bulk_update_commands(m, chat_id, commands_list, rang,
                                   f'Все команды подраздела «{under_section_info["UnderName"]}»')

    elif target_type == "section":
        section_info = SECTIONS_BY_ID.get(target_id)
        commands_list = COMMANDS_BY_SECTION.get(target_id, [])
        await bulk_update_commands(m, chat_id, commands_list, rang,
                                   f'Все команды раздела «{section_info["SectionName"]}»')


# ==========================================
#          ЛОГИКА ПРОСМОТРА СТРУКТУРЫ
# ==========================================

async def show_all_sections(m: types.Message):
    sections_text = "▶️ Доступы команд:\n"
    for section in sections:
        sections_text += f"{section['SectionId']}. {section['SectionName']}\n"
    await m.answer(sections_text, parse_mode='HTML')


async def show_command_by_id(m: types.Message, command_id: int, chat_id: int):
    command_info = COMMANDS_BY_ID.get(command_id)
    access_level = await get_command_access_level(chat_id, command_info['CommandId'])
    under_section_info = UNDER_SECTIONS_BY_ID.get(command_info['UnderSectionId'])
    rang_emoji = RANG_EMOJIS.get(access_level, '❓')

    command_text = (
        f'<b>🔽 Раздел {under_section_info["UnderName"]}:</b>\n\n'
        f'{rang_emoji} {command_info["CommandId"]}. {command_info["CommandName"]} (ранг {access_level})'
    )
    await m.answer(command_text, parse_mode='HTML')


async def identify_and_show_target(m: types.Message, target: str):
    chat_id = m.chat.id
    target_lower = target.lower()

    if target_lower in COMMANDS_BY_NAME:
        await show_command_by_id(m, COMMANDS_BY_NAME[target_lower]['CommandId'], chat_id)
        return

    if target.isdigit():
        target_id = int(target)
        if target_id in COMMANDS_BY_ID:
            await show_command_by_id(m, target_id, chat_id)
            return
        if target_id in SECTIONS_BY_ID:
            await show_under_sections(m, SECTIONS_BY_ID[target_id])
            return
        if target_id in UNDER_SECTIONS_BY_ID:
            await show_commands_in_under_section(m, UNDER_SECTIONS_BY_ID[target_id], chat_id)
            return

    if '.' in target:
        section_part, under_section_part = target.split('.', 1)
        if section_part.isdigit() and under_section_part.isdigit():
            us_id = int(under_section_part)
            s_id = int(section_part)
            if us_id in UNDER_SECTIONS_BY_ID and UNDER_SECTIONS_BY_ID[us_id]['SectionId'] == s_id:
                await show_commands_in_under_section(m, UNDER_SECTIONS_BY_ID[us_id], chat_id)
                return
        else:
            composite_key = (under_section_part.lower(), section_part.lower())
            if composite_key in UNDER_SECTIONS_BY_COMPOSITE:
                await show_commands_in_under_section(m, UNDER_SECTIONS_BY_COMPOSITE[composite_key], chat_id)
                return

    if target_lower in SECTIONS_BY_NAME:
        await show_under_sections(m, SECTIONS_BY_NAME[target_lower])
        return

    if target_lower in UNDER_SECTIONS_BY_NAME:
        await show_commands_in_under_section(m, UNDER_SECTIONS_BY_NAME[target_lower], chat_id)
        return

    await m.answer('❌ Команда, раздел или подраздел не найден!', parse_mode='HTML')


async def show_under_sections(m: types.Message, section_info: dict):
    under_sections_list = UNDER_SECTIONS_BY_SECTION.get(section_info['SectionId'], [])
    if not under_sections_list:
        await m.answer(f'{section_info["SectionName"]}\n\n❌ В разделе нет подразделов', parse_mode='HTML')
        return
    under_sections_text = f'🔽 Раздел {section_info["SectionName"]}\n\n'
    for under_section in under_sections_list:
        under_sections_text += f"{under_section['UnderSectionId']}. {under_section['UnderName']}\n"
    await m.answer(under_sections_text, parse_mode='HTML')


async def show_commands_in_under_section(m: types.Message, under_section_info: dict, chat_id: int):
    commands_list = COMMANDS_BY_UNDER_SECTION.get(under_section_info['UnderSectionId'], [])
    if not commands_list:
        await m.answer(f'🔽 Раздел {under_section_info["UnderName"]}\n\n❌ <b>В подразделе нет команд</b>',
                       parse_mode='HTML')
        return
    commands_text = f'🔽 <b>Раздел</b> {under_section_info["UnderName"]}\n\n'
    for command in commands_list:
        access_level = await get_command_access_level(chat_id, command['CommandId'])
        rang_emoji = RANG_EMOJIS.get(access_level, '❓')
        commands_text += f"{rang_emoji} {command['CommandId']}. <code>{command['CommandName']}</code>\n"
    await m.answer(commands_text, parse_mode='HTML')


# ==========================================
#             АНКЕРНЫЕ ХЭНДЛЕРЫ
# ==========================================

@DkCommandsRouter.message(lambda m: m.text and m.text.lower().startswith(('.рк', '!рк', '/рк', '+рк', '-рк', 'рк')))
async def handle_rk_modification(m: types.Message) -> None:
    try:
        if m.chat.type == 'private':
            return

        ChatId = m.chat.id
        User_Id = m.from_user.id

        text = m.text.strip()
        command_parts = text.split(maxsplit=1)
        if not command_parts:
            return

        command_prefix = command_parts[0].lower()

        # -------------------------------------------------------------
        # СИТУАЦИЯ 1: Быстрое включение/выключение (+рк / -рк)
        # Это всегда МОДИФИКАЦИЯ -> Проверяем команду 61
        # -------------------------------------------------------------
        if command_prefix in ("+рк", "-рк"):
            if User_Id not in boss_agent and not await auto_check_AccessLevel_for_rang(User_Id, ChatId, 61):
                return

            if len(command_parts) < 2 or not command_parts[1].strip():
                await show_help_message(m, command_prefix)
                return

            target_value = command_parts[1].strip()
            target_type, target_id = await identify_target_type(target_value)
            if target_type == "not_found":
                await m.answer('❌ <b>Команда, раздел или подраздел не найдены!</b>', parse_mode='HTML')
                return

            await handle_enable_disable(m, ChatId, target_type, target_id, command_prefix == "+рк")

        # -------------------------------------------------------------
        # СИТУАЦИЯ 2: Работа с префиксами рк / .рк / !рк / /рк
        # Здесь логика может разветвляться на просмотр (62) и изменение (61)
        # -------------------------------------------------------------
        elif command_prefix in (".рк", "!рк", "/рк", "рк"):

            # Вариант А: Юзер написал просто "рк" (без аргументов)
            # Это чистый ПРОСМОТР разделов -> Проверяем команду 62
            if len(command_parts) < 2 or not command_parts[1].strip():
                if User_Id not in boss_agent and not await auto_check_AccessLevel_for_rang(User_Id, ChatId, 62):
                    return
                await show_all_sections(m)
                return

            args_text = command_parts[1].strip()
            args_parts = args_text.rsplit(maxsplit=1)

            is_rank_provided = False
            if len(args_parts) == 2:
                potential_rang = args_parts[1].strip()
                if potential_rang.isdigit() and int(potential_rang) in range(0, 7):
                    is_rank_provided = True

            # Вариант Б: Юзер передал в конце валидный ранг (например, "рк Мут 3")
            # Это МОДИФИКАЦИЯ ранга -> Проверяем команду 61
            if is_rank_provided:
                if User_Id not in boss_agent and not await auto_check_AccessLevel_for_rang(User_Id, ChatId, 61):
                    return

                target_value = args_parts[0].strip()
                rang_int = int(args_parts[1].strip())

                target_type, target_id = await identify_target_type(target_value)
                if target_type == "not_found":
                    await m.answer('❌ <b>Команда, раздел или подраздел не найдены!</b>', parse_mode='HTML')
                    return

                await set_target_rang(m, ChatId, target_type, target_id, rang_int)

            # Вариант В: Юзер написал "рк Мудерация" или "рк 15" (без ранга в конце)
            # Это карточка ПРОСМОТРА конкретной цели -> Проверяем команду 62
            else:
                if User_Id not in boss_agent and not await auto_check_AccessLevel_for_rang(User_Id, ChatId, 62):
                    return
                await identify_and_show_target(m, args_text)

    except Exception as e:
        logger.error(e, exc_info=True)


@DkCommandsRouter.message(lambda m: m.text and m.text.lower().startswith(('!чек рк', '.чек рк', '/чек рк', 'чек рк')))
async def check_commands_handler(m: types.Message):
    try:
        if m.chat.type == 'private':
            return

        ChatId = m.chat.id
        User_Id = m.from_user.id

        # Чекер структуры — это всегда ПРОСМОТР -> Проверяем команду 62
        if User_Id not in boss_agent and not await auto_check_AccessLevel_for_rang(User_Id, ChatId, 62):
            return

        parts = m.text.split(maxsplit=2)
        if len(parts) == 2:
            await show_all_sections(m)
            return

        target = parts[2].strip()
        await identify_and_show_target(m, target)

    except Exception as e:
        logger.error(e, exc_info=True)
        await m.answer('❌ <b>Произошла ошибка при выполнении команды.</b>', parse_mode='HTML')