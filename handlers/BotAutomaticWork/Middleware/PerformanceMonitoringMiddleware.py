import time
import logging
from aiogram import BaseMiddleware
from typing import Callable, Awaitable, Dict, Any
from aiogram.types import Update

logger = logging.getLogger(__name__)


class PerformanceMonitoringMiddleware(BaseMiddleware):
    """Middleware для мониторинга производительности обработки обновлений"""

    def __init__(self, alert_threshold: float = 1.0):
        """
        Args:
            alert_threshold: Порог в секундах для предупреждения о медленной обработке
        """
        self.alert_threshold = alert_threshold

    async def __call__(
            self,
            handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
            event: Update,
            data: Dict[str, Any]
    ) -> Any:
        start_time = time.time()
        try:
            result = await handler(event, data)
            return result
        finally:
            processing_time = time.time() - start_time
            if processing_time > self.alert_threshold:
                logger.warning(
                    f"⚠️ Медленная обработка update_id={event.update_id}: {processing_time:.3f}с"
                )
            # Логируем очень медленные обработки
            if processing_time > self.alert_threshold * 3:
                logger.error(
                    f"❌ Очень медленная обработка update_id={event.update_id}: {processing_time:.3f}с"
                )