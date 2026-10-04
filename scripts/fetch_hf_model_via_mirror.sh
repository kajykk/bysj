#!/usr/bin/env bash
# 通过 hf-mirror 断点续传下载 HuggingFace 模型到本地目录。
#
# 为什么需要这个脚本（本机实测 2026-10-04）:
#   1. huggingface.co 直连不通(超时)，需 HF_ENDPOINT=https://hf-mirror.com；
#   2. 镜像对大文件连接会中断（470MB 每次只给 ~5.7MB），huggingface_hub 的
#      snapshot_download 未能续传 → 空文件 → JSONDecodeError；
#   3. python urllib 带 Range 跟随重定向时会丢头，续传失效(0 字节卡死)；
#      curl -C - 有效。
#   4. 小文件也可能被截断且 curl 仍返回 0 —— 必须做完整性校验(见 verify)。
#
# 用法:
#   bash scripts/fetch_hf_model_via_mirror.sh <repo_id> <dest_dir> [expected_bytes]
# 例:
#   bash scripts/fetch_hf_model_via_mirror.sh \
#     sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 models/_cache/minilm-l12
set -u
REPO="${1:?用法: fetch_hf_model_via_mirror.sh <repo_id> <dest_dir> [expected_bytes]}"
DEST="${2:?缺少 dest_dir}"
EXPECT="${3:-0}"
ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
B="$ENDPOINT/$REPO/resolve/main"

mkdir -p "$DEST/1_Pooling"
echo "== 目标: $REPO -> $DEST（镜像 $ENDPOINT）=="

# 1) 小文件：存在即跳过（幂等重跑）
for f in config.json config_sentence_transformers.json modules.json \
         sentence_bert_config.json special_tokens_map.json tokenizer_config.json \
         tokenizer.json sentencepiece.bpe.model 1_Pooling/config.json; do
  if [ -s "$DEST/$f" ]; then echo "  skip $f"; continue; fi
  curl -sS -L --max-time 120 -o "$DEST/$f" "$B/$f" || echo "  WARN 下载失败: $f"
done

# 2) 大文件：按 X-Linked-Size 断点续传到齐
remote_size() { curl -sI --max-time 20 -L "$1" | tr -d '\r' | awk 'tolower($1)=="x-linked-size:"{print $2}'; }
W="$DEST/model.safetensors"
TARGET="${EXPECT:-$(remote_size "$B/model.safetensors")}"
echo "== 权重续传: 目标 ${TARGET:-未知} 字节 =="
if [ -z "${TARGET:-}" ] || [ "$TARGET" -eq 0 ] 2>/dev/null; then
  echo "  拿不到 X-Linked-Size，退化为单次下载（可能不完整，务必手工校验）"
  curl -sS -L --max-time 600 -o "$W" "$B/model.safetensors" || true
else
  for i in $(seq 1 300); do
    sz=$(stat -c %s "$W" 2>/dev/null || echo 0)
    [ "$sz" -ge "$TARGET" ] && { echo "  完成: $sz 字节（第 $i 轮）"; break; }
    if [ "$i" -eq 1 ]; then
      curl -sS -L --max-time 180 -o "$W" "$B/model.safetensors" || true
    else
      curl -sS -L -C - --max-time 180 -o "$W" "$B/model.safetensors" || true
    fi
    nsz=$(stat -c %s "$W" 2>/dev/null || echo 0)
    echo "  [$i] $sz -> $nsz / $TARGET"
    [ "$nsz" = "$sz" ] && sleep 1
  done
fi

# 3) 完整性校验（关键: 大小对不代表内容对）
echo "== 校验 =="
python - "$DEST" "$TARGET" <<'PY'
import json, os, sys
dest, target = sys.argv[1], int(sys.argv[2] or 0)
ok = True
w = os.path.join(dest, "model.safetensors")
if os.path.exists(w):
    sz = os.path.getsize(w)
    print(f"  safetensors: {sz:,} / {target:,}" if target else f"  safetensors: {sz:,}")
    if target and sz != target:
        print("    ! 大小不符"); ok = False
    with open(w, "rb") as f:
        if f.read(2) != b'{"':
            print("    ! 头部不是 safetensors JSON, 内容可能损坏"); ok = False
t = os.path.join(dest, "tokenizer.json")
if os.path.exists(t):
    try:
        d = json.load(open(t, encoding="utf-8"))
        print(f"  tokenizer.json: OK, vocab={len(d.get('model',{}).get('vocab',{}))}")
    except Exception as e:
        print(f"  tokenizer.json: 损坏 ({type(e).__name__}) — 用 curl -C - 续传补齐"); ok = False
print("VERIFY:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
PY
