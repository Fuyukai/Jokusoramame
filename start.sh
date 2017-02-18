#!/usr/bin/env bash

pipenv &> /dev/null || { echo "You must have 'pipenv' installed to boot this bot."; exit; }

# Git pull
BRANCH=`git rev-parse --abbrev-ref HEAD`
echo "Currently on branch $BRANCH".
echo "Pulling latest version..."
git pull || exit 1

echo "Updating requirements..."
pipenv --three install || exit 1;
echo "Starting Jokusoramame."
pipenv run python3.6 run.py config.yml
