"""Exercise an existing lock under an open-or-create race without weakening safety."""
import os
from scholar_workflow.research.store import storage_lock


def test_existing_lock_survives_create_race(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    lock = tmp_path / ".recommendations.lock"
    lock.touch(mode=0o600)
    real_open = os.open
    def race_open(path, flags, *args, **kwargs):
        if path == lock.name and flags & os.O_CREAT and not flags & os.O_EXCL:
            raise FileNotFoundError(2, "Synthetic open-or-create race", path)
        return real_open(path, flags, *args, **kwargs)
    fd = real_open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        monkeypatch.setattr(os, "open", race_open)
        with storage_lock(fd, name=lock.name) as held:
            assert os.fstat(held).st_ino == lock.stat().st_ino
            assert os.fstat(held).st_mode & 0o777 == 0o600
    finally:
        os.close(fd)
