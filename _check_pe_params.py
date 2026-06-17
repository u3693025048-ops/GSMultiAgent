"""Check PE T4 records for non-empty parameters."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))

PE_JSON = pathlib.Path(__file__).parent / "parameter_experience_memory.json"
d = json.loads(PE_JSON.read_text(encoding="utf-8"))

lt = d.get("long_term", [])
print(f"Total long_term: {len(lt)}")
print()

# Show ALL records with their parameters status
for i, e in enumerate(lt):
    tc = e.get("task_context", {})
    params = e.get("parameters", {})
    objs = e.get("objectives", {})
    fit = e.get("fitness", 0)
    mid = e.get("memory_id", "")[:16]
    si = tc.get("SUB_IDX", "?")
    rc = tc.get("RUN_CASE", "?")
    has_params = bool(params and any(v for v in params.values()))
    
    # Only show T4 or records with interesting data
    if si == 4 or (rc == "T" and si == 4):
        print(f"Record#{i}: {mid}  RC={rc} SI={si}  fit={fit:.3f}  "
              f"params={'NON-EMPTY' if has_params else 'EMPTY'}  "
              f"n_params={len(params)}")
        if has_params:
            print(f"  params: {json.dumps(params, indent=2)}")
        if objs:
            print(f"  objectives: {json.dumps(objs)}")
        print()

# Also check: how many records total have non-empty params?
n_with = sum(1 for e in lt if e.get("parameters") and any(v for v in e["parameters"].values()))
n_without = len(lt) - n_with
print(f"\nSummary: {n_with} records with params, {n_without} records with EMPTY params")

# Show a few records WITH params for reference
print("\n--- Sample records WITH params ---")
count = 0
for i, e in enumerate(lt):
    params = e.get("parameters", {})
    if params and any(v for v in params.values()):
        tc = e.get("task_context", {})
        mid = e.get("memory_id", "")[:16]
        print(f"  Record#{i}: {mid}  RC={tc.get('RUN_CASE','?')} SI={tc.get('SUB_IDX','?')}  "
              f"n_params={len(params)}  keys={list(params.keys())[:5]}...")
        count += 1
        if count >= 5:
            break
