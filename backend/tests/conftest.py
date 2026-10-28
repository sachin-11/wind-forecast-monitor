import os

# Tests never hit the network: use the deterministic synthetic source.
os.environ.setdefault("DATA_SOURCE", "sample")
