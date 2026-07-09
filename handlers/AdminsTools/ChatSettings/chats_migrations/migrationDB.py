import logging
import html
from typing import AsyncGenerator, Literal
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


async def transfer_chat_data(
        old_chat_id: int,
        new_chat_id: int,
        mode: Literal['settings', 'stats', 'all']
) -> AsyncGenerator[tuple[int, str], None]:
    """
    Высокооптимизированный перенос и слияние данных чатов в одной транзакции.
    Параметры динамически распределяются в зависимости от структуры запроса.
    """
    pool = get_db_pool()
    execution_plan = []

    # --- БЛОК 1: КОПИРОВАНИЕ НАСТРОЕК (UPSERT / UPDATE) ---
    if mode in ('settings', 'all'):
        settings_queries = [
            ("chats", """
                UPDATE chats AS target
                SET status_v = source.status_v, 
                    status_e = source.status_e, 
                    push_status = source.push_status, 
                    antispam = source.antispam, 
                    voice_settings = source.voice_settings, 
                    bot_chat_status = source.bot_chat_status, 
                    chat_ignore_status = source.chat_ignore_status, 
                    number_for_inputs = source.number_for_inputs, 
                    min_rp_rating = source.min_rp_rating,
                    last_update = source.last_update
                FROM chats AS source
                WHERE target.chat_id = $1 AND source.chat_id = $2
            """),
            ("rules", "INSERT INTO rules (chat_id, rules_text) SELECT $1, rules_text FROM rules WHERE chat_id = $2 ON CONFLICT (chat_id) DO UPDATE SET rules_text = EXCLUDED.rules_text"),
            ("welcome", "INSERT INTO welcome (chat_id, welcome_text) SELECT $1, welcome_text FROM welcome WHERE chat_id = $2 ON CONFLICT (chat_id) DO UPDATE SET welcome_text = EXCLUDED.welcome_text"),
            ("captcha_settings", "INSERT INTO captcha_settings (chat_id, time_limit, difficulty, attempts_limit, enabled) SELECT $1, time_limit, difficulty, attempts_limit, enabled FROM captcha_settings WHERE chat_id = $2 ON CONFLICT (chat_id) DO UPDATE SET time_limit = EXCLUDED.time_limit, difficulty = EXCLUDED.difficulty, attempts_limit = EXCLUDED.attempts_limit, enabled = EXCLUDED.enabled"),
            ("default_time", "INSERT INTO default_time (chat_id, type, time) SELECT $1, type, time FROM default_time WHERE chat_id = $2 ON CONFLICT (chat_id, type) DO UPDATE SET time = EXCLUDED.time"),
            ("link_filter_settings", "INSERT INTO link_filter_settings (chat_id, filter_websites, filter_chats, filter_referrals, filter_all, action, created_at, updated_at) SELECT $1, filter_websites, filter_chats, filter_referrals, filter_all, action, created_at, updated_at FROM link_filter_settings WHERE chat_id = $2 ON CONFLICT (chat_id) DO UPDATE SET filter_websites = EXCLUDED.filter_websites, filter_chats = EXCLUDED.filter_chats, filter_referrals = EXCLUDED.filter_referrals, filter_all = EXCLUDED.filter_all, action = EXCLUDED.action, updated_at = NOW()"),
            ("link_filter_whitelist", "INSERT INTO link_filter_whitelist (chat_id, link_pattern, is_regex, added_by, created_at) SELECT $1, link_pattern, is_regex, added_by, created_at FROM link_filter_whitelist WHERE chat_id = $2 ON CONFLICT (chat_id, link_pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, added_by = EXCLUDED.added_by, created_at = EXCLUDED.created_at"),
            ("commands_chats", "INSERT INTO commands_chats (ChatId, CommandId, AccessLevel) SELECT $1, CommandId, AccessLevel FROM commands_chats WHERE ChatId = $2 ON CONFLICT (ChatId, CommandId) DO UPDATE SET AccessLevel = EXCLUDED.AccessLevel"),
            ("notes", "INSERT INTO notes (notes_id, chat_id, notes_name, notes_text) SELECT notes_id, $1, notes_name, notes_text FROM notes WHERE chat_id = $2 ON CONFLICT (chat_id, notes_id) DO UPDATE SET notes_name = EXCLUDED.notes_name, notes_text = EXCLUDED.notes_text"),
            ("first_comments", "INSERT INTO first_comments (chat_id, comment_text) SELECT $1, comment_text FROM first_comments WHERE chat_id = $2 ON CONFLICT (chat_id) DO UPDATE SET comment_text = EXCLUDED.comment_text"),
            ("first_comment_buttons", "INSERT INTO first_comment_buttons (chat_id, button_index, button_text, button_url) SELECT $1, button_index, button_text, button_url FROM first_comment_buttons WHERE chat_id = $2 ON CONFLICT (chat_id, button_index) DO UPDATE SET button_text = EXCLUDED.button_text, button_url = EXCLUDED.button_url"),
            ("chat_admins", "INSERT INTO chat_admins (UserId, ChatId, ManagementAdminId, ManagementRang, time) SELECT UserId, $1, ManagementAdminId, ManagementRang, time FROM chat_admins WHERE ChatId = $2 ON CONFLICT (UserId, ChatId) DO UPDATE SET ManagementAdminId = EXCLUDED.ManagementAdminId, ManagementRang = EXCLUDED.ManagementRang, time = EXCLUDED.time"),
            ("users_rangs", "INSERT INTO users_rangs (UserId, ChatId, rang) SELECT UserId, $1, rang FROM users_rangs WHERE ChatId = $2 ON CONFLICT (UserId, ChatId) DO UPDATE SET rang = EXCLUDED.rang"),
            ("warn_settings", "INSERT INTO warn_settings (chat_id, action, warn_limit) SELECT $1, action, warn_limit FROM warn_settings WHERE chat_id = $2 ON CONFLICT (chat_id) DO UPDATE SET action = EXCLUDED.action, warn_limit = EXCLUDED.warn_limit"),
            ("await_checks_approvals", "INSERT INTO await_checks_approvals (chat_id, type, text, message_id, admin_message_id, user_id) SELECT $1, type, text, message_id, admin_message_id, user_id FROM await_checks_approvals WHERE chat_id = $2 ON CONFLICT (chat_id, type) DO UPDATE SET text = EXCLUDED.text, message_id = EXCLUDED.message_id, admin_message_id = EXCLUDED.admin_message_id, user_id = EXCLUDED.user_id"),
            ("await_checks_approvals_notes", "INSERT INTO await_checks_approvals_notes (chat_id, notes_name, notes_text, message_id, admin_message_id, user_id, is_edit) SELECT $1, notes_name, notes_text, message_id, admin_message_id, user_id, is_edit FROM await_checks_approvals_notes WHERE chat_id = $2 ON CONFLICT (chat_id, notes_name) DO UPDATE SET notes_text = EXCLUDED.notes_text, message_id = EXCLUDED.message_id, admin_message_id = EXCLUDED.admin_message_id, user_id = EXCLUDED.user_id, is_edit = EXCLUDED.is_edit"),
            ("await_checks_approvals_first_comment", "INSERT INTO await_checks_approvals_first_comment (chat_id, comment_text, message_id, admin_message_id, user_id, buttons) SELECT $1, comment_text, message_id, admin_message_id, user_id, buttons FROM await_checks_approvals_first_comment WHERE chat_id = $2 ON CONFLICT (chat_id) DO UPDATE SET comment_text = EXCLUDED.comment_text, message_id = EXCLUDED.message_id, admin_message_id = EXCLUDED.admin_message_id, user_id = EXCLUDED.user_id, buttons = EXCLUDED.buttons")
        ]
        for table, sql in settings_queries:
            execution_plan.append((table, [sql]))

    # --- БЛОК 2: ПОЛНЫЙ ПЕРЕНОС И УДАЛЕНИЕ СТАРЫХ ДАННЫХ (СТАТИСТИКА И ЛОГИ) ---
    if mode in ('stats', 'all'):
        stats_queries = [
            ("chats_stub", ["INSERT INTO chats (chat_id, chat_title) VALUES ($1, 'Migrated Chat') ON CONFLICT (chat_id) DO NOTHING"]),
            ("bundle_chats", [
                "DELETE FROM bundle_chats WHERE chat_id = $1",
                "UPDATE bundle_chats SET chat_id = $1 WHERE chat_id = $2"
            ]),
            ("message_stats", [
                """UPDATE message_stats AS m 
                   SET total = m.total + o.total, daily = m.daily + o.daily, weekly = m.weekly + o.weekly, monthly = m.monthly + o.monthly, yearly = m.yearly + o.yearly 
                   FROM message_stats AS o WHERE m.chat_id = $1 AND o.chat_id = $2 AND m.user_id = o.user_id""",
                "DELETE FROM message_stats AS m USING message_stats AS o WHERE m.chat_id = $1 AND o.chat_id = $2 AND m.user_id = o.user_id",
                "UPDATE message_stats SET chat_id = $1 WHERE chat_id = $2"
            ]),
            ("moderation_stats", [
                """UPDATE moderation_stats AS m 
                   SET day_count = m.day_count + o.day_count, week_count = m.week_count + o.week_count, month_count = m.month_count + o.month_count, year_count = m.year_count + o.year_count, total_count = m.total_count + o.total_count 
                   FROM moderation_stats AS o WHERE m.chat_id = $1 AND o.chat_id = $2 AND m.user_id = o.user_id""",
                "DELETE FROM moderation_stats AS m USING moderation_stats AS o WHERE m.chat_id = $1 AND o.chat_id = $2 AND m.user_id = o.user_id",
                "UPDATE moderation_stats SET chat_id = $1 WHERE chat_id = $2"
            ]),
            ("marriages_strength", [
                """UPDATE marriages_strength AS o 
                   SET level = GREATEST(o.level, m.level), points = GREATEST(o.points, m.points) 
                   FROM marriages_strength AS m 
                   WHERE o.chat_id = $2 AND m.chat_id = $1 AND ((o.user1_id = m.user1_id AND o.user2_id = m.user2_id) OR (o.user1_id = m.user2_id AND o.user2_id = m.user1_id))""",
                """DELETE FROM marriages_strength AS m 
                   USING marriages_strength AS o 
                   WHERE m.chat_id = $1 AND o.chat_id = $2 AND ((m.user1_id = o.user1_id AND m.user2_id = o.user2_id) OR (m.user1_id = o.user2_id AND m.user2_id = o.user1_id))""",
                "UPDATE marriages_strength SET chat_id = $1 WHERE chat_id = $2"
            ]),
            ("bans", [
                "DELETE FROM bans AS m USING bans AS o WHERE m.chat_id = $1 AND o.chat_id = $2 AND m.user_id = o.user_id",
                "UPDATE bans SET chat_id = $1 WHERE chat_id = $2"
            ]),
            ("mutes", [
                "DELETE FROM mutes AS m USING mutes AS o WHERE m.chat_id = $1 AND o.chat_id = $2 AND m.user_id = o.user_id",
                "UPDATE mutes SET chat_id = $1 WHERE chat_id = $2"
            ]),
            ("warns", ["UPDATE warns SET chat_id = $1 WHERE chat_id = $2"]),
            ("users_chats", [
                "DELETE FROM users_chats AS m USING users_chats AS o WHERE m.chat_id = $1 AND o.chat_id = $2 AND m.user_id = o.user_id",
                "UPDATE users_chats SET chat_id = $1 WHERE chat_id = $2"
            ]),
            ("full_users_chats", [
                "DELETE FROM full_users_chats AS m USING full_users_chats AS o WHERE m.chat_id = $1 AND o.chat_id = $2 AND m.user_id = o.user_id",
                "UPDATE full_users_chats SET chat_id = $1 WHERE chat_id = $2"
            ]),
            ("punishment_time", [
                "DELETE FROM punishment_time AS m USING punishment_time AS o WHERE m.chat_id = $1 AND o.chat_id = $2 AND m.user_id = o.user_id AND m.types = o.types",
                "UPDATE punishment_time SET chat_id = $1 WHERE chat_id = $2"
            ]),
            ("captcha_history", ["UPDATE captcha_history SET chat_id = $1 WHERE chat_id = $2"]),
            ("history_chat_admins", ["UPDATE history_chat_admins SET ChatId = $1 WHERE ChatId = $2"]),
            ("reports", ["UPDATE reports SET reported_chat = $1 WHERE reported_chat = $2"]),
            ("chat_reports", [
                "UPDATE chat_reports SET report_chat = $1 WHERE report_chat = $2",
                "UPDATE chat_reports SET reported_chat = $1 WHERE reported_chat = $2"
            ])
        ]
        for table, sqls in stats_queries:
            execution_plan.append((table, sqls))

    if not execution_plan:
        yield 100, "Нет задач для выполнения."
        return

    yield 0, "⏳ Инициализация защищенной транзакции базы данных..."

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                for table_name, sqls in execution_plan:
                    for sql in sqls:
                        # Умное распределение аргументов для предотвращения ошибок asyncpg
                        if "$2" in sql:
                            await conn.execute(sql, new_chat_id, old_chat_id)
                        elif "$1" in sql:
                            await conn.execute(sql, new_chat_id)
                        else:
                            await conn.execute(sql)

        yield 100, "✅ Все изменения успешно зафиксированы в PostgreSQL!"
    except Exception as e:
        logger.critical(f"Ошибка транзакции при миграции чата: {e}", exc_info=True)
        yield -1, f"Ошибка в ядре БД: {html.escape(str(e))}"