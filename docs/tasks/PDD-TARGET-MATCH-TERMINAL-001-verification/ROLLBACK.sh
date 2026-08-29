#!/usr/bin/env bash
git apply -R --check --unidiff-zero --whitespace=nowarn DIFF_FILE.patch
git apply -R --unidiff-zero --whitespace=nowarn DIFF_FILE.patch
