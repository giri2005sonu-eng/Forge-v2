from fastapi import APIRouter, Cookie, HTTPException
from typing import Optional

from core import firmware, wiring
from server.state import store

router = APIRouter(prefix="/api/wiring", tags=["wiring"])


@router.get("")
def get_wiring_data(forge_session: Optional[str] = Cookie(None)):
    session = store.get_or_create(forge_session)
    parts = session.get_active_parts()
    if not parts:
        raise HTTPException(status_code=400, detail="No active BOM build for wiring")

    label = session.get_build_label()
    parts_dict = parts if isinstance(parts, dict) else {p.get("role", f"part_{i}"): p for i, p in enumerate(parts)}

    data = wiring.generate_wiring(parts_dict, project_label=label)
    ctrl = data["controller"]
    conns = data["connections"]

    ard_res = firmware.generate_arduino_firmware(parts_dict, conns, ctrl, label)
    mpy_res = firmware.generate_micropython_firmware(parts_dict, conns, ctrl, label)

    arduino_code = ard_res.get("code", "") if isinstance(ard_res, dict) else str(ard_res)
    micropython_code = mpy_res.get("code", "") if isinstance(mpy_res, dict) else str(mpy_res)

    return {
        "controller": ctrl,
        "connections": conns,
        "wokwi_diagram": data.get("wokwi_diagram", {}),
        "wokwi_json_str": data.get("wokwi_json_str", "{}"),
        "mermaid_code": data.get("mermaid_code", ""),
        "svg_canvas": data.get("svg_canvas", ""),
        "arduino_code": arduino_code,
        "micropython_code": micropython_code,
        "label": label,
    }
