#!/usr/bin/env bash

set -euo pipefail
# set -x

python3 -m venv imdb
source imdb/bin/activate
pip3 install Cinemagoer tabulate termcolor

echo "Please run: 'source imdb/bin/activate'"
