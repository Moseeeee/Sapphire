import time
from collections import deque
from typing import Dict
import threading
import logging
import statistics

logger = logging.getLogger(__name__)


class PerBotRPS:
    """Статистика RPS для конкретного бота"""

    def __init__(self, bot_id: str):
        self.bot_id = bot_id

        # Счетчики запросов
        self.total_requests = 0
        self.handled_requests = 0
        self.request_timestamps = deque(maxlen=100000)
        self.handled_timestamps = deque(maxlen=100000)
        self.unique_users = set()
        self.unique_users_timestamps = deque(maxlen=100000)

        # Пинг
        self.ping_times = deque(maxlen=1000)
        self.best_ping = float('inf')
        self.worst_ping = 0

        # Ошибки
        self.error_count = 0
        self.error_timestamps = deque(maxlen=1000)

        # Блокировки
        self._counter_lock = threading.Lock()
        self._timestamp_lock = threading.Lock()
        self._ping_lock = threading.Lock()
        self._error_lock = threading.Lock()

    def record_request(self):
        with self._counter_lock:
            self.total_requests += 1
        with self._timestamp_lock:
            self.request_timestamps.append(time.time())

    def record_handled(self):
        with self._counter_lock:
            self.handled_requests += 1
        with self._timestamp_lock:
            self.handled_timestamps.append(time.time())

    def record_unique_user(self, user_id: int):
        with self._counter_lock:
            self.unique_users.add(user_id)
        with self._timestamp_lock:
            self.unique_users_timestamps.append((time.time(), user_id))

    def record_ping(self, ping_time: float):
        with self._ping_lock:
            self.ping_times.append(ping_time)
            if ping_time < self.best_ping:
                self.best_ping = ping_time
            if ping_time > self.worst_ping:
                self.worst_ping = ping_time

    def record_error(self):
        with self._error_lock:
            self.error_count += 1
            self.error_timestamps.append(time.time())

    def _calculate_rps(self, timestamps: deque, window_seconds: float = 1.0) -> float:
        if not timestamps:
            return 0.0

        now = time.time()
        cutoff = now - window_seconds

        with self._timestamp_lock:
            timestamps_copy = list(timestamps)

        count = 0
        for ts in reversed(timestamps_copy):
            if ts >= cutoff:
                count += 1
            else:
                break

        return count / window_seconds

    def _calculate_ups(self, window_seconds: float = 1.0) -> float:
        if not self.unique_users_timestamps:
            return 0.0

        now = time.time()
        cutoff = now - window_seconds
        unique_users = set()

        with self._timestamp_lock:
            timestamps_copy = list(self.unique_users_timestamps)

        for ts, user_id in reversed(timestamps_copy):
            if ts >= cutoff:
                unique_users.add(user_id)
            else:
                break

        return len(unique_users) / window_seconds

    def get_rps_stats_for_last_minutes(self, minutes: int) -> Dict[str, float]:
        """Получить статистику RPS за последние N минут"""
        cutoff = time.time() - (minutes * 60)

        with self._timestamp_lock:
            # Считаем сообщения
            msg_count = sum(1 for ts in self.request_timestamps if ts >= cutoff)
            avg_msg_rps = msg_count / (minutes * 60) if minutes > 0 else 0

            # Пиковые значения
            peak_msg_rps = 0
            current_window = deque()
            for ts in self.request_timestamps:
                if ts >= cutoff:
                    current_window.append(ts)
                    # Удаляем старые
                    while current_window and current_window[0] < ts - 1:
                        current_window.popleft()
                    peak_msg_rps = max(peak_msg_rps, len(current_window))

            # Уникальные пользователи
            unique_users = set()
            for ts, user_id in self.unique_users_timestamps:
                if ts >= cutoff:
                    unique_users.add(user_id)
            avg_ups_rps = len(unique_users) / (minutes * 60) if minutes > 0 else 0

            # Пик уникальных пользователей (за 1 секунду)
            peak_ups_rps = 0
            current_users_window = deque()
            for ts, user_id in self.unique_users_timestamps:
                if ts >= cutoff:
                    current_users_window.append((ts, user_id))
                    # Удаляем старые
                    while current_users_window and current_users_window[0][0] < ts - 1:
                        current_users_window.popleft()

                    # Считаем уникальных в окне
                    unique_in_window = len(set(uid for _, uid in current_users_window))
                    peak_ups_rps = max(peak_ups_rps, unique_in_window)

        return {
            "avg_msg_rps": avg_msg_rps,
            "peak_msg_rps": peak_msg_rps,
            "avg_ups_rps": avg_ups_rps,
            "peak_ups_rps": peak_ups_rps,
            "total_msgs": msg_count,
            "total_unique_users": len(unique_users)
        }

    def get_ping_stats(self) -> Dict[str, float]:
        with self._ping_lock:
            if not self.ping_times:
                return {"avg": 0, "best": 0, "worst": 0}

            avg_ping = statistics.mean(self.ping_times)
            return {
                "avg": avg_ping,
                "best": self.best_ping if self.best_ping != float('inf') else 0,
                "worst": self.worst_ping
            }

    async def get_stats_detailed_async(self) -> Dict:
        """Асинхронная версия получения статистики"""
        with self._counter_lock:
            total = self.total_requests
            handled = self.handled_requests
            total_unique = len(self.unique_users)

        # Процент успешной обработки
        percent = (handled / total * 100) if total > 0 else 100.0

        # RPS за разные периоды
        rps_1s = self._calculate_rps(self.request_timestamps, 1.0)
        handled_rps_1s = self._calculate_rps(self.handled_timestamps, 1.0)
        ups_1s = self._calculate_ups(1.0)

        rps_5min = self._calculate_rps(self.request_timestamps, 300.0)
        handled_rps_5min = self._calculate_rps(self.handled_timestamps, 300.0)

        # Пинг
        ping_stats = self.get_ping_stats()

        return {
            "total": total,
            "handled": handled,
            "total_unique": total_unique,
            "percent": round(percent, 2),
            "rps_1s": round(rps_1s, 2),
            "handled_rps_1s": round(handled_rps_1s, 2),
            "ups_1s": round(ups_1s, 2),
            "rps_5min": round(rps_5min, 2),
            "handled_rps_5min": round(handled_rps_5min, 2),
            "ping_stats": ping_stats,
            "error_count": self.error_count,
            "current_msg_rps": rps_1s,
            "current_ups_rps": ups_1s,
            "success_info": f"{handled}/{total} ({percent:.1f}%)",
            "display": f"({handled}/{total}) → {percent:.2f}% | "
                       f"RPS: {handled_rps_1s:.1f}/{rps_1s:.1f}/s | "
                       f"Users: {total_unique} ({ups_1s:.1f}/s)"
        }

    def reset_stats(self):
        """Сбросить статистику"""
        with self._counter_lock:
            self.total_requests = 0
            self.handled_requests = 0
            self.unique_users.clear()

        with self._timestamp_lock:
            self.request_timestamps.clear()
            self.handled_timestamps.clear()
            self.unique_users_timestamps.clear()

        with self._ping_lock:
            self.ping_times.clear()
            self.best_ping = float('inf')
            self.worst_ping = 0

        with self._error_lock:
            self.error_count = 0
            self.error_timestamps.clear()