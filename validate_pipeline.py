import ast, sys

files = [
    "edge/pipeline.py",
    "backend/services/cv_event_bus.py",
]

all_ok = True
for fpath in files:
    try:
        with open(fpath, encoding="utf-8") as f:
            src = f.read()
        ast.parse(src)
        print(f"[OK] {fpath}")
    except SyntaxError as e:
        print(f"[SYNTAX ERROR] {fpath}: {e}")
        all_ok = False
    except FileNotFoundError:
        print(f"[NOT FOUND] {fpath}")
        all_ok = False

# Also verify all 5 camera YAML files exist
import os, yaml
cam_yamls = [
    "edge/config/cameras/cam1_entrance.yaml",
    "edge/config/cameras/cam2_top_shelves.yaml",
    "edge/config/cameras/cam3_foh_makeup.yaml",
    "edge/config/cameras/cam4_bottom_shelves.yaml",
    "edge/config/cameras/cam5_checkout.yaml",
]
for y in cam_yamls:
    if os.path.exists(y):
        with open(y) as f:
            cfg = yaml.safe_load(f)
        n_zones = len(cfg.get("zones", []))
        print(f"[OK] {y} — {n_zones} zones | cam_id={cfg.get('camera_id','?')[:16]}")
    else:
        print(f"[MISSING] {y}")
        all_ok = False

print()
print("All OK!" if all_ok else "Errors found — check above.")
