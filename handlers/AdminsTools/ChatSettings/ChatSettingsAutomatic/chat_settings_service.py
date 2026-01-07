
import logging
import asyncio
from datetime import datetime
from typing import Optional, List
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
        self.check_interval = 30  # Проверять каждые 30 секунд
        self._check_task: Optional[asyncio.Task] = None

    async def start(self):
        """Запускает сервис автоматических изменений."""
        if self.is_running:
            return

        self.is_running = True
        self._check_task = asyncio.create_task(self._check_loop())
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
                        success = await self._apply_change(change)
                        if success:
                            # Обновляем запись в базе
                            await update_change_after_application(change['id'])
                            logger.info(f"✅ Применено изменение {change['id']} для чата {change['chat_id']}")
                        else:
                            logger.warning(
                                f"❌ Не удалось применить изменение {change['id']} для чата {change['chat_id']}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка применения изменения {change['id']}: {e}", exc_info=True)
                        continue
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке изменений: {e}", exc_info=True)

    async def _apply_change(self, change: dict) -> bool:
        """Применяет конкретное изменение с обработкой ошибок."""
        try:
            chat_id = change['chat_id']
            change_type = change['change_type']
            new_value = change['new_value']

            logger.info(f"🔄 Применение {change_type} в чате {chat_id}: {new_value[:50]}...")

            # Проверяем, является ли бот администратором
            try:
                chat_member = await self.bot.get_chat_member(chat_id, self.bot.id)
                if chat_member.status not in ['creator', 'administrator']:
                    logger.warning(f"⚠️ Бот не является администратором в чате {chat_id}")
                    return False

                # Проверяем права на конкретные действия
                if chat_member.status == 'administrator':
                    if change_type == 'title' and not chat_member.can_change_info:
                        logger.warning(f"⚠️ Нет прав на изменение названия в чате {chat_id}")
                        return False
                    elif change_type == 'description' and not chat_member.can_change_info:
                        logger.warning(f"⚠️ Нет прав на изменение описания в чате {chat_id}")
                        return False
                    elif change_type == 'avatar' and not chat_member.can_change_info:
                        logger.warning(f"⚠️ Нет прав на изменение аватарки в чате {chat_id}")
                        return False
            except TelegramForbiddenError:
                logger.warning(f"⛔ Бот исключен из чата {chat_id}")
                return False
            except Exception as e:
                logger.error(f"❌ Ошибка проверки прав бота в чате {chat_id}: {e}", exc_info=True)
                return False

            if change_type == 'title':
                if len(new_value) > 255:
                    logger.error(f"❌ Название слишком длинное: {len(new_value)} символов")
                    return False

                await self.bot.set_chat_title(chat_id, new_value)
                logger.info(f"✅ Установлено название в чате {chat_id}: {new_value[:50]}...")
                return True

            elif change_type == 'description':
                if len(new_value) > 255:
                    logger.error(f"❌ Описание слишком длинное: {len(new_value)} символов")
                    return False

                await self.bot.set_chat_description(chat_id, new_value)
                logger.info(f"✅ Установлено описание в чате {chat_id}: {new_value[:50]}...")
                return True

            elif change_type == 'avatar':
                return await self._apply_avatar_change(chat_id, change)

            logger.error(f"❌ Неизвестный тип изменения: {change_type}")
            return False

        except TelegramBadRequest as e:
            error_msg = str(e).lower()
            if "not enough rights" in error_msg:
                logger.warning(f"⚠️ Нет прав для изменения чата {chat_id}: {e}")
            elif "chat not found" in error_msg:
                logger.warning(f"⚠️ Чат {chat_id} не найден: {e}")
            elif "too long" in error_msg:
                logger.error(f"❌ Текст слишком длинный для чата {chat_id}: {e}")
            elif "chat description is not modified" in error_msg:
                logger.info(f"ℹ️ Описание чата {chat_id} не изменилось (уже такое же)")
                return True  # Это не ошибка
            elif "chat title is not modified" in error_msg:
                logger.info(f"ℹ️ Название чата {chat_id} не изменилось (уже такое же)")
                return True  # Это не ошибка
            else:
                logger.error(f"❌ Telegram ошибка в чате {chat_id}: {e}", exc_info=True)
            return False

        except TelegramForbiddenError as e:
            logger.warning(f"⛔ Доступ запрещен к чату {chat_id}: {e}")
            return False

        except Exception as e:
            logger.error(f"❌ Ошибка применения изменения в чате {chat_id}: {e}", exc_info=True)
            return False

    async def _apply_avatar_change(self, chat_id: int, change: dict) -> bool:
        """Применяет изменение аватарки чата."""
        try:
            file_id = change.get('file_id')

            if not file_id:
                logger.error(f"❌ Для аватарки не указан file_id")
                return False

            logger.info(f"🖼️ Установка аватарки в чате {chat_id} с file_id: {file_id}")

            # Если есть file_id, скачиваем файл и создаем InputFile
            return await self._set_avatar_by_file_id(chat_id, file_id)

        except Exception as e:
            logger.error(f"❌ Ошибка применения аватарки в чате {chat_id}: {e}", exc_info=True)
            return False

    async def _set_avatar_by_file_id(self, chat_id: int, file_id: str) -> bool:
        """Устанавливает аватарку по file_id."""
        try:
            # Скачиваем файл напрямую через бот
            file = await self.bot.get_file(file_id)
            # Скачиваем содержимое файла
            file_content = await self.bot.download_file(file.file_path)

            if file_content is None:
                logger.error(f"❌ Не удалось скачать файл {file_id}")
                return False

            # Читаем содержимое файла
            image_data = file_content.read()
            if not image_data:
                logger.error(f"❌ Файл {file_id} пустой")
                return False

            # Создаем BufferedInputFile из данных
            input_file = BufferedInputFile(
                file=image_data,
                filename="avatar.jpg"
            )

            # Устанавливаем аватарку
            await self.bot.set_chat_photo(chat_id, photo=input_file)
            logger.info(f"✅ Установлена аватарка по file_id в чате {chat_id}")
            return True

        except TelegramBadRequest as e:
            error_msg = str(e).lower()
            if "chat photo is not modified" in error_msg:
                logger.info(f"ℹ️ Аватарка чата {chat_id} не изменилась (уже такая же)")
                return True  # Это не ошибка
            elif "photo" in error_msg and "invalid" in error_msg:
                logger.error(f"❌ Неверный формат изображения для чата {chat_id}: {e}")
            else:
                logger.error(f"❌ Telegram ошибка при установке аватарки: {e}", exc_info=True)
            return False

        except Exception as e:
            logger.error(f"❌ Ошибка установки аватарки по file_id: {e}", exc_info=True)
            return False

    async def apply_change_now(self, change_id: int) -> bool:
        """Принудительно применяет изменение сейчас."""
        try:
            # Получаем изменение из базы
            change = await get_change_by_id(change_id)
            if not change:
                logger.error(f"❌ Изменение {change_id} не найдено")
                return False

            success = await self._apply_change(change)
            if success:
                # Обновляем в базе
                await update_change_after_application(change_id)
                logger.info(f"✅ Принудительно применено изменение {change_id}")
                return success
            return False

        except Exception as e:
            logger.error(f"❌ Ошибка принудительного применения: {e}", exc_info=True)
            return False

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
            'bot_id': self.bot.id if self.bot else None
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