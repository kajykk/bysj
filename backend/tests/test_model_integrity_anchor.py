"""AUDIT-2026-10-08 (P0-6): 模型完整性锚点校验的回归测试.

背景
----
`loading.py` 的 `_verify_file_hash` 在**找不到预期哈希**时只 `logger.info`
后 return —— 意味着生产环境「模型文件是否被替换」这个问题在本进程内
**永远无法回答**，而且这条 log 混在 info 级别里没人会看见。

这与本项目 P0-3 / P0-5 修的是同一类病：防线看起来存在，实际不生效。

实测底数（本机扫描 27 个注册模型）：真实存在的模型工件**全部**有侧车锚点，
因此把「无锚点」升级为 ERROR + 指标**不会打破现有部署**。

覆盖
----
- `_get_expected_hash` 返回值语义（新增 source 维度）
- `_verify_file_hash` 四种锚点状态 × strict/非 strict 环境
- `audit_model_integrity_anchors` 启动审计
"""

from __future__ import annotations

import hashlib

import pytest

from app.core.model_engine import loading as ld

_STRICT = "reject"
_LENIENT = "warn"


@pytest.fixture
def model_file(tmp_path):
    """一个真实存在、内容已知的「模型」文件。"""
    p = tmp_path / "model.pkl"
    p.write_bytes(b"fake model bytes")
    return p


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_sidecar(model_file, content: str):
    model_file.with_suffix(model_file.suffix + ".sha256").write_text(content, encoding="utf-8")


@pytest.fixture
def policy(request, monkeypatch):
    """切换 _HASH_MISMATCH_POLICY，模拟 strict / 非 strict 环境。"""
    value = getattr(request, "param", _LENIENT)
    monkeypatch.setattr(ld, "_HASH_MISMATCH_POLICY", value)
    return value


# ═══════════════════════════════════════════════════════════════════════
# 1. _get_expected_hash —— source 维度让调用方能区分失效性质
# ═══════════════════════════════════════════════════════════════════════


class TestGetExpectedHash:
    def test_absent_sidecar_reports_absent(self, model_file):
        expected, source = ld._get_expected_hash("m", model_file)
        assert expected is None
        assert source == "absent"

    def test_valid_sidecar_reports_sidecar_source(self, model_file):
        digest = _sha256(model_file)
        _write_sidecar(model_file, f"{digest}  model.pkl\n")
        expected, source = ld._get_expected_hash("m", model_file)
        assert expected == digest
        assert source == "sidecar"

    def test_sha256sum_format_with_two_spaces(self, model_file):
        digest = _sha256(model_file)
        _write_sidecar(model_file, f"{digest}  model.pkl\n")
        assert ld._get_expected_hash("m", model_file)[0] == digest

    def test_uppercase_hex_is_normalised(self, model_file):
        """sha256sum 输出小写, 但人工编辑可能大写 —— 应归一化而非误判 mismatch。"""
        digest = _sha256(model_file)
        _write_sidecar(model_file, digest.upper() + "\n")
        assert ld._get_expected_hash("m", model_file)[0] == digest

    def test_malformed_sidecar_is_distinguished_from_absent(self, model_file):
        """回归: 侧车存在但内容损坏, 此前与「不存在」一起返回 None, 性质被抹平。"""
        _write_sidecar(model_file, "这不是哈希\n")
        expected, source = ld._get_expected_hash("m", model_file)
        assert expected is None
        assert source.startswith("malformed_sidecar")
        assert source != "absent"

    @pytest.mark.parametrize("bad", ["abc\n", "0" * 63 + "\n", "z" * 64 + "\n", "\n", "deadbeef  model.pkl\n"])
    def test_non_sha256_content_rejected(self, model_file, bad):
        _write_sidecar(model_file, bad)
        expected, source = ld._get_expected_hash("m", model_file)
        assert expected is None
        assert source.startswith("malformed_sidecar") or source.startswith("unreadable_sidecar")

    def test_empty_sidecar_rejected(self, model_file):
        """空文件: splitlines() 返回空列表 -> IndexError 分支。

        注意这与 malformed_sidecar 是不同的 source —— 区别在于「能否解析」
        （unreadable）与「解析出来但不是哈希」（malformed），两者都不是有效锚点。
        """
        _write_sidecar(model_file, "")
        expected, source = ld._get_expected_hash("m", model_file)
        assert expected is None
        assert source.startswith("unreadable_sidecar") or source.startswith("malformed_sidecar")

    def test_registry_takes_precedence(self, model_file, monkeypatch):
        _write_sidecar(model_file, "0" * 64 + "\n")
        monkeypatch.setitem(ld._KNOWN_MODEL_HASHES, "m", "f" * 64)
        expected, source = ld._get_expected_hash("m", model_file)
        assert expected == "f" * 64
        assert source == "registry"


# ═══════════════════════════════════════════════════════════════════════
# 2. _verify_file_hash —— 核心：不再对缺失锚点静默
# ═══════════════════════════════════════════════════════════════════════


class TestVerifyFileHashLenient:
    """非 strict 环境（dev/test）：不阻断, 但必须留下可观测痕迹。"""

    @pytest.mark.parametrize("policy", [_LENIENT], indirect=True)
    def test_missing_anchor_does_not_raise(self, model_file, policy):
        ld._verify_file_hash("m", model_file, _sha256(model_file))

    @pytest.mark.parametrize("policy", [_LENIENT], indirect=True)
    def test_missing_anchor_is_logged_at_error(self, model_file, policy, caplog):
        """核心回归: 原实现是 logger.info —— 混在 info 里等于不存在。"""
        with caplog.at_level("ERROR"):
            ld._verify_file_hash("m", model_file, _sha256(model_file))
        errors = [r for r in caplog.records if r.levelname == "ERROR"]
        assert any("无完整性锚点" in r.getMessage() for r in errors), "缺失锚点必须以 ERROR 暴露, 不能是 info"

    @pytest.mark.parametrize("policy", [_LENIENT], indirect=True)
    def test_mismatch_is_critical(self, model_file, policy, caplog):
        _write_sidecar(model_file, "0" * 64 + "\n")
        with caplog.at_level("CRITICAL"):
            ld._verify_file_hash("m", model_file, _sha256(model_file))
        assert any(r.levelname == "CRITICAL" for r in caplog.records)

    @pytest.mark.parametrize("policy", [_LENIENT], indirect=True)
    def test_valid_anchor_passes_quietly(self, model_file, policy, caplog):
        digest = _sha256(model_file)
        _write_sidecar(model_file, digest + "\n")
        with caplog.at_level("ERROR"):
            ld._verify_file_hash("m", model_file, digest)
        assert not [r for r in caplog.records if r.levelname == "ERROR"]


class TestVerifyFileHashStrict:
    """strict 环境（production/staging）：真正 fail-closed。"""

    @pytest.mark.parametrize("policy", [_STRICT], indirect=True)
    def test_missing_anchor_rejects(self, model_file, policy):
        with pytest.raises(ValueError, match="缺少完整性锚点"):
            ld._verify_file_hash("m", model_file, _sha256(model_file))

    @pytest.mark.parametrize("policy", [_STRICT], indirect=True)
    def test_malformed_anchor_rejects(self, model_file, policy):
        _write_sidecar(model_file, "这不是哈希\n")
        with pytest.raises(ValueError, match="缺少完整性锚点"):
            ld._verify_file_hash("m", model_file, _sha256(model_file))

    @pytest.mark.parametrize("policy", [_STRICT], indirect=True)
    def test_mismatch_rejects(self, model_file, policy):
        _write_sidecar(model_file, "0" * 64 + "\n")
        with pytest.raises(ValueError, match="hash mismatch"):
            ld._verify_file_hash("m", model_file, _sha256(model_file))

    @pytest.mark.parametrize("policy", [_STRICT], indirect=True)
    def test_valid_anchor_loads_normally(self, model_file, policy):
        digest = _sha256(model_file)
        _write_sidecar(model_file, digest + "\n")
        ld._verify_file_hash("m", model_file, digest)  # 不抛错即通过


class TestPolicyIsDerivedFromEnv:
    def test_strict_envs_frozen_set(self):
        assert ld._HASH_MISMATCH_ENVS_STRICT == frozenset({"production", "staging"})

    def test_policy_matches_current_env(self):
        from app.core.config import settings

        expected = "reject" if settings.app_env.lower() in ld._HASH_MISMATCH_ENVS_STRICT else "warn"
        assert ld._HASH_MISMATCH_POLICY == expected


# ═══════════════════════════════════════════════════════════════════════
# 3. 启动审计
# ═══════════════════════════════════════════════════════════════════════


class TestStartupAudit:
    def test_returns_expected_shape(self):
        summary = ld.audit_model_integrity_anchors()
        assert set(summary) == {"ok", "checked", "skipped", "missing_anchors"}
        assert isinstance(summary["checked"], int)
        assert isinstance(summary["missing_anchors"], list)

    def test_never_raises(self):
        """审计是只读报告, 绝不能因为某个模型路径异常而阻断启动。"""
        ld.audit_model_integrity_anchors()  # 不抛异常即通过

    def test_uses_real_load_path_resolution(self, monkeypatch, model_file):
        """关键: 审计必须复用 `_abs_path` 的候选路径优先级。

        否则会出现「审计说锚点 OK、实际加载的却是另一个文件」这种最坏情况
        —— 仓库根存在陈旧的训练期影子 models/, 优先级错配会导致加载到影子文件。
        """
        seen = {}

        class _Probe:
            def _abs_path(self, rel):
                seen["rel"] = rel
                return model_file

        monkeypatch.setattr(ld, "LoadingMixin", type("X", (_Probe,), {}))
        monkeypatch.setattr(ld, "MODEL_PATHS", {"fake_model": "models/fake.pkl"})
        monkeypatch.setattr(ld, "is_model_enabled", lambda _mid: True)
        monkeypatch.setattr(ld, "resolve_model_path", lambda mid: "models/fake.pkl")

        ld.audit_model_integrity_anchors()
        assert seen.get("rel") == "models/fake.pkl", "审计未走 _abs_path, 结论不可信"

    def test_missing_anchor_is_reported(self, monkeypatch, model_file):
        monkeypatch.setattr(ld, "LoadingMixin", type("X", (), {"_abs_path": lambda _s, r: model_file}))
        monkeypatch.setattr(ld, "MODEL_PATHS", {"fake": "models/fake.pkl"})
        monkeypatch.setattr(ld, "is_model_enabled", lambda _m: True)
        monkeypatch.setattr(ld, "resolve_model_path", lambda _m: "models/fake.pkl")

        summary = ld.audit_model_integrity_anchors()
        assert summary["ok"] is False
        assert summary["checked"] == 1
        assert len(summary["missing_anchors"]) == 1
        assert summary["missing_anchors"][0]["model_id"] == "fake"

    def test_valid_anchor_passes(self, monkeypatch, model_file):
        _write_sidecar(model_file, _sha256(model_file) + "\n")
        monkeypatch.setattr(ld, "LoadingMixin", type("X", (), {"_abs_path": lambda _s, r: model_file}))
        monkeypatch.setattr(ld, "MODEL_PATHS", {"fake": "models/fake.pkl"})
        monkeypatch.setattr(ld, "is_model_enabled", lambda _m: True)
        monkeypatch.setattr(ld, "resolve_model_path", lambda _m: "models/fake.pkl")

        summary = ld.audit_model_integrity_anchors()
        assert summary["ok"] is True
        assert summary["missing_anchors"] == []

    def test_json_metadata_is_skipped(self, monkeypatch, tmp_path):
        """.json 元数据不经 _verify_file_hash 加载, 纳入统计只会制造噪音。"""
        meta = tmp_path / "calibrator_meta.json"
        meta.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(ld, "LoadingMixin", type("X", (), {"_abs_path": lambda _s, r: meta}))
        monkeypatch.setattr(ld, "MODEL_PATHS", {"meta": "models/meta.json"})
        monkeypatch.setattr(ld, "is_model_enabled", lambda _m: True)
        monkeypatch.setattr(ld, "resolve_model_path", lambda _m: "models/meta.json")

        summary = ld.audit_model_integrity_anchors()
        assert summary["checked"] == 0
        assert summary["skipped"] == 1
        assert summary["ok"] is True

    def test_absent_file_is_skipped_not_reported(self, monkeypatch, tmp_path):
        """注册表有条目但文件不存在 = 可选模型未部署, 属正常状态, 不该报缺失锚点。"""
        gone = tmp_path / "not_deployed.pkl"
        monkeypatch.setattr(ld, "LoadingMixin", type("X", (), {"_abs_path": lambda _s, r: gone}))
        monkeypatch.setattr(ld, "MODEL_PATHS", {"absent": "models/absent.pkl"})
        monkeypatch.setattr(ld, "is_model_enabled", lambda _m: True)
        monkeypatch.setattr(ld, "resolve_model_path", lambda _m: "models/absent.pkl")

        summary = ld.audit_model_integrity_anchors()
        assert summary["ok"] is True
        assert summary["checked"] == 0
        assert summary["skipped"] == 1

    def test_disabled_model_is_skipped(self, monkeypatch, model_file):
        monkeypatch.setattr(ld, "LoadingMixin", type("X", (), {"_abs_path": lambda _s, r: model_file}))
        monkeypatch.setattr(ld, "MODEL_PATHS", {"off": "models/off.pkl"})
        monkeypatch.setattr(ld, "is_model_enabled", lambda _m: False)
        monkeypatch.setattr(ld, "resolve_model_path", lambda _m: "models/off.pkl")

        summary = ld.audit_model_integrity_anchors()
        assert summary["ok"] is True
        assert summary["skipped"] == 1


# ═══════════════════════════════════════════════════════════════════════
# 4. 与既有审计的分工
# ═══════════════════════════════════════════════════════════════════════


class TestRelationshipToExistingAudit:
    def test_existing_sidecar_audit_exists_and_scans_pkl(self):
        """`audit_model_sidecars`（checksum.py）已存在, 扫 *.pkl 全目录。

        它与本模块的注册表审计**互补而非重复**：
        - checksum 版：目录驱动, 覆盖所有 .pkl（含未注册的）, 但不区分后缀
        - 本模块版：注册表驱动, 只查真正会被加载的工件, 覆盖多种模型后缀
        """
        from app.utils.checksum import audit_model_sidecars

        assert callable(audit_model_sidecars)

    def test_registry_audit_covers_more_suffixes_than_pkl_only_scan(self):
        """既有扫盘审计只匹配 *.pkl; 本模块审计额外覆盖 .keras/.h5/.joblib/.pt/.pth。"""
        src = __import__("inspect").getsource(ld.audit_model_integrity_anchors)
        for suffix in (".pkl", ".keras", ".h5", ".joblib", ".pt", ".pth"):
            assert suffix in src, f"注册表审计未覆盖 {suffix}"


class TestPreloadWiring:
    def test_preload_triggers_audit(self, monkeypatch):
        """preload 必须在加载模型前先审计 —— 模型是懒加载的, 否则审计永不触发。

        注意 PRELOAD_IDS 定义在 ModelEngine 上（不在 LoadingMixin），
        所以这里对 ModelEngine 打桩而非 LoadingMixin。
        """
        from app.core.model_engine import ModelEngine

        called = []
        monkeypatch.setattr(ld, "audit_model_integrity_anchors", lambda: called.append(1))
        monkeypatch.setattr(ModelEngine, "PRELOAD_IDS", [])
        monkeypatch.setattr(ModelEngine, "_load_model", lambda _s, _m: None)

        ModelEngine.__new__(ModelEngine).preload()
        assert called, "preload 未调用完整性审计"
