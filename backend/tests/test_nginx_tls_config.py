"""SEC-P1-006 回归测试：nginx TLS 配置验证

验证以下文件的 TLS 配置正确性：
- frontend/nginx.conf: 443 ssl server + 80→443 跳转 + TLS 优化 + HSTS
- frontend/Dockerfile: EXPOSE 80 443 + 移除 USER nginx + HTTPS healthcheck
- docker-compose.yml: 443:443 端口 + 证书挂载 + HTTPS healthcheck
- scripts/generate-self-signed-cert.sh: 证书生成脚本存在且内容正确
- .gitignore: 证书目录被排除 (不提交到 git)

测试策略: 静态文件解析 (不依赖 nginx 运行时), 验证关键配置项存在
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# 项目根目录 (backend/tests/ → ../../)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = PROJECT_ROOT / "frontend" / "nginx.conf"
DOCKERFILE = PROJECT_ROOT / "frontend" / "Dockerfile"
DOCKER_COMPOSE = PROJECT_ROOT / "docker-compose.yml"
CERT_SCRIPT = PROJECT_ROOT / "scripts" / "generate-self-signed-cert.sh"
GITIGNORE = PROJECT_ROOT / ".gitignore"


# ===== 辅助函数 =====


def _read(path: Path) -> str:
    """读取文件内容, 不存在则跳过。"""
    if not path.exists():
        pytest.skip(f"文件不存在: {path}")
    return path.read_text(encoding="utf-8")


def _extract_server_blocks(nginx_conf: str) -> list[str]:
    """从 nginx.conf 中提取所有 server { ... } 块 (支持嵌套花括号)。"""
    blocks: list[str] = []
    i = 0
    while i < len(nginx_conf):
        # 找到 server { 开始位置
        match = re.search(r"\bserver\s*\{", nginx_conf[i:])
        if not match:
            break
        start = i + match.end() - 1  # 指向 '{'
        # 匹配花括号 (支持嵌套)
        depth = 0
        j = start
        while j < len(nginx_conf):
            if nginx_conf[j] == "{":
                depth += 1
            elif nginx_conf[j] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(nginx_conf[start + 1 : j])
                    break
            j += 1
        i = j + 1
    return blocks


# ===== 测试类 =====


class TestNginxConfigStructure:
    """验证 nginx.conf 整体结构: 两个 server 块 (80 跳转 + 443 ssl)。"""

    def test_nginx_conf_exists(self):
        """nginx.conf 文件存在。"""
        assert NGINX_CONF.exists(), f"nginx.conf 不存在: {NGINX_CONF}"

    def test_has_two_server_blocks(self):
        """应有且仅有 2 个 server 块: 80 跳转 + 443 ssl。"""
        content = _read(NGINX_CONF)
        blocks = _extract_server_blocks(content)
        assert len(blocks) == 2, f"期望 2 个 server 块, 实际 {len(blocks)} 个"

    def test_80_server_block_is_redirect(self):
        """80 端口 server 块仅做 301 跳转到 HTTPS。"""
        content = _read(NGINX_CONF)
        blocks = _extract_server_blocks(content)
        redirect_block = None
        for block in blocks:
            if re.search(r"listen\s+80\s*;", block):
                redirect_block = block
                break
        assert redirect_block is not None, "未找到 listen 80 的 server 块"
        assert (
            "return 301 https://" in redirect_block
        ), "80 端口 server 块应包含 return 301 https:// 跳转"
        # 跳转块不应包含 root/location/proxy_pass (纯跳转)
        assert "proxy_pass" not in redirect_block, "80 跳转块不应包含 proxy_pass"
        assert "try_files" not in redirect_block, "80 跳转块不应包含 try_files"

    def test_443_server_block_has_ssl(self):
        """443 端口 server 块应启用 ssl。"""
        content = _read(NGINX_CONF)
        blocks = _extract_server_blocks(content)
        ssl_block = None
        for block in blocks:
            if re.search(r"listen\s+443\s+ssl\s*;", block):
                ssl_block = block
                break
        assert ssl_block is not None, "未找到 listen 443 ssl 的 server 块"
        # 验证包含核心配置
        assert "root /usr/share/nginx/html" in ssl_block, "443 块应包含 root 指令"
        assert "location /" in ssl_block, "443 块应包含 location / (SPA 路由)"
        assert (
            "proxy_pass http://backend:8000" in ssl_block
        ), "443 块应包含 API 反向代理"


class TestNginxTlsConfig:
    """验证 TLS 协议、密码套件、会话缓存配置。"""

    def test_ssl_certificate_paths(self):
        """证书路径指向 /etc/nginx/certs/。"""
        content = _read(NGINX_CONF)
        assert (
            "ssl_certificate /etc/nginx/certs/server.crt;" in content
        ), "ssl_certificate 应指向 /etc/nginx/certs/server.crt"
        assert (
            "ssl_certificate_key /etc/nginx/certs/server.key;" in content
        ), "ssl_certificate_key 应指向 /etc/nginx/certs/server.key"

    def test_ssl_protocols_tls_1_2_and_1_3(self):
        """仅启用 TLS 1.2 / 1.3, 禁用旧协议。"""
        content = _read(NGINX_CONF)
        assert (
            "ssl_protocols TLSv1.2 TLSv1.3;" in content
        ), "ssl_protocols 应为 TLSv1.2 TLSv1.3"
        # 提取 ssl_protocols 指令行 (非注释), 验证旧协议不在指令中
        ssl_protocols_match = re.search(
            r"^\s*ssl_protocols\s+([^;]+);", content, re.MULTILINE
        )
        assert ssl_protocols_match, "应配置 ssl_protocols 指令"
        protocols_value = ssl_protocols_match.group(1)
        assert "SSLv2" not in protocols_value, "ssl_protocols 不应包含 SSLv2"
        assert "SSLv3" not in protocols_value, "ssl_protocols 不应包含 SSLv3"
        assert "TLSv1.0" not in protocols_value, "ssl_protocols 不应包含 TLSv1.0"
        assert "TLSv1.1" not in protocols_value, "ssl_protocols 不应包含 TLSv1.1"

    def test_ssl_ciphers_ecdhe(self):
        """密码套件应优先 ECDHE (前向保密)。"""
        content = _read(NGINX_CONF)
        assert "ssl_ciphers" in content, "应配置 ssl_ciphers"
        assert "ECDHE" in content, "密码套件应包含 ECDHE (前向保密)"
        assert "GCM" in content, "密码套件应包含 GCM (AEAD 加密)"
        assert "CHACHA20" in content, "密码套件应包含 CHACHA20"

    def test_ssl_prefer_server_ciphers_off(self):
        """关闭服务端密码偏好 (TLS 1.3 最佳实践)。"""
        content = _read(NGINX_CONF)
        assert (
            "ssl_prefer_server_ciphers off;" in content
        ), "ssl_prefer_server_ciphers 应为 off"

    def test_ssl_session_cache(self):
        """配置会话缓存以减少握手开销。"""
        content = _read(NGINX_CONF)
        assert (
            "ssl_session_cache shared:SSL:10m;" in content
        ), "ssl_session_cache 应为 shared:SSL:10m"
        assert "ssl_session_timeout" in content, "应配置 ssl_session_timeout"

    def test_ssl_session_tickets_disabled(self):
        """禁用会话票据 (避免前向保密被削弱)。"""
        content = _read(NGINX_CONF)
        assert "ssl_session_tickets off;" in content, "ssl_session_tickets 应为 off"

    def test_http2_enabled(self):
        """443 端口应启用 HTTP/2。"""
        content = _read(NGINX_CONF)
        assert "http2 on;" in content, "应启用 http2"


class TestNginxSecurityHeaders:
    """验证安全头 (HSTS 在 HTTPS 下生效)。"""

    def test_hsts_header_present(self):
        """HSTS 头存在 (max-age=31536000 = 1 年)。"""
        content = _read(NGINX_CONF)
        assert "Strict-Transport-Security" in content, "应配置 HSTS 头"
        assert "max-age=31536000" in content, "HSTS max-age 应为 31536000 (1 年)"
        assert "includeSubDomains" in content, "HSTS 应包含 includeSubDomains"

    def test_hsts_in_443_block_not_80(self):
        """HSTS 应在 443 server 块中, 不在 80 跳转块中 (HTTP 下 HSTS 无效)。"""
        content = _read(NGINX_CONF)
        blocks = _extract_server_blocks(content)
        for block in blocks:
            if re.search(r"listen\s+80\s*;", block):
                assert (
                    "Strict-Transport-Security" not in block
                ), "HSTS 不应在 80 跳转块中 (HTTP 下浏览器不接受 HSTS)"
            if re.search(r"listen\s+443\s+ssl\s*;", block):
                assert (
                    "Strict-Transport-Security" in block
                ), "HSTS 应在 443 ssl 块中 (HTTPS 下浏览器接受 HSTS)"

    def test_other_security_headers_preserved(self):
        """其他安全头保留 (X-Frame-Options / X-Content-Type-Options / CSP 等)。"""
        content = _read(NGINX_CONF)
        assert "X-Frame-Options" in content, "应保留 X-Frame-Options"
        assert "X-Content-Type-Options" in content, "应保留 X-Content-Type-Options"
        assert "Content-Security-Policy" in content, "应保留 CSP"
        assert "Referrer-Policy" in content, "应保留 Referrer-Policy"
        assert "Permissions-Policy" in content, "应保留 Permissions-Policy"


class TestDockerfileConfig:
    """验证 Dockerfile: EXPOSE 80 443 + 移除 USER nginx + HTTPS healthcheck。"""

    def test_dockerfile_exists(self):
        """Dockerfile 文件存在。"""
        assert DOCKERFILE.exists(), f"Dockerfile 不存在: {DOCKERFILE}"

    def test_expose_80_and_443(self):
        """EXPOSE 应包含 80 和 443。"""
        content = _read(DOCKERFILE)
        # 匹配 EXPOSE 80 443 或 EXPOSE 80 和 443 分开
        expose_match = re.search(r"^EXPOSE\s+(.+)$", content, re.MULTILINE)
        assert expose_match, "应包含 EXPOSE 指令"
        expose_values = expose_match.group(1)
        assert "80" in expose_values, "EXPOSE 应包含 80"
        assert "443" in expose_values, "EXPOSE 应包含 443"

    def test_no_user_nginx(self):
        """不应有 USER nginx (443 < 1024 非 root 无法绑定)。"""
        content = _read(DOCKERFILE)
        # 查找 USER 指令 (注释中的不算)
        user_matches = re.findall(r"^USER\s+\S+", content, re.MULTILINE)
        assert (
            len(user_matches) == 0
        ), f"不应包含 USER 指令 (443 需 root 绑定), 实际: {user_matches}"

    def test_healthcheck_uses_https(self):
        """HEALTHCHECK 应使用 https:// (80 端口已跳转)。"""
        content = _read(DOCKERFILE)
        healthcheck_match = re.search(
            r"HEALTHCHECK.*?CMD\s+(.+?)(?:\\?\s*$)",
            content,
            re.MULTILINE | re.DOTALL,
        )
        assert healthcheck_match, "应包含 HEALTHCHECK 指令"
        cmd = healthcheck_match.group(1)
        assert "https://" in cmd, "HEALTHCHECK 应使用 https://"
        assert (
            "--no-check-certificate" in cmd
        ), "HEALTHCHECK 应包含 --no-check-certificate (容忍自签名证书)"

    def test_chown_nginx_preserved(self):
        """chown nginx:nginx 保留 (worker 进程仍以 nginx 用户运行)。"""
        content = _read(DOCKERFILE)
        assert (
            "chown -R nginx:nginx" in content
        ), "应保留 chown nginx:nginx (worker 进程权限)"


class TestDockerComposeConfig:
    """验证 docker-compose.yml: 443 端口 + 证书挂载 + HTTPS healthcheck。"""

    def test_docker_compose_exists(self):
        """docker-compose.yml 文件存在。"""
        if not DOCKER_COMPOSE.exists():
            pytest.skip(f"docker-compose.yml 不存在 (CI 环境可能未包含): {DOCKER_COMPOSE}")

    def test_frontend_ports_80_and_443(self):
        """frontend 服务 ports 应包含 80:80 和 443:443。"""
        content = _read(DOCKER_COMPOSE)
        # 提取 frontend 服务的 ports 配置
        frontend_match = re.search(
            r"frontend:\s*\n(.*?)(?=\n  \w|\n  #|\Z)",
            content,
            re.DOTALL,
        )
        assert frontend_match, "未找到 frontend 服务"
        frontend_config = frontend_match.group(1)
        assert '"80:80"' in frontend_config, "frontend ports 应包含 80:80"
        assert '"443:443"' in frontend_config, "frontend ports 应包含 443:443"

    def test_frontend_volumes_cert_mount(self):
        """frontend 服务 volumes 应挂载证书目录。"""
        content = _read(DOCKER_COMPOSE)
        frontend_match = re.search(
            r"frontend:\s*\n(.*?)(?=\n  \w|\n  #|\Z)",
            content,
            re.DOTALL,
        )
        assert frontend_match, "未找到 frontend 服务"
        frontend_config = frontend_match.group(1)
        assert (
            "infra/nginx/certs" in frontend_config
        ), "frontend volumes 应挂载 infra/nginx/certs"
        assert "/etc/nginx/certs" in frontend_config, "证书应挂载到 /etc/nginx/certs"
        assert ":ro" in frontend_config, "证书挂载应为只读 (:ro)"

    def test_frontend_healthcheck_https(self):
        """frontend healthcheck 应使用 https://。"""
        content = _read(DOCKER_COMPOSE)
        frontend_match = re.search(
            r"frontend:\s*\n(.*?)(?=\n  \w|\n  #|\Z)",
            content,
            re.DOTALL,
        )
        assert frontend_match, "未找到 frontend 服务"
        frontend_config = frontend_match.group(1)
        assert (
            "https://localhost/health" in frontend_config
        ), "healthcheck 应使用 https://localhost/health"
        assert (
            "--no-check-certificate" in frontend_config
        ), "healthcheck 应包含 --no-check-certificate"


class TestCertScript:
    """验证证书生成脚本存在且内容正确。"""

    def test_script_exists(self):
        """证书生成脚本存在。"""
        if not CERT_SCRIPT.exists():
            pytest.skip(f"证书脚本不存在 (CI 环境可能未包含): {CERT_SCRIPT}")

    def test_script_uses_openssl_req(self):
        """脚本应使用 openssl req -x509 生成自签名证书。"""
        content = _read(CERT_SCRIPT)
        assert "openssl req -x509" in content, "应使用 openssl req -x509"
        assert "-nodes" in content, "应使用 -nodes (私钥不加密)"
        assert "-newkey rsa:2048" in content, "应使用 RSA 2048"

    def test_script_output_paths(self):
        """脚本输出路径应为 infra/nginx/certs/server.{crt,key}。"""
        content = _read(CERT_SCRIPT)
        assert "infra/nginx/certs" in content, "输出目录应为 infra/nginx/certs"
        assert "server.crt" in content, "证书文件应为 server.crt"
        assert "server.key" in content, "私钥文件应为 server.key"

    def test_script_sets_permissions(self):
        """脚本应设置私钥权限 600。"""
        content = _read(CERT_SCRIPT)
        assert "chmod 600" in content, "应 chmod 600 私钥"

    def test_script_adds_san(self):
        """脚本应添加 subjectAltName (现代浏览器要求)。"""
        content = _read(CERT_SCRIPT)
        assert (
            "subjectAltName" in content or "addext" in content
        ), "应添加 subjectAltName (SAN)"

    def test_script_mentions_production_warning(self):
        """脚本应包含生产环境替换证书的警告。"""
        content = _read(CERT_SCRIPT)
        assert (
            "Let's Encrypt" in content or "CA" in content
        ), "应提及生产环境使用 CA 证书"


class TestGitignoreExcludesCerts:
    """验证 .gitignore 排除证书目录 (证书不应提交到 git)。"""

    def test_gitignore_exists(self):
        """.gitignore 文件存在。"""
        assert GITIGNORE.exists(), f".gitignore 不存在: {GITIGNORE}"

    def test_infra_excluded(self):
        """infra/ 目录应被 gitignore 排除。"""
        content = _read(GITIGNORE)
        # 匹配 infra/ 或 infra/* 单独一行 (非注释)
        lines = [
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert "infra/" in lines or "infra/*" in lines, "infra/ 或 infra/* 应在 .gitignore 中 (证书不提交)"

    def test_certs_not_tracked(self):
        """证书目录不应被 git 跟踪 (infra/nginx/certs/ 在 infra/ 下)。"""
        # 由于 infra/ 或 infra/* 被 gitignore, infra/nginx/certs/ 自动被排除
        # 这里验证 .gitignore 规则即可
        content = _read(GITIGNORE)
        assert "infra/" in content or "infra/*" in content, "infra/ 或 infra/* 应在 .gitignore 中"


class TestIntegrationConsistency:
    """验证各文件间配置一致性 (路径/端口/协议)。"""

    def test_cert_paths_consistent_across_files(self):
        """nginx.conf 证书路径与 docker-compose 挂载路径一致。"""
        nginx_conf = _read(NGINX_CONF)
        compose = _read(DOCKER_COMPOSE)
        # nginx.conf: ssl_certificate /etc/nginx/certs/server.crt
        # docker-compose: ./infra/nginx/certs:/etc/nginx/certs:ro
        assert (
            "/etc/nginx/certs/server.crt" in nginx_conf
        ), "nginx.conf 证书路径应为 /etc/nginx/certs/server.crt"
        assert "/etc/nginx/certs:/etc/nginx/certs" in compose or (
            "infra/nginx/certs" in compose and "/etc/nginx/certs" in compose
        ), "docker-compose 应挂载到 /etc/nginx/certs"

    def test_healthcheck_consistent_across_files(self):
        """Dockerfile 和 docker-compose healthcheck 都使用 https://。"""
        dockerfile = _read(DOCKERFILE)
        compose = _read(DOCKER_COMPOSE)
        assert (
            "https://localhost/health" in dockerfile
        ), "Dockerfile healthcheck 应使用 https://localhost/health"
        assert (
            "https://localhost/health" in compose
        ), "docker-compose healthcheck 应使用 https://localhost/health"

    def test_ports_consistent_across_files(self):
        """Dockerfile EXPOSE 与 docker-compose ports 一致 (80 + 443)。"""
        dockerfile = _read(DOCKERFILE)
        compose = _read(DOCKER_COMPOSE)
        # Dockerfile: EXPOSE 80 443
        expose_match = re.search(r"^EXPOSE\s+(.+)$", dockerfile, re.MULTILINE)
        assert expose_match, "Dockerfile 应有 EXPOSE"
        assert "443" in expose_match.group(1), "Dockerfile EXPOSE 应含 443"
        # docker-compose: "443:443"
        assert '"443:443"' in compose, 'docker-compose 应含 "443:443"'
