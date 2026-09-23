# 一键拉起全栈演示（P1，Windows PowerShell）：端口冲突检测 -> compose up -> 健康检查。
# 用法：powershell -ExecutionPolicy Bypass -File scripts/demo_up.ps1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path (Split-Path $MyInvocation.MyCommand.Path -Parent) -Parent)

$ports = @(80, 443, 3001, 8001, 9090)
$conflict = $false
foreach ($p in $ports) {
  $hit = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
  if ($hit) { Write-Host "[conflict] 端口 $p 被占用（Grafana 3001 常见为旧栈残留，见 docs/DEMO_CHECKLIST.md）"; $conflict = $true }
}
if ($conflict) { Write-Host '[abort] 请先释放冲突端口或按 DEMO_CHECKLIST 调整映射后重跑。'; exit 1 }

docker compose up -d --build
Write-Host '[wait] 等待 backend healthy...'
for ($i = 0; $i -lt 30; $i++) {
  try {
    $h = Invoke-RestMethod 'http://127.0.0.1:8001/health' -TimeoutSec 5
    Write-Host ("[ok] 全栈已拉起：{0}" -f ($h | ConvertTo-Json -Compress))
    exit 0
  } catch { Start-Sleep -Seconds 10 }
}
Write-Host '[fail] backend 300s 内未 healthy，请 docker compose ps / logs backend 排查。'
exit 1
