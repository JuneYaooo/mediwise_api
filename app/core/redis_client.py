import os
import json
import asyncio
from typing import Optional, Any
import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

class RedisClient:
    """Redis客户端，用于用户反馈等待机制"""
    
    def __init__(self):
        self._redis = None
        self._lock = asyncio.Lock()
    
    async def get_redis(self):
        """获取Redis连接，使用单例模式"""
        if self._redis is None:
            async with self._lock:
                if self._redis is None:
                    redis_host = os.getenv("REDIS_HOST", "localhost")
                    redis_port = int(os.getenv("REDIS_PORT", "36379"))
                    redis_db = int(os.getenv("REDIS_DB", "0"))
                    redis_password = os.getenv("REDIS_PASSWORD")
                    
                    connection_kwargs = {
                        'host': redis_host,
                        'port': redis_port,
                        'db': redis_db,
                        'decode_responses': True,
                        'socket_timeout': 5,
                        'socket_connect_timeout': 5,
                        'retry_on_timeout': True
                    }
                    
                    if redis_password:
                        connection_kwargs['password'] = redis_password
                    
                    self._redis = redis.Redis(**connection_kwargs)
        return self._redis
    
    async def set_with_expiry(self, key: str, value: Any, ttl: int = 300):
        """设置带过期时间的键值对"""
        redis_client = await self.get_redis()
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        await redis_client.setex(key, ttl, value)
    
    async def get(self, key: str) -> Optional[str]:
        """获取键值"""
        redis_client = await self.get_redis()
        value = await redis_client.get(key)
        return value
    
    async def delete(self, key: str):
        """删除键"""
        redis_client = await self.get_redis()
        await redis_client.delete(key)
    
    async def publish(self, channel: str, message: str):
        """发布消息到频道"""
        redis_client = await self.get_redis()
        await redis_client.publish(channel, message)
    
    async def subscribe(self, channel: str):
        """订阅频道"""
        redis_client = await self.get_redis()
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel)
        return pubsub
    
    async def close(self):
        """关闭连接"""
        if self._redis:
            await self._redis.aclose()

# 全局Redis客户端实例
redis_client = RedisClient() 