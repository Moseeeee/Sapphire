import time
from collections import deque
from typing import Dict, Optional
import threading

import asyncio
import logging

logger = logging.getLogger(__name__)

class PerBotRPS:
    """
    Класс для отслеживания RPS статистики отдельного бота
    """

    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        # Счетчики для этого бота
        self.total_requests = 0
        self.handled_requests = 0
        self.error_count = 0
        self.error_types = {}  # "DB Error" -> count
        # Множество уникальных пользователей
        self.unique_users = set()
        # История RPS за каждую секунду: (timestamp, msg_count, ups_count)
        # maxlen=300 -> 5 минут
        self.rps_history = deque(maxlen=300)
        # Временные счётчики для *текущей* секунды
        # Эти счётчики обнуляются каждый раз при переходе к новой секунде
        self.current_second = int(time.time())
        self.current_msg_count = 0
        self.current_ups_set = set() # множество юзеров в текущей секунде
        # Пинг
        self.ping_history = deque(maxlen=100)
        # Блокировки для потокобезопасности
        self.counter_lock = threading.Lock()
        self.timestamp_lock = threading.Lock()
        logger.info(f"📊 RPS мониторинг для бота {bot_id} инициализирован")

    def _update_current_second(self):
        """Обновить счётчики, если текущая секунда изменилась"""
        now = int(time.time())
        if now != self.current_second:
            # Записываем данные за прошлую секунду
            with self.timestamp_lock:
                self.rps_history.append((self.current_second, self.current_msg_count, len(self.current_ups_set)))
            # Сбрасываем счётчики для новой секунды
            self.current_second = now
            self.current_msg_count = 0
            self.current_ups_set.clear()

    def record_request(self):
        """Учесть входящий запрос (любое сообщение) для этого бота"""
        with self.counter_lock:
            self.total_requests += 1
        self._update_current_second() # Обновляем, если нужно
        with self.timestamp_lock:
            self.current_msg_count += 1

    def record_handled(self):
        """Учесть обработанный запрос для этого бота"""
        with self.counter_lock:
            self.handled_requests += 1
        # Обработка не влияет на RPS (msg/s), только на success_rate

    def record_error(self, error_type: str = "Unknown"):
        """Учесть ошибку с типом"""
        with self.counter_lock:
            self.error_count += 1
            self.error_types[error_type] = self.error_types.get(error_type, 0) + 1

    def record_unique_user(self, user_id: int):
        """Учесть уникального пользователя для этого бота"""
        with self.counter_lock:
            self.unique_users.add(user_id)
        self._update_current_second() # Обновляем, если нужно
        with self.timestamp_lock:
            self.current_ups_set.add(user_id)

    def record_ping(self, ping_ms: float):
        """Записать пинг в историю"""
        with self.timestamp_lock:
            self.ping_history.append(ping_ms)

    def _calculate_rps_for_window(self, window_seconds: int) -> tuple[float, float, float, float]:
        """
        Рассчитать avg и peak RPS/UPS за последние window_seconds
        Возвращает (avg_msg_rps, peak_msg_rps, avg_ups_rps, peak_ups_rps)
        """
        now = int(time.time())
        cutoff = now - window_seconds
        with self.timestamp_lock:
            # Копируем историю
            hist_copy = list(self.rps_history)
        # Фильтруем по времени
        relevant_data = [(ts, msg, ups) for ts, msg, ups in hist_copy if ts > cutoff]
        if not relevant_data:
            return 0.0, 0.0, 0.0, 0.0

        msg_counts = [msg for ts, msg, ups in relevant_data]
        ups_counts = [ups for ts, msg, ups in relevant_data]

        # Среднее = сумма за период / количество секунд
        # (это приближённо, т.к. может не быть данных для всех секунд, но близко к реальности)
        total_secs = min(len(relevant_data), window_seconds)
        if total_secs == 0:
            total_secs = 1 # избегаем деления на 0, если данных нет

        avg_msg_rps = sum(msg_counts) / total_secs
        avg_ups_rps = sum(ups_counts) / total_secs

        # Пик = максимальное значение за период
        peak_msg_rps = max(msg_counts) if msg_counts else 0
        peak_ups_rps = max(ups_counts) if ups_counts else 0

        return avg_msg_rps, peak_msg_rps, avg_ups_rps, peak_ups_rps

    def get_rps_stats_for_last_minutes(self, minutes: int = 5) -> Dict[str, float]:
        """Получить avg и peak RPS/UPS за последние N минут"""
        window_seconds = minutes * 60
        avg_msg, peak_msg, avg_ups, peak_ups = self._calculate_rps_for_window(window_seconds)
        return {
            "avg_msg_rps": avg_msg,
            "peak_msg_rps": peak_msg,
            "avg_ups_rps": avg_ups,
            "peak_ups_rps": peak_ups
        }

    def get_current_rps(self) -> tuple[float, float]:
        """Получить RPS/UPS за текущую (последнюю завершённую) секунду"""
        # Текущая секунда ещё не завершена, поэтому берём предыдущую
        now = int(time.time())
        last_completed_second = now - 1
        with self.timestamp_lock:
            # Ищем в истории последнюю завершённую секунду
            for ts, msg, ups in reversed(self.rps_history):
                if ts == last_completed_second:
                    return float(msg), float(ups)
            # Если не нашли (например, только начали), возвращаем 0
            return 0.0, 0.0


    def get_ping_stats(self) -> Dict[str, Optional[float]]:
        if not self.ping_history:
            return {"best": None, "worst": None, "avg": None}
        pings = list(self.ping_history)
        return {
            "best": min(pings),
            "worst": max(pings),
            "avg": sum(pings) / len(pings),
        }

    def get_error_stats(self) -> Dict:
        """Возвращает статистику ошибок"""
        with self.counter_lock:
            total = self.error_count
            types = dict(self.error_types)
        return {
            "total": total,
            "types": types
        }

    def get_stats_detailed(self) -> Dict:
        # Обновляем историю RPS перед выдачей статистики
        self._update_current_second()

        with self.counter_lock:
            total = self.total_requests
            handled = self.handled_requests
            total_unique = len(self.unique_users)
            error_count = self.error_count

        success_rate = (handled / total * 100) if total > 0 else 100.0
        current_msg_rps, current_ups_rps = self.get_current_rps()
        rps_5min_stats = self.get_rps_stats_for_last_minutes(5)

        success_info = f"{handled}/{total} ({success_rate:.1f}%)"

        return {
            "bot_id": self.bot_id,
            "total": total,
            "handled": handled,
            "total_unique": total_unique,
            "success_rate": round(success_rate, 2),
            "success_info": success_info,
            # Текущие (последней секунды)
            "current_msg_rps": round(current_msg_rps, 2),
            "current_ups_rps": round(current_ups_rps, 2),
            # За 5 минут (avg и peak)
            "avg_msg_rps_5min": round(rps_5min_stats["avg_msg_rps"], 2),
            "peak_msg_rps_5min": round(rps_5min_stats["peak_msg_rps"], 2),
            "avg_ups_rps_5min": round(rps_5min_stats["avg_ups_rps"], 2),
            "peak_ups_rps_5min": round(rps_5min_stats["peak_ups_rps"], 2),
            "error_count": error_count,
            "error_stats": self.get_error_stats(),
            "ping_stats": self.get_ping_stats(),
        }

    async def get_stats_detailed_async(self) -> Dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_stats_detailed)

    def reset_stats(self):
        with self.counter_lock:
            self.total_requests = 0
            self.handled_requests = 0
            self.error_count = 0
            self.error_types.clear()
            self.unique_users.clear()
        with self.timestamp_lock:
            self.rps_history.clear()
            self.ping_history.clear()
        # Сбрасываем текущую секунду
        self.current_second = int(time.time())
        self.current_msg_count = 0
        self.current_ups_set.clear()
        logger.info(f"📊 Статистика для бота {self.bot_id} сброшена")