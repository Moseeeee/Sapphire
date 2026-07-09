import asyncio
import logging
from typing import Dict, Any, List, Optional
from asyncio import Lock

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)

# ------------------ ГЛОБАЛЬНЫЙ КЕШ С АВТОМАТИЧЕСКИМ ОБНОВЛЕНИЕМ ------------------
memory_cache: Dict[str, Any] = {}
cache_lock = Lock()

# Таблицы для кеширования (должны соответствовать структуре PostgreSQL)
CACHE_TABLES = {
    #'users': ['user_id', 'name', 'username', 'last_activity'],
    #'chats': ['chat_id', 'chat_title', 'chat_username', 'bot_chat_status', 'owner_id', 'status_v', 'status_e', 'invite_link'],
    #'rules': ['chat_id', 'rules_text'],
    #'welcome': ['chat_id', 'welcome_text'],
    #'agents': ['agent_id', 'agent_appointed_id', 'date_appointed'],
    #'acting_agents': ['acting_agent_id', 'agent_status'],
    #'chat_admins': ['userid', 'chatid'],
    #'users_rangs': ['userid', 'chatid', 'rang']
}

def auto_cache_update(table_name: str, key_column: str = None, key_columns: list = None):
    """
    Декоратор для автоматического обновления кеша после операций записи.
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            # Обновляем кеш только для функций, которые изменяют данные
            if func.__name__.startswith(('add_', 'update_', 'edit_', 'delete_', 'new_', 'del_')):
                if key_columns:
                    # Составной ключ
                    entity_ids = {}
                    for key_col in key_columns:
                        key_value = None
                        # Поиск в позиционных аргументах
                        if len(args) > 0:
                            try:
                                key_index = key_columns.index(key_col)
                                if key_index < len(args):
                                    key_value = args[key_index]
                            except ValueError:
                                pass
                        # Поиск в именованных аргументах
                        if key_value is None and key_col in kwargs:
                            key_value = kwargs[key_col]
                        if key_value is not None:
                            entity_ids[key_col] = key_value

                    if len(entity_ids) == len(key_columns):
                        await update_cache_entry_composite(table_name, key_columns, entity_ids)
                    else:
                        await update_cache_table(table_name)

                elif key_column:
                    # Одиночный ключ
                    entity_id = None
                    if len(args) > 0:
                        entity_id = args[0]
                    elif key_column in kwargs:
                        entity_id = kwargs[key_column]

                    if entity_id is not None:
                        await update_cache_entry(table_name, key_column, entity_id)
                    else:
                        await update_cache_table(table_name)
                else:
                    await update_cache_table(table_name)

            return result
        return wrapper
    return decorator


def multi_cache_update(*cache_configs):
    """Декоратор для обновления нескольких таблиц в кеше."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            if func.__name__.startswith(('add_', 'update_', 'edit_', 'delete_', 'new_', 'del_')):
                for config in cache_configs:
                    table_name = config[0]
                    key_column = config[1] if len(config) > 1 else None
                    key_columns = config[2] if len(config) > 2 else None

                    if key_columns:
                        entity_ids = {}
                        for key_col in key_columns:
                            key_value = None
                            if len(args) > 0:
                                try:
                                    key_index = key_columns.index(key_col)
                                    if key_index < len(args):
                                        key_value = args[key_index]
                                except ValueError:
                                    pass
                            if key_value is None and key_col in kwargs:
                                key_value = kwargs[key_col]
                            if key_value is not None:
                                entity_ids[key_col] = key_value

                        if len(entity_ids) == len(key_columns):
                            await update_cache_entry_composite(table_name, key_columns, entity_ids)
                        else:
                            await update_cache_table(table_name)

                    elif key_column:
                        entity_id = args[0] if len(args) > 0 else kwargs.get(key_column)
                        if entity_id is not None:
                            await update_cache_entry(table_name, key_column, entity_id)
                        else:
                            await update_cache_table(table_name)
                    else:
                        await update_cache_table(table_name)
            return result
        return wrapper
    return decorator


async def update_cache_entry_composite(table_name: str, key_columns: List[str], entity_ids: Dict[str, Any]):
    """Обновляет запись по составному ключу."""
    cache_key = f"{table_name}_" + "_".join(f"{col}_{entity_ids[col]}" for col in key_columns)
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            columns = CACHE_TABLES[table_name]
            columns_str = ', '.join(f'"{col}"' for col in columns)
            where_clause = ' AND '.join(f'"{col}" = ${i+1}' for i, col in enumerate(key_columns))
            query = f'SELECT {columns_str} FROM "{table_name}" WHERE {where_clause}'
            params = [entity_ids[col] for col in key_columns]

            row = await conn.fetchrow(query, *params)
            async with cache_lock:
                if row:
                    memory_cache[cache_key] = dict(row)  # asyncpg.Row поддерживает dict()
                elif cache_key in memory_cache:
                    del memory_cache[cache_key]
    except Exception as e:
        logger.error(e, exc_info=True)
        async with cache_lock:
            memory_cache.pop(cache_key, None)


async def update_cache_entry(table_name: str, key_column: str, entity_id: Any):
    """Обновляет запись по одиночному ключу."""
    cache_key = f"{table_name}_{entity_id}"
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            columns = CACHE_TABLES[table_name]
            columns_str = ', '.join(f'"{col}"' for col in columns)
            query = f'SELECT {columns_str} FROM "{table_name}" WHERE "{key_column}" = $1'
            row = await conn.fetchrow(query, entity_id)

            async with cache_lock:
                if row:
                    memory_cache[cache_key] = dict(row)
                elif cache_key in memory_cache:
                    del memory_cache[cache_key]
    except Exception as e:
        logger.error(e, exc_info=True)
        async with cache_lock:
            memory_cache.pop(cache_key, None)


async def update_cache_table(table_name: str):
    """Обновляет всю таблицу в кеше."""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            columns = CACHE_TABLES[table_name]
            columns_str = ', '.join(f'"{col}"' for col in columns)
            query = f'SELECT {columns_str} FROM "{table_name}"'
            rows = await conn.fetch(query)

            async with cache_lock:
                # Удаляем старые записи этой таблицы
                keys_to_remove = [k for k in memory_cache if k.startswith(f"{table_name}_")]
                for k in keys_to_remove:
                    del memory_cache[k]

                # Добавляем новые
                for row in rows:
                    # Предполагаем, что первый столбец — идентификатор
                    cache_key = f"{table_name}_{row[columns[0]]}"
                    memory_cache[cache_key] = dict(row)

    except Exception as e:
        logger.error(e, exc_info=True)


async def load_full_db_to_cache():
    """Выгружает всю БД в кеш."""
    logger.info("🚀 Начало полной загрузки БД в кеш")
    try:
        async with cache_lock:
            memory_cache.clear()
            logger.info("🧹 Кеш очищен")

        pool = get_db_pool()
        async with pool.acquire() as conn:
            for table, columns in CACHE_TABLES.items():
                columns_str = ', '.join(f'"{col}"' for col in columns)
                query = f'SELECT {columns_str} FROM "{table}"'
                rows = await conn.fetch(query)

                async with cache_lock:
                    for row in rows:
                        cache_key = f"{table}_{row[columns[0]]}"
                        memory_cache[cache_key] = dict(row)

                logger.info(f"✅ Таблица {table} загружена: {len(rows)} записей")

        logger.info(f"🎉 Кеш полностью загружен: {len(memory_cache)} записей")
        return 'ok'
    except Exception as e:
        logger.error(e, exc_info=True)
        return 'error'


async def auto_cache_updater():
    """Автоматическое обновление кеша каждые 2 минуты."""
    while True:
        await asyncio.sleep(120)
        await load_full_db_to_cache()


async def print_cache_by_tables():
    """Вывод кеша с группировкой (только для отладки!)."""
    async with cache_lock:
        if not memory_cache:
            logger.info("📭 Кеш пуст!")
            return

        tables_data = {}
        for key, value in memory_cache.items():
            table_name = key.split('_')[0]
            tables_data.setdefault(table_name, []).append((key, value))

        logger.info("📊 КЕШ С ГРУППИРОВКОЙ ПО ТАБЛИЦАМ:")
        for table_name, records in tables_data.items():
            logger.info(f"📋 ТАБЛИЦА: {table_name.upper()} ({len(records)} записей)")
            for key, data in records[:3]:  # Только первые 3 записи
                logger.info(f"   🔑 {key}: {data}")
            if len(records) > 3:
                logger.info(f"   ... и ещё {len(records) - 3} записей")


async def init_cache():
    """Инициализация кеша при старте."""
    cache_status = await load_full_db_to_cache()
    asyncio.create_task(auto_cache_updater())
    return cache_status

