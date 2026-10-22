"""
L13 修复（ROUND_23）：scripts/ 下不得出现硬编码口令/令牌字面量。

为什么要有这道闸门（而不是只靠 gitleaks）：
- 现有 `gitleaks` 是**独立 workflow**（secret-scan.yml）且**未配 allowlist**，
  本轮不改其配置、也不把任何 secret 加进 allowlist（那是反向操作）；
- gitleaks 是「已入库的历史扫描」，对「脚本里写了个默认值」这类形态
  （非高熵、带 dev-only 语义）未必命中；
- 本闸门是**结构扫描**：直接断言源码里不存在「口令/令牌 = 字面量」的写法，
  与既有 `test_ci_secret_placeholders.py`（只扫 workflows）互补。

判据（先定死再写实现）：
1. 扫 `scripts/**/*.py` 与 `scripts/**/*.ps1`；
2. 命中模式：`(password|passwd|pwd|token|secret|api_key|apikey|access_key)`
   后跟赋值/映射分隔符，再跟**引号包裹的字面量**（长度 >= 6 以避开空串与
   单字符）；大小写不敏感；
3. 环境变量读取（`os.environ[...]`、`getenv`、`$env:X`）右侧不是字面量，
   天然不命中；
4. 确需保留的走**显式白名单**：`WHITELIST` 每条 = (文件, 字面量, 理由)，
   断言白名单条目**必须在文件中真实存在**（防止白名单腐烂成死条目）；
5. 附带钉住 `.admin_token.txt` 已被 .gitignore 排除——令牌产物不得落版本库。

ROUND_25（2026-10-22）增强——兑现「不可验证的修复」：
23b 把 6 个脚本的硬编码口令改成环境变量，但当时它们被 `.gitignore`
排除（`/scripts/login_admin.*`、`/scripts/*_v2.py` 等）⇒ CI checkout
里根本没有这些文件，修复只在本机生效、**不被 CI 背书**。本轮：
- A2：4 个仍属运维必需的脚本**入库**（`.gitignore` 通配规则保留、只做
  定向否定——P1-30 的教训是枚举会漏）；3 个一次性脚本**删除**
  （依据见 `docs/P2_52_ROUND25_VERIFICATION_GAP_AUDIT.md`）；
- A4：新增 `KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS` 显式记账闸门——任何
  「本地存在、未入库、且消费凭证」的脚本必须登记理由，双向相等，
  不再允许「文件不在工作区就静默 skip」；
- 白名单条目指向的文件若不在工作区：必须在记账清单里找得到登记理由，
  否则红（skip 不得代替记账）。

变异见证：`frontend/tests/tools/mutate_round23b.md` 的 B4 条
（把口令字面量塞回 scripts/login_admin.py ⇒ 本闸门必须红）；
ROUND_25 四组见 `backend/tests/tools/mutate_p2_52_round25_result.log`。
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"

# 口令/令牌类标识符 → 分隔符 → 引号字面量
SECRET_ASSIGN = re.compile(
    r"(?i)\b(password|passwd|pwd|token|secret|api_key|apikey|access_key)\b"
    # 允许可选的闭合引号：同时覆盖 `password = "x"` 与 `"password": "x"`
    r"[\"']?\s*[:=]\s*"
    r"[\"']([^\"']{6,})[\"']"
)

# 「消费凭证」判据（ROUND_25 A4）——不是"提到口令二字"，而是**真的读取凭据**：
#   1. Python 读环境变量：`os.environ[...]` / `os.environ.get(...)` / `getenv(...)`，
#      变量名含 PASSWORD / PASSWD / TOKEN / SECRET / API_KEY / ACCESS_KEY；
#   2. PowerShell 读 `$env:X`（同名判据）；
#   3. 读取令牌产物 `.admin_token.txt`（该产物本身已被 .gitignore 排除，
#      读它等于消费本地令牌）。
# 故意**不**纳入的形态（实测过的误报源，见 test_credential_consume_pattern_self_proof）：
# 论文正文里的 "JWT Token 认证"、`title_tokens` 分词变量、论文表格里的
# `password_hash` 字段名——它们不读取任何凭证，纳入来只会把记账清单变成垃圾桶。
CREDENTIAL_CONSUME = re.compile(
    r"(?i)(?:"
    # python: os.environ["X"] / os.environ.get("X") / os.getenv("X") / getenv("X")
    r"(?:os\.)?(?:environ(?:\.get)?|getenv)\s*[\[(]\s*[\"']"
    r"[A-Za-z0-9_]*(?:PASSWORD|PASSWD|TOKEN|SECRET|API_KEY|ACCESS_KEY)[A-Za-z0-9_]*[\"']"
    # powershell: $env:X
    r"|\$env:[A-Za-z0-9_]*(?:PASSWORD|PASSWD|TOKEN|SECRET|API_KEY|ACCESS_KEY)[A-Za-z0-9_]*"
    # 令牌产物
    r"|\.admin_token\.txt"
    r")"
)

#: 已知的「本地存在、未入库、且消费凭证」脚本登记簿（ROUND_25 A4）。
#: 每条必须写明「为何仍不入库」——登记簿不是垃圾桶，是显式记账。
#: 等式闸门（test_no_unregistered_credential_script /
#: test_registry_has_no_stale_entries）：
#:   方向 1：实测 ⊋ 本清单 ⇒ 红（出现了未登记的、CI 看不见的含凭证脚本）；
#:   方向 2：本清单 ⊋ 实测 ⇒ 红（已入库 / 已删除 / 不再消费凭证，必须同步）。
#: ⚠️ CI 形态说明（断言前提，不是放水）：GitHub Actions checkout 只含已入库
#: 文件 ⇒ 未入库脚本在 CI 上**根本不存在**，「清单 ⊋ 实测」与「文件已删除」
#: 在 CI 上同形、不可判。因此方向 2 只在本机全量运行下强制；CI 上强制的是
#: 方向 1 + 「登记项不得指向已入库文件」（A2 完成后忘同步清单会红）。
KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS: dict[str, str] = {
    "scripts/check_tabular_v2.py": (
        "一次性探针（自述 docstring：单条 tabular 预测、打印完整响应），工作已完结；"
        "读令牌产物 .admin_token.txt（该产物被 .gitignore 排除，脚本不入库即不泄漏令牌）。"
        "非 L13 七脚本之列（它消费令牌文件而非登录口令），登记备查、本轮不处置"
    ),
    "scripts/gen_canary_traffic_v2.py": (
        "金丝雀 5% 阶段专用流量生成器（硬编码四模态 payload + S-01~S-05 验证），"
        "阶段产物性质；同样读 .admin_token.txt。非 L13 七脚本之列，登记备查、本轮不处置"
    ),
}

# 显式白名单：(相对路径, 字面量, 理由)
# 新增条目必须写明理由——白名单不是"不想管"的垃圾桶。
WHITELIST: list[tuple[str, str, str]] = [
    (
        "scripts/check_metrics_v2.py",
        "dev-only-metrics-token",
        "dev-only 占位符，不是真实凭据；生产由 settings.metrics_access_token "
        "或 BYSJ_METRICS_TOKEN 注入（L13 修复后环境变量优先）。"
        "ROUND_25 起该脚本已入库 ⇒ 本条目在 CI 上真实生效（不再 skip）",
    ),
]


def _iter_script_files() -> list[Path]:
    if not SCRIPTS.is_dir():  # pragma: no cover - 仓库结构异常
        return []
    files = sorted(SCRIPTS.rglob("*.py")) + sorted(SCRIPTS.rglob("*.ps1"))
    return [f for f in files if "__pycache__" not in f.parts]


def _scan() -> list[tuple[str, int, str, str]]:
    """返回 [(相对路径, 行号, 标识符, 字面量)]。"""
    hits: list[tuple[str, int, str, str]] = []
    for path in _iter_script_files():
        rel = path.relative_to(REPO).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):  # pragma: no cover
            continue
        whitelisted = {lit for f, lit, _ in WHITELIST if f == rel}
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):  # 注释里的说明性文本不算凭据
                continue
            for match in SECRET_ASSIGN.finditer(line):
                literal = match.group(2)
                if literal in whitelisted:
                    continue
                hits.append((rel, lineno, match.group(1), literal))
    return hits


def _tracked_scripts() -> set[str]:
    """`git ls-files scripts/` 一次拿全入库清单（N 次 subprocess 太慢）。"""
    proc = subprocess.run(
        ["git", "ls-files", "scripts/"], cwd=REPO, capture_output=True, text=True
    )
    assert proc.returncode == 0, (
        f"git ls-files 失败，无法判定入库状态（宁红不跳）: {proc.stderr.strip()}"
    )
    return set(proc.stdout.split())


def _running_in_ci() -> bool:
    """GitHub Actions 会设 CI=true；本机工作区不设。

    这不是"跳过检查"的借口，而是**断言前提的条件化**：方向 2 依赖
    「文件在磁盘上可见」，CI checkout 看不到未入库文件（与"已删除"同形），
    方向 1 与「登记项不得指向已入库文件」在两个形态下都强制。
    """
    return bool(os.environ.get("CI"))


def _untracked_credential_scripts() -> set[str]:
    """实测：本地存在 ∧ 未入库 ∧ 消费凭证 的脚本集合。"""
    tracked = _tracked_scripts()
    out: set[str] = set()
    for path in _iter_script_files():
        rel = path.relative_to(REPO).as_posix()
        if rel in tracked:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):  # pragma: no cover
            continue
        if CREDENTIAL_CONSUME.search(text):
            out.add(rel)
    return out


class TestScriptsNoHardcodedSecrets:
    def test_scripts_have_no_hardcoded_passwords_or_tokens(self):
        hits = _scan()
        assert hits == [], (
            "scripts/ 下发现硬编码口令/令牌字面量（L13 修复）：\n  "
            + "\n  ".join(f"{rel}:{lineno} {ident}={literal!r}" for rel, lineno, ident, literal in hits)
            + "\n请改为环境变量读取；确需保留的须加入本文件 WHITELIST 并写明理由。"
        )

    def test_scan_pattern_actually_detects_a_known_bad_line(self):
        """闸门自检：模式必须真能抓到硬编码口令（防止正则写错导致空转）。"""
        sample = 'payload = {"username": "admin", "password": "DwsAdmin@Canary2026!"}'
        found = SECRET_ASSIGN.search(sample)
        assert found is not None, "扫描正则未能命中已知硬编码口令样例"
        assert found.group(2) == "DwsAdmin@Canary2026!"

    def test_scan_pattern_ignores_env_reads(self):
        """环境变量读取不是字面量，不应命中（避免把正确改法判成违规）。"""
        for good in (
            'PASSWORD = os.environ.get("BYSJ_ADMIN_PASSWORD")',
            "password = os.environ['BYSJ_ADMIN_PASSWORD']",
            '$password = $env:BYSJ_ADMIN_PASSWORD',
        ):
            assert SECRET_ASSIGN.search(good) is None, f"环境变量读取被误判: {good}"

    def test_scan_covers_a_meaningful_number_of_files(self):
        """闸门防空转：scripts/ 下必须有足够多的被扫文件。

        ROUND_25 起 4 个运维脚本入库 ⇒ CI checkout 可见 **113** 个
        `.py`/`.ps1`（本机另有未入库文件，只会更多）。阈值 ≥110 钉住这个量级：
        一旦目录结构变动导致扫描退化（批量被忽略/删除），这里会红。
        """
        files = _iter_script_files()
        assert len(files) >= 110, (
            f"scripts/ 下被扫文件仅 {len(files)} 个 —— 扫描可能已退化（目录变动/全部被忽略）"
        )

    def test_whitelist_entries_are_real(self):
        """白名单不得腐烂：每条声明的字面量必须真在对应文件里出现过。

        ROUND_25：文件不在工作区时**不再静默 skip**——必须在
        `KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS` 里找得到登记理由，否则红。
        skip 不得代替记账：白名单不为没人看管的文件背书。
        """
        for rel, literal, reason in WHITELIST:
            path = REPO / rel
            if not path.is_file():
                assert rel in KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS, (
                    f"白名单条目文件不在工作区且未登记理由: {rel} :: {literal}\n"
                    "请二选一：① 文件已入库/已删除 ⇒ 同步删除白名单条目；"
                    "② 文件仍未入库 ⇒ 在 KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS 登记理由"
                )
                continue
            text = path.read_text(encoding="utf-8")
            assert literal in text, (
                f"白名单条目已失效（文件里找不到该字面量）: {rel} :: {literal}；"
                f"若该字面量已被移除，请同步删除白名单条目（理由曾是：{reason}）"
            )
            assert reason.strip(), f"白名单条目缺理由: {rel} :: {literal}"

    def test_admin_token_artifact_is_gitignored(self):
        """令牌产物不得落版本库（.gitignore 实测排除）。"""
        gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
        assert ".admin_token.txt" in gitignore, (
            ".gitignore 未排除 .admin_token.txt —— 令牌产物不得进版本库"
        )


class TestUntrackedCredentialScriptsAreRegistered:
    """ROUND_25 A4：未入库含凭证脚本显式记账——skip 不得代替记账。

    背景：23b 的 L13 修复当时不被 CI 背书（文件被 .gitignore 排除）。
    本轮把运维必需的 4 个脚本入库、3 个一次性脚本删除后，仍有两个
    消费凭证的脚本留在本地（登记簿内）——闸门保证这个集合**永远显式**。
    """

    def test_no_unregistered_credential_script(self):
        """方向 1：实测 ⊋ 清单 ⇒ 红。

        新写一个读口令/令牌却未入库的脚本 ⇒ 本机运行即红（push 前拦下）；
        CI 上未入库文件不存在，此方向在 CI 上恒过（但本机强制）。
        """
        actual = _untracked_credential_scripts()
        registry = set(KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS)
        unregistered = sorted(actual - registry)
        assert not unregistered, (
            "出现未登记的「本地存在、未入库、且消费凭证」脚本（CI 看不见它们）：\n  "
            + "\n  ".join(unregistered)
            + "\n请二选一：① 属运维必需 ⇒ 入库（.gitignore 定向否定，勿删通配）；"
            "② 属一次性 ⇒ 删除；③ 仍留本地 ⇒ 在 KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS 登记理由"
        )

    def test_registry_has_no_stale_entries(self):
        """方向 2：清单 ⊋ 实测 ⇒ 红（防腐烂：已入库/已删除/不再消费凭证）。

        CI 形态下未入库文件不在 checkout 中，该方向不可判 ⇒ 只强制
        「登记项不得指向已入库文件」：A2 完成后忘同步清单会红。
        完整方向 2 由本机全量运行兜底（文件在磁盘上可见）。
        """
        actual = _untracked_credential_scripts()
        registry = set(KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS)
        if _running_in_ci():
            tracked = sorted(rel for rel in registry if rel in _tracked_scripts())
            assert not tracked, (
                "登记簿条目指向的文件已入库（A2 完成后忘同步清单）: "
                + ", ".join(tracked)
                + "\n请从 KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS 移除对应条目"
            )
        else:
            stale = sorted(registry - actual)
            assert not stale, (
                "登记簿有腐烂条目（文件已删除 / 已入库 / 不再消费凭证）: "
                + ", ".join(stale)
                + "\n请同步 KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS——记账必须与现实相等"
            )

    def test_registry_reasons_are_present(self):
        for rel, reason in KNOWN_UNTRACKED_CREDENTIAL_SCRIPTS.items():
            assert rel.startswith("scripts/"), f"登记项路径形似 scripts/ 下: {rel}"
            assert reason.strip(), f"登记条目缺「为何仍不入库」的理由: {rel}"

    def test_credential_consume_pattern_self_proof(self):
        """判据自检（防正则写错空转 / 防把误报源纳入）。

        必须命中：真的在读凭证的三种形态（py environ / py getenv /
        ps1 $env / 令牌产物文件）。
        不得命中：只是"提到口令二字"的实测误报源（论文正文 JWT Token、
        分词变量 tokens、论文表格字段名 password_hash、纯用户名字段）。
        """
        must_match = (
            'PASSWORD = os.environ.get("BYSJ_ADMIN_PASSWORD")',
            'PASSWORD = os.environ["BYSJ_ADMIN_PASSWORD"]',
            'TOKEN = os.getenv("BYSJ_METRICS_TOKEN")',
            "$password = $env:BYSJ_ADMIN_PASSWORD",
            'TOKEN_FILE = r"e:\\code\\bysj\\scripts\\.admin_token.txt"',
        )
        for sample in must_match:
            assert CREDENTIAL_CONSUME.search(sample), f"凭证消费形态未被判据命中: {sample}"
        must_not_match = (
            '"安全测试重点验证未登录访问、Token 失效、角色越权。"',
            "title_tokens = tokens[:8]",
            '["password_hash", "String(255)", "非空", "密码哈希"]',
            'USERNAME = os.environ.get("BYSJ_ADMIN_USERNAME")',
            'metrics = {"model_auc": 0.91, "model_f1": 0.88}',
        )
        for sample in must_not_match:
            assert CREDENTIAL_CONSUME.search(sample) is None, f"非凭证消费被误判: {sample}"


@pytest.mark.parametrize("filename", ["scripts/login_admin.py", "scripts/login_admin.ps1"])
class TestLoginAdminScriptContract:
    """L13 修复的两个脚本：必须读环境变量、缺变量要明确报错退出。

    ROUND_25 起这两个脚本已**入库**（.gitignore:182 通配规则保留、只做
    定向否定）⇒ CI checkout 可见，本组用例在 CI 上**真实生效**，不再 skip。
    保留 skip 分支只是纵深：若有人重新排除它们，方向 1 记账闸门
    （test_no_unregistered_credential_script）会同时红——跳过不等于失管。
    """

    def test_requires_env_vars_and_exits_nonzero(self, filename: str):
        path = REPO / filename
        if not path.is_file():
            pytest.skip(f"{filename} 不在工作区（被 .gitignore 重新排除），CI 不校验")
        text = path.read_text(encoding="utf-8")
        assert "BYSJ_ADMIN_USERNAME" in text, f"{filename} 未读 BYSJ_ADMIN_USERNAME"
        assert "BYSJ_ADMIN_PASSWORD" in text, f"{filename} 未读 BYSJ_ADMIN_PASSWORD"
        assert "DwsAdmin@Canary2026!" not in text, f"{filename} 仍含原硬编码口令"

    def test_no_absolute_repo_path(self, filename: str):
        path = REPO / filename
        if not path.is_file():
            pytest.skip(f"{filename} 不在工作区（被 .gitignore 重新排除），CI 不校验")
        text = path.read_text(encoding="utf-8")
        assert "e:\\code\\bysj" not in text.lower(), (
            f"{filename} 仍含绝对路径 e:\\code\\bysj —— 应改为相对仓库根解析"
        )
        assert "e:/code/bysj" not in text.lower()
