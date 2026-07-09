from aiogram.types import Message
import logging
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)

# --- Списки перенесены на уровень модуля для глобального доступа ---

sections = [
    {"SectionId": 1, "SectionName": "Модерация чата"},
    {"SectionId": 2, "SectionName": "Настройки чата"},
    {"SectionId": 3, "SectionName": "Информация"},
    {"SectionId": 4, "SectionName": "Команды участников"},
]

under_sections = [
    {"UnderSectionId": 5, "UnderName": "Управление блокировками", "SectionId": 1},
    {"UnderSectionId": 6, "UnderName": "Управление ограничениями", "SectionId": 1},
    {"UnderSectionId": 7, "UnderName": "Система репортов", "SectionId": 1},
    {"UnderSectionId": 8, "UnderName": "Система предупреждений", "SectionId": 1},

    {"UnderSectionId": 9, "UnderName": "Управление правилами", "SectionId": 2},
    {"UnderSectionId": 10, "UnderName": "Управление приветствия", "SectionId": 2},
    {"UnderSectionId": 11, "UnderName": "Управление видом чата", "SectionId": 2},
    {"UnderSectionId": 12, "UnderName": "Управление рангом команд", "SectionId": 2},
    {"UnderSectionId": 13, "UnderName": "Управление администраторами", "SectionId": 2},
    {"UnderSectionId": 14, "UnderName": "Система заметок", "SectionId": 2},
    {"UnderSectionId": 15, "UnderName": "Управление пинами", "SectionId": 2},
    {"UnderSectionId": 16, "UnderName": "Управление уведомлениями", "SectionId": 2},
    {"UnderSectionId": 17, "UnderName": "Система доступа команд", "SectionId": 2},
    {"UnderSectionId": 18, "UnderName": "Система защиты", "SectionId": 2},
    {"UnderSectionId": 73, "UnderName": "Модуль первого комментария", "SectionId": 2},
    {"UnderSectionId": 78, "UnderName": "Распознание голосовых сообщений", "SectionId": 2},

    {"UnderSectionId": 19, "UnderName": "Информация о участниках", "SectionId": 3},
    {"UnderSectionId": 20, "UnderName": "Профиль участников", "SectionId": 4},
    {"UnderSectionId": 70, "UnderName": "Ролевые команды", "SectionId": 4},
    {"UnderSectionId": 76, "UnderName": "Помощь", "SectionId": 4},
    {"UnderSectionId": 81, "UnderName": "Команды для участников", "SectionId": 4},
    {"UnderSectionId": 83, "UnderName": "Экономика и сапфиры", "SectionId": 4},
    {"UnderSectionId": 90, "UnderName": "Система браков", "SectionId": 4},
]

commands = [
    {"names": ["Управление чёрным списком"], "CommandId": 21, "AccessLevel": 1, "UnderSectionId": 5},
    {"names": ["Список активных банов"], "CommandId": 22, "AccessLevel": 1, "UnderSectionId": 5},
    {"names": ["Информация о блокировке"], "CommandId": 23, "AccessLevel": 1, "UnderSectionId": 5},
    {"names": ["Настройка длительности бана по умолчанию"], "CommandId": 24, "AccessLevel": 4, "UnderSectionId": 5},

    {"names": ["Ограничения пользователя"], "CommandId": 25, "AccessLevel": 1, "UnderSectionId": 6},
    {"names": ["Список активных мутов"], "CommandId": 26, "AccessLevel": 1, "UnderSectionId": 6},
    {"names": ["Информация о муте"], "CommandId": 27, "AccessLevel": 1, "UnderSectionId": 6},
    {"names": ["Настройка длительности мута по умолчанию"], "CommandId": 28, "AccessLevel": 4, "UnderSectionId": 6},

    {"names": ["Управление варнами"], "CommandId": 29, "AccessLevel": 1, "UnderSectionId": 8},
    {"names": ["Список активных варнов"], "CommandId": 30, "AccessLevel": 1, "UnderSectionId": 8},
    {"names": ["Список активных варнов пользователя"], "CommandId": 60, "AccessLevel": 0, "UnderSectionId": 8},
    {"names": ["Настройка длительности варна по умолчанию"], "CommandId": 31, "AccessLevel": 4, "UnderSectionId": 8},
    {"names": ["Настройка лимита варнов"], "CommandId": 32, "AccessLevel": 4, "UnderSectionId": 8},
    {"names": ["Настройка автонаказания"], "CommandId": 33, "AccessLevel": 4, "UnderSectionId": 8},

    {"names": ["Отправка жалоб"], "CommandId": 34, "AccessLevel": 0, "UnderSectionId": 7},
    {"names": ["Список необработанных жалоб"], "CommandId": 35, "AccessLevel": 1, "UnderSectionId": 7},
    {"names": ["Статистика по жалобам"], "CommandId": 36, "AccessLevel": 1, "UnderSectionId": 7},
    {"names": ["Настройка чат-репортов"], "CommandId": 37, "AccessLevel": 4, "UnderSectionId": 7},
    {"names": ["Список привязанных чатов"], "CommandId": 38, "AccessLevel": 1, "UnderSectionId": 7},

    {"names": ["Настройка информации о чате"], "CommandId": 39, "AccessLevel": 4, "UnderSectionId": 11},
    {"names": ["Просмотр запланированных изменений"], "CommandId": 40, "AccessLevel": 2, "UnderSectionId": 11},

    {"names": ["Управление администраторами"], "CommandId": 41, "AccessLevel": 4, "UnderSectionId": 13},
    {"names": ["Просмотр историй администраторов"], "CommandId": 42, "AccessLevel": 4, "UnderSectionId": 13},
    {"names": ["Восстановление прав владельца"], "CommandId": 43, "AccessLevel": 4, "UnderSectionId": 13},
    {"names": ["Список администраторов"], "CommandId": 64, "AccessLevel": 0, "UnderSectionId": 13},

    {"names": ["Настройка капчи"], "CommandId": 44, "AccessLevel": 4, "UnderSectionId": 18},
    {"names": ["Просмотр истории о капче"], "CommandId": 45, "AccessLevel": 1, "UnderSectionId": 18},
    {"names": ["Настройка антиспама"], "CommandId": 46, "AccessLevel": 4, "UnderSectionId": 18},

    {"names": ["Настройка запрещённых ссылок"], "CommandId": 65, "AccessLevel": 3, "UnderSectionId": 18},
    {"names": ["Просмотр настроек запрещённых ссылок"], "CommandId": 66, "AccessLevel": 1, "UnderSectionId": 18},
    {"names": ["Проверка ссылок"], "CommandId": 67, "AccessLevel": 0, "UnderSectionId": 18},

    {"names": ["Настройка правил"], "CommandId": 47, "AccessLevel": 3, "UnderSectionId": 9},
    {"names": ["Просмотр правил"], "CommandId": 48, "AccessLevel": 0, "UnderSectionId": 9},
    {"names": ["Настройка приветствия"], "CommandId": 49, "AccessLevel": 4, "UnderSectionId": 10},
    {"names": ["Просмотр приветствия"], "CommandId": 50, "AccessLevel": 1, "UnderSectionId": 10},

    {"names": ["Настройка заметок"], "CommandId": 51, "AccessLevel": 4, "UnderSectionId": 14},
    {"names": ["Просмотр заметок"], "CommandId": 52, "AccessLevel": 0, "UnderSectionId": 14},

    {"names": ["Настройка первого комментария"], "CommandId": 74, "AccessLevel": 2, "UnderSectionId": 73},
    {"names": ["Просмотр первого комментария"], "CommandId": 75, "AccessLevel": 4, "UnderSectionId": 73},

    {"names": ["Управление закрепами"], "CommandId": 53, "AccessLevel": 3, "UnderSectionId": 15},
    {"names": ["Список закрепов"], "CommandId": 63, "AccessLevel": 3, "UnderSectionId": 15},

    {"names": ["Настройка уведомлений о входах и выходах"], "CommandId": 54, "AccessLevel": 3, "UnderSectionId": 16},
    {"names": ["Уведомления о доступах команд"], "CommandId": 55, "AccessLevel": 3, "UnderSectionId": 16},

    {"names": ["Настройка доступа команд"], "CommandId": 61, "AccessLevel": 4, "UnderSectionId": 17},
    {"names": ["Просмотр доступа команд"], "CommandId": 62, "AccessLevel": 0, "UnderSectionId": 17},

    {"names": ["Просмотр статистики сообщений"], "CommandId": 56, "AccessLevel": 0, "UnderSectionId": 19},
    {"names": ["Просмотр статистики входов и выходах"], "CommandId": 57, "AccessLevel": 3, "UnderSectionId": 19},

    {"names": ["Просмотр профиля пользователя"], "CommandId": 58, "AccessLevel": 0, "UnderSectionId": 20},
    {"names": ["Настройка профиля пользователя"], "CommandId": 68, "AccessLevel": 0, "UnderSectionId": 20},
    {"names": ["Список ников"], "CommandId": 69, "AccessLevel": 0, "UnderSectionId": 20},
    {"names": ["Погода"], "CommandId": 59, "AccessLevel": 0, "UnderSectionId": 20},
    {"names": ["Ролевые команды"], "CommandId": 71, "AccessLevel": 0, "UnderSectionId": 70},
    {"names": ["Настройка ролевых команд"], "CommandId": 72, "AccessLevel": 3, "UnderSectionId": 70},
    {"names": ["Список команд бота"], "CommandId": 77, "AccessLevel": 0, "UnderSectionId": 76},
    {"names": ["Настройка распознания голосовых сообщений (автоматическое распознавание)"], "CommandId": 79,
     "AccessLevel": 3, "UnderSectionId": 78},
    {"names": ["Распознания голосовых сообщений (через команду)"], "CommandId": 80, "AccessLevel": 0,
     "UnderSectionId": 78},
    {"names": ["Просмотр связки чатов"], "CommandId": 82, "AccessLevel": 0, "UnderSectionId": 81},

    # --- Экономика и мешки (UnderSectionId: 83) ---
    {"names": ["Покупка сапфиров"], "CommandId": 84, "AccessLevel": 0, "UnderSectionId": 83},
    {"names": ["Просмотр баланса мешка"], "CommandId": 85, "AccessLevel": 0, "UnderSectionId": 83},
    {"names": ["Настройка приватности мешка"], "CommandId": 86, "AccessLevel": 0, "UnderSectionId": 83},
    {"names": ["Перевод сапфиров"], "CommandId": 87, "AccessLevel": 0, "UnderSectionId": 83},

    # --- Модуль онлайна и приватности ---
    {"names": ["Просмотр онлайна участников"], "CommandId": 88, "AccessLevel": 0, "UnderSectionId": 19},
    {"names": ["Настройка приватности онлайна"], "CommandId": 89, "AccessLevel": 0, "UnderSectionId": 20},

    {"names": ["Список браков"], "CommandId": 91, "AccessLevel": 0, "UnderSectionId": 90},
    {"names": ["Статус брака"], "CommandId": 92, "AccessLevel": 0, "UnderSectionId": 90},
    {"names": ["Действия брака"], "CommandId": 93, "AccessLevel": 0, "UnderSectionId": 90},
    {"names": ["История брака"], "CommandId": 94, "AccessLevel": 0, "UnderSectionId": 90},
    {"names": ["Брак и развод"], "CommandId": 95, "AccessLevel": 0, "UnderSectionId": 90},
    {"names": ["Принудительный брак и развод"], "CommandId": 96, "AccessLevel": 3, "UnderSectionId": 90},

    {"names": ["Важная информация"], "CommandId": 97, "AccessLevel": 0, "UnderSectionId": 76},

    {"names": ["Миграция бесед"], "CommandId": 98, "AccessLevel": 5, "UnderSectionId": 11},
    {"names": ["Управление тг-правами"], "CommandId": 99, "AccessLevel": 3, "UnderSectionId": 6},

    {"names": ["Миграция бесед"], "CommandId": 98, "AccessLevel": 5, "UnderSectionId": 11},
    {"names": ["Управление тг-правами"], "CommandId": 99, "AccessLevel": 3, "UnderSectionId": 6},\
    {"names": ["Удаление сообщений"], "CommandId": 100, "AccessLevel": 3, "UnderSectionId": 6},
]

# 100

async def delete_table(table_name: str):
    pool = get_db_pool()
    """Удалить таблицу (только для разработки!)."""
    if not table_name.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Некорректное имя таблицы")

    async with pool.acquire() as conn:
        try:
            await conn.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')
            logger.info(f"Таблица {table_name} удалена")
        except Exception as e:
            logger.error(f"Ошибка удаления таблицы {table_name}: {e}", exc_info=True)
            raise


async def update_table_structure():
    pool = get_db_pool()
    """Добавить недостающие колонки, если их нет."""
    async with pool.acquire() as conn:
        try:
            exists = await conn.fetchval(
                "ALTER TABLE punishment_time ALTER COLUMN time_end TYPE TIMESTAMPTZ USING time_end::TIMESTAMPTZ;"
            )
            if not exists:
                print('кек лол кукукдууу')
        except Exception as e:
            logger.error(f"Ошибка обновления структуры: {e}", exc_info=True)
            raise

    async with pool.acquire() as conn:
        try:
            exists = await conn.fetchval(
                "ALTER TABLE warns ALTER COLUMN expires_at TYPE TIMESTAMPTZ USING expires_at::TIMESTAMPTZ;"
            )
            if not exists:
                print('кек лол кукукдууу')
        except Exception as e:
            logger.error(f"Ошибка обновления структуры: {e}", exc_info=True)
            raise

    async with pool.acquire() as conn:
        try:
            exists = await conn.fetchval(
                "ALTER TABLE pinned_messages ALTER COLUMN unpin_time TYPE TIMESTAMPTZ USING unpin_time::TIMESTAMPTZ;"
            )
            if not exists:
                print('кек лол кукукдууу')
        except Exception as e:
            logger.error(f"Ошибка обновления структуры: {e}", exc_info=True)
            raise


async def init_commands_structure():
    pool = get_db_pool()
    """Инициализировать структуру команд, секций и подсекций."""

    # Последнее: 96
    async with pool.acquire() as conn:
        async with conn.transaction():  # Добавляем транзакцию
            try:
                # Очищаем таблицы в правильном порядке с CASCADE
                await conn.execute('DELETE FROM commands CASCADE')
                await conn.execute('DELETE FROM under_sections CASCADE')
                await conn.execute('DELETE FROM sections CASCADE')
                logger.info("Таблицы очищены")

                # Вставляем секции с пакетной вставкой
                if sections:
                    await conn.executemany(
                        """INSERT INTO sections (SectionId, SectionName) 
                           VALUES ($1, $2) ON CONFLICT DO NOTHING""",
                        [(sec["SectionId"], sec["SectionName"]) for sec in sections]
                    )

                # Подсекции с пакетной вставкой
                if under_sections:
                    await conn.executemany(
                        """INSERT INTO under_sections (UnderSectionId, UnderName, SectionId)
                           VALUES ($1, $2, $3) ON CONFLICT DO NOTHING""",
                        [(us["UnderSectionId"], us["UnderName"], us["SectionId"])
                         for us in under_sections]
                    )

                # Команды - предварительно собираем все UnderSectionId
                if commands:
                    # Получаем все существующие подсекции одним запросом
                    existing_sections = await conn.fetch(
                        "SELECT UnderSectionId FROM under_sections"
                    )
                    existing_ids = {row['undersectionid'] for row in existing_sections}

                    # Подготавливаем данные для вставки
                    commands_to_insert = []
                    for cmd_group in commands:
                        under_section_id = cmd_group["UnderSectionId"]

                        if under_section_id not in existing_ids:
                            logger.warning(
                                f"⚠️ Подсекция с ID={under_section_id} не найдена, "
                                f"пропускаем команды: {cmd_group.get('names', [])}"
                            )
                            continue

                        for name in cmd_group["names"]:
                            commands_to_insert.append((
                                name,
                                cmd_group["CommandId"],
                                cmd_group["AccessLevel"],
                                under_section_id
                            ))

                    # Пакетная вставка команд
                    if commands_to_insert:
                        await conn.executemany(
                            """INSERT INTO commands (CommandName, CommandId, AccessLevel, UnderSectionId)
                               VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING""",
                            commands_to_insert
                        )

                logger.info("✅ Структура команд инициализирована")
                return 'ok'

            except Exception as e:
                logger.error(f"❌ Ошибка инициализации команд: {e}", exc_info=True)
                await Message.answer(chat_id='-1002315959104', text=f'{e}')
                # При ошибке транзакция автоматически откатится
                return 'error'