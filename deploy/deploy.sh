#!/usr/bin/env bash
# Deploy the committed HEAD to the server. Usage: deploy/deploy.sh [ssh target]
# Secrets live only on the server in /etc/verified-asset.env (MODEL_API_KEY, SPEND_CAP_USD).
set -euo pipefail
TARGET=${1:-${VA_HOST:-root@192.168.100.231}}
SSH=(ssh -J prox -i ~/.ssh/id_ed25519_homelab "$TARGET")
cd "$(git rev-parse --show-toplevel)"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
git archive HEAD app pyproject.toml uv.lock deploy/verified-asset.service | tar -x -C "$STAGE"
git rev-parse --short HEAD > "$STAGE/REVISION"
rsync -a --delete -e "ssh -J prox -i $HOME/.ssh/id_ed25519_homelab" --exclude deploy \
  "$STAGE"/ "$TARGET":/opt/verified-asset/app/
"${SSH[@]}" "install -m 644 /dev/stdin /etc/systemd/system/verified-asset.service" < "$STAGE/deploy/verified-asset.service"
"${SSH[@]}" 'chown -R va:va /opt/verified-asset && cd /opt/verified-asset/app \
  && runuser -u va -- env UV_CACHE_DIR=/opt/verified-asset/.cache/uv /usr/local/bin/uv sync --frozen --no-dev -q \
  && systemctl daemon-reload && systemctl enable -q verified-asset && systemctl restart verified-asset \
  && sleep 3 && curl -fsS -o /dev/null -w "deployed $(cat REVISION): HTTP %{http_code}\n" http://127.0.0.1:8000/'
