#!/bin/bash
set -x

docker pull registry.access.redhat.com/ubi8/python-312

docker build -t demo-chainguard-python:ubi . -f ubi.Dockerfile

{ set +x; } 2>/dev/null
echo "Paused — press Enter to scan with grype"
read -r
set -x

grype --by-cve demo-chainguard-python:ubi