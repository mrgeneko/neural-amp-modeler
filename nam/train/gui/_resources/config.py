import json
from pathlib import Path
from typing import Any, Dict, Optional

_CONFIG_DIR = Path.home() / ".config" / "nam_trainer"
_CONFIG_FILE = _CONFIG_DIR / "settings.json"

_DEFAULTS: Dict[str, Any] = {
    "default_architectures": ["standard"],
    "output_template": "__ID_{guid}__{model}_{type}_{size}_{date}",
    "dry_path": "",
    "wet_path": "",
    "default_destination": "",
    "model_name": "",
    "modeled_by": "",
    "gear_type": "",
    "gear_make": "",
    "gear_model": "",
    "tone_type": "",
    "input_level_dbu": "",
    "output_level_dbu": "",
}


def _ensure_config_dir():
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load() -> Dict[str, Any]:
    _ensure_config_dir()
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE, "r") as f:
                saved = json.load(f)
                return {**_DEFAULTS, **saved}
        except (json.JSONDecodeError, IOError):
            pass
    return _DEFAULTS.copy()


def save(settings: Dict[str, Any]):
    _ensure_config_dir()
    with open(_CONFIG_FILE, "w") as f:
        json.dump(settings, f, indent=2)


def get(key: str, default: Any = None) -> Any:
    config = load()
    return config.get(key, default)


def set(key: str, value: Any):
    config = load()
    config[key] = value
    save(config)
