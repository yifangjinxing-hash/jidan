from __future__ import annotations

import json

from jidan.message_compose import (
    MESSAGE_COMPOSE_CAPABILITY_ID,
    planned_message_compose_binding,
)
from jidan.registry import CapabilityRegistry


payload = {
    "recipient": "VIP客户群",
    "content": "老板通知：今日特惠三文鱼套餐仅需 12 美金，欢迎预约！",
}

outputs = []
for platform in ("android", "ios", "web"):
    registry = CapabilityRegistry()
    planned_message_compose_binding(platform).register(registry)
    outputs.append(registry.invoke(MESSAGE_COMPOSE_CAPABILITY_ID, payload))

print(json.dumps(outputs, ensure_ascii=False, indent=2))
