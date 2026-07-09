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
        self.db_times = deque(maxlen=20)  # время БД
        self.api_calls = deque(maxlen=20)  # вызовы API
        self.transactions = deque(maxlen=20)  # транзакции БД
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
        # Копируем данные под блокировкой
        with self.lock:
            handler_times_copy = list(self.handler_times)
            db_times_copy = list(self.db_times)
            api_calls_copy = list(self.api_calls)
            transactions_copy = list(self.transactions)

        # Вычисления вне блокировки для повышения производительности
        # Используем медиану вместо среднего для устойчивости к выбросам
        avg_handler_time = statistics.median(handler_times_copy) if handler_times_copy else 0
        avg_db_time = statistics.median(db_times_copy) if db_times_copy else 0

        # Увеличиваем окно для более точных расчётов частоты (3 секунды)
        time_window = 3.0  # секунд
        current_time = time.time()

        # Считаем API вызовы за фиксированное окно времени
        recent_api_calls = [t for t in api_calls_copy if current_time - t <= time_window]
        api_calls_per_sec = len(recent_api_calls) / time_window if recent_api_calls else 0

        # Аналогично для транзакций
        recent_transactions = [t for t in transactions_copy if current_time - t <= time_window]
        db_transactions_per_sec = len(recent_transactions) / time_window if recent_transactions else 0

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

    def _get_empty_stats(self) -> Dict[str, float]:
        """Возвращает пустую статистику"""
        return {
            "avg_load": 0.0, "min_load": 0.0, "max_load": 0.0, "trend_load": 0.0,
            "avg_handler_time": 0.0, "avg_db_time": 0.0,
            "avg_api_calls_per_sec": 0.0, "avg_db_transactions_per_sec": 0.0
        }

    def get_stats_for_last_minutes(self, minutes: int) -> Dict[str, float]:
        """Получить статистику нагрузки за последние N минут с весовыми коэффициентами"""
        points = self.get_last_minutes(minutes)
        if not points:
            return self._get_empty_stats()

        # Создаём веса: более новые точки имеют больший вес (линейное увеличение)
        weights = [i + 1 for i in range(len(points))]
        total_weight = sum(weights)
        weights = [w / total_weight for w in weights]

        # Распаковка
        loads = [load for _, load, _ in points]
        avg_handler_times = [m["avg_handler_time_ms"] for _, _, m in points]
        avg_db_times = [m["avg_db_time_ms"] for _, _, m in points]
        avg_api_calls = [m["api_calls_per_sec"] for _, _, m in points]
        avg_db_trans = [m["db_transactions_per_sec"] for _, _, m in points]

        # Средневзвешенные значения
        avg_load = sum(l * w for l, w in zip(loads, weights))
        min_load = min(loads)
        max_load = max(loads)

        # Более точный расчёт тренда через линейную регрессию
        if len(points) > 1:
            x = list(range(len(points)))
            y = loads
            n = len(x)
            # Линейная регрессия
            sum_x = sum(x)
            sum_y = sum(y)
            sum_xy = sum(x_i * y_i for x_i, y_i in zip(x, y))
            sum_x2 = sum(x_i ** 2 for x_i in x)

            if (n * sum_x2 - sum_x ** 2) != 0:
                slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
                trend_load = slope * len(points)  # Общее изменение за период
            else:
                trend_load = 0.0
        else:
            trend_load = 0.0

        # Средние метрики (простые средние)
        avg_handler_time = statistics.mean(avg_handler_times) if avg_handler_times else 0
        avg_db_time = statistics.mean(avg_db_times) if avg_db_times else 0
        avg_api_calls_per_sec = statistics.mean(avg_api_calls) if avg_api_calls else 0
        avg_db_transactions_per_sec = statistics.mean(avg_db_trans) if avg_db_trans else 0

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
        # Используем более плавные формулы с оптимизированными порогами
        # 1. Время обработки хендлера (влияние: 40%)
        # Оптимизированный порог: 800ms вместо 1000ms для более раннего реагирования
        handler_load = min(40, (metrics["avg_handler_time_ms"] / 800) * 40)

        # 2. Время БД (влияние: 30%)
        # Оптимизированный порог: 400ms вместо 500ms
        db_load = min(30, (metrics["avg_db_time_ms"] / 400) * 30)

        # 3. API вызовы (влияние: 20%)
        # Оптимизированный порог: 8 вызовов/сек вместо 10
        api_load = min(20, (metrics["api_calls_per_sec"] / 8) * 20)

        # 4. Транзакции БД (влияние: 10%)
        # Оптимизированный порог: 4 транзакции/сек вместо 5
        db_trans_load = min(10, (metrics["db_transactions_per_sec"] / 4) * 10)

        return min(100, handler_load + db_load + api_load + db_trans_load)

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

    def get_load_level(self, load_percent: float) -> str:
        """Определяет уровень нагрузки"""
        if load_percent < 30:
            return "low"
        elif load_percent < 70:
            return "medium"
        else:
            return "high"

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