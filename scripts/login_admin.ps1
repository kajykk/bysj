# Admin login helper for canary release operations (PowerShell twin of login_admin.py).
#
# L13 修复（ROUND_23）：口令与令牌路径一律从环境变量读取，缺失即报错退出。
# 修前硬编码了管理员口令，且令牌写绝对路径 scripts\.admin_token.txt
# （换机器即失效）。口令字面量不再出现在版本库的任何位置（含注释）。
# 闸门：backend/tests/test_p2_49_round23b_secret_scan.py 扫描 scripts/ 下的
# 硬编码口令/令牌字面量（含 .ps1）。
$env:PYTHONIOENCODING = "utf-8"

$username = $env:BYSJ_ADMIN_USERNAME
$password = $env:BYSJ_ADMIN_PASSWORD

if (-not $username -or -not $password) {
    Write-Host "ERROR: missing env vars BYSJ_ADMIN_USERNAME / BYSJ_ADMIN_PASSWORD." -ForegroundColor Red
    Write-Host "This script no longer embeds any password (L13 fix). Set them first:"
    Write-Host '  $env:BYSJ_ADMIN_USERNAME = "admin"'
    Write-Host '  $env:BYSJ_ADMIN_PASSWORD = "<your password>"'
    exit 2
}

$repoRoot = Split-Path -Parent $PSScriptRoot
if ($env:BYSJ_ADMIN_TOKEN_PATH) {
    $tokenPath = $env:BYSJ_ADMIN_TOKEN_PATH
} else {
    $tokenPath = Join-Path $repoRoot "scripts/.admin_token.txt"
}

$loginBody = @{
    username = $username
    password = $password
} | ConvertTo-Json -Compress

$resp = curl.exe -s -X POST http://localhost:8001/api/v1/auth/login -H "Content-Type: application/json" -d $loginBody
Write-Host "Login resp:"
Write-Host $resp
# 提取 token
try {
    $obj = $resp | ConvertFrom-Json
    if ($obj.data.access_token) {
        $tokenDir = Split-Path -Parent $tokenPath
        if (-not (Test-Path $tokenDir)) { New-Item -ItemType Directory -Path $tokenDir -Force | Out-Null }
        $obj.data.access_token | Out-File -FilePath $tokenPath -NoNewline -Encoding utf8
        Write-Host "Token saved to $tokenPath"
    }
} catch {
    Write-Host "Failed to parse token: $_"
}
