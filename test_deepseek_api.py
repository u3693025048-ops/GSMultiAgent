"""
Diagnostic script: test DeepSeek API with different prompt strategies.
Run: python test_deepseek_api.py
"""
import openai, time

API_KEY = "sk-4ac3052962934920b3934de9565a52c8"
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-pro"

client = openai.OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=60)

# The exact prompt used in Expert Tuning
EXPERT_PROMPT = (
    "导弹驾驶仪调参，第1轮。\n"
    "当前指标: 命中率=100.0% SEP=4.01m 峰值过载=4.4g PM=77.1° BW=6.3rad/s\n"
    "要求: 命中率>=92% SEP<=7m 峰值过载<=20g PM在45~70° BW在20~85\n"
    "★ PM & BW depend ONLY on pitch: w1(↑→↑BW,↓PM), zeta1(↑→↑PM), tao1(↑→↓PM)\n"
    "Good region: w1∈[25,50], zeta1∈[0.6,1.0], tao1∈[0.08,0.25]\n"
    "Yaw(w2,zeta2,tao2): affects SEP lateral. Roll(w3,zeta3): affects PeakNy.\n"
    "N_pn(1-8): ↑→↑hit,↓SEP,↑PeakNy.\n"
    "参数范围: w1[10,80] | zeta1[0.2,1.5] | tao1[0.05,0.6] | w2[10,80] | zeta2[0.2,1.5] | tao2[0.05,0.6] | w3[10,80] | zeta3[0.2,1.5] | N_pn[1,8]\n"
    "历史: None\n\n"
    '请直接给出9个参数的数值，只返回JSON:\n'
    '{"w1":数值,"zeta1":数值,"tao1":数值,"w2":数值,"zeta2":数值,"tao2":数值,"w3":数值,"zeta3":数值,"N_pn":数值,"analysis":"原因"}'
)

tests = [
    # Test 1: max_tokens=4096 (the fix)
    {
        "name": "max_tokens=4096 (FIX)",
        "messages": [{"role": "user", "content": EXPERT_PROMPT}],
        "temperature": 0.4,
        "max_tokens": 4096,
    },
    # Test 2: max_tokens=600 (old broken value)
    {
        "name": "max_tokens=600 (OLD)",
        "messages": [{"role": "user", "content": EXPERT_PROMPT}],
        "temperature": 0.4,
        "max_tokens": 600,
    },
    # Test 3: max_tokens=8192
    {
        "name": "max_tokens=8192",
        "messages": [{"role": "user", "content": EXPERT_PROMPT}],
        "temperature": 0.4,
        "max_tokens": 8192,
    },
]

print(f"Testing DeepSeek API: model={MODEL}")
print(f"{'='*70}")

for i, t in enumerate(tests, 1):
    name = t.pop("name")
    print(f"\n--- Test {i}: {name} ---")
    try:
        start = time.time()
        resp = client.chat.completions.create(model=MODEL, **t)
        elapsed = time.time() - start
        content = (resp.choices[0].message.content or "").strip()
        finish_reason = resp.choices[0].finish_reason
        print(f"  Time: {elapsed:.1f}s | finish_reason: {finish_reason}")
        if content:
            print(f"  Response ({len(content)} chars): {content[:300]}")
        else:
            print(f"  ⚠️ EMPTY RESPONSE")
            # Check if there's a refusal
            msg = resp.choices[0].message
            if hasattr(msg, 'refusal') and msg.refusal:
                print(f"  Refusal: {msg.refusal}")
    except Exception as exc:
        print(f"  ❌ ERROR: {exc}")
    time.sleep(2)

print(f"\n{'='*70}")
print("Done. Check which strategies return non-empty responses.")
