#!/usr/bin/env bash
set -euo pipefail

apt-get update
apt-get install -y ffmpeg

python -m pip install --upgrade pip
pip install -r requirements.txt
