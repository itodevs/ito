from app.main import descriptor

def test_descriptor():
    result = descriptor()
    assert result["type"] == "visual-processor"
    assert result["scene"]["format"] == "ply"
