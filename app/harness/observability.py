import logging
import json

logger = logging.getLogger("learning_agent")


class Observability:
    def trace(self, session_id: str, node: str, event: str,
              data: dict | None = None):
        logger.info(json.dumps({
            "type": "trace", "session_id": session_id,
            "node": node, "event": event, "data": data or {},
        }))

    def metric(self, name: str, value: float, tags: dict | None = None):
        logger.info(json.dumps({
            "type": "metric", "name": name,
            "value": value, "tags": tags or {},
        }))

    def log(self, level: str, event: str, context: dict | None = None):
        log_fn = getattr(logger, level, logger.info)
        log_fn(json.dumps({
            "type": "log", "event": event, "context": context or {},
        }))


_instance: Observability | None = None


def get_observability() -> Observability:
    global _instance
    if _instance is None:
        _instance = Observability()
    return _instance
