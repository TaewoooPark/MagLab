"""ModelProvider abstract base class and registry.

Each ModelProvider registers EffectModels for a single domain.
Automatically registered in the global registry via the @register_provider decorator.

Design basis: plan/04-analysis.md §11.1, impl/03-P2-analysis.md T-P2-02
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from maglab.analysis.effects.base import EffectModel

# ---------------------------------------------------------------------------
# Global provider registry
# ---------------------------------------------------------------------------

_PROVIDER_REGISTRY: dict[str, ModelProvider] = {}


def register_provider(cls: type) -> type:
    """Decorator that registers a ModelProvider subclass in the global registry.

    Usage:
        @register_provider
        class MagnetotransportProvider(ModelProvider): ...
    """
    instance = cls()
    _PROVIDER_REGISTRY[instance.name] = instance
    return cls


def get_provider(name: str) -> ModelProvider:
    """Return a registered ModelProvider by name.

    Args:
        name: Provider name.

    Returns:
        ModelProvider instance.

    Raises:
        KeyError: Unknown provider name.
    """
    if name not in _PROVIDER_REGISTRY:
        raise KeyError(
            f"Unknown provider: '{name}'. Registered providers: {list(_PROVIDER_REGISTRY.keys())}"
        )
    return _PROVIDER_REGISTRY[name]


def list_providers() -> list[str]:
    """Return a list of all registered ModelProvider names."""
    return list(_PROVIDER_REGISTRY.keys())


def get_all_effects() -> dict[str, EffectModel]:
    """Return all registered EffectModels as a {name: instance} dictionary."""
    all_effects: dict[str, EffectModel] = {}
    for provider in _PROVIDER_REGISTRY.values():
        for effect in provider.effects:
            all_effects[effect.name] = effect
    return all_effects


def get_effect(effect_name: str) -> EffectModel:
    """Return an EffectModel by effect name.

    Args:
        effect_name: Effect name (e.g., "anomalous_hall").

    Returns:
        EffectModel instance.

    Raises:
        KeyError: Unknown effect name.
    """
    all_effects = get_all_effects()
    if effect_name not in all_effects:
        raise KeyError(f"Unknown effect: '{effect_name}'. Registered effects: {list(all_effects.keys())}")
    return all_effects[effect_name]


# ---------------------------------------------------------------------------
# ModelProvider ABC
# ---------------------------------------------------------------------------


class ModelProvider(ABC):
    """Abstract base class for effect fitting model providers.

    Registers and retrieves EffectModels for a single domain.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., "magnetotransport")."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Provider description."""
        ...

    @property
    @abstractmethod
    def effects(self) -> list[EffectModel]:
        """List of EffectModels managed by this provider."""
        ...

    def get(self, effect_name: str) -> EffectModel:
        """Return an EffectModel by name.

        Args:
            effect_name: Effect name.

        Returns:
            EffectModel instance.

        Raises:
            KeyError: Unknown effect name.
        """
        for effect in self.effects:
            if effect.name == effect_name:
                return effect
        raise KeyError(
            f"Effect '{effect_name}' not found in provider '{self.name}'. Available effects: {self.list()}"
        )

    def list(self) -> list[str]:
        """Return a list of effect names."""
        return [e.name for e in self.effects]

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.name}' effects={self.list()}>"
