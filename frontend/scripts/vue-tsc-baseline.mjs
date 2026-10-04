#!/usr/bin/env node
/**
 * vue-tsc 错误数增量基线门禁 (决策四, 2026-10-02).
 *
 * 背景: 代码审查报告 §六 第 9 条 —— 前端存在 45 个存量 vue-tsc 错误,
 * 集中在 10 个 admin/counselor 表格组件的 Element Plus DefaultRow 泛型
 * 兼容性上. 全量清零属于重构范畴, 不属于本轮「危险路径止血」, 因此以
 * 错误总数做增量门禁:
 *
 *   - 错误总数 > BASELINE  -> 失败 (阻断存量继续恶化)
 *   - 错误总数 <= BASELINE -> 通过 (允许在存量范围内波动)
 *
 * 存量修复使错误数下降后, 应主动调低 BASELINE 收紧门禁 (棘轮式).
 * 查看完整错误列表: npm run typecheck
 *
 * 三种输入模式:
 *   node vue-tsc-baseline.mjs            自行 spawn vue-tsc (CI / 本地终端)
 *   node vue-tsc-baseline.mjs --stdin    从管道读 vue-tsc 输出
 *   node vue-tsc-baseline.mjs <file>     从文件读 vue-tsc 输出
 * stdin/file 模式用于受限环境验证 (如沙箱内嵌套 spawn 被禁):
 *   node node_modules/vue-tsc/bin/vue-tsc.js --noEmit -p tsconfig.app.json \
 *     --pretty false 2>&1 | node scripts/vue-tsc-baseline.mjs --stdin
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";

const BASELINE = 45;
const TSC_ARGS = ["--noEmit", "-p", "tsconfig.app.json", "--pretty", "false"];

const arg = process.argv[2] ?? "";
let output = "";
let exitStatus = null; // 仅 spawn 模式可知

if (arg === "--stdin") {
  output = fs.readFileSync(0, "utf8");
} else if (arg) {
  output = fs.readFileSync(path.resolve(process.cwd(), arg), "utf8");
} else {
  const require = createRequire(import.meta.url);
  const frontendRoot = path.resolve(import.meta.dirname, "..");
  let vueTscBin;
  try {
    vueTscBin = require.resolve("vue-tsc/bin/vue-tsc.js");
  } catch {
    console.error("[typecheck:baseline] 无法解析 vue-tsc, 请先 npm install");
    process.exit(2);
  }
  const result = spawnSync(process.execPath, [vueTscBin, ...TSC_ARGS], {
    encoding: "utf8",
    cwd: frontendRoot,
    maxBuffer: 64 * 1024 * 1024,
  });
  if (result.error) {
    console.error(
      `[typecheck:baseline] 无法启动 vue-tsc (${result.error.code ?? result.error}): ` +
        `受限环境可用 stdin 模式, 见脚本头部注释`
    );
    process.exit(2);
  }
  output = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;
  exitStatus = result.status;
}

const errorLines = output.split(/\r?\n/).filter((l) => /\berror TS\d+/.test(l));
const errorCount = errorLines.length;

// spawn 模式: 解析不到错误但退出码异常 —— vue-tsc 自身崩溃 (配置/依赖问题),
// 必须失败而不是静默放行
if (exitStatus !== null && errorCount === 0 && exitStatus !== 0) {
  console.error("[typecheck:baseline] vue-tsc 异常退出且未解析到错误行, 疑似崩溃:");
  console.error(output.split(/\r?\n/).slice(-30).join("\n"));
  process.exit(2);
}

// 按文件聚合, 便于定位漂移来源
const byFile = new Map();
for (const line of errorLines) {
  const file = line.split("(")[0].split(":")[0].trim();
  byFile.set(file, (byFile.get(file) ?? 0) + 1);
}

console.log(`[typecheck:baseline] vue-tsc 错误总数: ${errorCount} (基线 ${BASELINE})`);
if (byFile.size > 0) {
  const sorted = [...byFile.entries()].sort((a, b) => b[1] - a[1]);
  for (const [file, n] of sorted.slice(0, 15)) {
    console.log(`  ${n}\t${file}`);
  }
  if (sorted.length > 15) console.log(`  ... 共 ${sorted.length} 个文件`);
}

if (errorCount > BASELINE) {
  console.error(
    `[typecheck:baseline] ❌ 超出基线: ${errorCount} > ${BASELINE}. ` +
      `禁止新增 vue-tsc 错误. 运行 'npm run typecheck' 查看完整列表, ` +
      `新增错误必须当场修复; 修复存量后请调低脚本内 BASELINE.`
  );
  process.exit(1);
}

console.log(
  `[typecheck:baseline] ✅ 通过. ` +
    (errorCount === 0
      ? `错误已清零, 请把 BASELINE 调为 0 收紧门禁!`
      : `存量 ${BASELINE - errorCount} 个余量; 修复存量后请同步调低 BASELINE.`)
);
process.exit(0);
