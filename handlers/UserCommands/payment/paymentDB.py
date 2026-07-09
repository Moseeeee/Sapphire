import logging
from datetime import datetime, timezone, timedelta

# Предполагается, что get_db_pool импортируется корректно из твоего проекта
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


def get_current_datetime() -> datetime:
    return datetime.now()


# ==========================================
# ОСНОВНАЯ ЛОГИКА БАЛАНСА И ИСТОРИИ
# ==========================================

async def get_balance(user_id: int) -> int:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT balance FROM sapphire_bag WHERE user_id = $1', user_id)
        return row['balance'] if row else 0


async def get_bag_info(user_id: int) -> dict:
    """Получить баланс и статус видимости мешка."""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT balance, is_hidden FROM sapphire_bag WHERE user_id = $1',
            user_id
        )
        return dict(row) if row else {'balance': 0, 'is_hidden': False}


async def add_to_bag(user_id: int, amount: int, agent_id: int, date: datetime, comment: str) -> tuple[bool, int, str]:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow('SELECT balance FROM sapphire_bag WHERE user_id = $1 FOR UPDATE', user_id)
            balance_before = row['balance'] if row else 0
            balance_after = balance_before + amount

            await conn.execute('''
                INSERT INTO sapphire_bag (user_id, balance, last_update)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) 
                DO UPDATE SET balance = EXCLUDED.balance, last_update = EXCLUDED.last_update
            ''', user_id, balance_after, date)

            if "рефаунд" in comment.lower() or "возврат" in comment.lower():
                op_type = "Рефаунд"
            elif "штраф" in comment.lower() or "наказать" in comment.lower():
                op_type = "Штраф"
            elif "перевод" in comment.lower():
                op_type = "Перевод"
            elif amount > 0:
                op_type = "Пополнение"
            else:
                op_type = "Списание"

            await conn.execute('''
                INSERT INTO sapphire_history 
                (user_id, agent_id, operation_type, amount, balance_before, balance_after, date, comment)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ''', user_id, agent_id, op_type, amount, balance_before, balance_after, date, comment)

            return True, balance_after, "Операция успешно проведена"


async def set_bag_visibility(user_id: int, hide: bool) -> None:
    """Установить статус видимости мешка (True - скрыть, False - показать)"""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO sapphire_bag (user_id, is_hidden)
            VALUES ($1, $2)
            ON CONFLICT (user_id) 
            DO UPDATE SET is_hidden = EXCLUDED.is_hidden, last_update = CURRENT_TIMESTAMP
        ''', user_id, hide)


async def get_bag_history(user_id: int, page: int = 1) -> list[str]:
    limit = 5
    offset = (page - 1) * limit

    pool = get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT operation_type, amount, balance_after, date, comment 
            FROM sapphire_history 
            WHERE user_id = $1 
            ORDER BY date DESC 
            LIMIT $2 OFFSET $3
        ''', user_id, limit, offset)

        formatted_history = []
        for row in rows:
            dt = row['date'].strftime('%d.%m.%Y %H:%M')
            sign = "+" if row['amount'] > 0 else ""

            op_emoji = "💎"
            if row['operation_type'] == "REFUND":
                op_emoji = "🛑"
            elif row['operation_type'] == "PUNISHMENT":
                op_emoji = "🚨"
            elif row['operation_type'] == "TRANSFER":
                op_emoji = "💸"

            line = (
                f"📅 <code>{dt}</code> | {op_emoji} <b>{row['operation_type']}</b>\n"
                f" Изменение: <code>{sign}{row['amount']:,}</code> сапф.\n"
                f" Итог: <code>{row['balance_after']:,}</code> сапф.\n"
                f" 💬 <i>{row['comment']}</i>\n"
            )
            formatted_history.append(line)

        return formatted_history


async def get_agent_audit_info(user_id: int) -> dict:
    """Расширенная сводка для команды 'чек мешок' у агентов"""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        bag_row = await conn.fetchrow(
            'SELECT balance, is_hidden, last_update FROM sapphire_bag WHERE user_id = $1',
            user_id
        )

        punishments = await conn.fetchval(
            "SELECT COUNT(*) FROM sapphire_history WHERE user_id = $1 AND operation_type = 'PUNISHMENT'",
            user_id
        )

        donated = await conn.fetchval(
            "SELECT SUM(sapphires) FROM telegram_stars_payments WHERE user_id = $1 AND status = 'success'",
            user_id
        )

        return {
            'balance': bag_row['balance'] if bag_row else 0,
            'is_hidden': bag_row['is_hidden'] if bag_row else False,
            'last_update': bag_row['last_update'] if bag_row else None,
            'punishments_count': punishments or 0,
            'total_donated': donated or 0
        }


async def get_top_bags(include_hidden: bool = False, page: int = 1) -> list[dict]:
    """Получить список богачей (Только для агентов, поэтому скрытых можно учитывать)"""
    limit = 10
    offset = (page - 1) * limit
    pool = get_db_pool()
    async with pool.acquire() as conn:
        if include_hidden:
            rows = await conn.fetch(
                'SELECT user_id, balance, is_hidden FROM sapphire_bag ORDER BY balance DESC LIMIT $1 OFFSET $2', limit,
                offset)
        else:
            rows = await conn.fetch(
                'SELECT user_id, balance, is_hidden FROM sapphire_bag WHERE is_hidden = FALSE ORDER BY balance DESC LIMIT $1 OFFSET $2',
                limit, offset)
        return [dict(row) for row in rows]


# ==========================================
# РАБОТА С TELEGRAM STARS И РЕФАУНДАМИ
# ==========================================

async def save_star_transaction(code: str, user_id: int, charge_id: str, sapphires: int):
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO telegram_stars_payments (code, user_id, charge_id, sapphires, status)
            VALUES ($1, $2, $3, $4, 'success')
        ''', code, user_id, charge_id, sapphires)


async def get_star_transaction(code: str) -> dict | None:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('''
            SELECT user_id, charge_id, sapphires, status 
            FROM telegram_stars_payments 
            WHERE code = $1
        ''', code)
        return dict(row) if row else None


async def mark_transaction_refunded(code: str):
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE telegram_stars_payments SET status = 'refunded' WHERE code = $1", code)


async def process_sapphire_purchase(user_id: int, amount: int, item_name: str) -> bool | str:
    """
    Возвращает True, если покупка успешна.
    В случае неудачи возвращает строку с причиной (например, "недостаточно сапфирок").
    """
    # Фиксируем МСК время
    msk_tz = timezone(timedelta(hours=3))
    current_msk_time = datetime.now(msk_tz).replace(tzinfo=None)

    # 1. Проверяем баланс
    current_balance = await get_balance(user_id)
    if current_balance < amount:
        return "недостаточно сапфирок"

    # 2. Оформляем покупку
    comment = f"Покупка: {item_name}"

    success, _, db_msg = await add_to_bag(
        user_id=user_id,
        amount=-amount,
        agent_id=0,
        date=current_msk_time,
        comment=comment
    )

    if success:
        return True
    else:
        # Оставляем возврат ошибки БД на случай технических сбоев
        return f"ошибка базы данных: {db_msg}"