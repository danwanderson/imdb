#!/usr/bin/env bash

set -euo pipefail
# set -x

python3 -m venv .venv
source .venv/bin/activate
pip3 install tabulate termcolor # Cinemagoer 
pip3 install git+https://github.com/cinemagoer/cinemagoer
