# EATD 外部锁定测试 · 数据获取指引（给操作者）

> 这两个脚本已就绪并通过 synthetic fixture 端到端验证。**唯一缺的是真实的 EATD 数据**
> ——它不在 GitHub、只能经官方 OneDrive 手动获取（本机直连 OneDrive 超时，需你在浏览器完成）。

## 步骤一：下载

1. 浏览器打开（必要时用可访问 OneDrive 的网络/代理）：
   `https://1drv.ms/u/s!AsGVGqImbOwYhHUHcodFC3xmKZKK?e=mCT5oN`
2. 下载压缩包，解压密码：`Ymj26Uv5`
3. 解压后应得到 162 个志愿者文件夹，每个含：
   - `positive.txt / negative.txt / neutral.txt`（访谈转录）
   - `positive.wav ...`（音频，**你不需要，占空间可删**）
   - `label.txt`（原始 SDS 分）、`new_label.txt`（标准化 = 原始×1.25）

## 步骤二：放置

把解压出来的志愿者文件夹放到：

```
data/external/eatd/
```

目录层级形如：

```
data/external/eatd/
  <志愿者文件夹1>/positive.txt negative.txt neutral.txt label.txt new_label.txt ...
  <志愿者文件夹2>/...
  ...
```

（`data/external/` 被 .gitignore 排除，不会入库；只登记形态。若解压多套了一层目录无妨，
脚本用 `rglob` 递归找。）

## 步骤三：先校验结构（不报指标）

```bash
cd backend
.venv/Scripts/python.exe scripts/modeling/eval/v1_31/validate_eatd.py --data-root ../data/external/eatd
```

预期输出类似：`subjects=162 scored=162 pos>=53=... overlap=0`。
- 若 `scored` 远小于 `subjects`：label 文件命名/编码有出入，看生成的 `eatd_structure_report.json`。
- 若 `overlap>0`：脚本会警告——说明与训练语料有重叠，评估时须剔除（按理不应发生）。

## 步骤四：一次性锁定评估（只跑一次，按预注册）

```bash
cd backend
.venv/Scripts/python.exe scripts/modeling/eval/v1_31/eval_eatd_locked.py --data-root ../data/external/eatd
```

产出 `eatd_eval.json` + `eatd_predictions.csv`（逐样本概率，供复算与 CI）。
**这是唯一一次**：看到结果后不得改切点/阈值/预处理重跑（见 `EATD_PREREGISTRATION.md` §8）。

## 我已经替你挡掉的坑

- 生产文本模型加载：验证过 `improved_bilingual_tfidf.pkl`(120k 特征)+ `improved_bilingual_model.pkl`
  可 transform、给出合理概率；
- 编码：label 读取用 `utf-8-sig` + 正则取数，容忍 BOM 和 `SDS: 53` 之类前缀；
- 划分泄漏：脚本**只 transform 不 fit**，不存在"在 EATD 上重训"的可能；
- 小样本：CI 按 subject 分组 bootstrap，会如实给出宽区间。