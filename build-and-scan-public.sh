#!/bin/bash
set -x

docker pull python:latest

docker build -t demo-chainguard-python:public . -f Dockerfile

{ set +x; } 2>/dev/null
echo "Paused — press Enter to scan with grype"
read -r
set -x

grype --by-cve demo-chainguard-python:public