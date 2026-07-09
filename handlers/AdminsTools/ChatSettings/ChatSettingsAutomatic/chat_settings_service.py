import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from aiogram import Bot
from aiogram.types import BufferedInputFile
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from handlers.AdminsTools.ChatSettings.ChatSettingsAutomatic.ChatSettingsDB import (
    get_changes_due_now, update_change_after_application,
    get_change_by_id, get_all_active_changes
)

logger = logging.getLogger(__name__)


class AutoChatService:
    """Сервис для автоматического применения изменений чата."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.is_running = False
        self.check_interval = 60  # Проверять каждые 30 секунд
        self._check_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self.max_failed_attempts = 3  # Максимальное количество неудачных попыток
        self._failed_attempts: Dict[
            int, Dict] = {}  # {change_id: {'count': int, 'last_error': str, 'last_attempt': datetime}}

    async def start(self):
        """Запускает сервис автоматических изменений."""
        if self.is_running:
            return

        self.is_running = True
        self._check_task = asyncio.create_task(self._check_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("✅ Сервис автоматических изменений чата запущен")

    async def stop(self):
        """Останавливает сервис."""
        self.is_running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        self._failed_attempts.clear()
        logger.info("⛔ Сервис автоматических изменений чата остановлен")

    async def _check_loop(self):
        """Основной цикл проверки изменений."""
        logger.info("🔍 Цикл проверки изменений запущен")
        while self.is_running:
            try:
                await self._check_and_apply_changes()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                logger.info("🔍 Цикл проверки отменен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле проверки: {e}", exc_info=True)
                await asyncio.sleep(10)

    async def _cleanup_loop(self):
        """Цикл очистки словаря с неудачными попытками (каждые 12 часов)."""
        logger.info("🧹 Цикл очистки словаря запущен (интервал: 12 часов)")
        while self.is_running:
            try:
                await asyncio.sleep(43200)  # 12 часов = 43200 секунд
                await self._cleanup_failed_attempts()
            except asyncio.CancelledError:
                logger.info("🧹 Цикл очистки отменен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в цикле очистки: {e}", exc_info=True)

    async def _cleanup_failed_attempts(self):
        """Очищает старые записи из словаря (старше 24 часов)."""
        try:
            now = datetime.now()
            to_delete = []

            for change_id, data in self._failed_attempts.items():
                if data['last_attempt'] and (now - data['last_attempt']).total_seconds() > 86400:  # 24 часа
                    to_delete.append(change_id)

            for change_id in to_delete:
                del self._failed_attempts[change_id]

            if to_delete:
                logger.info(f"🧹 Очищено {len(to_delete)} старых записей из словаря неудачных попыток")
        except Exception as e:
            logger.error(f"❌ Ошибка при очистке словаря: {e}", exc_info=True)

    async def _record_failed_attempt(self, change_id: int, error_message: str) -> bool:
        """
        Отмечает неудачную попытку и удаляет изменение после 3 неудач.
        Возвращает True если запись удалена, False если еще есть попытки.
        """
        try:
            if change_id not in self._failed_attempts:
                self._failed_attempts[change_id] = {
                    'count': 0,
                    'last_error': '',
                    'last_attempt': None
                }

            self._failed_attempts[change_id]['count'] += 1
            self._failed_attempts[change_id]['last_error'] = error_message[:200]
            self._failed_attempts[change_id]['last_attempt'] = datetime.now()

            current_count = self._failed_attempts[change_id]['count']

            # Если 3 неудачные попытки - удаляем из базы
            if current_count >= self.max_failed_attempts:
                logger.warning(
                    f"🗑️ Изменение {change_id} удалено после {current_count} неудачных попыток. Последняя ошибка: {error_message}")

                # Удаляем из базы
                from handlers.AdminsTools.ChatSettings.ChatSettingsAutomatic.ChatSettingsDB import delete_change
                await delete_change(change_id)

                # Удаляем из словаря
                del self._failed_attempts[change_id]
                return True

            logger.warning(
                f"❌ Неудачная попытка {current_count}/{self.max_failed_attempts} для изменения {change_id}: {error_message[:100]}")
            return False

        except Exception as e:
            logger.error(f"❌ Ошибка при записи неудачной попытки: {e}", exc_info=True)
            return False

    async def _reset_failed_attempts(self, change_id: int):
        """Сбрасывает счетчик неудачных попыток после успешного применения."""
        if change_id in self._failed_attempts:
            del self._failed_attempts[change_id]
            logger.debug(f"✅ Сброшен счетчик неудачных попыток для изменения {change_id}")

    async def _check_and_apply_changes(self):
        """Проверяет и применяет изменения, которые должны быть применены сейчас."""
        try:
            changes = await get_changes_due_now()
            if changes:
                logger.info(f"🔍 Найдено {len(changes)} изменений для применения")
                for change in changes:
                    try:
                        logger.info(
                            f"🔄 Применение изменения {change['id']} для чата {change['chat_id']} (тип: {change['change_type']})")

                        # Применяем изменение
                        success, error_message = await self._apply_change(change)

                        if success:
                            # Обновляем запись в базе
                            await update_change_after_application(change['id'])
                            # Сбрасываем счетчик неудачных попыток
                            await self._reset_failed_attempts(change['id'])
                            logger.info(f"✅ Применено изменение {change['id']} для чата {change['chat_id']}")
                        else:
                            # Записываем неудачную попытку
                            was_deleted = await self._record_failed_attempt(change['id'],
                                                                            error_message or "Unknown error")

                            if not was_deleted:
                                logger.warning(
                                    f"❌ Не удалось применить изменение {change['id']} для чата {change['chat_id']}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка применения изменения {change['id']}: {e}", exc_info=True)
                        await self._record_failed_attempt(change['id'], str(e)[:200])
                        continue
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке изменений: {e}", exc_info=True)

    async def _apply_change(self, change: dict) -> tuple[bool, Optional[str]]:
        """Применяет конкретное изменение с обработкой ошибок.
        Возвращает (успех, сообщение_об_ошибке)"""
        try:
            chat_id = change['chat_id']
            change_type = change['change_type']
            new_value = change['new_value']

            logger.info(f"🔄 Применение {change_type} в чате {chat_id}: {new_value[:50]}...")

            # Проверяем, является ли бот администратором
            try:
                chat_member = await self.bot.get_chat_member(chat_id, self.bot.id)
                if chat_member.status not in ['creator', 'administrator']:
                    error_msg = f"⚠️ Бот не является администратором в чате {chat_id}"
                    logger.warning(error_msg)
                    return False, error_msg

                # Проверяем права на конкретные действия
                if chat_member.status == 'administrator':
                    if change_type == 'title' and not chat_member.can_change_info:
                        error_msg = f"⚠️ Нет прав на изменение названия в чате {chat_id}"
                        logger.warning(error_msg)
                        return False, error_msg
                    elif change_type == 'description' and not chat_member.can_change_info:
                        error_msg = f"⚠️ Нет прав на изменение описания в чате {chat_id}"
                        logger.warning(error_msg)
                        return False, error_msg
                    elif change_type == 'avatar' and not chat_member.can_change_info:
                        error_msg = f"⚠️ Нет прав на изменение аватарки в чате {chat_id}"
                        logger.warning(error_msg)
                        return False, error_msg
            except TelegramForbiddenError:
                error_msg = f"⛔ Бот исключен из чата {chat_id}"
                logger.warning(error_msg)
                return False, error_msg
            except Exception as e:
                error_msg = f"❌ Ошибка проверки прав бота в чате {chat_id}: {e}"
                logger.error(error_msg, exc_info=True)
                return False, error_msg

            if change_type == 'title':
                if len(new_value) > 255:
                    error_msg = f"❌ Название слишком длинное: {len(new_value)} символов"
                    logger.error(error_msg)
                    return False, error_msg

                await self.bot.set_chat_title(chat_id, new_value)
                logger.info(f"✅ Установлено название в чате {chat_id}: {new_value[:50]}...")
                return True, None

            elif change_type == 'description':
                if len(new_value) > 255:
                    error_msg = f"❌ Описание слишком длинное: {len(new_value)} символов"
                    logger.error(error_msg)
                    return False, error_msg

                await self.bot.set_chat_description(chat_id, new_value)
                logger.info(f"✅ Установлено описание в чате {chat_id}: {new_value[:50]}...")
                return True, None

            elif change_type == 'avatar':
                return await self._apply_avatar_change(chat_id, change)

            error_msg = f"❌ Неизвестный тип изменения: {change_type}"
            logger.error(error_msg)
            return False, error_msg

        except TelegramBadRequest as e:
            error_msg = str(e)
            error_msg_lower = error_msg.lower()

            # Эти ошибки не считаются критическими - изменение уже такое же
            if "not modified" in error_msg_lower:
                logger.info(f"ℹ️ {change_type} чата {chat_id} не изменилось (уже такое же)")
                return True, None  # Это успех, ничего менять не нужно

            # Критические ошибки
            if "not enough rights" in error_msg_lower:
                error_msg = f"⚠️ Нет прав для изменения чата {chat_id}: {e}"
            elif "chat not found" in error_msg_lower:
                error_msg = f"⚠️ Чат {chat_id} не найден: {e}"
            elif "too long" in error_msg_lower:
                error_msg = f"❌ Текст слишком длинный для чата {chat_id}: {e}"
            else:
                error_msg = f"❌ Telegram ошибка в чате {chat_id}: {e}"

            logger.error(error_msg)
            return False, error_msg

        except TelegramForbiddenError as e:
            error_msg = f"⛔ Доступ запрещен к чату {chat_id}: {e}"
            logger.warning(error_msg)
            return False, error_msg

        except Exception as e:
            error_msg = f"❌ Ошибка применения изменения в чате {chat_id}: {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    async def _apply_avatar_change(self, chat_id: int, change: dict) -> tuple[bool, Optional[str]]:
        """Применяет изменение аватарки чата."""
        try:
            file_id = change.get('file_id')

            if not file_id:
                error_msg = f"❌ Для аватарки не указан file_id"
                logger.error(error_msg)
                return False, error_msg

            logger.info(f"🖼️ Установка аватарки в чате {chat_id} с file_id: {file_id}")

            # Если есть file_id, скачиваем файл и создаем InputFile
            return await self._set_avatar_by_file_id(chat_id, file_id)

        except Exception as e:
            error_msg = f"❌ Ошибка применения аватарки в чате {chat_id}: {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    async def _set_avatar_by_file_id(self, chat_id: int, file_id: str) -> tuple[bool, Optional[str]]:
        """Устанавливает аватарку по file_id."""
        try:
            # Скачиваем файл напрямую через бот
            file = await self.bot.get_file(file_id)
            # Скачиваем содержимое файла
            file_content = await self.bot.download_file(file.file_path)

            if file_content is None:
                error_msg = f"❌ Не удалось скачать файл {file_id}"
                logger.error(error_msg)
                return False, error_msg

            # Читаем содержимое файла
            image_data = file_content.read()
            if not image_data:
                error_msg = f"❌ Файл {file_id} пустой"
                logger.error(error_msg)
                return False, error_msg

            # Создаем BufferedInputFile из данных
            input_file = BufferedInputFile(
                file=image_data,
                filename="avatar.jpg"
            )

            # Устанавливаем аватарку
            await self.bot.set_chat_photo(chat_id, photo=input_file)
            logger.info(f"✅ Установлена аватарка по file_id в чате {chat_id}")
            return True, None

        except TelegramBadRequest as e:
            error_msg = str(e)
            error_msg_lower = error_msg.lower()

            if "not modified" in error_msg_lower:
                logger.info(f"ℹ️ Аватарка чата {chat_id} не изменилась (уже такая же)")
                return True, None
            elif "photo" in error_msg_lower and "invalid" in error_msg_lower:
                error_msg = f"❌ Неверный формат изображения для чата {chat_id}: {e}"
            else:
                error_msg = f"❌ Telegram ошибка при установке аватарки: {e}"

            logger.error(error_msg)
            return False, error_msg

        except Exception as e:
            error_msg = f"❌ Ошибка установки аватарки по file_id: {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    async def apply_change_now(self, change_id: int) -> tuple[bool, Optional[str]]:
        """Принудительно применяет изменение сейчас."""
        try:
            # Получаем изменение из базы
            change = await get_change_by_id(change_id)
            if not change:
                error_msg = f"❌ Изменение {change_id} не найдено"
                logger.error(error_msg)
                return False, error_msg

            success, error_msg = await self._apply_change(change)
            if success:
                # Обновляем в базе
                await update_change_after_application(change_id)
                await self._reset_failed_attempts(change_id)
                logger.info(f"✅ Принудительно применено изменение {change_id}")
                return True, None
            else:
                # Записываем неудачную попытку
                await self._record_failed_attempt(change_id, error_msg or "Unknown error")
                return False, error_msg

        except Exception as e:
            error_msg = f"❌ Ошибка принудительного применения: {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    async def get_failed_attempts_info(self, change_id: int = None) -> Dict:
        """Возвращает информацию о неудачных попытках."""
        if change_id:
            return self._failed_attempts.get(change_id, {})
        return self._failed_attempts

    async def test_chat_permissions(self, chat_id: int) -> dict:
        """Проверяет права бота в чате."""
        try:
            chat_member = await self.bot.get_chat_member(chat_id, self.bot.id)
            return {
                'is_admin': chat_member.status in ['creator', 'administrator'],
                'can_change_info': getattr(chat_member, 'can_change_info', False),
                'can_delete_messages': getattr(chat_member, 'can_delete_messages', False),
                'can_invite_users': getattr(chat_member, 'can_invite_users', False),
                'can_restrict_members': getattr(chat_member, 'can_restrict_members', False),
                'can_pin_messages': getattr(chat_member, 'can_pin_messages', False),
                'can_promote_members': getattr(chat_member, 'can_promote_members', False)
            }
        except TelegramForbiddenError:
            return {'is_admin': False, 'error': 'bot_not_in_chat'}
        except Exception as e:
            logger.error(f"❌ Ошибка проверки прав: {e}", exc_info=True)
            return {'is_admin': False, 'error': str(e)}

    async def get_upcoming_changes(self, chat_id: int, hours: int = 24) -> List[dict]:
        """Получает изменения, которые должны произойти в ближайшие часы."""
        try:
            all_changes = await get_all_active_changes(chat_id)
            now = datetime.now()
            upcoming = []

            for change in all_changes:
                time_diff = change['scheduled_time'] - now
                if 0 < time_diff.total_seconds() <= hours * 3600:
                    upcoming.append({
                        **change,
                        'hours_left': int(time_diff.total_seconds() // 3600),
                        'minutes_left': int((time_diff.total_seconds() % 3600) // 60)
                    })

            return sorted(upcoming, key=lambda x: x['scheduled_time'])
        except Exception as e:
            logger.error(f"❌ Ошибка получения ближайших изменений: {e}", exc_info=True)
            return []

    async def debug_service(self) -> dict:
        """Отладочная информация о сервисе."""
        return {
            'is_running': self.is_running,
            'check_interval': self.check_interval,
            'check_task_running': self._check_task is not None and not self._check_task.done(),
            'cleanup_task_running': self._cleanup_task is not None and not self._cleanup_task.done(),
            'bot_id': self.bot.id if self.bot else None,
            'max_failed_attempts': self.max_failed_attempts,
            'failed_attempts_count': len(self._failed_attempts)
        }


# Глобальный экземпляр сервиса
_auto_chat_service: Optional[AutoChatService] = None


def get_auto_chat_service(bot: Bot = None) -> Optional[AutoChatService]:
    """Возвращает или создает экземпляр сервиса."""
    global _auto_chat_service
    if _auto_chat_service is None and bot is not None:
        _auto_chat_service = AutoChatService(bot)
    return _auto_chat_service


async def init_auto_chat_service(bot: Bot):
    """Инициализирует и запускает сервис."""
    service = get_auto_chat_service(bot)
    if service:
        await service.start()


async def shutdown_auto_chat_service():
    """Останавливает сервис."""
    service = get_auto_chat_service()
    if service:
        await service.stop()


async def test_service_status(bot: Bot) -> dict:
    """Тестирует статус сервиса."""
    service = get_auto_chat_service(bot)
    if service:
        return await service.debug_service()
    return {'error': 'service_not_initialized'}


async def force_check_now(bot: Bot) -> dict:
    """Принудительно запускает проверку изменений."""
    service = get_auto_chat_service(bot)
    if service and service.is_running:
        await service._check_and_apply_changes()
        return {'status': 'check_completed'}
    return {'error': 'service_not_running'}