import time
from collections import deque
from typing import Dict
import threading
import asyncio

# Глобальные счетчики
_total_requests = 0
_handled_requests = 0
_request_timestamps = deque(maxlen=100000)
_handled_timestamps = deque(maxlen=100000)
_unique_users = set()
_unique_users_timestamps = deque(maxlen=100000)

# Блокировки для потокобезопасности
_counter_lock = threading.Lock()
_timestamp_lock = threading.Lock()


def record_request():
    """Учесть входящий запрос"""
    global _total_requests

    with _counter_lock:
        _total_requests += 1

    with _timestamp_lock:
        _request_timestamps.append(time.time())


def record_handled():
    """Учесть обработанный запрос"""
    global _handled_requests

    with _counter_lock:
        _handled_requests += 1

    with _timestamp_lock:
        _handled_timestamps.append(time.time())


def record_unique_user(user_id: int):
    """Учесть уникального пользователя"""
    with _counter_lock:
        _unique_users.add(user_id)

    with _timestamp_lock:
        _unique_users_timestamps.append((time.time(), user_id))


def _calculate_rps(timestamps: deque, window_seconds: float = 1.0) -> float:
    """Рассчитать RPS за указанный период"""
    if not timestamps:
        return 0.0

    now = time.time()
    cutoff = now - window_seconds

    # Эффективный подсчет элементов в окне
    with _timestamp_lock:
        # Создаем копию для безопасности
        timestamps_copy = list(timestamps)

    # Считаем с конца (новые элементы в конце)
    count = 0
    for ts in reversed(timestamps_copy):
        if ts >= cutoff:
            count += 1
        else:
            break

    return count / window_seconds


def _calculate_ups(timestamps: deque, window_seconds: float = 1.0) -> float:
    """Рассчитать Unique Users Per Second"""
    if not timestamps:
        return 0.0

    now = time.time()
    cutoff = now - window_seconds
    unique_users = set()

    with _timestamp_lock:
        timestamps_copy = list(timestamps)

    for ts, user_id in reversed(timestamps_copy):
        if ts >= cutoff:
            unique_users.add(user_id)
        else:
            break

    return len(unique_users) / window_seconds


def get_rps_detailed() -> Dict:
    """Получить детальную статистику RPS"""
    with _counter_lock:
        total = _total_requests
        handled = _handled_requests
        total_unique = len(_unique_users)

    # Рассчитываем процент успешной обработки
    percent = (handled / total * 100) if total > 0 else 100.0

    # RPS за разные периоды
    rps_1s = _calculate_rps(_request_timestamps, 1.0)
    handled_rps_1s = _calculate_rps(_handled_timestamps, 1.0)
    ups_1s = _calculate_ups(_unique_users_timestamps, 1.0)

    rps_5min = _calculate_rps(_request_timestamps, 300.0)
    handled_rps_5min = _calculate_rps(_handled_timestamps, 300.0)
    ups_5min = _calculate_ups(_unique_users_timestamps, 300.0)

    rps_1h = _calculate_rps(_request_timestamps, 3600.0)
    handled_rps_1h = _calculate_rps(_handled_timestamps, 3600.0)
    ups_1h = _calculate_ups(_unique_users_timestamps, 3600.0)

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
        "ups_5min": round(ups_5min, 2),
        "rps_1h": round(rps_1h, 2),
        "handled_rps_1h": round(handled_rps_1h, 2),
        "ups_1h": round(ups_1h, 2),
        "display": f"({handled}/{total}) → {percent:.2f}% | "
                   f"RPS: {handled_rps_1s:.1f}/{rps_1s:.1f}/s | "
                   f"Users: {total_unique} ({ups_1s:.1f}/s)"
    }


async def get_rps_detailed_async() -> Dict:
    """Асинхронная версия получения статистики RPS"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_rps_detailed)
