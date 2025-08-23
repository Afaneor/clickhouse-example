import random
from datetime import datetime, timedelta
import psycopg
from psycopg import sql
import time


class PostgreSQLDataGenerator:
    def __init__(self, host='localhost', port=5444, user='postgres',
                 password='postgres', dbname='main_app'):
        self.connection_params = {
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'dbname': dbname
        }
        self.conn = None
        self.connect()

    def connect(self):
        """Установка соединения с PostgreSQL"""
        try:
            self.conn = psycopg.connect(**self.connection_params)
            self.conn.autocommit = False  # Для управления транзакциями
            print("✓ Подключение к PostgreSQL установлено")
        except Exception as e:
            print(f"✗ Ошибка подключения: {e}")
            raise

    def drop_existing_tables(self):
        """Удаление существующих таблиц"""
        print("\n🗑️ Удаление существующих таблиц...")

        tables_to_drop = [
            'daily_page_views_mv',  # Материализованное представление удаляем первым
            'daily_metrics',
            'user_events',
            'user_profiles',
            'performance_test'
        ]

        with self.conn.cursor() as cur:
            for table in tables_to_drop:
                try:
                    # Проверяем существование таблицы
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = %s
                        )
                    """, (table,))

                    exists = cur.fetchone()[0]

                    if exists:
                        # Определяем тип объекта (таблица или материализованное представление)
                        if 'mv' in table:
                            cur.execute(sql.SQL("DROP MATERIALIZED VIEW IF EXISTS {} CASCADE").format(
                                sql.Identifier(table)
                            ))
                        else:
                            cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                                sql.Identifier(table)
                            ))
                        print(f"  ✓ Объект {table} удален")
                    else:
                        print(f"  ℹ️ Объект {table} не существует")

                    self.conn.commit()

                except Exception as e:
                    print(f"  ⚠️ Ошибка при удалении {table}: {e}")
                    self.conn.rollback()

    def create_tables(self):
        """Создание новых таблиц"""
        print("\n📊 Создание новых таблиц...")

        with self.conn.cursor() as cur:
            try:
                # 1. Основная таблица событий с партиционированием
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_events (
                        event_date DATE NOT NULL,
                        event_time TIMESTAMP NOT NULL,
                        user_id INTEGER NOT NULL,
                        session_id VARCHAR(50) NOT NULL,
                        event_type VARCHAR(20) NOT NULL,
                        page_url VARCHAR(255),
                        user_agent TEXT,
                        country_code CHAR(2),
                        city VARCHAR(50),
                        referrer VARCHAR(255),
                        device_type VARCHAR(20),
                        response_time_ms SMALLINT,
                        bytes_sent INTEGER
                    ) PARTITION BY RANGE (event_date)
                """)

                # Создаем партиции для последних 3 месяцев
                today = datetime.now()
                for i in range(3):
                    month_start = (today.replace(day=1) - timedelta(days=30*i)).replace(day=1)
                    month_end = (month_start + timedelta(days=32)).replace(day=1)
                    partition_name = f"user_events_{month_start.strftime('%Y_%m')}"

                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS {partition_name} 
                        PARTITION OF user_events
                        FOR VALUES FROM ('{month_start.strftime('%Y-%m-%d')}') 
                        TO ('{month_end.strftime('%Y-%m-%d')}')
                    """)

                # Создаем индексы для user_events
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_events_date_user 
                    ON user_events (event_date, user_id, event_time)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_events_type 
                    ON user_events (event_type)
                """)

                print("  ✓ Таблица user_events создана с партициями")

                # 2. Таблица профилей пользователей с уникальным индексом
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        user_id INTEGER PRIMARY KEY,
                        updated_at TIMESTAMP NOT NULL,
                        name VARCHAR(100),
                        email VARCHAR(255),
                        registration_date DATE,
                        last_activity TIMESTAMP,
                        total_sessions INTEGER,
                        total_page_views INTEGER
                    )
                """)

                # Индекс для поиска по email
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_profiles_email 
                    ON user_profiles (email)
                """)

                print("  ✓ Таблица user_profiles создана")

                # 3. Таблица для метрик
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS daily_metrics (
                        metric_date DATE NOT NULL,
                        metric_name VARCHAR(50) NOT NULL,
                        metric_value BIGINT DEFAULT 0,
                        PRIMARY KEY (metric_date, metric_name)
                    )
                """)

                print("  ✓ Таблица daily_metrics создана")

                # 4. Таблица для тестирования производительности с партиционированием
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS performance_test (
                        id BIGINT NOT NULL,
                        timestamp TIMESTAMP NOT NULL,
                        user_id INTEGER NOT NULL,
                        category VARCHAR(10),
                        value DOUBLE PRECISION,
                        metadata JSONB
                    ) PARTITION BY RANGE (timestamp)
                """)

                # Создаем партиции для последних 13 месяцев
                for i in range(13):
                    month_start = (today.replace(day=1) - timedelta(days=30*i)).replace(day=1)
                    month_end = (month_start + timedelta(days=32)).replace(day=1)
                    partition_name = f"performance_test_{month_start.strftime('%Y_%m')}"

                    cur.execute(f"""
                        CREATE TABLE IF NOT EXISTS {partition_name} 
                        PARTITION OF performance_test
                        FOR VALUES FROM ('{month_start.strftime('%Y-%m-%d')}') 
                        TO ('{month_end.strftime('%Y-%m-%d')}')
                    """)

                # Создаем индексы для performance_test
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_performance_test_timestamp_user 
                    ON performance_test (timestamp, user_id)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_performance_test_category 
                    ON performance_test (category)
                """)

                print("  ✓ Таблица performance_test создана с партициями")

                # 5. Материализованное представление
                cur.execute("""
                    CREATE MATERIALIZED VIEW IF NOT EXISTS daily_page_views_mv AS
                    SELECT 
                        event_date as metric_date,
                        'page_views' as metric_name,
                        COUNT(*) as metric_value
                    FROM user_events
                    WHERE event_type = 'page_view'
                    GROUP BY event_date
                """)

                # Создаем индекс для материализованного представления
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_daily_page_views_mv_date 
                    ON daily_page_views_mv (metric_date)
                """)

                print("  ✓ Материализованное представление daily_page_views_mv создано")

                self.conn.commit()

            except Exception as e:
                print(f"  ✗ Ошибка при создании таблиц: {e}")
                self.conn.rollback()
                raise

    def reset_database(self):
        """Полное пересоздание таблиц"""
        print("\n🔄 ПЕРЕСОЗДАНИЕ СТРУКТУРЫ БАЗЫ ДАННЫХ")
        print("=" * 50)
        self.drop_existing_tables()
        self.create_tables()
        print("\n✅ Структура базы данных готова к работе!")

    def generate_user_events(self, num_records=1000000):
        """Генерация событий пользователей"""
        print(f"\nГенерация {num_records:,} событий пользователей...")

        # Справочники для реалистичных данных
        event_types = ['page_view', 'click', 'purchase', 'signup', 'login', 'logout']
        countries = ['US', 'GB', 'DE', 'FR', 'CA', 'AU', 'RU', 'CN', 'JP', 'BR']
        cities = ['New York', 'London', 'Berlin', 'Paris', 'Toronto', 'Sydney',
                  'Moscow', 'Beijing', 'Tokyo', 'São Paulo']
        devices = ['desktop', 'mobile', 'tablet']
        pages = [f'/page/{i}' for i in range(1, 101)]

        batch_size = 10000
        total_batches = num_records // batch_size

        with self.conn.cursor() as cur:
            for batch in range(total_batches):
                batch_data = []

                for _ in range(batch_size):
                    event_time = datetime.now() - timedelta(
                        days=random.randint(0, 30),
                        hours=random.randint(0, 23),
                        minutes=random.randint(0, 59)
                    )

                    batch_data.append((
                        event_time.date(),
                        event_time,
                        random.randint(1, 50000),
                        f"sess_{random.randint(100000, 999999)}",
                        random.choice(event_types),
                        random.choice(pages),
                        f"Mozilla/5.0 (compatible; Bot {random.randint(1, 100)})",
                        random.choice(countries)[:2],
                        random.choice(cities),
                        random.choice(['google.com', 'facebook.com', 'direct', '']),
                        random.choice(devices),
                        random.randint(50, 5000),
                        random.randint(1000, 50000)
                    ))

                # Вставка батча с использованием execute_values для оптимизации
                try:
                    cur.executemany("""
                        INSERT INTO user_events VALUES 
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, batch_data)

                    self.conn.commit()
                    print(f"  ✓ Батч {batch + 1}/{total_batches} вставлен")

                except Exception as e:
                    print(f"  ✗ Ошибка в батче {batch + 1}: {e}")
                    self.conn.rollback()

    def generate_user_profiles(self, num_users=10000):
        """Генерация профилей пользователей"""
        print(f"\nГенерация {num_users:,} профилей пользователей...")

        batch_data = []
        for user_id in range(1, num_users + 1):
            updated_at = datetime.now() - timedelta(days=random.randint(0, 365))
            name = f"User_{user_id}"
            email = f"user{user_id}@example.com"
            registration_date = updated_at.date() - timedelta(days=random.randint(1, 730))
            last_activity = updated_at
            total_sessions = random.randint(1, 100)
            total_page_views = random.randint(total_sessions, total_sessions * 50)

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

        with self.conn.cursor() as cur:
            try:
                cur.executemany("""
                    INSERT INTO user_profiles VALUES 
                    (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        updated_at = EXCLUDED.updated_at,
                        name = EXCLUDED.name,
                        email = EXCLUDED.email,
                        registration_date = EXCLUDED.registration_date,
                        last_activity = EXCLUDED.last_activity,
                        total_sessions = EXCLUDED.total_sessions,
                        total_page_views = EXCLUDED.total_page_views
                """, batch_data)

                self.conn.commit()
                print("  ✓ Профили пользователей созданы")

            except Exception as e:
                print(f"  ✗ Ошибка при создании профилей: {e}")
                self.conn.rollback()

    def generate_performance_test_data(self, num_records=10_000_000):
        """Генерация данных для тестирования производительности"""
        print(f"\nГенерация {num_records:,} записей для тестирования производительности...")

        categories = ['A', 'B', 'C', 'D', 'E']
        batch_size = 100000
        total_batches = num_records // batch_size

        start_time = time.time()

        with self.conn.cursor() as cur:
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
                    metadata = psycopg.types.json.Json({
                        "batch": batch,
                        "record": i
                    })

                    batch_data.append((
                        record_id,
                        timestamp,
                        user_id,
                        category,
                        value,
                        metadata
                    ))

                try:
                    cur.executemany("""
                        INSERT INTO performance_test VALUES 
                        (%s, %s, %s, %s, %s, %s)
                    """, batch_data)

                    self.conn.commit()

                    elapsed = time.time() - start_time
                    rate = (batch + 1) * batch_size / elapsed
                    print(f"  ✓ Батч {batch + 1}/{total_batches} | Скорость: {rate:,.0f} записей/сек")

                except Exception as e:
                    print(f"  ✗ Ошибка в батче {batch + 1}: {e}")
                    self.conn.rollback()

    def run_performance_benchmarks(self):
        """Запуск бенчмарков для демонстрации"""
        print("\n" + "=" * 50)
        print("БЕНЧМАРКИ ПРОИЗВОДИТЕЛЬНОСТИ PostgreSQL")
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
                SELECT TO_CHAR(timestamp, 'YYYYMM') as month,
                       category,
                       COUNT(*) as records,
                       AVG(value) as avg_value,
                       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value) as p95_value
                FROM performance_test
                WHERE timestamp >= NOW() - INTERVAL '90 days'
                GROUP BY month, category
                ORDER BY month DESC, category
            """),

            # TOP пользователей
            ("TOP-10 пользователей", """
                SELECT user_id,
                       COUNT(*) as activity_count,
                       AVG(value) as avg_value,
                       MAX(timestamp) as last_activity
                FROM performance_test
                GROUP BY user_id
                ORDER BY activity_count DESC
                LIMIT 10
            """)
        ]

        with self.conn.cursor() as cur:
            for name, query in benchmarks:
                print(f"\n🚀 {name}")
                print("-" * 30)

                start_time = time.time()
                try:
                    cur.execute(query)
                    result = cur.fetchall()
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
        print("\n📈 СТАТИСТИКА ТАБЛИЦ PostgreSQL")
        print("=" * 50)

        tables = ['user_events', 'user_profiles', 'performance_test', 'daily_metrics']

        with self.conn.cursor() as cur:
            for table in tables:
                try:
                    # Количество записей
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cur.fetchone()[0]

                    # Размер таблицы
                    cur.execute(f"""
                        SELECT pg_size_pretty(pg_total_relation_size('{table}'))
                    """)
                    size = cur.fetchone()[0]

                    print(f"\n📊 {table}:")
                    print(f"   Записей: {count:,}")
                    print(f"   Размер: {size}")

                except Exception as e:
                    print(f"\n⚠️ {table}: нет данных или таблица не существует")

    def optimize_database(self):
        """Оптимизация базы данных после загрузки данных"""
        print("\n🔧 Оптимизация базы данных...")

        tables = ['user_events', 'user_profiles', 'performance_test']

        with self.conn.cursor() as cur:
            for table in tables:
                try:
                    print(f"  Анализ {table}...")
                    cur.execute(f"ANALYZE {table}")
                    self.conn.commit()
                    print(f"  ✓ {table} проанализирована")
                except Exception as e:
                    print(f"  ⚠️ Ошибка при анализе {table}: {e}")

    def __del__(self):
        """Закрытие соединения при удалении объекта"""
        if self.conn:
            self.conn.close()
            print("\n✓ Соединение с PostgreSQL закрыто")


def main():
    """Основной скрипт для демонстрации"""
    print("🐘 ДЕМОНСТРАЦИЯ PostgreSQL")
    print("=" * 50)

    # Подключение
    generator = PostgreSQLDataGenerator(
        host='localhost',
        port=5444,
        user='postgres',
        password='postgres',
        dbname='main_app'
    )

    # Меню выбора действий
    print("\nВыберите действие:")
    print("1. Пересоздать все таблицы (удалить существующие и создать новые)")
    print("2. Генерировать тестовые данные")
    print("3. Запустить бенчмарки")
    print("4. Показать статистику таблиц")
    print("5. Оптимизировать базу данных (ANALYZE)")
    print("6. Полный цикл (пересоздать таблицы + данные + бенчмарки)")

    choice = input("\nВаш выбор (1-7): ").strip()

    if choice == '1':
        generator.reset_database()

    elif choice == '2':
        print("\n📝 Генерация данных...")
        generator.generate_user_profiles(num_users=10000)
        generator.generate_user_events(num_records=100000)
        generator.generate_performance_test_data(num_records=10_000_000)

    elif choice == '3':
        generator.run_performance_benchmarks()

    elif choice == '4':
        generator.show_table_stats()

    elif choice == '5':
        generator.optimize_database()

    elif choice == '6':
        # Полный цикл
        generator.reset_database()

        print("\n📝 Генерация данных...")
        generator.generate_user_profiles(num_users=10000)
        generator.generate_user_events(num_records=100000)
        generator.generate_performance_test_data(num_records=10_000_000)

        generator.optimize_database()
        generator.show_table_stats()
        generator.run_performance_benchmarks()

    else:
        print("❌ Неверный выбор")

    print("\n✅ Готово!")


if __name__ == "__main__":
    main()