import ast, json, yaml, sys

# 1. Syntax check zone_analytics_engine.py
with open('backend/services/zone_analytics_engine.py', encoding='utf-8') as f:
    src = f.read()
ast.parse(src)
print('[OK] zone_analytics_engine.py — syntax valid')

# 2. Validate zone_config.json
with open('edge/config/zone_config.json', encoding='utf-8') as f:
    cfg = json.load(f)
zones = cfg['zones']
print(f'[OK] zone_config.json — {len(zones)} zones loaded')
for z in zones:
    assert 'zone_id' in z
    assert 'polygon' in z
    poly = z['polygon']
    assert len(poly) >= 3, f"Zone {z['zone_id']} polygon < 3 vertices"
print('[OK] All zone polygons valid (>= 3 vertices each)')

# 3. Validate YAML pipeline config
with open('edge/config/cameras/cam_brigade_full_store.yaml', encoding='utf-8') as f:
    pipe = yaml.safe_load(f)
print(f'[OK] cam_brigade_full_store.yaml — {len(pipe["zones"])} zones in pipeline config')

# 4. Zone ID cross-check
json_ids = {z['zone_id'] for z in zones}
yaml_ids = {z['id'] for z in pipe['zones']}
shared = json_ids & yaml_ids
print(f'[OK] Zone ID overlap: {len(shared)}/{len(yaml_ids)} YAML zones present in zone_config.json')

# 5. Print zone inventory
print()
print('ZONE INVENTORY:')
for z in zones:
    print(f"  {z['zone_id']:<42} type={z['zone_type']:<16} centroid={z['centroid']}")

# 6. Heatmap + shelf config checks
hm = cfg['heatmap_config']
print(f"\n[OK] Heatmap config: {hm['frame_width']}x{hm['frame_height']}px, scale={hm['grid_scale_px']}px, sigma={hm['kde_sigma']}")
shelf = cfg['shelf_engagement_config']
print(f"[OK] Shelf zones: {len(shelf['shelf_zones'])}, Brand zones: {len(shelf['brand_zone_ids'])}")

print("\nAll validations passed.")
