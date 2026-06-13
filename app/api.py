from __future__ import annotations

import base64
import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import webview

from .definitions import KeybindDefinition, ScriptDefinition, load_definitions, load_shared_perks
from .runtime import (
    active_scripts_json_path,
    current_ahk_runtime_label,
    format_keybind_display,
    keybind_settings_path,
    launch_script,
    managed_runtime_dir,
    normalize_keybind_value,
    prefs_path,
    project_root,
    resolve_entry,
    resources_root,
    stop_managed_ahk_scripts,
    stop_process,
)
from .updater import sync_scripts
from .version import APP_VERSION


class Api:
    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self._prefs: dict = self._load_prefs()
        self._definitions: list[ScriptDefinition] = []
        self._global_keybinds: list[KeybindDefinition] = []
        self._keybind_settings: dict[str, str] = {}
        self._keybinds_initialized: bool = False
        self._selected_id: str | None = None
        self._running_process = None
        self._running_definition: ScriptDefinition | None = None
        self._running_option_overrides: dict[str, str] = {}
        self._last_exit_unexpected: bool = False
        self._timing_overrides: dict[str, str] = {}
        self._last_version_notice: str = ""

        self._reload_definitions()
        self._global_keybinds = self._build_global_keybinds()
        self._keybind_settings = self._load_keybind_settings()
        self._apply_saved_keybinds()
        self._keybinds_initialized = bool(self._keybind_settings)

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    # --- Window control ---

    def minimize_window(self) -> None:
        if self._window:
            self._window.minimize()

    def close_window(self) -> None:
        self._shutdown_scripts()
        if self._window:
            self._window.destroy()

    def open_url(self, url: str) -> None:
        import webbrowser
        webbrowser.open(url)

    def get_position(self) -> dict:
        if self._window:
            return {"x": self._window.x, "y": self._window.y}
        return {"x": 0, "y": 0}

    def move_window(self, x: int, y: int) -> None:
        if self._window:
            self._window.move(int(x), int(y))

    def get_size(self) -> dict:
        if self._window:
            return {"width": self._window.width, "height": self._window.height}
        return {"width": 860, "height": 760}

    def resize_window(self, width: int, height: int) -> None:
        if self._window:
            self._window.resize(max(700, int(width)), max(640, int(height)))

    # --- Initialization ---

    def get_initial_state(self) -> dict:
        scripts = self._script_list()
        last_id = self._prefs.get("last_selected_script_id")
        selected_data = None
        if last_id:
            definition = next((d for d in self._definitions if d.id == last_id and not d.disabled), None)
            if definition:
                self._selected_id = definition.id
                self._timing_overrides = {t.key: t.value for t in definition.timings}
                selected_data = self._script_detail(definition)

        return {
            "scripts": scripts,
            "selected": selected_data,
            "keybinds_initialized": self._keybinds_initialized,
            "version": APP_VERSION,
            "ahk_label": current_ahk_runtime_label(),
            "perks": self._perks_data(),
            "status": self._status_data(),
        }

    def get_version(self) -> str:
        return APP_VERSION

    # --- Script list and selection ---

    def get_scripts(self) -> list[dict]:
        return self._script_list()

    def select_script(self, script_id: str) -> dict:
        definition = next((d for d in self._definitions if d.id == script_id), None)
        if definition is None:
            return {"error": "Script not found"}
        if definition.disabled:
            return {"error": "disabled", "name": definition.name}

        if self._has_running_script() and self._running_definition and self._running_definition.id != script_id:
            result = self._stop_running_script()
            if not result.ok:
                return {"error": result.message}
        elif self._running_definition and self._running_definition.id != script_id:
            stop_managed_ahk_scripts(self._definitions)
            self._running_process = None
            self._running_definition = None

        self._selected_id = script_id
        self._prefs["last_selected_script_id"] = script_id
        self._save_prefs()
        self._timing_overrides = {t.key: t.value for t in definition.timings}
        return {"ok": True, "detail": self._script_detail(definition), "status": self._status_data()}

    def clear_selection(self) -> dict:
        self._selected_id = None
        return {"ok": True, "status": self._status_data()}

    # --- Timings ---

    def update_timing(self, key: str, value: str) -> dict:
        self._timing_overrides[key] = value
        return {"ok": True, "dirty_keys": self._dirty_option_keys()}

    # --- Launch / stop ---

    def launch_selected(self) -> dict:
        definition = self._selected_definition()
        if definition is None:
            return {"ok": False, "message": "No script selected"}

        if not self._keybinds_initialized:
            return {"ok": False, "message": "Set your keybinds first before launching"}

        errors = self._validate_launch()
        if errors:
            return {"ok": False, "message": "\n".join(errors)}

        if self._has_running_script():
            stop_result = self._stop_running_script()
            if not stop_result.ok:
                return {"ok": False, "message": stop_result.message}

        stop_managed_ahk_scripts(self._definitions)
        self._running_process = None
        self._running_definition = None

        option_overrides = self._collect_option_overrides(definition)
        bg_on = self._timing_overrides.get("background_input") == "1" or (
            any(t.key == "background_input" and t.value == "1" for t in definition.timings)
            and "background_input" not in self._timing_overrides
        )
        extra_args = ["--auto-start", "1"] if bg_on else None
        result = launch_script(definition, option_overrides, extra_args)
        if result.ok:
            self._running_process = result.process
            self._running_definition = definition
            self._running_option_overrides = option_overrides.copy()
            self._last_exit_unexpected = False

        return {"ok": result.ok, "message": result.message, "status": self._status_data()}

    def stop_selected(self) -> dict:
        if not self._has_running_script():
            return {"ok": False, "message": "Nothing is running", "status": self._status_data()}
        result = self._stop_running_script()
        return {"ok": result.ok, "message": result.message, "status": self._status_data()}

    def stop_all(self) -> dict:
        self._shutdown_scripts()
        return {"ok": True, "message": "Stopped all managed scripts", "status": self._status_data()}

    def get_status(self) -> dict:
        return self._status_data()

    # --- Sync ---

    def sync_scripts_cmd(self) -> None:
        thread = threading.Thread(target=self._run_sync, daemon=True)
        thread.start()

    # --- Perks / images ---

    def get_perks(self) -> dict:
        return self._perks_data()

    def get_image_b64(self, relative_path: str) -> str:
        path = resources_root() / relative_path
        if not path.exists():
            return ""
        try:
            return base64.b64encode(path.read_bytes()).decode("ascii")
        except Exception:
            return ""

    # --- Setup items ---

    def get_setup_items(self, script_name: str) -> dict:
        items = [
            "Load into Ashes of the Damned Directed mode and go up to Round Cap 7/10/12.",
            "Stand in the pictured spot and aim at the wooden post.",
            "Select your desired script, launch it and use the Toggle Script keybind to launch.",
            "Upgrade your gun as much as possible, goal is to kill the zombies with 1 shot.",
        ]
        if script_name in {"Shotgun", "Sniper"}:
            items.append("Ensure you have a Tomahawk equipped!")
        return {
            "items": items,
            "tip": "Keep pictured door CLOSED for the fastest spawns",
            "tip_image": "pictures/Closed.png",
            "setup_image": "pictures/Spot.png",
        }

    # --- Keybinds ---

    def get_keybinds(self) -> list[dict]:
        return [
            {
                "key": kb.key,
                "label": kb.label,
                "value": format_keybind_display(kb.value),
                "placeholder": format_keybind_display(kb.placeholder) if kb.placeholder else "",
            }
            for kb in self._global_keybinds
        ]

    def save_keybinds(self, data: list[dict]) -> dict:
        for item in data:
            key = item.get("key", "")
            raw_value = item.get("value", "")
            keybind = next((kb for kb in self._global_keybinds if kb.key == key), None)
            if keybind is None:
                continue
            resolved = normalize_keybind_value(raw_value.strip() or keybind.placeholder or keybind.value)
            keybind.value = resolved
            self._keybind_settings[key] = resolved
            for definition in self._definitions:
                for kb in definition.keybinds:
                    if kb.key == key:
                        kb.value = resolved

        self._save_keybind_settings()
        self._keybinds_initialized = True
        return {"ok": True, "keybinds_initialized": True}

    # --- Presets ---

    def get_presets(self, script_id: str) -> list[dict]:
        all_presets = self._load_presets()
        return [{"name": n, "values": v} for n, v in all_presets.get(script_id, {}).items()]

    def save_preset(self, script_id: str, name: str) -> dict:
        name = name.strip()
        if not name:
            return {"ok": False, "message": "Preset name cannot be empty"}
        all_presets = self._load_presets()
        all_presets.setdefault(script_id, {})[name] = dict(self._timing_overrides)
        self._save_presets(all_presets)
        return {"ok": True, "presets": self.get_presets(script_id)}

    def load_preset(self, script_id: str, name: str) -> dict:
        all_presets = self._load_presets()
        values = all_presets.get(script_id, {}).get(name)
        if values is None:
            return {"ok": False, "message": "Preset not found"}
        self._timing_overrides.update(values)
        definition = self._selected_definition()
        if definition is None:
            return {"ok": False, "message": "No script selected"}
        timings = [
            {
                "key": t.key,
                "label": t.label,
                "control": t.control,
                "value": self._timing_overrides.get(t.key, t.value),
                "suffix": t.suffix,
                "false_value": t.false_value,
                "true_value": t.true_value,
                "column": t.column,
            }
            for t in definition.timings
        ]
        return {"ok": True, "timings": timings, "dirty_keys": self._dirty_option_keys()}

    def delete_preset(self, script_id: str, name: str) -> dict:
        all_presets = self._load_presets()
        all_presets.get(script_id, {}).pop(name, None)
        self._save_presets(all_presets)
        return {"ok": True, "presets": self.get_presets(script_id)}

    # --- Prefs ---

    def suppress_warning(self, key: str) -> dict:
        self._prefs[key] = True
        self._save_prefs()
        return {"ok": True}

    def get_pref(self, key: str) -> dict:
        return {"value": self._prefs.get(key)}

    # --- Internal ---

    def _script_list(self) -> list[dict]:
        return [
            {"id": d.id, "name": d.name, "accent": d.accent, "disabled": d.disabled}
            for d in self._definitions
        ]

    def _script_detail(self, definition: ScriptDefinition) -> dict:
        timings = [
            {
                "key": t.key,
                "label": t.label,
                "control": t.control,
                "value": self._timing_overrides.get(t.key, t.value),
                "suffix": t.suffix,
                "false_value": t.false_value,
                "true_value": t.true_value,
                "column": t.column,
            }
            for t in definition.timings
        ]
        return {
            "id": definition.id,
            "name": definition.name,
            "accent": definition.accent,
            "timings": timings,
            "has_gpc": definition.gpc is not None and definition.gpc.supported,
        }

    def _selected_definition(self) -> ScriptDefinition | None:
        if self._selected_id is None:
            return None
        return next((d for d in self._definitions if d.id == self._selected_id), None)

    def _status_data(self) -> dict:
        running = self._has_running_script()
        definition = self._selected_definition()
        return {
            "running": running,
            "running_id": self._running_definition.id if self._running_definition else None,
            "selected_id": self._selected_id,
            "status_text": self._status_text(),
            "dirty_keys": self._dirty_option_keys(),
            "last_exit_unexpected": self._last_exit_unexpected,
            "keybinds_initialized": self._keybinds_initialized,
            "selected_is_running": self._is_selected_running(),
        }

    def _status_text(self) -> str:
        if self._has_running_script() and self._running_definition:
            return f"Running {self._running_definition.name}"
        definition = self._selected_definition()
        if definition:
            return f"Ready — {definition.name}"
        return "Select a script to begin"

    def _has_running_script(self) -> bool:
        if self._running_process is None:
            return False
        if self._running_process.poll() is None:
            return True
        self._last_exit_unexpected = self._running_definition is not None
        self._running_process = None
        self._running_definition = None
        self._running_option_overrides = {}
        return False

    def _is_selected_running(self) -> bool:
        return (
            self._selected_id is not None
            and self._running_definition is not None
            and self._selected_id == self._running_definition.id
            and self._has_running_script()
        )

    def _stop_running_script(self):
        result = stop_process(self._running_process)
        if result.ok:
            self._running_process = None
            self._running_definition = None
            self._running_option_overrides = {}
            self._last_exit_unexpected = False
        return result

    def _shutdown_scripts(self) -> None:
        if self._running_process is not None:
            self._stop_running_script()
        stop_managed_ahk_scripts(self._definitions)

    def _collect_option_overrides(self, definition: ScriptDefinition) -> dict[str, str]:
        overrides: dict[str, str] = {}
        for timing in definition.timings:
            overrides[timing.key] = self._timing_overrides.get(timing.key, timing.value)
        for keybind in definition.keybinds:
            overrides[keybind.key] = keybind.value
        return overrides

    def _dirty_option_keys(self) -> list[str]:
        definition = self._selected_definition()
        if definition is None or not self._running_option_overrides:
            return []
        dirty: list[str] = []
        for timing in definition.timings:
            current = self._timing_overrides.get(timing.key, timing.value)
            if current != self._running_option_overrides.get(timing.key, ""):
                dirty.append(timing.label)
        return dirty

    def _validate_launch(self) -> list[str]:
        errors: list[str] = []
        toggle_key = self._keybind_settings.get("toggle_key", "").strip()
        exit_key = self._keybind_settings.get("exit_key", "").strip()
        if not toggle_key:
            errors.append("Toggle key not set — open Keybinds and save first.")
        if not exit_key:
            errors.append("Exit key not set — open Keybinds and save first.")
        return errors

    def _perks_data(self) -> dict:
        shared_perks = load_shared_perks(resources_root() / "loadout.json")

        def perk_to_dict(perk):
            return {
                "name": perk.name,
                "image": perk.image,
                "augments": [{"slot": a.slot, "name": a.name, "image": a.image} for a in perk.augments],
            }

        return {
            "required": [perk_to_dict(p) for p in shared_perks.required],
            "recommended": [perk_to_dict(p) for p in shared_perks.recommended],
        }

    def _reload_definitions(self) -> None:
        definitions = load_definitions(active_scripts_json_path(), project_root())
        self._definitions = [d for d in definitions if resolve_entry(d.entry).exists()]

    def _build_global_keybinds(self) -> list[KeybindDefinition]:
        desired_order = ["toggle_key", "exit_key", "lethal_key", "weapon_switch_key", "scoreboard_key", "melee_key"]
        found: dict[str, KeybindDefinition] = {}
        for definition in self._definitions:
            for keybind in definition.keybinds:
                found.setdefault(keybind.key, KeybindDefinition(
                    key=keybind.key, label=keybind.label, flag=keybind.flag,
                    value=keybind.value, placeholder=keybind.placeholder,
                ))
        ordered: list[KeybindDefinition] = []
        for key in desired_order:
            if key in found:
                ordered.append(found[key])
        for key, keybind in found.items():
            if key not in desired_order:
                ordered.append(keybind)
        return ordered

    def _load_keybind_settings(self) -> dict[str, str]:
        path = keybind_settings_path()
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        settings: dict[str, str] = {}
        for key, value in raw.items():
            if isinstance(key, str) and value is not None and not isinstance(value, dict):
                settings[key] = normalize_keybind_value(str(value))
        for script_values in raw.values():
            if not isinstance(script_values, dict):
                continue
            for key, value in script_values.items():
                if isinstance(key, str) and value is not None and key not in settings:
                    settings[key] = normalize_keybind_value(str(value))
        return settings

    def _apply_saved_keybinds(self) -> None:
        global_values = {item.key: item for item in self._global_keybinds}
        for key, value in self._keybind_settings.items():
            if key in global_values:
                global_values[key].value = value
        for definition in self._definitions:
            for keybind in definition.keybinds:
                if keybind.key in global_values:
                    keybind.value = global_values[keybind.key].value

    def _save_keybind_settings(self) -> None:
        path = keybind_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._keybind_settings, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _load_presets(self) -> dict:
        path = managed_runtime_dir() / "presets.json"
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _save_presets(self, data: dict) -> None:
        path = managed_runtime_dir() / "presets.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def _load_prefs(self) -> dict:
        path = prefs_path()
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _save_prefs(self) -> None:
        path = prefs_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._prefs, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass

    def _run_sync(self) -> None:
        result = sync_scripts()
        previous_selected_id = self._selected_id
        self._reload_definitions()
        self._global_keybinds = self._build_global_keybinds()
        self._apply_saved_keybinds()

        if previous_selected_id:
            restored = next((d for d in self._definitions if d.id == previous_selected_id), None)
            if restored is None:
                self._selected_id = None

        if self._window:
            scripts_js = json.dumps(self._script_list())
            summary_js = json.dumps(result.summary())
            errors_js = json.dumps(result.errors[:5] if result.errors else [])
            update_js = json.dumps({
                "available": result.app_update_available,
                "current": result.current_version,
                "latest": result.latest_version or "",
                "url": result.release_url or "",
            })
            self._window.evaluate_js(
                f"window.onSyncDone && window.onSyncDone({scripts_js}, {summary_js}, {errors_js}, {update_js})"
            )
