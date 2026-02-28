import logging
from datetime import datetime
from typing import Dict, List, Tuple
import asyncpg
from html import escape

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)

# Константы
MAX_BALANCE = 1_000_000

# Типы операций с эмодзи и названиями
OPERATION_TYPES = {
    # Административные операции
    'add': {
        'emoji': '🧾',
        'name': 'Покупка сапфиров'
    },
    'remove': {
        'emoji': '➖',
        'name': 'Списание сапфиров'
    },
    'admin_transfer_in': {
        'emoji': '⚖️',
        'name': 'Судебная кара (компенсация)'
    },
    'admin_transfer_out': {
        'emoji': '⚖️',
        'name': 'Судебная кара (штраф)'
    },
    'user_transfer_in': {
        'emoji': '📥',
        'name': 'Перевод от пользователя'
    },
    'user_transfer_out': {
        'emoji': '📤',
        'name': 'Перевод пользователю'
    },
    'purchase': {
        'emoji': '🧾',
        'name': 'Покупка сапфов'
    },
    'sale': {
        'emoji': '💰',
        'name': 'Продажа сапфов'
    },
    'reward': {
        'emoji': '🎁',
        'name': 'Награда за активность'
    },
    'bonus': {
        'emoji': '🎯',
        'name': 'Бонус'
    },
    'penalty': {
        'emoji': '⚠️',
        'name': 'Штраф'
    },
    'refund': {
        'emoji': '↩️',
        'name': 'Возврат средств'
    }
}


def get_current_datetime() -> datetime:
    """Возвращает текущее datetime для базы данных"""
    return datetime.utcnow()


async def get_operation_with_details(operation_record: dict) -> dict:
    """Добавляет базовую информацию к записи операции"""
    try:
        # Базовые поля из записи
        result = dict(operation_record)

        # Получаем информацию об операции
        operation_type = result.get('operation_type', '')
        op_info = OPERATION_TYPES.get(operation_type, {'emoji': '📝', 'name': 'Операция'})

        # Форматируем сумму с плюсом/минусом
        amount = result.get('amount', 0)
        if amount > 0:
            result['formatted_amount'] = f"+{amount:,}"
            result['amount_color'] = "🟢"
            result['amount_prefix'] = "➕"
        else:
            result['formatted_amount'] = f"{amount:,}"
            result['amount_color'] = "🔴"
            result['amount_prefix'] = "➖"

        # Форматируем балансы
        balance_before = result.get('balance_before', 0)
        balance_after = result.get('balance_after', 0)
        result['formatted_balance_change'] = f"{balance_before:,} → {balance_after:,}"

        # Форматируем дату
        if isinstance(result.get('date'), datetime):
            result['formatted_date'] = result['date'].strftime("%d.%m.%Y %H:%M")
        else:
            result['formatted_date'] = str(result.get('date', ''))

        # Базовые поля операции
        result['emoji'] = op_info['emoji']
        result['display_name'] = op_info['name']

        # Комментарий
        comment = result.get('comment', '')
        if comment:
            # Экранируем HTML в комментарии
            clean_comment = escape(comment)
            if len(clean_comment) > 100:
                clean_comment = clean_comment[:97] + "..."
            result['formatted_comment'] = clean_comment
        else:
            result['formatted_comment'] = 'Без комментария'

        # ID пользователей для дальнейшей обработки
        result['agent_id'] = result.get('agent_id')
        result['user_id'] = result.get('user_id')

        return result

    except Exception as e:
        logger.error(f"Error in get_operation_with_details: {e}", exc_info=True)
        return operation_record


async def ensure_user_exists(conn: asyncpg.Connection, user_id: int, date: datetime) -> bool:
    """Создает запись пользователя, если не существует"""
    exists = await conn.fetchval(
        'SELECT 1 FROM sapphire_bag WHERE user_id = $1',
        user_id
    )

    if not exists:
        await conn.execute(
            '''
            INSERT INTO sapphire_bag (user_id, balance, last_update, is_hidden)
            VALUES ($1, 0, $2, FALSE)
            ''',
            user_id, date
        )
    return True


async def get_user_bag(user_id: int) -> int:
    """Возвращает текущий баланс сапфов пользователя"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                'SELECT COALESCE(balance, 0) FROM sapphire_bag WHERE user_id = $1',
                user_id
            ) or 0
    except Exception as e:
        logger.error(f"Error in get_user_bag: {e}", exc_info=True)
        return 0


async def execute_bag_operation(
        user_id: int,
        amount: int,
        agent_id: int,
        date: datetime,
        operation_type: str,
        comment: str = ""
) -> Tuple[bool, int, str]:
    """Базовая функция для операций с мешком"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Гарантируем существование пользователя
                await ensure_user_exists(conn, user_id, date)

                # Получаем текущий баланс
                current_balance = await conn.fetchval(
                    'SELECT balance FROM sapphire_bag WHERE user_id = $1',
                    user_id
                ) or 0

                # Проверяем возможность списания
                if operation_type in ['remove', 'admin_transfer_out', 'user_transfer_out'] and current_balance < amount:
                    return False, current_balance, "❌ Недостаточно сапфов!"

                # Вычисляем новый баланс
                if operation_type in ['add', 'admin_transfer_in', 'user_transfer_in', 'purchase', 'reward', 'bonus']:
                    new_balance = current_balance + amount
                else:
                    new_balance = current_balance - amount

                # Обновляем баланс
                await conn.execute(
                    '''
                    UPDATE sapphire_bag 
                    SET balance = $1, last_update = $2 
                    WHERE user_id = $3
                    ''',
                    new_balance, date, user_id
                )

                # Определяем сумму для записи в историю
                if operation_type in ['add', 'admin_transfer_in', 'user_transfer_in', 'purchase', 'reward', 'bonus']:
                    history_amount = amount
                else:
                    history_amount = -amount

                # Форматируем комментарий в зависимости от типа операции
                formatted_comment = comment
                if not formatted_comment:
                    formatted_comment = ''

                # Записываем в историю
                await conn.execute(
                    '''
                    INSERT INTO sapphire_history 
                    (user_id, agent_id, operation_type, amount, 
                     balance_before, balance_after, date, comment) 
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ''',
                    user_id, agent_id, operation_type,
                    history_amount, current_balance, new_balance, date, formatted_comment
                )

                return True, new_balance, "✅ Успешно"

    except Exception as e:
        logger.error(f"Error in execute_bag_operation: {e}", exc_info=True)
        return False, 0, f"❌ Ошибка: {str(e)}"


async def add_to_bag(
        user_id: int,
        amount: int,
        agent_id: int,
        date: datetime,
        comment: str = ""
) -> Tuple[bool, int, str]:
    """Добавляет сапфы в мешок"""
    return await execute_bag_operation(user_id, amount, agent_id, date, 'add', comment)


async def remove_from_bag(
        user_id: int,
        amount: int,
        agent_id: int,
        date: datetime,
        comment: str = ""
) -> Tuple[bool, int, str]:
    """Убирает сапфы из мешка"""
    return await execute_bag_operation(user_id, amount, agent_id, date, 'remove', comment)


async def purchase_sapphires(
        user_id: int,
        amount: int,
        agent_id: int,
        date: datetime,
        comment: str = ""
) -> Tuple[bool, int, str]:
    """Покупка сапфов (специальный тип операции)"""
    if not comment:
        comment = "Покупка сапфов"
    return await execute_bag_operation(user_id, amount, agent_id, date, 'purchase', comment)


async def reward_user(
        user_id: int,
        amount: int,
        agent_id: int,
        date: datetime,
        comment: str = ""
) -> Tuple[bool, int, str]:
    """Награда пользователя"""
    if not comment:
        comment = "Награда за активность"
    return await execute_bag_operation(user_id, amount, agent_id, date, 'reward', comment)


async def transfer_sapphires(
        from_user_id: int,
        to_user_id: int,
        amount: int,
        agent_id: int,
        date: datetime,
        comment: str = "",
        is_user_transfer: bool = False
) -> Tuple[bool, str]:
    """Переводит сапфы между пользователями с правильными типами операций"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Проверка условий
                if from_user_id == to_user_id:
                    return False, "❌ Нельзя переводить самому себе!"

                if amount <= 0:
                    return False, "❌ Сумма должна быть положительной!"

                await ensure_user_exists(conn, from_user_id, date)
                await ensure_user_exists(conn, to_user_id, date)

                # Получаем балансы
                from_balance = await get_user_bag(from_user_id)
                to_balance = await get_user_bag(to_user_id)

                # Проверяем достаточность средств
                if from_balance < amount:
                    return False, f"❌ Недостаточно сапфов! Доступно: {from_balance:,}"

                # Проверяем лимит получателя
                if to_balance + amount > MAX_BALANCE:
                    return False, f"❌ У получателя превышен лимит баланса!"

                # Выполняем перевод
                new_from_balance = from_balance - amount
                new_to_balance = to_balance + amount

                # Обновляем балансы
                await conn.execute(
                    'UPDATE sapphire_bag SET balance = $1 WHERE user_id = $2',
                    new_from_balance, from_user_id
                )
                await conn.execute(
                    'UPDATE sapphire_bag SET balance = $1 WHERE user_id = $2',
                    new_to_balance, to_user_id
                )

                # Определяем типы операций и комментарии
                if is_user_transfer:
                    # Пользовательский перевод
                    from_op_type = 'user_transfer_out'
                    to_op_type = 'user_transfer_in'
                    transfer_comment = f"📤 Перевод"
                    receive_comment = f"📥 Получено"

                    if comment:
                        clean_comment = escape(comment)
                        transfer_comment += f" ({clean_comment})"
                        receive_comment += f" ({clean_comment})"
                else:
                    # Административный перевод (наказание)
                    from_op_type = 'admin_transfer_out'
                    to_op_type = 'admin_transfer_in'
                    transfer_comment = f"⚖️ Судебная кара (штраф)"
                    receive_comment = f"⚖️ Судебная кара (компенсация)"

                    if comment:
                        clean_comment = escape(comment)
                        transfer_comment += f" ({clean_comment})"
                        receive_comment += f" ({clean_comment})"

                # Записываем историю для отправителя
                await conn.execute(
                    '''
                    INSERT INTO sapphire_history 
                    (user_id, agent_id, operation_type, amount,
                     balance_before, balance_after, date, comment)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ''',
                    from_user_id, agent_id, from_op_type,
                    -amount, from_balance, new_from_balance, date,
                    transfer_comment
                )

                # Записываем историю для получателя
                await conn.execute(
                    '''
                    INSERT INTO sapphire_history 
                    (user_id, agent_id, operation_type, amount,
                     balance_before, balance_after, date, comment)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ''',
                    to_user_id, agent_id, to_op_type,
                    amount, to_balance, new_to_balance, date,
                    receive_comment
                )

                return True, "✅ Перевод успешно выполнен!"

    except Exception as e:
        logger.error(f"Error in transfer_sapphires: {e}", exc_info=True)
        return False, f"❌ Ошибка: {str(e)}"


async def get_bag_info(user_id: int) -> Dict:
    """Возвращает полную информацию о мешке"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await ensure_user_exists(conn, user_id, get_current_datetime())

            row = await conn.fetchrow(
                '''
                SELECT 
                    b.balance,
                    b.last_update,
                    b.is_hidden,
                    COUNT(h.id) as operations_count
                FROM sapphire_bag b
                LEFT JOIN sapphire_history h ON b.user_id = h.user_id
                WHERE b.user_id = $1
                GROUP BY b.balance, b.last_update, b.is_hidden
                ''',
                user_id
            )

            if row:
                result = dict(row)
                # Форматируем дату
                if result['last_update']:
                    result['last_update_str'] = result['last_update'].strftime('%d.%m.%Y %H:%M')
                else:
                    result['last_update_str'] = "никогда"
                return result
            return {
                'balance': 0,
                'last_update': None,
                'last_update_str': "никогда",
                'is_hidden': False,
                'operations_count': 0
            }

    except Exception as e:
        logger.error(f"Error in get_bag_info: {e}", exc_info=True)
        return {
            'balance': 0,
            'last_update': None,
            'last_update_str': "никогда",
            'is_hidden': False,
            'operations_count': 0
        }


async def get_top_bags(limit: int = 15, offset: int = 0, include_hidden: bool = False) -> Tuple[List[Dict], int]:
    """Возвращает топ пользователей по сапфам с учетом скрытых мешков"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Формируем запрос в зависимости от настроек
            if include_hidden:
                # Все мешки включая скрытые (для агентов)
                total_query = 'SELECT COUNT(*) FROM sapphire_bag WHERE balance > 0'
                top_query = '''
                    SELECT user_id, balance, last_update, is_hidden
                    FROM sapphire_bag 
                    WHERE balance > 0 
                    ORDER BY balance DESC 
                    LIMIT $1 OFFSET $2
                '''
            else:
                # Только не скрытые мешки (для обычных пользователей)
                total_query = 'SELECT COUNT(*) FROM sapphire_bag WHERE balance > 0 AND NOT is_hidden'
                top_query = '''
                    SELECT user_id, balance, last_update, is_hidden
                    FROM sapphire_bag 
                    WHERE balance > 0 AND NOT is_hidden
                    ORDER BY balance DESC 
                    LIMIT $1 OFFSET $2
                '''

            # Общее количество
            total = await conn.fetchval(total_query) or 0

            # Топ пользователей
            rows = await conn.fetch(top_query, limit, offset)

            return [dict(row) for row in rows], total

    except Exception as e:
        logger.error(f"Error in get_top_bags: {e}", exc_info=True)
        return [], 0


async def get_total_sapphires() -> int:
    """Общее количество сапфов в системе"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval('SELECT COALESCE(SUM(balance), 0) FROM sapphire_bag') or 0
    except Exception as e:
        logger.error(f"Error in get_total_sapphires: {e}", exc_info=True)
        return 0


async def get_recent_transfers(limit: int = 10, offset: int = 0) -> Tuple[List[Dict], int]:
    """Последние переводы в системе"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Общее количество
            total = await conn.fetchval('''
                SELECT COUNT(*) FROM sapphire_history 
                WHERE operation_type LIKE '%_transfer_%'
            ''') or 0

            # Переводы
            rows = await conn.fetch('''
                SELECT * FROM sapphire_history 
                WHERE operation_type LIKE '%_transfer_%'
                ORDER BY date DESC 
                LIMIT $1 OFFSET $2
            ''', limit, offset)

            # Добавляем отформатированную информацию
            transfers = []
            for row in rows:
                record = dict(row)
                detailed_record = await get_operation_with_details(record)
                transfers.append(detailed_record)

            return transfers, total

    except Exception as e:
        logger.error(f"Error in get_recent_transfers: {e}", exc_info=True)
        return [], 0


async def get_formatted_bag_history(user_id: int, limit: int = 10, offset: int = 0) -> Tuple[List[Dict], int]:
    """Возвращает историю операций с форматированными названиями"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await ensure_user_exists(conn, user_id, get_current_datetime())

            # Общее количество операций
            total = await conn.fetchval(
                'SELECT COUNT(*) FROM sapphire_history WHERE user_id = $1',
                user_id
            ) or 0

            # Получаем историю
            rows = await conn.fetch('''
                SELECT 
                    h.*
                FROM sapphire_history h
                WHERE h.user_id = $1 
                ORDER BY h.date DESC 
                LIMIT $2 OFFSET $3
            ''', user_id, limit, offset)

            history = []
            for row in rows:
                record = dict(row)
                detailed_record = await get_operation_with_details(record)
                history.append(detailed_record)

            return history, total

    except Exception as e:
        logger.error(f"Error in get_formatted_bag_history: {e}", exc_info=True)
        return [], 0


async def get_user_recent_transfers(user_id: int, limit: int = 10, offset: int = 0) -> Tuple[List[Dict], int]:
    """Возвращает последние переводы конкретного пользователя с пагинацией."""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await ensure_user_exists(conn, user_id, get_current_datetime())

            # Общее количество переводов пользователя
            count_row = await conn.fetchrow(
                '''
                SELECT COUNT(*) as total FROM sapphire_history 
                WHERE user_id = $1 AND operation_type IN ('user_transfer_in', 'user_transfer_out', 'admin_transfer_in', 'admin_transfer_out')
                ''',
                user_id
            )
            total = count_row['total'] if count_row else 0

            # Записи для текущей страницы
            rows = await conn.fetch(
                '''
                SELECT * FROM sapphire_history 
                WHERE user_id = $1 AND operation_type IN ('user_transfer_in', 'user_transfer_out', 'admin_transfer_in', 'admin_transfer_out')
                ORDER BY date DESC 
                LIMIT $2 OFFSET $3
                ''',
                user_id, limit, offset
            )

            transfers = []
            for row in rows:
                record = dict(row)
                detailed_record = await get_operation_with_details(record)
                transfers.append(detailed_record)

            return transfers, total

    except Exception as e:
        logger.error(f"Error in get_user_recent_transfers: {e}", exc_info=True)
        return [], 0


async def toggle_bag_visibility(user_id: int, hidden: bool) -> bool:
    """Включает/выключает видимость мешка"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await ensure_user_exists(conn, user_id, get_current_datetime())

            await conn.execute(
                'UPDATE sapphire_bag SET is_hidden = $1 WHERE user_id = $2',
                hidden, user_id
            )
        return True
    except Exception as e:
        logger.error(f"Toggle bag visibility error: {e}", exc_info=True)
        return False


async def is_bag_hidden(user_id: int) -> bool:
    """Проверяет, скрыт ли мешок"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await ensure_user_exists(conn, user_id, get_current_datetime())

            result = await conn.fetchval(
                'SELECT is_hidden FROM sapphire_bag WHERE user_id = $1',
                user_id
            )
            return result or False
    except Exception as e:
        logger.error(f"Is bag hidden error: {e}", exc_info=True)
        return False


async def get_user_bag_rank(user_id: int) -> int:
    """Возвращает место пользователя в топе (0 если не в топе)"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Проверяем, скрыт ли мешок
            is_hidden = await conn.fetchval(
                'SELECT is_hidden FROM sapphire_bag WHERE user_id = $1',
                user_id
            ) or False

            if is_hidden:
                # Для скрытых мешков не показываем место в общем топе
                return 0

            # Получаем место в рейтинге среди не скрытых мешков
            rank = await conn.fetchval('''
                SELECT position FROM (
                    SELECT user_id, 
                           ROW_NUMBER() OVER (ORDER BY balance DESC) as position
                    FROM sapphire_bag 
                    WHERE balance > 0 AND NOT is_hidden
                ) ranked
                WHERE user_id = $1
            ''', user_id)

            return rank or 0

    except Exception as e:
        logger.error(f"Error in get_user_bag_rank: {e}", exc_info=True)
        return 0