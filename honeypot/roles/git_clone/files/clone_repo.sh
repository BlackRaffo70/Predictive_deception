#!/bin/bash
REPO_DIR="/home/vagrant/predictive_deception"
REPO_URL="https://github.com/BlackRaffo70/Predictive_deception"

if [ ! -d "$REPO_DIR/.git" ]; then
    git clone "$REPO_URL" "$REPO_DIR"
else
    cd "$REPO_DIR"
    git pull
fi
