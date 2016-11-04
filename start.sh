#!/usr/bin/env bash
if [[ ! -d "./.venv" ]]; then
    echo "Creating new virtualenv..."
    python3.5 -m venv .venv
fi
# Source the virtualenv.
source .venv/bin/activate
PATH=.venv/bin/:/usr/bin:/usr/sbin:/bin:/sbin

# Git pull
BRANCH=`git rev-parse --abbrev-ref HEAD`
echo "Currently on branch $BRANCH".
echo "Pulling latest version..."
git pull || exit 1

echo "Updating requirements..."
pip install -U -r requirements.txt || exit 1
echo "Starting RethinkDB suspended..."
rethinkdb --http-port 8787 --cache-size auto &
sleep 2
echo "Starting Jokusoramame."
python run.py config.yml

echo "Bot has terminated, killing RethinkDB safely."
kill -INT $!
