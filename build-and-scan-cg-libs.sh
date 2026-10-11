#!/bin/bash
set -x

docker pull cgr.dev/chainguard-private/python:3.14-dev

docker build --no-cache --progress=plain \
  --secret id=pip_conf,src=pip.conf \
  --secret id=netrc,src=.netrc \
  -t demo-chainguard-python:cg-libs . -f cg-libs.Dockerfile

{ set +x; } 2>/dev/null
echo "Paused — press Enter to scan with grype"
read -r
set -x

grype --by-cve demo-chainguard-python:cg-libs