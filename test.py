import asyncio
import logging
import random
import time
from typing import List, Deque
from collections import deque
from datetime import datetime
import plotext as plt
from aiogram.types import Update, Message, User, Chat
from aiogram import Bot

logger = logging.getLogger(__name__)

# === ГЛОБАЛЬНЫЕ НАСТРОЙКИ НАГРУЗКИ ===
LOAD_TEST_USER_ID = 6282374712
REPORT_INTERVAL = 5  # Отчёты каждые 5 секунд
INITIAL_RPS = 100_000  # Начинаем с 1к RPS
MAX_RPS = 5_000_000  # Максимально до 50k RPS
RPS_INCREASE_STEP = 1.50  # Увеличиваем нагрузку в 1.25 раза каждые 10 секунд
WORKER_INCREASE_INTERVAL = 20  # Увеличиваем воркеры каждые 20 секунд

CURRENT_RPS = INITIAL_RPS
RPS_COUNTER = 0
LAST_REPORT_TIME = time.time()
ACTIVE_WORKERS = 500_000  # Начинаем с 5 воркеров
MAX_WORKERS = 3_000_000  # Максимум 30 воркеров
START_TIME = time.time()

# История для графиков
RPS_HISTORY: Deque[float] = deque(maxlen=30)
TARGET_RPS_HISTORY: Deque[int] = deque(maxlen=30)
TIMESTAMPS: Deque[str] = deque(maxlen=30)
WORKER_HISTORY: Deque[int] = deque(maxlen=30)

# === ПОДГОТОВКА ДАННЫХ ===
USER_IDS_POOL = list(range(100_000_000, 100_000_000 + 500_000))  # 500k пользователей

TEXT_COMMANDS = [
    *[".статус"] * 100,
    *[".помощь"] * 34,
    *[".время"] * 263,
    *[".пинг"] * 232322,
    *[".check"] * 24,
    *["/start"] * 166523,
    *["/help"] * 154,
    *["Привет"] * 122223543,
    *["Как дела?"] * 1565642,
    *["Что нового?"] * 15667643,
    *[f".команда_{i}" for i in range(10)]
]

# Пул готовых updates для скорости
UPDATES_POOL: List[Update] = []


def init_updates_pool(pool_size: int = 500_000):
    """Предварительно создаём пул updates"""
    global UPDATES_POOL
    logger.info(f"Инициализация пула из {pool_size:,} updates...")

    for _ in range(pool_size):
        user_id = random.choice(USER_IDS_POOL)
        text = random.choice(TEXT_COMMANDS)
        UPDATES_POOL.append(generate_private_update(user_id, text))

    logger.info(f"Пул из {len(UPDATES_POOL):,} updates готов")


def generate_private_update(user_id: int, text: str) -> Update:
    """Создаёт минимальный, но валидный Update для private chat"""
    return Update(
        update_id=random.getrandbits(32),
        message=Message(
            message_id=random.randint(1, 999_999_999),
            date=int(time.time()),
            from_user=User(
                id=user_id,
                is_bot=False,
                first_name=f"User{user_id % 1000}",
                last_name=f"Test{user_id % 100}",
                username=f"test_user_{user_id}" if random.random() > 0.3 else None
            ),
            chat=Chat(id=user_id, type="private"),
            text=text,
            entities=[],
            caption_entities=[],
            audio=None,
            document=None,
            photo=None,
            sticker=None,
            video=None,
            animation=None,
            voice=None,
            video_note=None,
            caption=None,
            contact=None,
            location=None,
            venue=None,
            poll=None,
            dice=None,
            new_chat_members=[],
            left_chat_member=None,
            new_chat_title=None,
            new_chat_photo=[],
            delete_chat_photo=False,
            group_chat_created=False,
            supergroup_chat_created=False,
            channel_chat_created=False,
            migrate_to_chat_id=None,
            migrate_from_chat_id=None,
            pinned_message=None,
            invoice=None,
            successful_payment=None,
            connected_website=None,
            passport_data=None,
            proximity_alert_triggered=None,
            forum_topic_created=None,
            forum_topic_edited=None,
            forum_topic_closed=None,
            forum_topic_reopened=None,
            general_forum_topic_hidden=None,
            general_forum_topic_unhidden=None,
            video_chat_scheduled=None,
            video_chat_started=None,
            video_chat_ended=None,
            video_chat_participants_invited=None,
            web_app_data=None,
            reply_markup=None
        )
    )


def create_rps_chart() -> str:
    """Создаёт график RPS через plotext"""
    if len(RPS_HISTORY) < 2:
        return "📊 Сбор данных...\n(нужно минимум 2 точки)"

    plt.clear_figure()

    # Настраиваем размер
    plt.plotsize(70, 15)

    # Создаём данные для оси X (время)
    x_data = list(range(len(RPS_HISTORY)))

    # График текущего RPS
    plt.plot(x_data, list(RPS_HISTORY),
             label="Текущий RPS",
             color="cyan",
             marker="hd")

    # График целевого RPS
    plt.plot(x_data, list(TARGET_RPS_HISTORY),
             label="Целевой RPS",
             color="green",
             line_style="dashed")

    # Настраиваем оси
    plt.xlabel("Время (интервалы)")
    plt.ylabel("RPS (сообщений/сек)")
    plt.title(f"📈 Нагрузочный тест - RPS история")

    # Добавляем сетку
    plt.grid(True)

    # Настраиваем легенду
    plt.show_legend()

    # Получаем график как текст
    chart_text = plt.build()
    plt.clear_figure()

    return chart_text


def create_worker_chart() -> str:
    """Создаёт график количества воркеров через plotext"""
    if len(WORKER_HISTORY) < 2:
        return ""

    plt.clear_figure()
    plt.plotsize(70, 8)

    x_data = list(range(len(WORKER_HISTORY)))

    # Гистограмма для воркеров
    plt.bar(x_data, list(WORKER_HISTORY),
            label="Активные воркеры",
            color="yellow",
            marker="sd")

    # Целевое количество воркеров
    plt.hline(MAX_WORKERS,
              label=f"Макс. воркеров ({MAX_WORKERS})",
              color="red",
              line_style="dashed")

    plt.xlabel("Время (интервалы)")
    plt.ylabel("Количество воркеров")
    plt.title("👷 История воркеров")
    plt.grid(True)
    plt.show_legend()

    chart_text = plt.build()
    plt.clear_figure()

    return chart_text


def create_comparison_chart() -> str:
    """Создаёт комбинированный график сравнения"""
    if len(RPS_HISTORY) < 3:
        return ""

    plt.clear_figure()
    plt.plotsize(80, 12)

    # Создаём 2 подграфика
    plt.subplots(1, 2)

    # Первый график - RPS
    plt.subplot(1, 1).title("📈 RPS Прогресс")
    x_data = list(range(len(RPS_HISTORY)))
    plt.plot(x_data, list(RPS_HISTORY),
             label="Фактический",
             color="cyan")
    plt.plot(x_data, list(TARGET_RPS_HISTORY),
             label="Целевой",
             color="green",
             line_style="dashed")
    plt.grid(True)
    plt.show_legend()

    # Второй график - Эффективность (% от цели)
    plt.subplot(1, 2).title("⚡ Эффективность")

    # Рассчитываем эффективность
    efficiency = []
    for actual, target in zip(RPS_HISTORY, TARGET_RPS_HISTORY):
        if target > 0:
            efficiency.append((actual / target) * 100)
        else:
            efficiency.append(0)

    plt.bar(x_data, efficiency,
            label="% от цели",
            color=["red" if eff < 50 else "yellow" if eff < 80 else "green"
                   for eff in efficiency])
    plt.ylabel("Процент %")
    plt.grid(True)
    plt.ylim(0, 110)

    chart_text = plt.build()
    plt.clear_figure()

    return chart_text


def create_gauge_chart(current: float, target: float, max_val: float) -> str:
    """Создаёт график-индикатор"""
    plt.clear_figure()
    plt.plotsize(60, 8)

    # Данные для диаграммы
    labels = ["Текущий", "Целевой", "Максимум"]
    values = [current, target, max_val]
    colors = ["cyan", "green", "red"]

    plt.bar(labels, values, color=colors)
    plt.title("🎯 Показатели нагрузки")
    plt.ylabel("RPS")

    # Добавляем значения поверх столбцов
    for i, (label, value) in enumerate(zip(labels, values)):
        plt.text(label, value + max_val * 0.02, f"{value:,.0f}",
                 alignment='center', color=colors[i])

    chart_text = plt.build()
    plt.clear_figure()

    return chart_text


def format_number(num: float) -> str:
    """Форматирует число с разделителями"""
    if num >= 1_000_000:
        return f"{num / 1_000_000:.2f}M"
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K"
    else:
        return f"{num:,.0f}"


def create_stats_box() -> str:
    """Создаёт красивую статистическую панель"""
    uptime = time.time() - START_TIME
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    seconds = int(uptime % 60)

    if RPS_HISTORY:
        current_rps = RPS_HISTORY[-1]
        peak_rps = max(RPS_HISTORY) if RPS_HISTORY else 0
        avg_rps = sum(RPS_HISTORY) / len(RPS_HISTORY) if RPS_HISTORY else 0
    else:
        current_rps = peak_rps = avg_rps = 0

    stats = f"""
┌──────────────────────────────────────────────────────┐
│ 📊 СТАТИСТИКА НАГРУЗОЧНОГО ТЕСТА                     │
├──────────────────────────────────────────────────────┤
│ ⏱  Время работы:    {hours:02d}:{minutes:02d}:{seconds:02d}                    │
│ 📨  Всего сообщений: {RPS_COUNTER:>15,}              │
│ ⚡  Текущий RPS:     {format_number(current_rps):>15}             │
│ 📈  Средний RPS:     {format_number(avg_rps):>15}             │
│ 🏔  Пиковый RPS:     {format_number(peak_rps):>15}             │
│ 🎯  Целевой RPS:     {format_number(CURRENT_RPS):>15}             │
│ 👷  Активных воркеров: {len(WORKER_HISTORY[-1]):>13}             │
│ 📊  Записей в истории: {len(RPS_HISTORY):>13}             │
└──────────────────────────────────────────────────────┘
"""
    return stats


class LoadGenerator:
    """Класс для управления нагрузкой"""

    def __init__(self, dp, bot: Bot):
        self.dp = dp
        self.bot = bot
        self.workers = []
        self.is_running = False
        self.last_rps_increase = time.time()
        self.last_worker_increase = time.time()
        self.total_messages = 0

    async def start(self):
        """Запуск нагрузочного теста"""
        self.is_running = True
        logger.info(f"🚀 Запуск нагрузочного теста с plotext графиками...")
        logger.info(f"🎯 Начальный RPS: {INITIAL_RPS:,}")
        logger.info(f"📈 Шаг увеличения: {RPS_INCREASE_STEP}x каждые 10 сек")

        # Запускаем начальное количество воркеров
        await self.adjust_workers(ACTIVE_WORKERS)

    async def adjust_workers(self, target_workers: int):
        """Настраиваем количество воркеров"""
        current_workers = len(self.workers)

        if target_workers > current_workers:
            for i in range(current_workers, target_workers):
                worker_rps = CURRENT_RPS // max(1, target_workers)
                worker = asyncio.create_task(
                    self.worker_task(i, worker_rps)
                )
                self.workers.append(worker)
                await asyncio.sleep(0.01)

            logger.info(f"➕ Добавлено {target_workers - current_workers} воркеров")

    async def worker_task(self, worker_id: int, target_rps: int):
        """Задача одного воркера"""
        local_counter = 0

        while self.is_running:
            try:
                batch_size = max(1, min(20, target_rps // 100))
                batch_tasks = []

                for _ in range(batch_size):
                    if not UPDATES_POOL:
                        continue

                    update = random.choice(UPDATES_POOL)
                    task = asyncio.create_task(self.dp.feed_update(self.bot, update))
                    batch_tasks.append(task)
                    local_counter += 1

                    global RPS_COUNTER
                    RPS_COUNTER += 1
                    self.total_messages += 1

                if batch_tasks:
                    await asyncio.gather(*batch_tasks, return_exceptions=True)

                # Контроль скорости
                if target_rps > 0:
                    target_time = batch_size / target_rps
                    if target_time > 0.001:
                        await asyncio.sleep(target_time)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Воркер {worker_id}: {e}")
                await asyncio.sleep(0.1)

    async def update_load_parameters(self):
        """Обновляем параметры нагрузки"""
        global CURRENT_RPS, ACTIVE_WORKERS

        current_time = time.time()

        # Увеличиваем RPS каждые 10 секунд
        if current_time - self.last_rps_increase >= 10:
            if CURRENT_RPS < MAX_RPS:
                old_rps = CURRENT_RPS
                CURRENT_RPS = min(MAX_RPS, int(CURRENT_RPS * RPS_INCREASE_STEP))
                logger.info(f"📈 RPS: {old_rps:,} → {CURRENT_RPS:,}")

            self.last_rps_increase = current_time

        # Увеличиваем воркеров каждые 20 секунд
        if current_time - self.last_worker_increase >= 20:
            if ACTIVE_WORKERS < MAX_WORKERS:
                old_workers = ACTIVE_WORKERS
                ACTIVE_WORKERS = min(MAX_WORKERS, ACTIVE_WORKERS + 2)
                await self.adjust_workers(ACTIVE_WORKERS)
                logger.info(f"👷 Workers: {old_workers} → {ACTIVE_WORKERS}")

            self.last_worker_increase = current_time

    async def stop(self):
        """Остановка нагрузочного теста"""
        self.is_running = False

        for worker in self.workers:
            worker.cancel()

        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)

        self.workers.clear()


async def rps_reporter(bot: Bot, load_generator: LoadGenerator):
    """Отчёт с plotext графиками"""
    global RPS_COUNTER, LAST_REPORT_TIME

    report_count = 0

    while True:
        await asyncio.sleep(REPORT_INTERVAL)
        report_count += 1

        # Обновляем параметры нагрузки
        if load_generator.is_running:
            await load_generator.update_load_parameters()

        elapsed = time.time() - LAST_REPORT_TIME
        if elapsed <= 0:
            continue

        # Рассчитываем текущий RPS
        current_rps = RPS_COUNTER / elapsed

        # Сохраняем в историю
        current_time = datetime.now().strftime("%H:%M:%S")
        RPS_HISTORY.append(current_rps)
        TARGET_RPS_HISTORY.append(CURRENT_RPS)
        WORKER_HISTORY.append(len(load_generator.workers))
        TIMESTAMPS.append(current_time)

        # Формируем сообщение с графиками
        message_parts = []

        # Заголовок
        message_parts.append(f"<b>📊 LOAD TEST REPORT #{report_count}</b>")
        message_parts.append(f"⏰ {current_time} | 📅 {datetime.now().strftime('%Y-%m-%d')}")
        message_parts.append("━" * 50)

        # Основной график RPS (каждые 3 отчёта)
        if report_count % 3 == 0 and len(RPS_HISTORY) >= 5:
            message_parts.append("<b>📈 ОСНОВНОЙ ГРАФИК RPS:</b>")
            rps_chart = create_rps_chart()
            message_parts.append(f"<pre>{rps_chart}</pre>")
        else:
            # Мини-график
            message_parts.append("<b>📊 ТЕКУЩАЯ СТАТИСТИКА:</b>")
            if len(RPS_HISTORY) >= 3:
                gauge_chart = create_gauge_chart(
                    current_rps, CURRENT_RPS, MAX_RPS
                )
                message_parts.append(f"<pre>{gauge_chart}</pre>")

        # Статистика
        stats_box = create_stats_box()
        message_parts.append(f"<pre>{stats_box}</pre>")

        # Прогресс
        progress_percent = (CURRENT_RPS / MAX_RPS) * 100
        message_parts.append(f"<b>🎯 ПРОГРЕСС: {progress_percent:.1f}%</b>")

        # Следующее обновление
        next_rps_in = max(0, 10 - (time.time() - load_generator.last_rps_increase))
        next_worker_in = max(0, 20 - (time.time() - load_generator.last_worker_increase))

        message_parts.append(
            f"⏱ Следующее обновление:\n"
            f"   • RPS через: <b>{next_rps_in:.1f} сек</b>\n"
            f"   • Воркеров через: <b>{next_worker_in:.1f} сек</b>"
        )

        # Специальные графики (каждые 5 отчётов)
        if report_count % 5 == 0 and len(RPS_HISTORY) >= 10:
            message_parts.append("\n<b>📊 СПЕЦИАЛЬНЫЙ ОТЧЁТ:</b>")

            # График воркеров
            worker_chart = create_worker_chart()
            if worker_chart:
                message_parts.append(f"<pre>{worker_chart}</pre>")

            # График сравнения
            comparison_chart = create_comparison_chart()
            if comparison_chart:
                message_parts.append(f"<pre>{comparison_chart}</pre>")

        # Собираем всё сообщение
        full_message = "\n".join(message_parts)

        try:
            await bot.send_message(
                chat_id=LOAD_TEST_USER_ID,
                text=full_message,
                parse_mode="HTML",
                disable_notification=True,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить отчёт: {e}")

        # Сбрасываем счётчики
        RPS_COUNTER = 0
        LAST_REPORT_TIME = time.time()


async def start_load_test(dp, bot: Bot):
    """Основная функция запуска нагрузочного теста"""

    # Предварительная инициализация
    if not UPDATES_POOL:
        init_updates_pool()

    # Создаём генератор нагрузки
    load_generator = LoadGenerator(dp, bot)

    # Запускаем репортер
    reporter_task = asyncio.create_task(rps_reporter(bot, load_generator))

    try:
        # Запускаем нагрузку
        await load_generator.start()

        # Информационное сообщение
        await bot.send_message(
            chat_id=LOAD_TEST_USER_ID,
            text=(
                f"🚀 <b>ЗАПУСК НАГРУЗОЧНОГО ТЕСТА С PLOTEXT</b>\n\n"
                f"⏱ Начало: {datetime.now().strftime('%H:%M:%S')}\n"
                f"🎯 Начальный RPS: {INITIAL_RPS:,}\n"
                f"🏔 Максимальный RPS: {MAX_RPS:,}\n"
                f"📈 Шаг увеличения: {RPS_INCREASE_STEP}x\n"
                f"👷 Начало с {ACTIVE_WORKERS} воркеров\n\n"
                f"📊 Графики будут обновляться каждые {REPORT_INTERVAL} секунд"
            ),
            parse_mode="HTML"
        )

        # Ждём, пока тест работает
        logger.info("✅ Нагрузочный тест запущен")

        while load_generator.is_running:
            await asyncio.sleep(1)

            # Автоматическая остановка при достижении максимума
            if CURRENT_RPS >= MAX_RPS and len(load_generator.workers) >= MAX_WORKERS:
                logger.info("🏁 Достигнут максимальный уровень нагрузки!")
                await bot.send_message(
                    chat_id=LOAD_TEST_USER_ID,
                    text="🏁 <b>ДОСТИГНУТ МАКСИМАЛЬНЫЙ УРОВЕНЬ НАГРУЗКИ!</b>",
                    parse_mode="HTML"
                )
                break

    except KeyboardInterrupt:
        logger.info("Load test остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка в load test: {e}")
    finally:
        # Останавливаем тест
        await load_generator.stop()
        reporter_task.cancel()

        # Финальный отчёт
        if len(RPS_HISTORY) >= 3:
            # Создаём финальные графики
            plt.clear_figure()
            plt.plotsize(80, 20)

            # Комбинированный финальный график
            plt.subplots(2, 1)

            # Верхний график - полная история RPS
            plt.subplot(1, 1).title("📈 ПОЛНАЯ ИСТОРИЯ НАГРУЗКИ")
            x_data = list(range(len(RPS_HISTORY)))
            plt.plot(x_data, list(RPS_HISTORY),
                     label="Фактический RPS",
                     color="cyan",
                     fillx=True)
            plt.plot(x_data, list(TARGET_RPS_HISTORY),
                     label="Целевой RPS",
                     color="green",
                     line_style="dashed")
            plt.grid(True)
            plt.show_legend()

            # Нижний график - эффективность
            plt.subplot(2, 1).title("⚡ ИСТОРИЯ ЭФФЕКТИВНОСТИ")

            efficiency = []
            for actual, target in zip(RPS_HISTORY, TARGET_RPS_HISTORY):
                if target > 0:
                    efficiency.append((actual / target) * 100)
                else:
                    efficiency.append(0)

            plt.plot(x_data, efficiency,
                     label="Эффективность %",
                     color="yellow",
                     marker="hd")
            plt.ylabel("Процент %")
            plt.grid(True)
            plt.ylim(0, 120)
            plt.hline(100, color="green", line_style="dashed")

            final_chart = plt.build()

            # Финальная статистика
            final_stats = f"""
┌─────────────────────────────────────────────────────────┐
│ 🏁 ФИНАЛЬНЫЙ ОТЧЁТ НАГРУЗОЧНОГО ТЕСТА                   │
├─────────────────────────────────────────────────────────┤
│ ⏱  Общее время:     {time.time() - START_TIME:.1f} сек                │
│ 📨  Всего сообщений: {load_generator.total_messages:>20,} │
│ ⚡  Пиковый RPS:     {format_number(max(RPS_HISTORY)):>20} │
│ 🎯  Макс. целевой:   {format_number(MAX_RPS):>20} │
│ 📊  Средний RPS:     {format_number(sum(RPS_HISTORY) / len(RPS_HISTORY)):>20} │
│ 👷  Макс. воркеров:  {max(WORKER_HISTORY):>20} │
│ 📈  Коэффициент:     {RPS_INCREASE_STEP:>20}x │
│ ✅  Тест завершён:   {datetime.now().strftime('%H:%M:%S'):>20} │
└─────────────────────────────────────────────────────────┘
"""

            final_message = (
                f"<b>🏁 НАГРУЗОЧНЫЙ ТЕСТ ЗАВЕРШЁН</b>\n"
                f"⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺⎺\n\n"
                f"<pre>{final_chart}</pre>\n\n"
                f"<pre>{final_stats}</pre>"
            )
        else:
            final_message = (
                f"<b>🏁 НАГРУЗОЧНЫЙ ТЕСТ ЗАВЕРШЁН ДОСРОЧНО</b>\n\n"
                f"⏱ Время работы: {time.time() - START_TIME:.1f} сек\n"
                f"📨 Сообщений: {load_generator.total_messages:,}\n"
                f"👷 Макс. воркеров: {len(load_generator.workers)}"
            )

        try:
            await bot.send_message(
                chat_id=LOAD_TEST_USER_ID,
                text=final_message,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить финальный отчёт: {e}")

        logger.info("✅ Load test полностью завершён")


# Установка plotext
def setup_plotext():
    """Настраивает plotext для лучшего отображения"""
    # Устанавливаем тему
    plt.theme("dark")

    # Настраиваем цвета
    plt.canvas_color("black")
    plt.axes_color("black")
    plt.ticks_color("white")

    logger.info("Plotext настроен для тёмной темы")