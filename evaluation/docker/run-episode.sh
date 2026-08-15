#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ "$#" -eq 0 ]; then
    printf '%s\n' "usage: $0 COMMAND [ARGUMENT ...]" >&2
    exit 64
fi

exec docker compose \
    --project-directory "$script_dir" \
    --file "$script_dir/compose.yaml" \
    run --rm --no-deps --no-TTY runner "$@"
