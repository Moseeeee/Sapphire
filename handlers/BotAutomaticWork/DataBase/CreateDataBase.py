import logging

from aiogram.types import Message

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


async def create_db():
    """Создать все таблицы в базе данных — каждую в отдельном соединении."""
    try:
        pool = get_db_pool()
        # ========== АГЕНТЫ ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id BIGINT,
                    agent_appointed_id BIGINT,
                    date_appointed TEXT
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS acting_agents (
                    acting_agent_id BIGINT PRIMARY KEY,
                    agent_status INTEGER
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS agents_history (
                    remove_agent_id BIGINT,
                    agent_appointed_id BIGINT,
                    date_appointed TEXT,
                    old_status INTEGER,
                    new_status INTEGER
                );
            ''')

        # ========== ЧАТЫ ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id BIGINT UNIQUE,
                    chat_title TEXT,
                    chat_username TEXT,
                    status_v TEXT DEFAULT 'no',
                    status_e TEXT DEFAULT 'no',
                    push_status TEXT DEFAULT 'on',
                    antispam TEXT DEFAULT 'on',
                    bot_chat_status TEXT,
                    chat_ignore_status TEXT,
                    number_for_inputs INTEGER,
                    owner_id BIGINT,
                    invite_link TEXT,
                    invite_link_updated_at TEXT,
                    first_seen TEXT,
                    last_update TEXT,
                    min_rp_rating INTEGER DEFAULT 0
                );
            ''')


        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS await_checks_approvals (
                chat_id BIGINT,
                type TEXT,
                text TEXT,
                message_id BIGINT,
                admin_message_id BIGINT,
                user_id BIGINT,
                PRIMARY KEY (chat_id, type)
                );
            ''')

        #============= ЗАМЕТКИ ===========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS notes (
                    notes_id INTEGER,
                    chat_id BIGINT NOT NULL,
                    notes_name TEXT NOT NULL,
                    notes_text TEXT NOT NULL,
                    PRIMARY KEY (chat_id, notes_id)
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS await_checks_approvals_notes (
                chat_id BIGINT,
                notes_name TEXT,
                notes_text TEXT,
                message_id BIGINT,
                admin_message_id BIGINT,
                user_id BIGINT,
                is_edit BOOLEAN DEFAULT False,
                PRIMARY KEY (chat_id, notes_name)
                );
            ''')

        # ========== РЕПОРТЫ ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    report_id BIGINT,
                    reported_id BIGINT,
                    reply_message_id BIGINT,
                    message_id BIGINT,
                    reported_chat BIGINT
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS chat_reports (
                    report_chat BIGINT,
                    reported_chat BIGINT
                );
            ''')

        # ========== ПОЛЬЗОВАТЕЛИ ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    name TEXT,
                    username TEXT,
                    gender TEXT DEFAULT 'не указан',
                    first_seen TEXT,
                    last_activity TEXT,
                    last_update TEXT 
                );
            ''')


            async with pool.acquire() as conn:
                # Создаем таблицу sapphire_bag с полем is_hidden
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS sapphire_bag (
                        user_id BIGINT PRIMARY KEY,
                        balance INTEGER NOT NULL DEFAULT 0,
                        last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_hidden BOOLEAN DEFAULT FALSE
                    );
                ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS sapphire_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                agent_id BIGINT NOT NULL,
                operation_type VARCHAR(30) NOT NULL,
                amount INTEGER NOT NULL,
                balance_before INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                comment TEXT
                );
            ''')



        # ========== ИСТОРИЯ УЧАСТИЯ В ЧАТАХ ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS full_users_chats (
                    chat_id BIGINT,
                    user_id BIGINT,
                    join_time TEXT,
                    leave_time TEXT,
                    member_status TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, user_id)
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users_chats (
                    chat_id BIGINT,
                    user_id BIGINT,
                    pseudonym TEXT,
                    PRIMARY KEY (chat_id, user_id)
                );
            ''')

        # ========== СТАТИСТИКА МОДЕРАЦИИ ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS moderation_stats (
                    user_id BIGINT NOT NULL,
                    chat_id BIGINT NOT NULL,
                    day_count INTEGER DEFAULT 0,
                    week_count INTEGER DEFAULT 0,
                    month_count INTEGER DEFAULT 0,
                    year_count INTEGER DEFAULT 0,
                    total_count INTEGER DEFAULT 0,
                    last_update TEXT NOT NULL,
                    PRIMARY KEY (user_id, chat_id)
                );
            ''')

        # ========== СТАТИСТИКА СООБЩЕНИЙ ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS message_stats (
                    chat_id BIGINT,
                    user_id BIGINT,
                    total INTEGER DEFAULT 0,
                    daily INTEGER DEFAULT 0,
                    weekly INTEGER DEFAULT 0,
                    monthly INTEGER DEFAULT 0,
                    yearly INTEGER DEFAULT 0,
                    last_daily_reset TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    last_weekly_reset TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    last_monthly_reset TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    last_yearly_reset TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, user_id)
                );
            ''')

        # ========== ПРАВИЛА И ПРИВЕТСТВИЕ ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS rules (
                    chat_id BIGINT PRIMARY KEY,
                    rules_text TEXT
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS welcome (
                    chat_id BIGINT PRIMARY KEY,
                    welcome_text TEXT
                );
            ''')

        # ========== БАНЫ И МУТЫ ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS bans (
                    chat_id BIGINT,
                    user_id BIGINT,
                    admin_id BIGINT,
                    reason TEXT,
                    duration TEXT,
                    PRIMARY KEY (chat_id, user_id)
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS mutes (
                    chat_id BIGINT,
                    user_id BIGINT,
                    admin_id BIGINT,
                    reason TEXT,
                    duration TEXT,
                    PRIMARY KEY (chat_id, user_id)
                );
            ''')

        # ========== ПРЕДУПРЕЖДЕНИЯ (ВАРНЫ) ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS warns (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    admin_id BIGINT NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMP WITH TIME ZONE,
                    expires_at TIMESTAMP WITH TIME ZONE
                );
            ''')


        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS warn_settings (
                    chat_id BIGINT PRIMARY KEY,
                    action TEXT NOT NULL DEFAULT 'ban',
                    warn_limit INTEGER NOT NULL DEFAULT 3
                );
            ''')

        # ========== КАПЧА ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS captcha_settings (
                    chat_id BIGINT PRIMARY KEY,
                    time_limit TEXT DEFAULT '5 минут',
                    difficulty TEXT DEFAULT 'средняя',
                    attempts_limit INTEGER DEFAULT 3,
                    enabled BOOLEAN DEFAULT FALSE
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS captcha_history (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT,
                    user_id BIGINT,
                    captcha_type TEXT,
                    difficulty TEXT,
                    success BOOLEAN,
                    time_taken INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')

        # ========== ВРЕМЕННЫЕ НАСТРОЙКИ ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS default_time (
                    chat_id BIGINT,
                    type TEXT,
                    time TEXT,
                    UNIQUE(chat_id, type)
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS punishment_time (
                    chat_id BIGINT,
                    user_id BIGINT,
                    types TEXT,
                    time_end TEXT,
                    UNIQUE(chat_id, user_id, types)
                );
            ''')

        # ========== АДМИНИСТРАТОРЫ ЧАТОВ ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS chat_admins (
                    UserId BIGINT,
                    ChatId BIGINT,
                    ManagementAdminId BIGINT,
                    ManagementRang INTEGER,
                    time TEXT,
                    PRIMARY KEY (UserId, ChatId)
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users_rangs (
                    UserId BIGINT,
                    ChatId BIGINT,
                    rang INTEGER DEFAULT 0,
                    PRIMARY KEY (UserId, ChatId)
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS history_chat_admins (
                    UserId BIGINT,
                    ChatId BIGINT,
                    rang INTEGER,
                    OldRang INTEGER,
                    ManagementAdminId BIGINT,
                    ManagementRang INTEGER,
                    time TEXT
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS anti_spam_users (
                user_id BIGINT PRIMARY KEY,
                agent_id BIGINT,
                date_added TEXT,
                reason TEXT
            );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS pinned_messages (
                chat_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                unpin_time TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (chat_id, message_id)
);
            ''')


        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS ignore_users (
                user_id BIGINT PRIMARY KEY,
                agent_id BIGINT NOT NULL,
                date_added TEXT NOT NULL,
                reason TEXT NOT NULL
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS ignore_history (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    agent_id_added BIGINT NOT NULL,
    agent_id_removed BIGINT,
    date_added TEXT NOT NULL,
    date_removed TEXT,
    reason TEXT NOT NULL
);
            ''')




        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS anti_spam_history (
                user_id BIGINT,
                agent_id_added BIGINT,
                agent_id_removed BIGINT,
                date_added TEXT,
                date_removed TEXT,
                reason TEXT
            );
            ''')

        # =========== ССЫЛКИ И НАСТРОЙКА ИХ ==========
            async with pool.acquire() as conn:
                await conn.execute('''
                            CREATE TABLE IF NOT EXISTS link_filter_settings (
                                chat_id BIGINT PRIMARY KEY,
                                filter_websites BOOLEAN DEFAULT FALSE,
                                filter_chats BOOLEAN DEFAULT FALSE,
                                filter_referrals BOOLEAN DEFAULT FALSE,
                                filter_all BOOLEAN DEFAULT FALSE,
                                action TEXT DEFAULT 'warn',
                                created_at TIMESTAMP DEFAULT NOW(),
                                updated_at TIMESTAMP DEFAULT NOW()
                            )
                        ''')

            # Таблица вайт-листа
            async with pool.acquire() as conn:
                await conn.execute('''
                            CREATE TABLE IF NOT EXISTS link_filter_whitelist (
                                id SERIAL PRIMARY KEY,
                                chat_id BIGINT NOT NULL,
                                link_pattern TEXT NOT NULL,
                                is_regex BOOLEAN DEFAULT FALSE,
                                added_by BIGINT,
                                created_at TIMESTAMP DEFAULT NOW(),
                                UNIQUE(chat_id, link_pattern)
                            )
                        ''')

                # Индексы для оптимизации
                #await conn.execute('CREATE INDEX IF NOT EXISTS idx_whitelist_chat ON link_filter_whitelist(chat_id)')



        async with pool.acquire() as conn:
            # Основная таблица для первого комментария
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS first_comments (
                    channel_id BIGINT PRIMARY KEY,
                    comment_text TEXT NOT NULL
                )
            ''')

            # Таблица для кнопок (максимум 5 на канал)
            async with pool.acquire() as conn:
                await conn.execute('''
                CREATE TABLE IF NOT EXISTS first_comment_buttons (
                    channel_id BIGINT NOT NULL,
                    button_index INTEGER NOT NULL, -- 0-4
                    button_text VARCHAR(50) NOT NULL,
                    button_url VARCHAR(500) NOT NULL,
                    PRIMARY KEY (channel_id, button_index),
                    FOREIGN KEY (channel_id) REFERENCES first_comments(channel_id) ON DELETE CASCADE
                )
            ''')

            # Таблица для модерации первого комментария
            async with pool.acquire() as conn:
                await conn.execute('''
                CREATE TABLE IF NOT EXISTS first_comment_moderation (
                    channel_id BIGINT PRIMARY KEY,
                    comment_text TEXT NOT NULL,
                    user_message_id INTEGER NOT NULL,
                    admin_message_id INTEGER,
                    user_id BIGINT NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending', -- pending, approved, rejected
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')

            # Таблица для кнопок на модерации
            async with pool.acquire() as conn:
                await conn.execute('''
                CREATE TABLE IF NOT EXISTS first_comment_moderation_buttons (
                    channel_id BIGINT NOT NULL,
                    button_index INTEGER NOT NULL,
                    button_text VARCHAR(50) NOT NULL,
                    button_url VARCHAR(500) NOT NULL,
                    PRIMARY KEY (channel_id, button_index),
                    FOREIGN KEY (channel_id) REFERENCES first_comment_moderation(channel_id) ON DELETE CASCADE
                )
            ''')


        # ========== КОМАНДЫ И ПРАВА ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS commands_chats (
                    ChatId BIGINT,
                    CommandId INTEGER,
                    AccessLevel INTEGER,
                    UNIQUE(ChatId, CommandId)
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS sections (
                    SectionId INTEGER PRIMARY KEY,
                    SectionName TEXT UNIQUE NOT NULL
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS under_sections (
                    UnderSectionId INTEGER PRIMARY KEY,
                    UnderName TEXT UNIQUE NOT NULL,
                    SectionId INTEGER REFERENCES sections(SectionId)
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS commands (
                    CommandName TEXT,
                    CommandId INTEGER,
                    AccessLevel INTEGER,
                    UnderSectionId INTEGER REFERENCES under_sections(UnderSectionId),
                    UNIQUE(CommandName, CommandId, UnderSectionId)
                );
            ''')

        logger.info("✅ Все таблицы успешно созданы в PostgreSQL")

    except Exception as e:
        logger.error(f"❌ Ошибка при создании таблиц: {e}", exc_info=True)
        raise


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


async def init_database():
    """Инициализировать базу данных (создать таблицы)."""
    await create_db()


async def init_commands_structure():
    pool = get_db_pool()
    """Инициализировать структуру команд, секций и подсекций."""
    sections = [{"SectionId": 1, "SectionName": "Модерация чата"},
                {"SectionId": 2, "SectionName": "Настройки чата"},
                {"SectionId": 3, "SectionName": "Информация"},
                {"SectionId": 4, "SectionName": "Команды участников"},]



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
        {"UnderSectionId": 73, "UnderName": "Система первого комментария", "SectionId": 2},

        {"UnderSectionId": 19, "UnderName": "Информация о участниках", "SectionId": 3},
        {"UnderSectionId": 20, "UnderName": "Профиль участников", "SectionId": 4},
        {"UnderSectionId": 70, "UnderName": "Ролевые команды", "SectionId": 4},
        {"UnderSectionId": 76, "UnderName": "Помощь", "SectionId": 4},
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
        {"names": ["Управление закрепами"], "CommandId": 63, "AccessLevel": 3, "UnderSectionId": 15},

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
    ]

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