import os
import tempfile

# Keep tests away from the real database and uploads folder.
os.environ.setdefault("RAINREADY_DATA", tempfile.mkdtemp(prefix="rainready-test-"))
os.environ.setdefault("RAINREADY_DB", ":memory:")
