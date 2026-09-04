#!/bin/bash
set -x

docker pull cgr.dev/chainguard/python:latest-dev

docker build  -t demo-chainguard-python:cg . -f cg.Dockerfile

{ set +x; } 2>/dev/null
echo "Paused — press Enter to scan with grype"
read -r
set -x

grype --by-cve demo-chainguard-python:cg