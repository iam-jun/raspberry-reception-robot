#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y \
  build-essential \
  cmake \
  git \
  pkg-config \
  libasound2-dev \
  portaudio19-dev \
  libsndfile1-dev \
  python3 \
  python3-venv \
  python3-pip

echo "Bootstrap complete."
echo "Optional audio device checks:"
echo "  arecord -l"
echo "  aplay -l"

