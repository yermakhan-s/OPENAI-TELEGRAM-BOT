import os
import redis
from dotenv import load_dotenv

# Load environment variables for Redis connection
load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)  # optional password
REDIS_DB = int(os.getenv("REDIS_DB", 0))            # default DB is 0

def get_redis_client():
    """
    Create and return a Redis client using environment variables.
    """
    client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        db=REDIS_DB,
        decode_responses=True  # ensures we get string responses instead of bytes
    )
    return client
