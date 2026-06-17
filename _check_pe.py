"""One-shot PE check & rebuild verification."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))

PE_JSON = pathlib.Path(__file__).parent / "parameter_experience_memory.json"
PE_BASE = pathlib.Path(__file__).parent / "parameter_experience_base"

# 1. Check main JSON
d = json.loads(PE_JSON.read_text(encoding="utf-8"))
lt = d.get("long_term", [])
st = d.get("short_term", [])
print(f"[Main JSON] long_term={len(lt)}  short_term={len(st)}  episodic={len(d.get('episodic',[]))}")

# 2. Check base dir files
lt_files = list((PE_BASE / "params" / "long_term").glob("*.json"))
st_files = list((PE_BASE / "params" / "short_term").glob("*.json"))
print(f"[Base Dir]  long_term_files={len(lt_files)}  short_term_files={len(st_files)}")

# 3. If main JSON empty but files exist, trigger rebuild
if not lt and lt_files:
    print("\n>>> Main JSON empty but base dir has files. Triggering rebuild...")
    from multi_agent.memory.parameter_experience import ParameterExperience
    pe = ParameterExperience(
        experience_base_dir=str(PE_BASE),
        persist_path=str(PE_JSON),
    )
    print(f">>> After rebuild: LT={len(pe._long_term_memory)}  ST={len(pe._short_term_memory)}")
    # Show T4 records
    t4 = [e for e in pe._long_term_memory.values() if e.task_context.get("SUB_IDX") == 4]
    print(f">>> T4 records: {len(t4)}")
    for e in t4:
        o = e.objectives
        print(f"    {e.memory_id[:16]}  fit={e.fitness:.3f}  hit={o.get('hit_rate',0):.0f}%  "
              f"PM={o.get('pitch_PM',0):.1f}  BW={o.get('pitch_BW',0):.1f}")
else:
    print(f"\n[OK] Main JSON already has {len(lt)} long_term entries.")
    t4 = [e for e in lt if e.get("task_context", {}).get("SUB_IDX") == 4]
    print(f"T4 records: {len(t4)}")
    for e in t4:
        o = e.get("objectives", {})
        print(f"    {e['memory_id'][:16]}  fit={e['fitness']:.3f}  hit={o.get('hit_rate',0):.0f}%  "
              f"PM={o.get('pitch_PM',0):.1f}  BW={o.get('pitch_BW',0):.1f}")
