"""
Example hook that logs point information to a file.
Demonstrates the ScanHook interface with minimal complexity.
"""
import os
from datetime import datetime

from hooks.base import ScanHook, HookResult


class LogHook(ScanHook):
    """Writes a log entry for each probed point."""
    name = "log"
    display_name = "Log to File"

    def __init__(self, config: dict) -> None:
        self.log_file = config.get("log_file", "scan_hook_log.txt")

    def before_power_on(self, point: dict, output_dir: str) -> HookResult | None:
        path = os.path.join(output_dir, self.log_file)
        with open(path, "a") as f:
            ts = datetime.now().isoformat()
            f.write(f"[{ts}] BEFORE_POWER_ON point={point['name']} "
                    f"x={point.get('x', '?')} y={point.get('y', '?')}\n")
        return HookResult(hook_name=self.name, success=True)

    def after_capture(self, point: dict, output_dir: str) -> HookResult | None:
        path = os.path.join(output_dir, self.log_file)
        with open(path, "a") as f:
            ts = datetime.now().isoformat()
            f.write(f"[{ts}] AFTER_CAPTURE  point={point['name']}\n")
        return HookResult(hook_name=self.name, success=True)
