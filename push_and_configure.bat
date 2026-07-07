@echo off
REM =====================================================
REM  DWS 仓库一键推送 + 配置脚本
REM  使用前请确保：
REM  1. 已配置好 Git 凭证（PAT 或 SSH key）
REM  2. 网络能访问 github.com:443
REM =====================================================
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  步骤 1/3: 推送本地提交到 GitHub
echo ============================================
git push origin main
if errorlevel 1 (
  echo.
  echo  ❌ 推送失败，请检查：
  echo     1. 网络是否能访问 github.com:443
  echo     2. 是否已配置 PAT (Settings -^> Developer settings -^> PAT)
  echo     3. PAT 需勾选 Contents: Read and write
  echo.
  pause
  exit /b 1
)

echo.
echo ============================================
echo  步骤 2/3: 添加 GitHub Topics (需 PAT)
echo ============================================
set /p TOKEN="请输入你的 GitHub Personal Access Token (直接回车跳过): "
if "%TOKEN%"=="" goto :SKIP_TOPICS

curl -s -X PUT "https://api.github.com/repos/kajykk/bysj/topics" ^
  -H "Authorization: token %TOKEN%" ^
  -H "Accept: application/vnd.github+json" ^
  -d "{\"names\":[\"vue\",\"fastapi\",\"docker\",\"ai\",\"fullstack\",\"mental-health\",\"ml\",\"typescript\",\"python\",\"websocket\"]}"
echo.
echo  ✅ Topics 已设置
goto :AFTER_TOPICS

:SKIP_TOPICS
echo.
echo  ⚠️  跳过 Topics 设置。你可以稍后手动在 GitHub 网页上添加。
echo     仓库页面 → About 右侧齿轮 → Topics 输入：
echo     vue fastapi docker ai fullstack mental-health ml

:AFTER_TOPICS
echo.
echo ============================================
echo  步骤 3/3: 验证
echo ============================================
echo  打开浏览器查看：
echo    https://github.com/kajykk/bysj
echo.
echo  验证清单：
echo    [√] README.md 显示 5 张截图和 AI 工具说明
echo    [√] LICENSE 文件存在
echo    [√] 仓库顶部显示 Topics 标签
echo.
pause
