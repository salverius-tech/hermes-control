from __future__ import annotations


def _display_model_name(model: str) -> str:
    return model.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ").title()


def discover_models() -> list[dict[str, str]]:
    """Return sanitized model options for configured Hermes providers."""
    try:
        from hermes_cli.models import list_available_providers, provider_model_ids
    except ImportError as exc:
        raise RuntimeError("Hermes model discovery is unavailable") from exc

    discovered: list[dict[str, str]] = []
    for provider in list_available_providers():
        if not provider.get("authenticated"):
            continue
        provider_id = provider["id"]
        try:
            model_ids = provider_model_ids(provider_id)
        except Exception:
            continue
        for model in model_ids:
            if not isinstance(model, str) or not model.strip():
                continue
            discovered.append({
                "provider": provider_id,
                "provider_label": provider.get("label", provider_id),
                "model": model,
                "label": _display_model_name(model),
            })
    return discovered
