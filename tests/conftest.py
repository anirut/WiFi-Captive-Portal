import os

os.environ.setdefault("SECRET_KEY", "test_secret_key_32_chars_long_xxx")
os.environ.setdefault("ENCRYPTION_KEY", "AF7LzGfwqzgX6h8uF89ph9XUwy-_GilZDJp0zv2y0hs=")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
