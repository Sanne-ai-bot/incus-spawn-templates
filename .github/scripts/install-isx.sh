#!/usr/bin/env bash
# Installs isx and isx-proxy from a release of Sanne/incus-spawn into ~/.local/bin, each checked
# against the release's SHA256SUMS. The release is $ISX_CI_VERSION, or the latest one: the templates
# are checked with the isx their users install. Needs gh with a token in $GH_TOKEN.
set -euo pipefail

repo=Sanne/incus-spawn
version=${ISX_CI_VERSION:-$(gh release view -R "$repo" --json tagName -q .tagName)}
case "$(uname -m)" in
  x86_64) arch=amd64 ;;
  aarch64) arch=aarch64 ;;
  *) echo "No isx release for $(uname -m)" >&2; exit 1 ;;
esac
cli=incus-spawn-linux-$arch
proxy=isx-proxy-linux-$arch

dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT
gh release download "$version" -R "$repo" -D "$dir" -p SHA256SUMS -p "$cli" -p "$proxy"
for name in "$cli" "$proxy"; do
  # Exactly one line per binary, so a release listing it twice cannot pick which sum is checked.
  if [ "$(awk -v n="$name" '$2 == n || $2 == "*" n' "$dir/SHA256SUMS" | wc -l)" -ne 1 ]; then
    echo "The SHA256SUMS of isx $version does not list $name exactly once" >&2
    exit 1
  fi
done
(cd "$dir" && awk -v a="$cli" -v b="$proxy" '$2 == a || $2 == b || $2 == "*" a || $2 == "*" b' SHA256SUMS | sha256sum -c -)

mkdir -p "$HOME/.local/bin"
install -m 755 "$dir/$cli" "$HOME/.local/bin/isx"
install -m 755 "$dir/$proxy" "$HOME/.local/bin/isx-proxy"
if [ -n "${GITHUB_PATH:-}" ]; then
  echo "$HOME/.local/bin" >> "$GITHUB_PATH"
fi
"$HOME/.local/bin/isx" --version
