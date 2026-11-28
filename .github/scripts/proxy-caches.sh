#!/bin/bash
# Lists the files of the proxy's artifact caches with their sizes, one per line, sorted: the CI
# saves those caches only when this listing changed during the build. A run that only confirmed
# copies again is not saved, though the proxy records a confirmation as its sidecar's mtime, so
# the next run asks the repository again: a new full copy of a cache on every run would crowd the
# repository's cache quota.
cd "$HOME/.cache/incus-spawn" 2>/dev/null || exit 0
find maven-verified gradle-verified npm -type f ! -name '*.tmp' -printf '%p %s\n' 2>/dev/null | LC_ALL=C sort
