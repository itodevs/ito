from app.main import descriptor

def test_descriptor():
    result = descriptor()
    assert result["type"] == "robot-driver"
    assert result["video"] == {"kind": "mono", "encoding": "vp8"}
