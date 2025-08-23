from django.db.models import CheckConstraint, Q, TextChoices, F
from django.utils import timezone
from clickhouse_backend import models


class UserEvent(models.ClickhouseModel):
    """Модель для событий пользователей"""

    class EventType(TextChoices):
        PAGE_VIEW = 'page_view', 'Page View'
        CLICK = 'click', 'Click'
        PURCHASE = 'purchase', 'Purchase'
        SIGNUP = 'signup', 'Sign Up'
        LOGIN = 'login', 'Login'
        LOGOUT = 'logout', 'Logout'

    class DeviceType(TextChoices):
        DESKTOP = 'desktop', 'Desktop'
        MOBILE = 'mobile', 'Mobile'
        TABLET = 'tablet', 'Tablet'

    event_date = models.DateField(default=timezone.now)
    event_time = models.DateTimeField(default=timezone.now)
    user_id = models.UInt32Field()
    session_id = models.StringField(max_length=100)
    event_type = models.StringField(
        max_length=20,
        choices=EventType.choices,
        low_cardinality=True
    )
    page_url = models.StringField(max_length=500)
    user_agent = models.StringField(max_length=500)
    country_code = models.FixedStringField(max_bytes=2)
    city = models.StringField(max_length=100, low_cardinality=True)
    referrer = models.StringField(max_length=500, default="")
    device_type = models.StringField(
        max_length=10,
        choices=DeviceType.choices,
        low_cardinality=True
    )
    response_time_ms = models.UInt16Field(default=0)
    bytes_sent = models.UInt32Field(default=0)

    class Meta:
        ordering = ["-event_time"]
        db_table = "user_events"
        engine = models.MergeTree(
            order_by=("event_date", "user_id", "event_time"),
            partition_by=models.toYYYYMM("event_date"),
            index_granularity=8192,
        )
        indexes = [
            models.Index(
                fields=["user_id"],
                name="event_user_id_bloom_idx",
                type=models.BloomFilter(0.01),
                granularity=1
            ),
            models.Index(
                fields=["event_type"],
                name="event_type_set_idx",
                type=models.Set(100),
                granularity=4
            )
        ]
        constraints = (
            CheckConstraint(
                name="response_time_range",
                check=Q(response_time_ms__gte=0, response_time_ms__lte=60000),
            ),
        )


class UserProfile(models.ClickhouseModel):
    """Модель для профилей пользователей с дедупликацией"""

    user_id = models.UInt32Field(primary_key=True)
    updated_at = models.DateTimeField(default=timezone.now)
    name = models.StringField(max_length=200)
    email = models.StringField(max_length=320)
    registration_date = models.DateField()
    last_activity = models.DateTimeField()
    total_sessions = models.UInt32Field(default=0)
    total_page_views = models.UInt32Field(default=0)

    class Meta:
        db_table = "user_profiles"
        ordering = ["-last_activity"]
        engine = models.ReplacingMergeTree(
            "updated_at",
            order_by="user_id",
        )
        indexes = [
            models.Index(
                fields=["email"],
                name="email_bloom_idx",
                type=models.BloomFilter(0.001),
                granularity=1
            )
        ]
        constraints = (
            CheckConstraint(
                name="sessions_views_relation",
                check=Q(total_page_views__gte=F('total_sessions')),
            ),
        )


class DailyMetric(models.ClickhouseModel):
    """Модель для ежедневных метрик с автоматическим суммированием"""

    metric_date = models.DateField()
    metric_name = models.StringField(max_length=100)
    metric_value = models.UInt64Field()

    class Meta:
        ordering = ["-metric_date", "metric_name"]
        db_table = "daily_metrics"
        engine = models.SummingMergeTree(
            order_by=("metric_date", "metric_name"),
            partition_by=models.toYYYYMM("metric_date"),
        )
        indexes = [
            models.Index(
                fields=["metric_name"],
                name="metric_name_set_idx",
                type=models.Set(1000),
                granularity=4
            )
        ]


class PerformanceTest(models.ClickhouseModel):
    """Модель для тестирования производительности"""

    class Category(TextChoices):
        A = 'A', 'Category A'
        B = 'B', 'Category B'
        C = 'C', 'Category C'
        D = 'D', 'Category D'
        E = 'E', 'Category E'

    id = models.UInt64Field(primary_key=True)
    timestamp = models.DateTimeField(default=timezone.now)
    user_id = models.UInt32Field()
    category = models.FixedStringField(
        max_length=1,
        choices=Category.choices,
        low_cardinality=True
    )
    value = models.Float64Field()
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "performance_test"
        ordering = ["-timestamp"]
        engine = models.MergeTree(
            order_by=("timestamp", "user_id"),
            partition_by=models.toYYYYMM("timestamp"),
            index_granularity=8192,
        )
        indexes = [
            models.Index(
                fields=["category"],
                name="category_set_idx",
                type=models.Set(10),
                granularity=4
            ),
            models.Index(
                fields=["user_id"],
                name="performance_user_id_bloom_idx",
                type=models.BloomFilter(0.01),
                granularity=1
            )
        ]
        constraints = (
            CheckConstraint(
                name="value_range",
                check=Q(value__gte=0, value__lte=10000),
            ),
        )
