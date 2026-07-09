import logging

from handlers.AdminsTools.ChatSettings.catalog.catalog_db import init_catalog_tables
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

            await conn.execute('''ALTER TABLE acting_agents ADD COLUMN IF NOT EXISTS online BOOLEAN DEFAULT TRUE;''')

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
                    voice_settings TEXT DEFAULT 'no',
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
                    last_update TEXT,
                    online_mode VARCHAR(10) DEFAULT 'exact'
                );
            ''')
            await conn.execute('''
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS online_mode VARCHAR(10) DEFAULT 'exact';
            ''')


            async with pool.acquire() as conn:
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

        async with pool.acquire() as conn:
            await conn.execute('''
                        CREATE TABLE IF NOT EXISTS telegram_stars_payments (
                            code VARCHAR(50) PRIMARY KEY,
                            user_id BIGINT NOT NULL,
                            charge_id VARCHAR(255) NOT NULL,
                            sapphires INTEGER NOT NULL,
                            status VARCHAR(20) NOT NULL DEFAULT 'success',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

        async with pool.acquire() as conn:
            await conn.execute('''
               CREATE TABLE IF NOT EXISTS first_comments (
               chat_id BIGINT PRIMARY KEY,
               comment_text TEXT NOT NULL
               );
            ''')

            async with pool.acquire() as conn:
                await conn.execute('''
                CREATE TABLE IF NOT EXISTS first_comment_buttons (
                chat_id BIGINT NOT NULL,
                button_index INTEGER NOT NULL,
                button_text VARCHAR(50) NOT NULL,
                button_url VARCHAR(500) NOT NULL,
                PRIMARY KEY (chat_id, button_index),
                FOREIGN KEY (chat_id) REFERENCES first_comments(chat_id) ON DELETE CASCADE
                );
            ''')

            async with pool.acquire() as conn:
                await conn.execute('''
                CREATE TABLE IF NOT EXISTS await_checks_approvals_first_comment (
                chat_id BIGINT PRIMARY KEY,
                comment_text TEXT NOT NULL,
                message_id BIGINT NOT NULL,
                admin_message_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                buttons JSONB
                );
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


        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS bundles (
                    id BIGSERIAL PRIMARY KEY,
                    owner_id BIGINT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(owner_id, name)
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS bundle_chats (
                    bundle_id BIGINT REFERENCES bundles(id) ON DELETE CASCADE,
                    chat_id BIGINT NOT NULL,
                    added_by BIGINT NOT NULL,
                    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    description TEXT,
                    PRIMARY KEY (bundle_id, chat_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_bundle_chats_chat_id ON bundle_chats(chat_id);
            ''')


        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_selected_bundle (
                    user_id BIGINT PRIMARY KEY,
                    bundle_id BIGINT NOT NULL REFERENCES bundles(id) ON DELETE CASCADE,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS bundle_admins (
                    bundle_id BIGINT NOT NULL REFERENCES bundles(id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL,
                    added_by BIGINT NOT NULL,
                    rank SMALLINT NOT NULL DEFAULT 1,
                    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    PRIMARY KEY (bundle_id, user_id)
                );
            ''')


        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS bundle_action_log (
                    id BIGSERIAL PRIMARY KEY,
                    bundle_id BIGINT NOT NULL REFERENCES bundles(id) ON DELETE CASCADE,
                    admin_id BIGINT NOT NULL,
                    target_user_id BIGINT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT,
                    duration TEXT,
                    success BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            ''')

        # ========== КРЕПКОСТЬ БРАКА ==========
        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS marriages_strength (
                    id BIGSERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    user1_id BIGINT NOT NULL,
                    user2_id BIGINT NOT NULL,
                    married_at TIMESTAMPTZ DEFAULT NOW(),
                    level INTEGER DEFAULT 0,
                    points BIGINT DEFAULT 0,
                    last_interaction TIMESTAMPTZ DEFAULT NOW(),
                    last_weekly_decay TIMESTAMPTZ DEFAULT NOW(),
                    cooldowns JSONB DEFAULT '{}'::jsonb,
                    action_counters JSONB DEFAULT '{}'::jsonb,
                    UNIQUE(chat_id, user1_id, user2_id)
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_marriages_strength_chat_pair 
                    ON marriages_strength(chat_id, LEAST(user1_id, user2_id), GREATEST(user1_id, user2_id));
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS marriage_epic_actions (
                    marriage_id BIGINT REFERENCES marriages_strength(id) ON DELETE CASCADE,
                    action_name TEXT,
                    used_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (marriage_id, action_name)
                );
            ''')

        async with pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS marriage_gifts (
                    id SERIAL PRIMARY KEY,
                    marriage_id BIGINT REFERENCES marriages_strength(id) ON DELETE CASCADE,
                    gift_name TEXT,
                    giver_id BIGINT,
                    points INTEGER DEFAULT 0,
                    given_at TIMESTAMPTZ DEFAULT NOW()
                );
            ''')

        # ТЕПЕРЬ ЗДЕСЬ ОСТАЛСЯ ТОЛЬКО ЧИСТЫЙ ВЫЗОВ НАШЕЙ ИНИЦИАЛИЗАЦИИ КАТАЛОГА
        await init_catalog_tables()

        logger.info("✅ Все таблицы успешно созданы в PostgreSQL")

    except Exception as e:
        logger.error(f"❌ Ошибка при создании таблиц: {e}", exc_info=True)
        raise