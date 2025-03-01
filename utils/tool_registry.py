import logging
from pathlib import Path
from typing import Any, Callable, Dict
import logging

# locals
from config.constants import setup_logging
setup_logging()

class ToolRegistry:
    def __init__(self) -> None:
        self.logger = logging.getLogger("TOOL_REGISTRY")
        self._registry: Dict[str, Callable[..., Any]] = {}
        self.tool_instances: Dict[str, Any] = {}  # Cache for instantiated tools

    def register(self, tool_name: str, tool_class: Callable[..., Any]) -> None:
        """Register a tool by name."""
        normalized_name = tool_name.lower()
        self._registry[normalized_name] = tool_class
        self.logger.info(f"{tool_class.__name__} registered in ToolRegistry as {normalized_name}")

    def get_tool_names(self) -> list:
        """Return a list of registered tool names."""
        return list(self._registry.keys())

    def instantiate_tool(self, tool_name: str, **override_kwargs: Any) -> Any:
        normalized = tool_name.lower()
        if normalized in self.tool_instances:
            self.logger.debug("Retrieving cached instance for tool '%s' with id: %s", normalized,
                              id(self.tool_instances[normalized]))
            return self.tool_instances[normalized]

        if normalized not in self._registry:
            self.logger.error(
                f"{tool_name} not registered in ToolRegistry due to incorrect import or a failure to instantiate.")
            raise ValueError(f"Tool '{tool_name}' is not registered.")

        tool_class = self._registry[normalized]
        tool_config_path = f"tools/{normalized}/configs/config.yaml"
        if "config_file" not in override_kwargs:
            override_kwargs["config_file"] = tool_config_path

        instance = tool_class(**override_kwargs)
        self.tool_instances[normalized] = instance
        self.logger.debug("Instantiated tool '%s' with config: %s (instance id: %s)", normalized, tool_config_path,
                          id(instance))
        return instance

    def __iter__(self):
        """Iterate over the registered tool classes."""
        return iter(self._registry.values())

tool_registry = ToolRegistry()

def register_tool(tool_name: str) -> Callable:
    """Decorator to register a tool by name."""
    def decorator(cls: Any) -> Any:
        tool_registry.register(tool_name, cls)
        logging.getLogger("REGISTER_TOOL").info(f"Registered tool: {tool_name}")
        return cls
    return decorator