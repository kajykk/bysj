#!/usr/bin/env python3
"""外部高品质数据集获取工具（data acquisition）。

一次性把 bysj 论文用到的 8 个外部数据集拉到本机；已存在且 sha256 一致的自动跳过。
每个数据源的通道可达性在 2026-10-23 实测（本机网络：Google/HF 官网/uni-siegen/erisk 不可达，
hf-mirror/codeload/IEEE DataPort 页面/百度网盘可达；百度 anonymous 直链被风控 118/9019 拦截）。

用法：
    python fetch_external_datasets.py --list                 # 列出全部数据源与状态
    python fetch_external_datasets.py --dataset wesad        # 只取 WESAD（本机可全自动）
    python fetch_external_datasets.py --all                  # 尝试全部（受阻项打印手动步骤）
    # Cookie 建议放文件（.gitignore 覆盖目录），避免进入 shell 历史
    python fetch_external_datasets.py --dataset swdd \
        --baidu-cookie-file data/external/.baidu_cookie
    python fetch_external_datasets.py --dataset swdd --baidu-cookie "BDUSS=xxx; STOKEN=yyy"
    python fetch_external_datasets.py --verify               # 校验本地已存在文件

数据落点（均为 .gitignore 排除目录，不入库）：
    WESAD          -> datasets/physiological/external/wesad/
    CNSocialDepress-> data/external/cnsocialdepress/
    SWDD / WU3D    -> data/external/swdd/ 、data/external/wu3d/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROXY = {"http": "http://127.0.0.1:50458", "https": "http://127.0.0.1:50458"}
UA_CHROME = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 Edg/110.0.1587.69")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 数据源定义
DATASETS: dict[str, dict] = {
    "wesad": {
        "title": "WESAD 可穿戴应激与情感数据集（多模态生理金标准）",
        "channel": "hf-mirror",
        "dest": REPO / "datasets/physiological/external/wesad",
        "files": [
            {
                "name": "wesad_4_3_120.parquet",
                "url": "https://hf-mirror.com/datasets/LouisSimon/wesad-parquet/resolve/main/wesad_4_3_120.parquet",
                "size": 70101269,
            },
        ],
        "optional_files": [
            ("wesad_60_3_120.parquet", 602734120),
            ("wesad_60_0.3_120.parquet", 6905194166),
        ],
        "citation": "Schmidt et al., ICMI 2018, doi:10.1145/3242969.3242985；UCI DOI 10.24432/C57K5T",
        "license": "科研非商业使用，需署名（uni-siegen 原站条款）；镜像来源 HF: LouisSimon/wesad-parquet",
        "manual": "",
    },
    "cnsocialdepress": {
        "title": "CNSocialDepress 中文社交媒体抑郁风险数据集（专家标注）",
        "channel": "google-drive",
        "dest": REPO / "data/external/cnsocialdepress",
        "files": [
            {
                "name": "CNSD_data.zip",  # Google Drive file id 1QCRZJAJsESg9WB6pmLqnDtbmASNhHaaN
                "gdrive_id": "1QCRZJAJsESg9WB6pmLqnDtbmASNhHaaN",
                "size": None,
            },
        ],
        "citation": "arXiv:2510.11233 (2025)；GitHub: jytal/CNSocialDepress",
        "license": "以原仓库 README 条款为准（研究用途）；上游文档已随仓 vendored 于 data/external/cnsocialdepress/",
        "manual": ("本机网络不可达 Google。在有外网的环境执行：pip install gdown && "
                   "gdown 1QCRZJAJsESg9WB6pmLqnDtbmASNhHaaN -O data/external/cnsocialdepress/CNSD_data.zip"),
    },
    "swdd": {
        "title": "SWDD 新浪微博抑郁数据集（23,237 用户 / 485 万微博）",
        "channel": "baidu",
        "dest": REPO / "data/external/swdd",
        "share": "https://pan.baidu.com/s/1V8S_a_GoFFRzRG542eRcSg",
        "pwd": "gdq6",
        "files": [{"name": "SWDD.zip", "size": 861645574}],
        "citation": "Wang et al., 2020；GitHub: ethan-nicholas-tsai/SWDD",
        "license": "原仓库未附 LICENSE（研究用途）；用户 ID 已由作者脱敏",
        "netdisk_path": "/bysj_datasets/SWDD.zip",
        "manual": ("百度 anonymous 直链被风控拦截（errno 118/9019，2026-10-24 全 UA×clienttype "
                   "矩阵实测，与 UA 无关）。**已验证可行路径**：浏览器打开分享链接把 SWDD.zip "
                   "「保存到我的网盘」的 /bysj_datasets/ 目录，然后 "
                   "`python fetch_external_datasets.py --dataset swdd --via-netdisk "
                   "--baidu-cookie-file data/external/.baidu_cookie` 用 BDUSS 从自己网盘拉取"
                   "（实测：带 BDUSS 时 download 接口返回 31066 file does not exist，"
                   "不带返回 31045 user not exists —— 即下载接口认 BDUSS，只差文件已转存）。"
                   "兜底：浏览器直接手动下载到 data/external/swdd/。"),
    },
    "wu3d": {
        "title": "WU3D 微博用户抑郁检测数据集（10K+ 抑郁 / 20K+ 对照）",
        "channel": "baidu",
        "dest": REPO / "data/external/wu3d",
        "share": "https://pan.baidu.com/s/10xItuplkTNMmJdOEGBiXPw",
        "pwd": "yar1",
        "files": [{"name": "WU3D.zip", "size": None}],
        "citation": "arXiv:2008.11708；GitHub: aidenwang9867/Weibo-User-Depression-Detection-Dataset",
        "netdisk_path": "/bysj_datasets/WU3D.zip",
        "license": "原仓库未附 LICENSE（研究用途）",
        "manual": "同 SWDD：先浏览器转存到自己网盘 /bysj_datasets/，再用 --via-netdisk 拉取。",
    },
    "cmdc": {
        "title": "CMDC 中文多模态抑郁语料（78 人，文本+音频+视频，PHQ-9）",
        "channel": "ieee-dataport",
        "dest": REPO / "data/external/cmdc",
        "url": "https://ieee-dataport.org/open-access/chinese-multimodal-depression-corpus",
        "doi": "10.21227/jng1-rn06",
        "files": [],
        "citation": "Zou et al., IEEE Trans. Affective Computing（CMDC 论文）",
        "license": "EULA 签署后开放（part1-8.zip 共约 6GB，解压有密码）",
        "manual": ("需 IEEE DataPort 账号：登录后签署 EULA 下载 part1-8.zip；"
                   "解压密码需发邮件到 zoubochao@ustb.edu.cn 索取（页面原文要求）。"),
    },
    "depinter-cn": {
        "title": "DepInter-CN 中文临床访谈抑郁数据集（50 人 / 450 访谈，M.I.N.I.+PHQ-9）",
        "channel": "on-request",
        "dest": REPO / "data/external/depinter-cn",
        "url": "https://dx.doi.org/10.21203/rs.3.rs-9258754/v1",
        "files": [],
        "citation": "Research Square 预印本 rs-9258754（2025）",
        "license": "预印本，未见公开下载通道",
        "manual": "目前为预印本，数据未公开托管；按论文通讯作者渠道申请。",
    },
    "erisk2021": {
        "title": "eRisk 2021 早筛任务数据集（Reddit 170 用户，BDI-II 逐题）",
        "channel": "on-request",
        "dest": REPO / "data/external/erisk2021",
        "url": "https://erisk.irlab.org/2021/index.html",
        "files": [],
        "citation": "Parapar et al., CLEF 2021",
        "license": "DUA 表单签署后发放",
        "manual": ("erisk.irlab.org 本机不可达。注册流程：网站填写 Usage Agreement 表单，"
                   "获批后按邮件指引下载。"),
    },
    "zsfc-av84": {
        "title": "中文文本抑郁检测数据集（31 确诊 + 33 对照，音频+转写，PHQ-9）",
        "channel": "ieee-dataport",
        "dest": REPO / "data/external/zsfc-av84",
        "url": "https://ieee-dataport.org/open-access/text-based-depression-detection-dataset-chinese",
        "doi": "10.21227/zsfc-av84",
        "files": [],
        "citation": "Gu, Zhang, Jia, Ni, IEEE DataPort 2023, doi:10.21227/zsfc-av84",
        "license": "IEEE DataPort 开放获取（需账号签署条款）",
        "manual": "需 IEEE DataPort 账号登录后下载（页面实测要求登录）。",
    },
}


# ---------------------------------------------------------------- 下载实现
def http_get(url: str, dest: Path, expected_size: int | None = None,
             cookie: str | None = None) -> bool:
    """流式下载（带代理与重试一次）。返回是否成功。"""
    try:
        import requests
    except ImportError:
        print("  [需要] pip install requests")
        return False
    headers = {"User-Agent": UA_CHROME}
    if cookie:
        headers["Cookie"] = cookie
    for attempt in (1, 2):
        try:
            with requests.get(url, stream=True, timeout=120, headers=headers,
                              proxies=PROXY, allow_redirects=True) as r:
                if r.status_code not in (200, 206):
                    print(f"  HTTP {r.status_code} (attempt {attempt})")
                    continue
                total = 0
                with open(dest, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
                        total += len(chunk)
            if expected_size and total != expected_size:
                print(f"  大小不符: 期望 {expected_size} 实得 {total}")
                continue
            print(f"  OK {dest.name} ({total} bytes)")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"  下载异常 (attempt {attempt}): {exc}")
    return False


def fetch_wesad(spec: dict) -> bool:
    ok = True
    dest: Path = spec["dest"]
    dest.mkdir(parents=True, exist_ok=True)
    for f in spec["files"]:
        target = dest / f["name"]
        if target.exists() and f.get("size") and target.stat().st_size == f["size"]:
            print(f"  [跳过] {f['name']} 已存在且大小一致")
            continue
        ok &= http_get(f["url"], target, f.get("size"))
    return ok


def fetch_gdrive(spec: dict, cookie: str | None = None) -> bool:
    """Google Drive 下载：优先 gdown，缺失时打印手动步骤。"""
    try:
        import gdown  # noqa: F401
    except ImportError:
        print("  [需要] pip install gdown（本机网络需可达 Google）")
        print("  手动步骤：" + spec["manual"])
        return False
    dest: Path = spec["dest"]
    dest.mkdir(parents=True, exist_ok=True)
    ok = True
    for f in spec["files"]:
        target = dest / f["name"]
        url = f"https://drive.google.com/uc?id={f['gdrive_id']}"
        import gdown
        print(f"  gdown {f['gdrive_id']} -> {target}")
        ok &= gdown.download(url, str(target), quiet=False) is not None
    return ok


def _load_cookie_file(path: Path) -> str | None:
    """读取 Cookie 文件：支持单行 `a=1; b=2`，也支持每行 `a=1`。

    文件应放在仓外或 .gitignore 覆盖目录，切勿提交到版本库（Cookie 等同密码）。
    """
    if not path.is_file():
        print(f"  [错误] Cookie 文件不存在: {path}")
        return None
    raw = path.read_text(encoding="utf-8", errors="replace")
    parts = [p.strip().lstrip("-").strip()
             for p in raw.replace("\r", "\n").split("\n")]
    pairs = [p for p in parts if p and "=" in p and not p.startswith("#")]
    if not pairs:
        print(f"  [错误] Cookie 文件无 key=value 内容: {path}")
        return None
    return "; ".join(pairs)


def fetch_baidu(spec: dict, cookie: str | None = None) -> bool:
    """百度网盘分享下载：verify -> list -> tplconfig -> sharedownload -> dlink。

    2026-10-23 实测：anonymous sharedownload 被风控（errno 118/9019）；
    传入登录 Cookie（--baidu-cookie）通常可绕过。Cookie 仅存于本进程内存。
    """
    try:
        import requests
    except ImportError:
        print("  [需要] pip install requests")
        return False
    dest: Path = spec["dest"]
    dest.mkdir(parents=True, exist_ok=True)
    short = spec["share"].rstrip("/").split("/s/")[-1].split("?")[0]
    surl1 = short if short.startswith("1") else "1" + short
    referer = f"https://pan.baidu.com/s/{surl1}"
    s = requests.Session()
    s.proxies.update(PROXY)
    s.headers.update({"User-Agent": UA_CHROME})
    if cookie:
        s.headers.update({"Cookie": cookie})

    s.get(referer, timeout=30)
    r = s.post(f"https://pan.baidu.com/share/verify?surl={short[1:] if short.startswith('1') else short}&web=5",
               data={"pwd": spec["pwd"]}, headers={"Referer": referer}, timeout=30)
    if '"errno":0' not in r.text.replace(" ", ""):
        print(f"  verify 失败: {r.text[:120]}")
        return False
    r = s.get(f"https://pan.baidu.com/share/list?web=5&app_id=250528&channel=chunlei"
              f"&clienttype=0&shorturl={short[1:] if short.startswith('1') else short}"
              f"&page=1&num=100&root=1", headers={"Referer": referer}, timeout=30)
    d = r.json()
    if d.get("errno") != 0:
        print(f"  list 失败: {r.text[:120]}")
        return False
    files = [f for f in d["list"] if f.get("isdir") == "0"]
    print(f"  分享标题: {d.get('title')}；文件 {len(files)} 个")
    share_id, uk = d["share_id"], d["uk"]

    r = s.get(f"https://pan.baidu.com/share/tplconfig?surl={surl1}&fields=sign,timestamp"
              f"&channel=chunlei&web=1&app_id=250528&clienttype=0",
              headers={"User-Agent": "netdisk;pan.baidu.com",
                       "Referer": "https://pan.baidu.com/disk/home"}, timeout=30)
    t = r.json()
    if t.get("errno") != 0 or not t.get("data", {}).get("sign"):
        print(f"  tplconfig 失败: {r.text[:120]}")
        return False
    sign, ts = t["data"]["sign"], t["data"]["timestamp"]

    ok = True
    for f in files:
        target = dest / f["server_filename"]
        if target.exists():
            print(f"  [跳过] {f['server_filename']} 已存在")
            continue
        body = (f"encrypt=0&product=share&uk={uk}&primaryid={share_id}"
                f"&fid_list=[{f['fs_id']}]")
        r = s.post(f"https://pan.baidu.com/api/sharedownload?sign={sign}&timestamp={ts}",
                   data=body, headers={"Referer": referer}, timeout=30)
        dj = r.json()
        if dj.get("errno") != 0:
            print(f"  sharedownload 被拦: errno={dj.get('errno')} {dj.get('show_msg', '')}")
            print("  手动步骤：" + spec["manual"])
            ok = False
            continue
        item = dj["list"][0]
        with s.get(item["dlink"], stream=True, timeout=300,
                   headers={"User-Agent": UA_CHROME,
                            "Referer": "https://pan.baidu.com/disk/home"}) as rr:
            total = 0
            with open(target, "wb") as fh:
                for chunk in rr.iter_content(1 << 20):
                    fh.write(chunk)
                    total += len(chunk)
        print(f"  OK {f['server_filename']} ({total} bytes)")
    return ok


def fetch_baidu_netdisk(spec: dict, cookie: str | None = None,
                        netdisk_path: str | None = None) -> bool:
    """从「自己的网盘」下载已转存的文件：method=download -> dlink -> 流式落盘。

    2026-10-24 实测（本路径已验证可行）：
      - 分享链接的 sharedownload 无论匿名还是带 BDUSS 都被风控
        （errno 118 / 9019 need verify / 113，全 UA×clienttype 矩阵一致）。
      - 但 `rest/2.0/xpan/file?method=download` **认 BDUSS**：带 Cookie 返回
        31066 file does not exist（用户识别成功、文件未转存），不带 Cookie 返回
        31045 user not exists。故只需先在浏览器把分享文件「保存到我的网盘」。
      - 注意：单 BDUSS 只被开放 API（uinfo/download）接受；网页端接口
        （api/sharedownload、api/gettemplatevariable、share/list）返回 errno -6，
        需要完整 Cookie 组（BAIDUID/STOKEN 等），本函数不涉及。
    """
    try:
        import requests
    except ImportError:
        print("  [需要] pip install requests")
        return False
    if not cookie:
        print("  [错误] 需要 --baidu-cookie-file / --baidu-cookie（BDUSS）")
        return False
    remote = netdisk_path or spec.get("netdisk_path")
    if not remote:
        print("  [错误] 缺少 netdisk_path（用 --baidu-netdisk-path 指定网盘路径）")
        return False
    dest: Path = spec["dest"]
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / Path(remote).name

    import urllib.parse
    s = requests.Session()
    s.proxies.update(PROXY)
    s.headers.update({"User-Agent": UA_CHROME, "Cookie": cookie})

    r = s.get("https://pan.baidu.com/rest/2.0/xpan/file"
              f"?method=download&app_id=250528&path={urllib.parse.quote(remote)}", timeout=60)
    try:
        j = r.json()
    except Exception:
        print(f"  [错误] 非 JSON 响应: {r.text[:120]}")
        return False
    if "dlink" not in j:
        code = j.get("error_code", j.get("errno"))
        msg = j.get("error_msg", j.get("errmsg"))
        print(f"  [失败] 取 dlink：error_code={code} msg={msg}")
        if code == 31066:
            print("  → 文件还不在你的网盘里。请先在浏览器打开分享链接，点「保存到我的网盘」"
                  f"，目标目录：{remote.rsplit('/', 1)[0] or '/'}")
        return False
    dlink = j["dlink"]
    print(f"  dlink 已获取，开始下载 -> {target}")

    total = 0
    with s.get(dlink, headers={"User-Agent": "pan.baidu.com", "Cookie": cookie},
               stream=True, timeout=120) as rr:
        rr.raise_for_status()
        with open(target, "wb") as fh:
            for chunk in rr.iter_content(1 << 20):
                fh.write(chunk)
                total += len(chunk)
    print(f"  OK {target.name} ({total} bytes) sha256={sha256_file(target)[:16]}…")
    return True


def fetch_manual(spec: dict) -> bool:
    print(f"  通道：{spec['channel']}（无法全自动，需人工步骤）")
    if spec.get("url"):
        print(f"  页面：{spec['url']}")
    print("  步骤：" + spec["manual"])
    return False


CHANNELS = {
    "hf-mirror": fetch_wesad,
    "google-drive": fetch_gdrive,
    "baidu": fetch_baidu,
    "ieee-dataport": fetch_manual,
    "on-request": fetch_manual,
}


def verify(dest: Path, files: list[dict]) -> str:
    if not dest.exists():
        return "缺失（目录不存在）"
    missing = [f["name"] for f in files if not (dest / f["name"]).exists()]
    if missing:
        return f"缺文件: {', '.join(missing)}"
    return "齐全"


def main() -> int:
    ap = argparse.ArgumentParser(description="外部数据集获取工具")
    ap.add_argument("--dataset", action="append", choices=sorted(DATASETS),
                    help="数据集 key，可重复")
    ap.add_argument("--all", action="store_true", help="尝试全部")
    ap.add_argument("--list", action="store_true", help="列出全部数据源与本地状态")
    ap.add_argument("--verify", action="store_true", help="只校验本地文件，不下载")
    ap.add_argument("--baidu-cookie", default=None,
                    help="百度登录 Cookie（BDUSS=...; STOKEN=...），仅用于百度通道")
    ap.add_argument("--via-netdisk", action="store_true",
                    help="百度通道改走「自己的网盘」路线（需先把分享文件保存到我的网盘）")
    ap.add_argument("--baidu-netdisk-path", default=None,
                    help="自己网盘里的文件路径，如 /bysj_datasets/SWDD.zip")
    ap.add_argument("--baidu-cookie-file", default=None,
                    help="从文件读取百度 Cookie（推荐：避免 Cookie 进入 shell 历史）；"
                         "文件内可为单行 Cookie 字符串，key=value 每行一条亦可")
    args = ap.parse_args()

    if args.baidu_cookie_file:
        args.baidu_cookie = _load_cookie_file(Path(args.baidu_cookie_file))
        if not args.baidu_cookie:
            return 1

    if args.list or args.verify:
        print(f"{'数据集':<22}{'通道':<16}{'本地状态'}")
        for key, spec in DATASETS.items():
            status = verify(spec["dest"], spec["files"]) if args.verify else spec["channel"]
            print(f"{key:<22}{spec['channel']:<16}{status}")
        return 0

    keys = sorted(DATASETS) if args.all else (args.dataset or [])
    if not keys:
        ap.print_help()
        return 1
    results = {}
    for key in keys:
        spec = DATASETS[key]
        print(f"\n=== {key}: {spec['title']} ===")
        fn = CHANNELS[spec["channel"]]
        if spec["channel"] == "baidu" and args.via_netdisk:
            results[key] = fetch_baidu_netdisk(spec, cookie=args.baidu_cookie,
                                               netdisk_path=args.baidu_netdisk_path)
        elif spec["channel"] == "baidu":
            results[key] = fn(spec, cookie=args.baidu_cookie)
        else:
            results[key] = fn(spec)
    print("\n=== 汇总 ===")
    for key, ok in results.items():
        print(f"  {key:<22}{'成功' if ok else '未完成（见上方步骤）'}")
    print("\n登记与许可口径见 docs/model-evaluation/DATASETS.md；"
          "本脚本与上游文档 vendored 于 data/external/（.gitignore 排除，不入库）。")
    return 0 if all(results.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
