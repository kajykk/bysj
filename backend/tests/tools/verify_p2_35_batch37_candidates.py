"""第三十七批存在性核查：1 接线 + 14 不接，12 文件 15 条。

挑簇口径（第五代信号：条目级终局扫描 + 人工逐簇分离）：
- 第三十七批挑簇（pick_p2_35_batch37_candidates.py）沿用第四代信号
  （location 登记表零收录）⇒ **候选 0 个**（排除文件 83 个 = 文件级
  信号耗尽）。**信号耗尽 ≠ 审计完成**。
- 转条目级：final_sweep_p2_35_round13.py 对 scan 全量 334 候选
  （318 真降级 + 16 ImportError 探针）逐条在三份审计文档查五种登记
  形态（路径:行号 / basename+L号 / 表格行共现 / 函数名+basename 同行 /
  L号±5行宽容），查不到 ⇒ 输出候选池 ⇒ **93 条 / 31 文件**。
- 本批人工逐簇核对 93 条：**78 条确认已裁残留**（历批登记格式多达
  六七种：location 表格行 / L号列 / 函数名 L号 / 路径:行号 / 裸数字 /
  中文括号行号等，文本匹配不可能穷尽 ⇒ 分离靠人工），**15 条真新
  库存**即本批工作面。

本批接线（X 117→116，W 102→103）：
    app/services/model_predict/fusion.py:229  事件写入失败
      —— 本函数是 MonitoringLog INFERENCE/FALLBACK 事件的**唯一写入方**
      （alert_lifecycle 只写 DRIFT_ALERT），而这两类事件正是
      auto_rollback_service.check_canary_rollback 计算 fallback_rate 的
      输入（L253-270 按 event_type + model_version + 1h 窗口计数）。
      写入失败 ⇒ 分子/分母同时缺样本 ⇒ fallback_rate 低估 ⇒ 超阈值
      金丝雀的回滚被静默抑制（安全侧）；RollbackCheckResult.metrics
      只报计数、无「数据可能不完整」标记 ⇒ 调用方无从分辨（同形）。

不接 14 条（逐条硬判据见 P2_13「一之三十八」节）：
  celery_app.py:254 S（DLQ error 日志+exc_info 已在，except 只包指标自增）/
  canary_fallback_monitor.py:232 K（停机取消标准清理）/
  canary_fallback_monitor.py:234 C（停机清理，任务已终止，warning+exc_info）/
  event_bus.py:141 K（同上）/
  observability_service.py:121 K（同上，且 stop 仍执行 final flush）/
  cache.py:241/247 C（停机 aclose 失败，warning，单例照旧重置）/
  kill_switch.py:119 V（调用方 _degrade 显式 degraded=True/source=unavailable
  +fail-closed，P1-7 有意设计）/
  main.py:396 V（启动 warning + 影响点（上传端点）显式失败）/
  reports.py:355 P（notify_task_progress→ws send_to_user 两条内层路径
  L175/L203 均已接线，外层是防御性重复层）/
  reports.py:403 V（status=failed+error 入 job_store + notify，调用方可见）/
  validation.py:254 D（单条 created_at 畸形只跳过自己，与第三十二批
  user_data_service 同型）/
  validation.py:478 V（status=failed+error 入 job_store + error 日志）/
  model_predict/inference.py:150 P（包裹的三个调用：单例获取/内存 dict
  更新/唯一现实异常（create_task RuntimeError）已被内层捕获且第十批接线
  ⇒ 外层运行期不可达）

运行时证据见 `probe_p2_35_batch37_runtime.py`。
"""

from __future__ import annotations

import ast
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[2]
BEPKG = BACKEND

# (文件, except 行号, 所属函数, 裁定桶, 是否接线)
CANDIDATES = [
    ("app/core/celery_app.py", 254, "on_task_failure", "S", False),
    ("app/services/canary_fallback_monitor.py", 232, "stop_canary_fallback_monitor", "K", False),
    ("app/services/canary_fallback_monitor.py", 234, "stop_canary_fallback_monitor", "C", False),
    ("app/core/event_bus.py", 141, "stop", "K", False),
    ("app/services/observability_service.py", 121, "stop", "K", False),
    ("app/core/cache.py", 241, "close_redis_client", "C", False),
    ("app/core/cache.py", 247, "close_redis_client", "C", False),
    ("app/core/kill_switch.py", 119, "_get_redis", "V", False),
    ("app/main.py", 396, None, "V", False),  # ROUND_40 +17
    ("app/api/v1/reports.py", 355, "_notify", "P", False),
    ("app/api/v1/reports.py", 403, "_execute_pdf_generation", "V", False),
    ("app/api/v1/validation.py", 254, "_cleanup_memory_expired", "D", False),
    ("app/api/v1/validation.py", 478, "_execute_validation", "V", False),
    ("app/services/model_predict/inference.py", 150, "_fire_shadow_check", "P", False),
    ("app/services/model_predict/fusion.py", 229, "_log_canary_event", "W", True),
]

LOCATION = "services.model_predict.fusion.canary_event_log_failed"


def handler_at(rel: str, line: int) -> ast.ExceptHandler:
    tree = ast.parse((BEPKG / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.lineno == line:
            return node
    raise AssertionError(f"{rel}:{line} 处没有 except handler（行号漂移）")


def enclosing(rel: str, line: int) -> str | None:
    tree = ast.parse((BEPKG / rel).read_text(encoding="utf-8"))
    best: tuple[int, str] | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= line <= (node.end_lineno or node.lineno):
                if best is None or node.lineno > best[0]:
                    best = (node.lineno, node.name)
    return best[1] if best else None


def main() -> int:
    missing = 0
    drift = 0
    wired_count = 0
    buckets: dict[str, int] = {}
    for rel, line, fn_name, bucket, wired in CANDIDATES:
        buckets[bucket] = buckets.get(bucket, 0) + 1
        try:
            handler = handler_at(rel, line)
        except AssertionError as e:
            print(f"MISSING  {rel}:{line}  {e}")
            missing += 1
            continue
        actual = enclosing(rel, line)
        if fn_name is not None and actual != fn_name:
            print(f"FUNC-DRIFT  {rel}:{line}  期望 {fn_name}，实际 {actual}")
            drift += 1
        seg = ast.unparse(handler)
        has = "record_silent_degradation" in seg
        if wired:
            if has:
                wired_count += 1
                print(f"WIRED-OK   {rel}:{line} ({fn_name}) 接线在位")
            else:
                print(f"WIRE-LOST  {rel}:{line} ({fn_name}) 接线消失！")
                missing += 1
        else:
            if has:
                print(f"UNEXPECTED-WIRE  {rel}:{line} ({fn_name}) 出现了接线！")
                drift += 1
            else:
                print(f"OK         {rel}:{line} ({fn_name}) [{bucket}] 未接线（符合裁定）")
    print("=" * 78)
    print("第三十七批存在性核查（1 接线 + 14 不接，15 条）")
    print("=" * 78)
    print(f"MISSING={missing}  FUNC-DRIFT={drift}  接线={wired_count}（期望 1）")
    print(f"分类器桶分布：{buckets}")
    ok = missing == 0 and drift == 0 and wired_count == 1
    print("结论：" + ("全部通过" if ok else "存在偏差，需修正"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
