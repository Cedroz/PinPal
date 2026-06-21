#!/usr/bin/env bash
# Run this on the machine that already has SSH access to the Pi, once per
# teammate, to grant them access. Takes the pubkey line a teammate sent you
# (from running scripts/pinpal_connect.sh) and appends it to the Pi's
# authorized_keys — skips it if already present, so it's safe to re-run.
#
# Usage:
#   ./scripts/pinpal_authorize.sh "ssh-ed25519 AAAA... pinpal-deploy-alice"

set -euo pipefail

PI_HOST="${PINPAL_HOST:-pinpal.local}"
PI_USER="${PINPAL_USER:-pinpal}"
KEY="$HOME/.ssh/pinpal_ed25519"

if [ $# -lt 1 ] || [ -z "$1" ]; then
  echo "Usage: $0 \"<full ssh-ed25519 ... line a teammate sent you>\"" >&2
  exit 1
fi
PUBKEY="$1"

if ! [[ "$PUBKEY" =~ ^ssh-ed25519\  ]]; then
  echo "That doesn't look like an ssh-ed25519 public key line. Aborting." >&2
  exit 1
fi

if [ ! -f "$KEY" ]; then
  echo "No $KEY found — run scripts/pinpal_connect.sh yourself first to get access." >&2
  exit 1
fi

ssh -o ConnectTimeout=8 -o IdentitiesOnly=yes -i "$KEY" "$PI_USER@$PI_HOST" \
  "grep -qxF '$PUBKEY' ~/.ssh/authorized_keys 2>/dev/null && echo ALREADY_PRESENT || (echo '$PUBKEY' >> ~/.ssh/authorized_keys && echo ADDED)"

echo "Key owner tag: $(echo "$PUBKEY" | awk '{print $NF}')"
