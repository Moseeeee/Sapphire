import time
import threading
import statistics
from collections import deque
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# КЛАСС: СБОР ВНУТРЕННИХ МЕТРИК БОТА
# ============================================================================
class BotInternalMetrics:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self.lock = threading.Lock()
        # Хранит: timestamp -> метрика
        # maxlen = 20 → среднее за последние ~2 секунды (при 10 замерах/сек)
        self.handler_times = deque(maxlen=20)  # время обработки хендлера
        self.db_times = deque(maxlen=20)       # время БД
        self.api_calls = deque(maxlen=20)      # вызовы API
        self.transactions = deque(maxlen=20)   # транзакции БД
        self.last_activity_time = time.time()  # время последней активности

    def record_handler_time(self, duration_ms: float):
        with self.lock:
            self.handler_times.append(duration_ms)
            self.last_activity_time = time.time()

    def record_db_time(self, duration_ms: float):
        with self.lock:
            self.db_times.append(duration_ms)
            self.last_activity_time = time.time()

    def record_api_call(self):
        with self.lock:
            self.api_calls.append(time.time())
            self.last_activity_time = time.time()

    def record_transaction(self):
        with self.lock:
            self.transactions.append(time.time())
            self.last_activity_time = time.time()

    def get_current_metrics(self) -> Dict[str, float]:
        with self.lock:
            # Считаем средние за последние 20 точек (или меньше, если нет)
            avg_handler_time = statistics.mean(list(self.handler_times)) if self.handler_times else 0
            avg_db_time = statistics.mean(list(self.db_times)) if self.db_times else 0
            # API вызовы в секунду: за последние 20 временных точек
            if self.api_calls:
                time_span = time.time() - min(self.api_calls)
                api_calls_per_sec = len(self.api_calls) / time_span if time_span > 0 else 0
            else:
                api_calls_per_sec = 0

            if self.transactions:
                time_span = time.time() - min(self.transactions)
                db_transactions_per_sec = len(self.transactions) / time_span if time_span > 0 else 0
            else:
                db_transactions_per_sec = 0

            return {
                "avg_handler_time_ms": avg_handler_time,
                "avg_db_time_ms": avg_db_time,
                "api_calls_per_sec": api_calls_per_sec,
                "db_transactions_per_sec": db_transactions_per_sec
            }


# ============================================================================
# КЛАСС: ХРАНЕНИЕ ИСТОРИИ НАГРУЗКИ БОТА
# ============================================================================
class BotLoadHistory:
    def __init__(self, bot_id: str, max_minutes: int = 5):
        self.bot_id = bot_id
        self.max_minutes = max_minutes
        self.max_points = max_minutes * 60  # 1 точка в секунду
        # (timestamp, load_percent, metrics)
        self.history = deque(maxlen=self.max_points)
        self.lock = threading.Lock()

    def add_point(self, load_percent: float, metrics: Dict[str, float]):
        """Добавить точку нагрузки в историю"""
        now = time.time()
        with self.lock:
            self.history.append((now, load_percent, metrics))

    def get_last_minutes(self, minutes: int) -> List[Tuple[float, float, Dict[str, float]]]:
        """Получить данные за последние N минут: [(timestamp, load, metrics), ...]"""
        now = time.time()
        cutoff = now - (minutes * 60)
        with self.lock:
            return [(ts, load, m) for ts, load, m in self.history if ts >= cutoff]

    def get_stats_for_last_minutes(self, minutes: int) -> Dict[str, float]:
        """Получить статистику нагрузки за последние N минут"""
        points = self.get_last_minutes(minutes)
        if not points:
            return {
                "avg_load": 0.0, "min_load": 0.0, "max_load": 0.0, "trend_load": 0.0,
                "avg_handler_time": 0.0, "avg_db_time": 0.0,
                "avg_api_calls_per_sec": 0.0, "avg_db_transactions_per_sec": 0.0
            }

        # Распаковка
        loads = [load for _, load, _ in points]
        avg_handler_times = [m["avg_handler_time_ms"] for _, _, m in points]
        avg_db_times = [m["avg_db_time_ms"] for _, _, m in points]
        avg_api_calls = [m["api_calls_per_sec"] for _, _, m in points]
        avg_db_trans = [m["db_transactions_per_sec"] for _, _, m in points]

        # Основные метрики
        avg_load = statistics.mean(loads)
        min_load = min(loads)
        max_load = max(loads)
        first_load = points[0][1]
        last_load = points[-1][1]
        trend_load = last_load - first_load

        # Средние метрики
        avg_handler_time = statistics.mean(avg_handler_times)
        avg_db_time = statistics.mean(avg_db_times)
        avg_api_calls_per_sec = statistics.mean(avg_api_calls)
        avg_db_transactions_per_sec = statistics.mean(avg_db_trans)

        return {
            "avg_load": avg_load,
            "min_load": min_load,
            "max_load": max_load,
            "trend_load": trend_load,
            "avg_handler_time": avg_handler_time,
            "avg_db_time": avg_db_time,
            "avg_api_calls_per_sec": avg_api_calls_per_sec,
            "avg_db_transactions_per_sec": avg_db_transactions_per_sec
        }

    def get_current_load(self) -> float:
        """Получить текущую нагрузку (последняя точка)"""
        with self.lock:
            if self.history:
                return self.history[-1][1]  # load_percent
            return 0.0


# ============================================================================
# КЛАСС: СУПЕР ТОЧНЫЙ ОПРЕДЕЛИТЕЛЬ НАГРУЗКИ (ТОЛЬКО ВНУТРЕННЯЯ)
# ============================================================================
class SuperBotLoadEstimator:
    def __init__(self):
        self.bot_metrics: Dict[str, BotInternalMetrics] = {}
        self.bot_histories: Dict[str, BotLoadHistory] = {}
        self.lock = threading.Lock()

    def _get_metrics(self, bot_id: str) -> BotInternalMetrics:
        with self.lock:
            if bot_id not in self.bot_metrics:
                self.bot_metrics[bot_id] = BotInternalMetrics(bot_id)
            return self.bot_metrics[bot_id]

    def _get_history(self, bot_id: str) -> BotLoadHistory:
        with self.lock:
            if bot_id not in self.bot_histories:
                self.bot_histories[bot_id] = BotLoadHistory(bot_id)
            return self.bot_histories[bot_id]

    def _calculate_internal_load(self, metrics: Dict[str, float]) -> float:
        """Рассчитывает нагрузку на основе внутренних метрик"""
        load = 0.0

        # 1. Время обработки хендлера (влияние: 40%)
        # Если хендлер работает > 1000ms — это критично
        handler_time_load = min(40, (metrics["avg_handler_time_ms"] / 1000) * 40)
        load += handler_time_load

        # 2. Время БД (влияние: 30%)
        # Если БД тормозит > 500ms — это критично
        db_time_load = min(30, (metrics["avg_db_time_ms"] / 500) * 30)
        load += db_time_load

        # 3. API вызовы (влияние: 20%)
        # Если > 10 вызовов/сек — бот "болтается"
        api_load = min(20, (metrics["api_calls_per_sec"] / 10) * 20)
        load += api_load

        # 4. Транзакции БД (влияние: 10%)
        # Если > 5 транзакций/сек — бот "пишет много"
        db_trans_load = min(10, (metrics["db_transactions_per_sec"] / 5) * 10)
        load += db_trans_load

        return min(100, load)

    def calculate_bot_load(self, bot_id: str) -> float:
        """Рассчитывает супер точную нагрузку бота (0–100%)"""
        metrics = self._get_metrics(bot_id).get_current_metrics()
        internal_load = self._calculate_internal_load(metrics)

        # Сохраняем в историю
        history = self._get_history(bot_id)
        history.add_point(internal_load, metrics)

        return internal_load

    def get_bot_metrics(self, bot_id: str) -> Dict[str, float]:
        """Получить текущие внутренние метрики бота"""
        return self._get_metrics(bot_id).get_current_metrics()

    def get_bot_history_stats(self, bot_id: str, minutes: int = 5) -> Dict[str, float]:
        """Получить статистику нагрузки бота за последние N минут"""
        history = self._get_history(bot_id)
        return history.get_stats_for_last_minutes(minutes)

    def get_bot_current_load(self, bot_id: str) -> float:
        """Получить текущую нагрузку бота"""
        history = self._get_history(bot_id)
        return history.get_current_load()

    async def estimate_all_loads(self) -> Dict[str, float]:
        """Получить нагрузки всех ботов"""
        loads = {}
        with self.lock:
            for bot_id in self.bot_metrics:
                loads[bot_id] = self.calculate_bot_load(bot_id)
        return loads


# ============================================================================
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР
# ============================================================================
super_bot_load_estimator = SuperBotLoadEstimator()