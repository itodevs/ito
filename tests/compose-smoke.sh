#!/bin/sh
set -eu
VIDEO_FILE=${VIDEO_FILE:-/tmp/ito-video.mp4} SPLAT_FILE=${SPLAT_FILE:-/tmp/ito-scene.ply} docker compose config >/dev/null
echo 'Compose configuration is valid.'
