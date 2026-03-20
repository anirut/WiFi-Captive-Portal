class RateLimitExceeded(Exception):
    pass

async def check_rate_limit(ip: str, redis_client, max_attempts: int, window_seconds: int) -> None:
    key = f"rate_limit:auth:{ip}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, window_seconds)
    if count > max_attempts:
        raise RateLimitExceeded(f"Too many attempts from {ip}")
