"""Blueprint grounding: the UI must stay aligned with ui_design.pen."""

import json
import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
REGIONS = [
    "header-brand-and-model-selector",
    "upload-media-dropzone",
    "job-status-progress",
    "media-player-panel-with-waveform",
    "click-to-seek-transcript-editor",
    "multi-format-export-panel",
    "blueprint-grounding-footer",
]


def blueprint_names(node, found=None):
    found = found if found is not None else set()
    if isinstance(node, dict):
        if node.get("name"):
            found.add(node["name"])
        if node.get("id"):
            found.add(node["id"])
        for child in node.get("children", []):
            blueprint_names(child, found)
    elif isinstance(node, list):
        for child in node:
            blueprint_names(child, found)
    return found


def test_pen_is_valid_json_and_defines_every_region():
    payload = json.loads((FRONTEND / "ui_design.pen").read_text(encoding="utf-8"))
    names = blueprint_names(payload)
    for region in REGIONS:
        assert region in names, f"missing blueprint node {region}"
    assert "model-size" in names
    assert "model-select" in names


def test_exported_svg_preview_exists():
    svg = (FRONTEND / "ui_design.svg").read_text(encoding="utf-8")
    assert svg.lstrip().startswith("<svg")
    assert "Antigravity Studio" in svg


def test_index_html_ids_match_blueprint_regions():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([^"]+)"', html))
    for region in REGIONS:
        assert region in ids, f"index.html drifted from blueprint: {region}"
    for anchor in ("model-size", "model-select", "waveform", "media-player", "progress-track"):
        assert anchor in ids
    assert "./ui_design.svg" in html


def test_frontend_is_vanilla_esm_grounded_in_the_api():
    main = (FRONTEND / "src" / "main.js").read_text(encoding="utf-8")
    api = (FRONTEND / "src" / "api.js").read_text(encoding="utf-8")
    assert "Waveform" in main
    assert "seekTo" in main
    assert "/api/jobs" in api
    assert "/api/export" in api
    assert "getModels" in api
    assert (FRONTEND / "vite.config.js").exists()
    assert (FRONTEND / "package.json").exists()
