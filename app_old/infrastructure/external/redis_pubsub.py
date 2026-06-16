"""Redis 发布订阅（可选依赖）"""


class RedisPubSub:
    def __init__(self):
        self._client = None

    async def publish(self, channel: str, message: str):
        pass

    async def subscribe(self, channel: str):
        pass
