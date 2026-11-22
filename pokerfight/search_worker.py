"""Persistent isolated worker; stdout is strictly the local JSONL protocol."""
from dataclasses import asdict
import json
import sys

from .arena import make_policy
from .domain import Observation, PublicAction
from .strategy import BotConfig


def main():
    config = BotConfig(**json.loads(sys.argv[1]))
    bot = make_policy(sys.argv[2] if len(sys.argv) > 2 else "v4", config, config.seed)
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.get("kind") == "observe":
                history = tuple(PublicAction(**event) for event in request["history"])
                bot.model.observe(request["table_id"], request["hand_id"], history)
                result = {"request_id": request["request_id"], "observed": True}
            else:
                obs = Observation.from_dict(request["observation"])
                result = {"request_id": request["request_id"], "decision": bot.decide(obs).to_dict()}
        except Exception as error:
            result = {"error": type(error).__name__ + ":" + str(error)}
        print(json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
