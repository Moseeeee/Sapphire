import asyncio
import logging
from aiogram import types, Dispatcher, Bot

logger = logging.getLogger(__name__)


class WebhookOptimizer:
    def __init__(self, max_concurrency: int = 50):
        # Очередь для хранения апдейтов
        self.queue = asyncio.Queue()
        # Максимальное количество одновременных задач
        self.max_concurrency = max_concurrency
        self.workers = []
        self.is_running = False

    async def add_update(self, bot: Bot, update_data: dict, dp: Dispatcher):
        """Добавляет апдейт в очередь и следит за нагрузкой."""
        await self.queue.put((bot, update_data, dp))

        # Мониторинг нагрузки
        q_size = self.queue.qsize()
        if q_size > 300:
            logger.warning(f"⚠️ ВНИМАНИЕ: Высокая нагрузка! В очереди {q_size} запросов.")
        elif q_size % 50 == 0 and q_size > 0:
            logger.info(f"📊 Очередь обрабатывается. Осталось: {q_size}")

    async def _worker_task(self):
        """Воркер, который берет апдейты из очереди и отдает их в Aiogram."""
        while self.is_running:
            try:
                bot, update_data, dp = await self.queue.get()

                # Конвертируем JSON в объект Aiogram и скармливаем диспетчеру
                # Стало:
                update = types.Update.model_validate(update_data)
                await dp.feed_update(bot=bot, update=update)

                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в воркере: {e}", exc_info=True)

    async def start(self):
        """Запуск пула воркеров."""
        self.is_running = True
        for _ in range(self.max_concurrency):
            task = asyncio.create_task(self._worker_task())
            self.workers.append(task)
        logger.info(f"⚡ Оптимизатор запущен (Пул воркеров: {self.max_concurrency})")

    async def stop(self):
        """Остановка всех воркеров."""
        self.is_running = False
        for w in self.workers:
            w.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        logger.info("🛑 Оптимизатор остановлен.")


# Создаем глобальный экземпляр оптимизатора
optimizer = WebhookOptimizer(max_concurrency=50)