from pathlib import Path
import pytest
from app.scene import load_ply, split_scene

def test_ply_validation_and_chunks(tmp_path: Path):
    data = b"ply\nformat ascii 1.0\nend_header\n" + b"x" * 25
    path = tmp_path / "scene.ply"; path.write_bytes(data)
    chunks = split_scene(load_ply(str(path)), 10)
    assert b"".join(chunks) == data
    assert all(len(chunk) <= 10 for chunk in chunks)

def test_invalid_ply(tmp_path: Path):
    path = tmp_path / "bad.ply"; path.write_text("nope")
    with pytest.raises(ValueError): load_ply(str(path))
