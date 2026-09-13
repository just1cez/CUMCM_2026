"""Finite Planner terminal/deadline regression using a protocol-shaped fake adapter."""
from __future__ import annotations

import json
from pathlib import Path

from submission.支撑材料.planner import Planner


class DeadlineAdapter:
    def __init__(self, remaining=1200, max_virtual=10, near_channel=None):
        self.remaining = remaining
        self.max_virtual = max_virtual
        self.virtual = 0.0
        self.channel = 1
        self.paths = []
        self.near_channel = near_channel

    def act(self, path, position=None, channel=None):
        self.paths.append(path)
        if path == "/enter":
            return {"accepted": True, "virtual_time_s": 0.0,
                    "remaining_real_duration_s": self.remaining,
                    "max_virtual_duration_s": self.max_virtual}
        if path == "/exit":
            if self.virtual >= self.max_virtual:
                raise AssertionError("Planner sent /exit after automatic virtual close")
            return {"accepted": True, "virtual_time_s": self.virtual,
                    "exit_reason": "user_exit"}
        if path == "/clear":
            self.virtual += 5
            return {"accepted":True,"virtual_time_s":self.virtual,"clear_result":"success"}
        switch = int(path == "/measure" and channel != self.channel)
        self.virtual += 5 + switch
        self.channel = channel
        return {"accepted": True, "virtual_time_s": self.virtual,
                "measure_result": "near" if channel == self.near_channel else "no_signal"}


def main():
    automatic = DeadlineAdapter(remaining=1200, max_virtual=10)
    result_auto = Planner(automatic, problem=3).run()
    assert result_auto["terminal_reason"] == "virtual_timeout"
    assert result_auto["certificate_complete"] is False
    assert "/exit" not in automatic.paths

    real = DeadlineAdapter(remaining=1, max_virtual=360000)
    result_real = Planner(real, problem=3).run()
    assert result_real["terminal_reason"] == "TimeoutError"
    assert result_real["certificate_complete"] is False
    assert "/exit" not in real.paths
    near = DeadlineAdapter(max_virtual=119, near_channel=20)
    policy = Planner(near, problem=3)
    for record in policy.scan_records.values():
        record.update(range(1,7))
    near_result = policy.run()
    assert near_result["channel_certificates"][20] == "detected"
    assert not near_result["certificate_complete"] and "/clear" not in near.paths
    assert "/exit" not in near.paths
    completed = DeadlineAdapter(max_virtual=119)
    policy = Planner(completed, problem=3)
    for record in policy.scan_records.values():
        record.update(range(1,7))
    completed_result = policy.run()
    assert completed_result["certificate_complete"]
    assert completed_result["termination"] == "complete_after_virtual_timeout"
    assert "/exit" not in completed.paths
    final_clear = DeadlineAdapter(max_virtual=5)
    policy = Planner(final_clear, problem=3)
    policy.action("/enter")
    policy.cleared.update(range(1,16))
    policy.clear(16,(0.0,0.0))
    assert policy._result()["certificate_complete"] and "/exit" not in final_clear.paths
    result = {"evidence": "local_protocol_shaped_terminal_regression_not_official",
              "automatic_virtual_timeout": result_auto,
              "preflight_real_deadline": result_real,
              "never_exited_after_terminal": True,
              "near_at_limit_not_absent": True,
              "final_absence_certificate_at_limit": True,
              "sixteenth_clear_at_limit_complete": True,
              "never_claimed_certificate": True}
    Path("results/terminal_verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
