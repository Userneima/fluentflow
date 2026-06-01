#!/bin/bash
# 将 FluentFlow.app 复制到桌面，双击即可在后台启动本地服务并打开浏览器（会重启占用 8000 端口的进程）。
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)/FluentFlow.app"
DEST="${HOME}/Desktop/FluentFlow.app"
if [[ ! -d "$SRC" ]]; then
	echo "找不到 $SRC" >&2
	exit 1
fi
rm -rf "$DEST"
cp -R "$SRC" "$DEST"
echo "已安装到: $DEST"
open -R "$DEST"
