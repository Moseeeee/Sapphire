import logging
import re
from typing import Dict, List, Optional

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)


async def get_link_filter_settings(chat_id: int) -> Dict[str, any]:
    """Получает настройки фильтрации ссылок для чата"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT filter_websites, filter_chats, filter_referrals, filter_all, action '
                'FROM link_filter_settings WHERE chat_id = $1',
                chat_id
            )
            if row:
                # Возвращаем настройки как есть
                return {
                    'filter_websites': bool(row['filter_websites']),
                    'filter_chats': bool(row['filter_chats']),
                    'filter_referrals': bool(row['filter_referrals']),
                    'filter_all': bool(row['filter_all']),
                    'action': row['action']
                }

            # Если запись не существует, создаем дефолтную
            await conn.execute('''
                INSERT INTO link_filter_settings (chat_id)
                VALUES ($1)
                ON CONFLICT (chat_id) DO NOTHING
            ''', chat_id)

            return {
                'filter_websites': False,
                'filter_chats': False,
                'filter_referrals': False,
                'filter_all': False,
                'action': 'warn'
            }
    except Exception as e:
        logger.error(f"Error getting link filter settings: {e}", exc_info=True)
        return {
            'filter_websites': False,
            'filter_chats': False,
            'filter_referrals': False,
            'filter_all': False,
            'action': 'warn'
        }


async def get_effective_filter_settings(chat_id: int) -> Dict[str, any]:
    """Получает эффективные настройки фильтрации с учетом приоритета"""
    settings = await get_link_filter_settings(chat_id)

    # Если включен filter_all, он имеет высший приоритет
    if settings['filter_all']:
        return {
            'filter_websites': True,
            'filter_chats': True,
            'filter_referrals': True,
            'filter_all': True,
            'action': settings['action']
        }

    return settings


async def set_link_filter_setting(chat_id: int, settings: Dict[str, any]) -> None:
    """Устанавливает настройки фильтрации ссылок для чата"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO link_filter_settings (
                    chat_id, filter_websites, filter_chats, filter_referrals, 
                    filter_all, action, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (chat_id) DO UPDATE SET
                    filter_websites = EXCLUDED.filter_websites,
                    filter_chats = EXCLUDED.filter_chats,
                    filter_referrals = EXCLUDED.filter_referrals,
                    filter_all = EXCLUDED.filter_all,
                    action = EXCLUDED.action,
                    updated_at = NOW()
            ''', chat_id,
                               settings.get('filter_websites', False),
                               settings.get('filter_chats', False),
                               settings.get('filter_referrals', False),
                               settings.get('filter_all', False),
                               settings.get('action', 'warn'))
    except Exception as e:
        logger.error(f"Error setting link filter settings: {e}", exc_info=True)


async def toggle_link_filter(chat_id: int, filter_type: str, enabled: bool) -> None:
    """Включает/выключает определенный тип фильтрации"""
    try:
        settings = await get_link_filter_settings(chat_id)

        # Если включаем filter_all, отключаем индивидуальные настройки
        if filter_type == 'filter_all' and enabled:
            settings = {
                'filter_websites': True,
                'filter_chats': True,
                'filter_referrals': True,
                'filter_all': True,
                'action': settings['action']
            }
        # Если выключаем filter_all, переходим в индивидуальный режим
        elif filter_type == 'filter_all' and not enabled:
            settings['filter_all'] = False
            # Оставляем текущие индивидуальные настройки без изменений
        # Если меняем индивидуальную настройку и filter_all включен
        elif settings['filter_all'] and filter_type in ['filter_websites', 'filter_chats', 'filter_referrals']:
            # Отключаем filter_all и устанавливаем все фильтры кроме изменяемого
            settings['filter_all'] = False
            settings['filter_websites'] = True
            settings['filter_chats'] = True
            settings['filter_referrals'] = True
            settings[filter_type] = enabled
        # Обычное изменение индивидуальной настройки
        elif filter_type in ['filter_websites', 'filter_chats', 'filter_referrals']:
            settings[filter_type] = enabled

        await set_link_filter_setting(chat_id, settings)
    except Exception as e:
        logger.error(f"Error toggling link filter: {e}", exc_info=True)


async def get_link_action(chat_id: int) -> str:
    """Получает действие при обнаружении запрещенных ссылок"""
    try:
        settings = await get_link_filter_settings(chat_id)
        return settings.get('action', 'warn')
    except Exception as e:
        logger.error(f"Error getting link action: {e}", exc_info=True)
        return 'warn'


async def set_link_action(chat_id: int, action: str) -> None:
    """Устанавливает действие при обнаружении запрещенных ссылок"""
    try:
        settings = await get_link_filter_settings(chat_id)
        settings['action'] = action
        await set_link_filter_setting(chat_id, settings)
    except Exception as e:
        logger.error(f"Error setting link action: {e}", exc_info=True)


async def add_to_whitelist(chat_id: int, url: str, added_by: Optional[int] = None) -> bool:
    """Добавляет ссылку в вайтлист"""
    try:
        # Очищаем и нормализуем URL
        url = url.strip()
        if not url:
            return False

        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Проверяем, является ли паттерн регулярным выражением
            is_regex = False
            try:
                re.compile(url)  # Пытаемся скомпилировать как regex
                is_regex = True
            except re.error:
                is_regex = False

            await conn.execute('''
                INSERT INTO link_filter_whitelist (chat_id, link_pattern, is_regex, added_by)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (chat_id, link_pattern) DO NOTHING
            ''', chat_id, url, is_regex, added_by)

            return True
    except Exception as e:
        logger.error(f"Error adding to whitelist: {e}", exc_info=True)
        return False


async def remove_from_whitelist(chat_id: int, url: str) -> bool:
    """Удаляет ссылку из вайтлиста"""
    try:
        url = url.strip()
        if not url:
            return False

        pool = get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.execute('''
                DELETE FROM link_filter_whitelist
                WHERE chat_id = $1 AND link_pattern = $2
            ''', chat_id, url)

            return result.split()[-1] == '1'  # Проверяем, была ли удалена хотя бы одна запись
    except Exception as e:
        logger.error(f"Error removing from whitelist: {e}", exc_info=True)
        return False


async def is_link_allowed(chat_id: int, url: str) -> bool:
    """Проверяет, разрешена ли ссылка в вайтлисте"""
    try:
        url = url.strip().lower()
        if not url:
            return False

        pool = get_db_pool()
        async with pool.acquire() as conn:
            # Получаем все правила вайтлиста для этого чата
            rows = await conn.fetch(
                'SELECT link_pattern, is_regex FROM link_filter_whitelist WHERE chat_id = $1',
                chat_id
            )

            for row in rows:
                pattern = row['link_pattern']
                is_regex = row['is_regex']

                try:
                    if is_regex:
                        # Проверяем по регулярному выражению
                        if re.match(pattern, url, re.IGNORECASE):
                            return True
                    else:
                        # Проверяем точное совпадение или вхождение
                        pattern_lower = pattern.lower()
                        if pattern_lower == url:
                            return True

                        # Проверяем вхождение
                        if pattern_lower in url:
                            return True

                        # Проверяем wildcard паттерны (например, *.example.com)
                        if pattern_lower.startswith('*.'):
                            domain = pattern_lower[2:]
                            if url.endswith(domain):
                                return True
                except Exception as e:
                    logger.warning(f"Error checking pattern {pattern}: {e}")
                    continue

        return False
    except Exception as e:
        logger.error(f"Error checking whitelist: {e}", exc_info=True)
        return False


async def get_whitelist(chat_id: int) -> List[Dict[str, any]]:
    """Получает список разрешенных ссылок для чата"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT id, link_pattern, is_regex, added_by, created_at 
                FROM link_filter_whitelist 
                WHERE chat_id = $1 
                ORDER BY created_at
            ''', chat_id)

            return [
                {
                    'id': row['id'],
                    'pattern': row['link_pattern'],
                    'is_regex': row['is_regex'],
                    'added_by': row['added_by'],
                    'created_at': row['created_at']
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Error getting whitelist: {e}", exc_info=True)
        return []


async def get_whitelisted_links_count(chat_id: int) -> int:
    """Получает количество разрешенных ссылок для чата"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                'SELECT COUNT(*) FROM link_filter_whitelist WHERE chat_id = $1',
                chat_id
            )
            return count or 0
    except Exception as e:
        logger.error(f"Error getting whitelist count: {e}", exc_info=True)
        return 0


async def clear_chat_whitelist(chat_id: int) -> int:
    """Очищает вайтлист для чата, возвращает количество удаленных записей"""
    try:
        pool = get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                'DELETE FROM link_filter_whitelist WHERE chat_id = $1',
                chat_id
            )
            # Извлекаем количество удаленных записей из результата
            deleted_count = int(result.split()[-1])
            return deleted_count
    except Exception as e:
        logger.error(f"Error clearing whitelist: {e}", exc_info=True)
        return 0


async def update_link_filter_settings(chat_id: int, **kwargs) -> bool:
    """Обновляет несколько настроек фильтрации одновременно"""
    try:
        settings = await get_link_filter_settings(chat_id)
        settings.update(kwargs)
        await set_link_filter_setting(chat_id, settings)
        return True
    except Exception as e:
        logger.error(f"Error updating link filter settings: {e}", exc_info=True)
        return False


async def get_link_filter_status(chat_id: int) -> Dict[str, any]:
    """Получает полный статус фильтрации ссылок для чата"""
    try:
        settings = await get_link_filter_settings(chat_id)
        effective_settings = await get_effective_filter_settings(chat_id)
        whitelist_count = await get_whitelisted_links_count(chat_id)

        return {
            'raw_settings': settings,
            'effective_settings': effective_settings,
            'whitelist_count': whitelist_count,
            'is_active': any([
                effective_settings['filter_websites'],
                effective_settings['filter_chats'],
                effective_settings['filter_referrals']
            ]),
            'mode': 'all' if effective_settings['filter_all'] else 'individual'
        }
    except Exception as e:
        logger.error(f"Error getting link filter status: {e}", exc_info=True)
        return {
            'raw_settings': {
                'filter_websites': False,
                'filter_chats': False,
                'filter_referrals': False,
                'filter_all': False,
                'action': 'warn'
            },
            'effective_settings': {
                'filter_websites': False,
                'filter_chats': False,
                'filter_referrals': False,
                'filter_all': False,
                'action': 'warn'
            },
            'whitelist_count': 0,
            'is_active': False,
            'mode': 'individual'
        }