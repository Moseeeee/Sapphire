import time
import logging
from aiogram import BaseMiddleware

logger = logging.getLogger(__name__)

class PerformanceMonitoringMiddleware(BaseMiddleware):
    def __init__(self, alert_threshold: float = 1.0):
        super().__init__()
        self.alert_threshold = alert_threshold

    async def __call__(self, handler, event, data):
        start = time.time()
        try:
            return await handler(event, data)
        finally:
            duration = time.time() - start
            if duration > self.alert_threshold:
                logger.warning(f"⏱️ SLOW: {duration:.3f}s for update {event.update_id}")