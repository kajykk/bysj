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
2. 命中模式：`(password|passwd|pwd|token|secret|api_key|access_key)`
   后跟赋值/映射分隔符，再跟**引号包裹的字面量**（长度 >= 6 以避开空串与
   单字符）；大小写不敏感；
3. 环境变量读取（`os.environ[...]`、`getenv`、`$env:X`）右侧不是字面量，
   天然不命中；
4. 确需保留的走**显式白名单**：`WHITELIST` 每条 = (文件, 字面量, 理由)，
   断言白名单条目**必须在文件中真实存在**（防止白名单腐烂成死条目）；
5. 附带钉住 `.admin_token.txt` 已被 .gitignore 排除——令牌产物不得落版本库。

变异见证：`frontend/tests/tools/mutate_round23b.md` 的 B4 条
（把口令字面量塞回 scripts/login_admin.py ⇒ 本闸门必须红）。
"""
from __future__ import annotations

import re
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

# 显式白名单：(相对路径, 字面量, 理由)
# 新增条目必须写明理由——白名单不是"不想管"的垃圾桶。
WHITELIST: list[tuple[str, str, str]] = [
    (
        "scripts/check_metrics_v2.py",
        "dev-only-metrics-token",
        "dev-only 占位符，不是真实凭据；生产由 settings.metrics_access_token "
        "或 BYSJ_METRICS_TOKEN 注入（L13 修复后环境变量优先）",
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

        注意这些脚本**并非全部入库**：`.gitignore` 刻意排除了
        `/scripts/login_admin.*`、`/scripts/*_v2.py` 等（前人为避免口令入库），
        因此 CI 上扫到的只是已入库的那部分。本断言保证"扫到至少 50 个文件"，
        一旦目录结构变动导致扫描退化为 0 文件，这里会红。
        """
        files = _iter_script_files()
        assert len(files) >= 50, (
            f"scripts/ 下被扫文件仅 {len(files)} 个 —— 扫描可能已退化（目录变动/全部被忽略）"
        )

    def test_whitelist_entries_are_real(self):
        """白名单不得腐烂：每条声明的字面量必须真在对应文件里出现过。

        若文件已被 .gitignore 排除（CI checkout 中不存在），跳过该条并
        在报告中记账——白名单不为不存在的文件背书。
        """
        for rel, literal, reason in WHITELIST:
            path = REPO / rel
            if not path.is_file():
                pytest.skip(f"白名单条目文件不在工作区（可能被 .gitignore 排除）: {rel}")
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


@pytest.mark.parametrize("filename", ["scripts/login_admin.py", "scripts/login_admin.ps1"])
class TestLoginAdminScriptContract:
    """L13 修复的两个脚本：必须读环境变量、缺变量要明确报错退出。

    ⚠️ 记账：这两个脚本被 `.gitignore:182`（`/scripts/login_admin.*`）**刻意排除**，
    CI checkout 中不存在 ⇒ 本组用例在 CI 上会 skip。它们只在本机工作区生效，
    因此这两个脚本的合规性**不由 CI 背书**（本机已实测合规，见
    frontend/tests/tools/mutate_round23b.md 的 B4）。
    """

    def test_requires_env_vars_and_exits_nonzero(self, filename: str):
        path = REPO / filename
        if not path.is_file():
            pytest.skip(f"{filename} 不在工作区（被 .gitignore 排除），CI 不校验")
        text = path.read_text(encoding="utf-8")
        assert "BYSJ_ADMIN_USERNAME" in text, f"{filename} 未读 BYSJ_ADMIN_USERNAME"
        assert "BYSJ_ADMIN_PASSWORD" in text, f"{filename} 未读 BYSJ_ADMIN_PASSWORD"
        assert "DwsAdmin@Canary2026!" not in text, f"{filename} 仍含原硬编码口令"

    def test_no_absolute_repo_path(self, filename: str):
        path = REPO / filename
        if not path.is_file():
            pytest.skip(f"{filename} 不在工作区（被 .gitignore 排除），CI 不校验")
        text = path.read_text(encoding="utf-8")
        assert "e:\\code\\bysj" not in text.lower(), (
            f"{filename} 仍含绝对路径 e:\\code\\bysj —— 应改为相对仓库根解析"
        )
        assert "e:/code/bysj" not in text.lower()
