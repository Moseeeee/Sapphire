import statistics
import time
from collections import deque
from typing import Dict, List, Tuple
import threading
import logging
from handlers.BotAutomaticWork.Middleware.MiddlewareMultiBot.BotRPSManager import bot_rps_manager

logger = logging.getLogger(__name__)

# ============================================================================
# КЛАСС: ХРАНЕНИЕ ИСТОРИИ НАГРУЗКИ БОТА
# ============================================================================
class BotLoadHistory:
    def __init__(self, bot_id: str, max_minutes: int = 5):
        self.bot_id = bot_id
        self.max_minutes = max_minutes
        self.max_points = max_minutes * 60  # 1 точка в секунду
        # (timestamp, load_percent, msg_rps, ups_rps, queue_time, errors, avg_ping, cpu, ram)
        self.history = deque(maxlen=self.max_points)
        self.lock = threading.Lock()

    def add_point(self, load_percent: float, msg_rps: float, ups_rps: float, queue_time: float, errors: int, avg_ping: float, cpu: float, ram: float):
        """Добавить точку нагрузки в историю"""
        now = time.time()
        with self.lock:
            self.history.append((now, load_percent, msg_rps, ups_rps, queue_time, errors, avg_ping, cpu, ram))

    def get_last_minutes(self, minutes: int) -> List[Tuple[float, float, float, float, float, int, float, float, float]]:
        """Получить данные за последние N минут: [(timestamp, load, ...), ...]"""
        now = time.time()
        cutoff = now - (minutes * 60)
        with self.lock:
            return [(ts, load, msg, ups, queue, err, ping, cpu, ram) for ts, load, msg, ups, queue, err, ping, cpu, ram in self.history if ts >= cutoff]

    def get_stats_for_last_minutes(self, minutes: int) -> Dict[str, float]:
        """Получить расширенную статистику за последние N минут"""
        points = self.get_last_minutes(minutes)
        if not points:
            return {
                "avg_load": 0.0, "min_load": 0.0, "max_load": 0.0, "trend_load": 0.0,
                "avg_msg_rps": 0.0, "max_msg_rps": 0.0, "avg_ups_rps": 0.0, "max_ups_rps": 0.0,
                "avg_queue_time": 0.0, "max_queue_time": 0.0, "queue_spikes_count": 0,
                "avg_ping": 0.0, "max_ping": 0.0, "ping_spikes_count": 0,
                "errors_count": 0, "errors_rate_per_min": 0.0,
                "avg_cpu": 0.0, "max_cpu": 0.0, "avg_ram": 0.0, "max_ram": 0.0
            }

        # Распаковка
        loads = [load for _, load, _, _, _, _, _, _, _ in points]
        msg_rps = [msg for _, _, msg, _, _, _, _, _, _ in points]
        ups_rps = [ups for _, _, _, ups, _, _, _, _, _ in points]
        queue_times = [queue for _, _, _, _, queue, _, _, _, _ in points]
        errors = [err for _, _, _, _, _, err, _, _, _ in points]
        pings = [ping for _, _, _, _, _, _, ping, _, _ in points]
        cpu_vals = [cpu for _, _, _, _, _, _, _, cpu, _ in points]
        ram_vals = [ram for _, _, _, _, _, _, _, _, ram in points]

        # Основные метрики
        avg_load = statistics.mean(loads)
        min_load = min(loads)
        max_load = max(loads)
        first_load = points[0][1]
        last_load = points[-1][1]
        trend_load = last_load - first_load

        # RPS
        avg_msg_rps = statistics.mean(msg_rps)
        max_msg_rps = max(msg_rps)
        avg_ups_rps = statistics.mean(ups_rps)
        max_ups_rps = max(ups_rps)

        # Очередь
        avg_queue_time = statistics.mean(queue_times)
        max_queue_time = max(queue_times)
        queue_spikes_count = sum(1 for q in queue_times if q >= 1.0)  # >1с = пик

        # Пинги
        avg_ping = statistics.mean(pings)
        max_ping = max(pings)
        ping_spikes_count = sum(1 for p in pings if p >= 500)  # >500ms = пик

        # Ошибки
        total_errors = sum(errors)
        errors_rate_per_min = total_errors / minutes

        # Система
        avg_cpu = statistics.mean(cpu_vals)
        max_cpu = max(cpu_vals)
        avg_ram = statistics.mean(ram_vals)
        max_ram = max(ram_vals)

        return {
            "avg_load": avg_load,
            "min_load": min_load,
            "max_load": max_load,
            "trend_load": trend_load,
            "avg_msg_rps": avg_msg_rps,
            "max_msg_rps": max_msg_rps,
            "avg_ups_rps": avg_ups_rps,
            "max_ups_rps": max_ups_rps,
            "avg_queue_time": avg_queue_time,
            "max_queue_time": max_queue_time,
            "queue_spikes_count": queue_spikes_count,
            "avg_ping": avg_ping,
            "max_ping": max_ping,
            "ping_spikes_count": ping_spikes_count,
            "errors_count": total_errors,
            "errors_rate_per_min": errors_rate_per_min,
            "avg_cpu": avg_cpu,
            "max_cpu": max_cpu,
            "avg_ram": avg_ram,
            "max_ram": max_ram
        }

    def get_current_load(self) -> float:
        """Получить текущую нагрузку (последняя точка)"""
        with self.lock:
            if self.history:
                return self.history[-1][1]  # load_percent
            return 0.0


# ============================================================================
# КЛАСС: ОЦЕНКА НАГРУЗКИ ВСЕХ БОТОВ
# ============================================================================
class BotLoadEstimator:
    def __init__(self):
        self.bot_histories: Dict[str, BotLoadHistory] = {}
        self.lock = threading.Lock()

    def _get_history(self, bot_id: str) -> BotLoadHistory:
        """Получить или создать историю для бота"""
        with self.lock:
            if bot_id not in self.bot_histories:
                self.bot_histories[bot_id] = BotLoadHistory(bot_id)
            return self.bot_histories[bot_id]

    async def estimate_loads(self) -> Dict[str, float]:
        """
        Возвращает нагрузку каждого бота в процентах (0–100%)
        И сохраняет в историю
        """
        from handlers.BotAutomaticWork.Gonfig.multi_bot_config import MultiBotConfig
        from handlers.BotAutomaticWork.Middleware.MiddlewareBackground import get_queue_delay_for_bot
        import psutil

        bot_scores = {}
        for cfg in MultiBotConfig.BOTS:
            bot_id = cfg["id"]
            stats = await bot_rps_manager.get_bot_stats_detailed(bot_id) or {}

            # Собираем метрики
            msg_rps = stats.get("msg_rps_1s", 0)
            ups_rps = stats.get("ups_rps_1s", 0)
            queue_time = await get_queue_delay_for_bot(bot_id)
            errors = stats.get("error_count", 0)
            avg_ping = stats.get("ping_stats", {}).get("avg", 0)

            # Системные метрики
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent

            # Считаем "ресурсный счёт"
            score = (
                    (msg_rps * 0.5) +
                    (ups_rps * 0.5) +
                    (queue_time * 10) +
                    (errors * 0.1)
                # + (cpu + ram) / 2
            )

            bot_scores[bot_id] = (score, msg_rps, ups_rps, queue_time, errors, avg_ping, cpu, ram)

        # Нормализуем в 0–100%
        scores_only = [s[0] for s in bot_scores.values()]
        max_score = max(scores_only) if scores_only else 1
        if max_score == 0:
            loads = {bot_id: 0.0 for bot_id in bot_scores}
        else:
            loads = {bot_id: (score[0] / max_score) * 100 for bot_id, score in bot_scores.items()}

        # Сохраняем в историю (все метрики)
        for bot_id, (score, msg_rps, ups_rps, queue_time, errors, avg_ping, cpu, ram) in bot_scores.items():
            history = self._get_history(bot_id)
            history.add_point(loads[bot_id], msg_rps, ups_rps, queue_time, errors, avg_ping, cpu, ram)

        return loads

    def get_bot_history_stats(self, bot_id: str, minutes: int = 5) -> Dict:
        """Получить расширенную статистику нагрузки бота за последние N минут"""
        history = self._get_history(bot_id)
        return history.get_stats_for_last_minutes(minutes)

    def get_bot_current_load(self, bot_id: str) -> float:
        """Получить текущую нагрузку бота"""
        history = self._get_history(bot_id)
        return history.get_current_load()

    def get_all_bot_histories(self) -> Dict[str, List[Tuple[float, float]]]:
        """Получить всю историю для всех ботов (для графиков)"""
        result = {}
        with self.lock:
            for bot_id, history in self.bot_histories.items():
                # Только (timestamp, load) для графиков
                result[bot_id] = [(ts, load) for ts, load, _, _, _, _, _, _, _ in history.history]
        return result


# ============================================================================
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР
# ============================================================================
bot_load_estimator = BotLoadEstimator()

# ============================================================================
# ФУНКЦИИ ДЛЯ ИСПОЛЬЗОВАНИЯ В КОМАНДАХ
# ============================================================================
async def estimate_all_bot_loads() -> Dict[str, float]:
    """Получить нагрузки всех ботов"""
    return await bot_load_estimator.estimate_loads()

def get_bot_load_history_stats(bot_id: str, minutes: int = 5) -> Dict:
    """Получить расширенную статистику нагрузки за N минут"""
    return bot_load_estimator.get_bot_history_stats(bot_id, minutes)

def get_current_bot_load(bot_id: str) -> float:
    """Получить текущую нагрузку бота"""
    return bot_load_estimator.get_bot_current_load(bot_id)