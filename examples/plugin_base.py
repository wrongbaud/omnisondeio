from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PluginResult:
    plugin_name: str
    screenshot_path: str | None = None
    waveform_path: str | None = None
    extra_files: dict[str, str] = field(default_factory=dict)
    measurements: dict[str, float | None] = field(default_factory=dict)


@dataclass
class PluginError:
    plugin_name: str
    phase: str  # 'prepare', 'capture', 'save'
    error_type: str  # 'timeout', 'connection', 'instrument', 'unknown'
    message: str
    recoverable: bool = True


class ScanPlugin(ABC):
    name: str = ""
    display_name: str = ""
    requires_power_supply: bool = True

    @abstractmethod
    def __init__(self, config: dict) -> None:
        """Receive plugin's config section from config.json instruments.<name>."""
        ...

    @abstractmethod
    def prepare(self, point: dict, output_dir: str) -> None:
        """Before power-on: arm trigger, configure capture, etc."""
        ...

    @abstractmethod
    def capture(self, point: dict, output_dir: str) -> None:
        """After power-on + timeout: stop acquisition, wait for capture, etc."""
        ...

    @abstractmethod
    def save(self, point: dict, output_dir: str) -> PluginResult:
        """Export data to files in output_dir. Return paths."""
        ...

    def reconnect(self) -> None:
        """Attempt to re-establish instrument connection. Override if applicable."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Release instrument resources at session end."""
        ...
