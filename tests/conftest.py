"""Shared test setup. Tests cover AIden's pure logic and run without any services."""
import os

# Deterministic defaults for the modules' environment-driven settings
os.environ.setdefault("AIDEN_PROFILES", "cpu,npu,intel-gpu")
os.environ.setdefault("AIDEN_SHOW_ROUTE", "true")
os.environ.setdefault("VAULT_DIR", "/nonexistent-vault")
