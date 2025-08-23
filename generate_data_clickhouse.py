import random
from datetime import datetime, timedelta
from clickhouse_driver import Client
import time


class ClickHouseDataGenerator:
    def __init__(self, host='localhost', port=9000, user='developer',
                 password='demo_password'):
        self.client = Client(
            host=host,
            port=port,
            user=user,
            password=password,
            database='analytics',
        )

    def drop_existing_tables(self):
        """Удаление существующих таблиц"""
        print("\n🗑️ Удаление существующих таблиц...")

        tables_to_drop = [
            'daily_page_views_mv',
            # Материализованное представление удаляем первым
            'daily_metrics',
            'user_events',
            'user_profiles',
            'performance_test'
        ]

        for table in tables_to_drop:
            try:
                # Проверяем существование таблицы
                result = self.client.execute(
                    f"EXISTS TABLE analytics.{table}"
                )

                if result[0][0]:
                    self.client.execute(
                        f"DROP TABLE IF EXISTS analytics.{table}")
                    print(f"  ✓ Таблица {table} удалена")
                else:
                    print(f"  ℹ️ Таблица {table} не существует")

            except Exception as e:
                print(f"  ⚠️ Ошибка при удалении {table}: {e}")

    def create_tables(self):
        """Создание новых таблиц"""
        print("\n📊 Создание новых таблиц...")

        # Создаем базу данных если не существует
        self.client.execute("CREATE DATABASE IF NOT EXISTS analytics")
        print("  ✓ База данных analytics создана/проверена")

        # 1. Основная таблица событий
        self.client.execute("""
                            CREATE TABLE IF NOT EXISTS analytics.user_events
                            (
                                event_date       Date,
                                event_time       DateTime,
                                user_id          UInt32,
                                session_id       String,
                                event_type       LowCardinality(String),
                                page_url         String,
                                user_agent       String,
                                country_code     FixedString(2),
                                city             LowCardinality(String),
                                referrer         String,
                                device_type      LowCardinality(String),
                                response_time_ms UInt16,
                                bytes_sent       UInt32
                            ) ENGINE = MergeTree()
            ORDER BY (event_date, user_id, event_time)
            PARTITION BY toYYYYMM(event_date)
            SETTINGS index_granularity = 8192
                            """)
        print("  ✓ Таблица user_events создана")

        # 2. Таблица для дедупликации
        self.client.execute("""
                            CREATE TABLE IF NOT EXISTS analytics.user_profiles
                            (
                                user_id           UInt32,
                                updated_at        DateTime,
                                name              String,
                                email             String,
                                registration_date Date,
                                last_activity     DateTime,
                                total_sessions    UInt32,
                                total_page_views  UInt32
                            ) ENGINE = ReplacingMergeTree(updated_at)
            ORDER BY user_id
                            """)
        print("  ✓ Таблица user_profiles создана")

        # 3. Таблица для автоматического суммирования
        self.client.execute("""
                            CREATE TABLE IF NOT EXISTS analytics.daily_metrics
                            (
                                metric_date  Date,
                                metric_name  String,
                                metric_value UInt64
                            ) ENGINE = SummingMergeTree()
            ORDER BY (metric_date, metric_name)
            PARTITION BY toYYYYMM(metric_date)
                            """)
        print("  ✓ Таблица daily_metrics создана")

        # 4. Таблица для демонстрации производительности
        self.client.execute("""
                            CREATE TABLE IF NOT EXISTS analytics.performance_test
                            (
                                id        UInt64,
                                timestamp DateTime,
                                user_id   UInt32,
                                category  LowCardinality(String),
                                value     Float64,
                                metadata  String
                            ) ENGINE = MergeTree()
            ORDER BY (timestamp, user_id)
            PARTITION BY toYYYYMM(timestamp)
                            """)
        print("  ✓ Таблица performance_test создана")

        # 5. Материализованное представление
        self.client.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.daily_page_views_mv 
            TO analytics.daily_metrics AS
            SELECT 
                event_date as metric_date,
                'page_views' as metric_name,
                count() as metric_value
            FROM analytics.user_events
            WHERE event_type = 'page_view'
            GROUP BY event_date
        """)
        print("  ✓ Материализованное представление daily_page_views_mv создано")

    def reset_database(self):
        """Полная пересоздание таблиц"""
        print("\n🔄 ПЕРЕСОЗДАНИЕ СТРУКТУРЫ БАЗЫ ДАННЫХ")
        print("=" * 50)
        self.drop_existing_tables()
        self.create_tables()
        print("\n✅ Структура базы данных готова к работе!")

    def generate_user_events(self, num_records=1000000):
        """Генерация событий пользователей"""
        print(f"\nГенерация {num_records:,} событий пользователей...")

        # Справочники для реалистичных данных
        event_types = ['page_view', 'click', 'purchase', 'signup', 'login',
                       'logout']
        countries = ['US', 'GB', 'DE', 'FR', 'CA', 'AU', 'RU', 'CN', 'JP', 'BR']
        cities = ['New York', 'London', 'Berlin', 'Paris', 'Toronto', 'Sydney',
                  'Moscow', 'Beijing', 'Tokyo', 'São Paulo']
        devices = ['desktop', 'mobile', 'tablet']
        pages = [f'/page/{i}' for i in range(1, 101)]

        batch_size = 10000
        total_batches = num_records // batch_size

        for batch in range(total_batches):
            batch_data = []

            for _ in range(batch_size):
                # Генерируем случайную дату за последние 30 дней
                event_time = datetime.now() - timedelta(
                    days=random.randint(0, 30),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )

                user_id = random.randint(1, 50000)
                session_id = f"sess_{random.randint(100000, 999999)}"
                event_type = random.choice(event_types)
                page_url = random.choice(pages)
                user_agent = f"Mozilla/5.0 (compatible; Bot {random.randint(1, 100)})"

                # Изменено для соответствия схеме таблицы (FixedString(2))
                country_code = random.choice(
                    ['US', 'GB', 'DE', 'FR', 'CA', 'AU', 'RU', 'CN', 'JP',
                     'BR'])
                city = random.choice(cities)
                referrer = random.choice(
                    ['google.com', 'facebook.com', 'direct', ''])
                device_type = random.choice(devices)
                response_time_ms = random.randint(50, 5000)
                bytes_sent = random.randint(1000, 50000)

                batch_data.append((
                    event_time.date(),
                    event_time,
                    user_id,
                    session_id,
                    event_type,
                    page_url,
                    user_agent,
                    country_code,  # Изменено с country
                    city,
                    referrer,
                    device_type,  # Изменено с device
                    response_time_ms,  # Изменено с response_time
                    bytes_sent
                ))

            # Вставка батча
            try:
                self.client.execute(
                    'INSERT INTO user_events VALUES',
                    batch_data
                )
                print(f"  ✓ Батч {batch + 1}/{total_batches} вставлен")
            except Exception as e:
                print(f"  ✗ Ошибка в батче {batch + 1}: {e}")

    def generate_user_profiles(self, num_users=10000):
        """Генерация профилей пользователей"""
        print(f"\nГенерация {num_users:,} профилей пользователей...")

        batch_data = []
        for user_id in range(1, num_users + 1):
            updated_at = datetime.now() - timedelta(days=random.randint(0, 365))
            name = f"User_{user_id}"
            email = f"user{user_id}@example.com"
            registration_date = updated_at.date() - timedelta(
                days=random.randint(1, 730))
            last_activity = updated_at
            total_sessions = random.randint(1, 100)
            total_page_views = random.randint(total_sessions,
                                              total_sessions * 50)

            batch_data.append((
                user_id,
                updated_at,
                name,
                email,
                registration_date,
                last_activity,
                total_sessions,
                total_page_views
            ))

        self.client.execute(
            'INSERT INTO user_profiles VALUES',
            batch_data
        )
        print("  ✓ Профили пользователей созданы")

    def generate_performance_test_data(self, num_records=10_000_000):
        """Генерация данных для тестирования производительности"""
        print(
            f"\nГенерация {num_records:,} записей для тестирования производительности...")

        categories = ['A', 'B', 'C', 'D', 'E']
        batch_size = 100000
        total_batches = num_records // batch_size

        start_time = time.time()

        for batch in range(total_batches):
            batch_data = []

            for i in range(batch_size):
                record_id = batch * batch_size + i + 1
                timestamp = datetime.now() - timedelta(
                    days=random.randint(0, 365),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )
                user_id = random.randint(1, 1000000)
                category = random.choice(categories)
                value = random.uniform(0, 1000)
                metadata = f'{{"batch": {batch}, "record": {i}}}'

                batch_data.append((
                    record_id,
                    timestamp,
                    user_id,
                    category,
                    value,
                    metadata
                ))

            self.client.execute(
                'INSERT INTO performance_test VALUES',
                batch_data
            )

            elapsed = time.time() - start_time
            rate = (batch + 1) * batch_size / elapsed
            print(
                f"  ✓ Батч {batch + 1}/{total_batches} | Скорость: {rate:,.0f} записей/сек")

    def run_performance_benchmarks(self):
        """Запуск бенчмарков для демонстрации"""
        print("\n" + "=" * 50)
        print("БЕНЧМАРКИ ПРОИЗВОДИТЕЛЬНОСТИ")
        print("=" * 50)

        benchmarks = [
            # Простой COUNT
            ("COUNT всех записей", "SELECT COUNT(*) FROM performance_test"),

            # GROUP BY с агрегацией
            ("GROUP BY категориям", """
                                    SELECT category,
                                           COUNT(*)   as count,
                                           AVG(value) as avg_value,
                                           MAX(value) as max_value
                                    FROM performance_test
                                    GROUP BY category
                                    ORDER BY count DESC
                                    """),

            # Сложная аналитика с фильтрами
            ("Сложная аналитика", """
                                  SELECT toYYYYMM(timestamp)   as month,
                                         category,
                                         COUNT(*)              as records,
                                         AVG(value)            as avg_value,
                                         quantile(0.95)(value) as p95_value
                                  FROM performance_test
                                  WHERE timestamp >= now() - INTERVAL 90 DAY
                                  GROUP BY month, category
                                  ORDER BY month DESC, category
                                  """),

            # TOP пользователей
            ("TOP-10 пользователей", """
                                     SELECT user_id,
                                            COUNT(*)       as activity_count,
                                            AVG(value)     as avg_value,
                                            MAX(timestamp) as last_activity
                                     FROM performance_test
                                     GROUP BY user_id
                                     ORDER BY activity_count DESC
                                     LIMIT 10
                                     """)
        ]

        for name, query in benchmarks:
            print(f"\n🚀 {name}")
            print("-" * 30)

            start_time = time.time()
            try:
                result = self.client.execute(query)
                end_time = time.time()

                execution_time = end_time - start_time
                print(f"⏱️  Время выполнения: {execution_time:.3f} секунд")
                print(f"📊 Результатов: {len(result)}")

                if result and len(result) > 0:
                    print("📝 Первые результаты:")
                    for i, row in enumerate(result[:3]):
                        print(f"   {i + 1}: {row}")

            except Exception as e:
                print(f"❌ Ошибка: {e}")

    def show_table_stats(self):
        """Показать статистику по таблицам"""
        print("\n📈 СТАТИСТИКА ТАБЛИЦ")
        print("=" * 50)

        tables = ['user_events', 'user_profiles', 'performance_test',
                  'daily_metrics']

        for table in tables:
            try:
                count = self.client.execute(f"SELECT COUNT(*) FROM {table}")[0][
                    0]
                size = self.client.execute(f"""
                    SELECT formatReadableSize(sum(bytes))
                    FROM system.parts
                    WHERE database = 'analytics' AND table = '{table}'
                """)[0][0]

                print(f"\n📊 {table}:")
                print(f"   Записей: {count:,}")
                print(f"   Размер: {size}")

            except Exception as e:
                print(f"\n⚠️ {table}: нет данных или таблица не существует")


def main():
    """Основной скрипт для демонстрации"""
    print("🚀 ДЕМОНСТРАЦИЯ CLICKHOUSE")
    print("=" * 50)

    # Подключение
    generator = ClickHouseDataGenerator()

    # Меню выбора действий
    print("\nВыберите действие:")
    print("1. Пересоздать все таблицы (удалить существующие и создать новые)")
    print("2. Генерировать тестовые данные")
    print("3. Запустить бенчмарки")
    print("4. Показать статистику таблиц")
    print("5. Полный цикл (пересоздать таблицы + данные + бенчмарки)")

    choice = input("\nВаш выбор (1-5): ").strip()

    if choice == '1':
        generator.reset_database()

    elif choice == '2':
        print("\n📝 Генерация данных...")
        generator.generate_user_profiles(num_users=10000)
        generator.generate_user_events(num_records=100000)
        generator.generate_performance_test_data(num_records=10_0000_00)

    elif choice == '3':
        generator.run_performance_benchmarks()

    elif choice == '4':
        generator.show_table_stats()

    elif choice == '5':
        # Полный цикл
        generator.reset_database()

        print("\n📝 Генерация данных...")
        generator.generate_user_profiles(num_users=10000)
        generator.generate_user_events(num_records=100000)
        generator.generate_performance_test_data(num_records=10_000_000)

        generator.show_table_stats()
        generator.run_performance_benchmarks()

    else:
        print("❌ Неверный выбор")

    print("\n✅ Готово!")


if __name__ == "__main__":
    main()