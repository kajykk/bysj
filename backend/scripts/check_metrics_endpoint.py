"""检查 /api/v1/metrics 端点是否输出 model_inference 指标."""
import os
import urllib.request

token = os.environ.get("METRICS_ACCESS_TOKEN", "")
req = urllib.request.Request(
    "http://localhost:8000/api/v1/metrics",
    headers={"Authorization": f"Bearer {token}"},
)
try:
    resp = urllib.request.urlopen(req, timeout=10)
    content = resp.read().decode()
    print(f"HTTP {resp.status}, total bytes: {len(content)}")
    lines = content.split("\n")
    # 找 model_inference 相关
    matched = [l for l in lines if "model_inference" in l or "fusion_canary" in l]
    if matched:
        print(f"\n找到 {len(matched)} 行 model_inference/fusion_canary 指标:")
        for l in matched[:30]:
            print(f"  {l}")
    else:
        print("\n[!] 未找到 model_inference 相关指标")
        # 输出所有指标名 (TYPE 行)
        type_lines = [l for l in lines if l.startswith("# TYPE")]
        print(f"\n/metrics 端点共 {len(type_lines)} 个指标:")
        for l in type_lines[:30]:
            print(f"  {l}")
        if len(type_lines) > 30:
            print(f"  ... (省略 {len(type_lines) - 30} 个)")

    # 检查 registry 中是否有 model_inference_total
    print("\n检查 metrics 模块中的 _REGISTRY:")
    try:
        from app.core import metrics as m
        all_keys = list(m._REGISTRY.keys())
        print(f"  _REGISTRY 共 {len(all_keys)} 个指标")
        inference_keys = [k for k in all_keys if "inference" in k or "canary" in k or "fusion" in k]
        print(f"  inference/canary/fusion 相关: {inference_keys}")
        if "model_inference_total" in m._REGISTRY:
            meta = m._REGISTRY["model_inference_total"]
            instance = meta.get("instance")
            try:
                collected = list(instance.collect())
                print(f"  model_inference_total.collect() 返回 {len(collected)} 条:")
                for entry in collected[:10]:
                    print(f"    {entry}")
            except Exception as e:
                print(f"  collect() failed: {e}")
        else:
            print("  [!] model_inference_total 不在 _REGISTRY 中")
    except Exception as e:
        print(f"  import metrics failed: {e}")
except Exception as e:
    print(f"Request failed: {type(e).__name__}: {e}")
