"""Video frames are captured as high-quality JPEG: about 3x faster than PNG in Chrome, and indistinguishable."""
import base64
import json

from jev_demofast.record.recorder import Recorder


class FakeSession:
    def __init__(self):
        self.calls = []

    class browser:
        pass

    def next_frame(self): pass


def test_frames_are_jpeg(tmp_path):
    s = FakeSession()
    calls = s.calls
    s.browser.call = staticmethod(lambda method, **params: calls.append((method, params)) or
                                  {"data": base64.b64encode(b"\xff\xd8 jpeg bytes").decode()})
    s.browser.evaluate = staticmethod(lambda js: None)
    rec = Recorder(str(tmp_path), s)
    rec.snap(1.0)
    rec.commit({"do": "open"})
    rec.save("a goal")
    method, params = calls[0]
    assert method == "Page.captureScreenshot" and params["format"] == "jpeg" and params["quality"] >= 90
    frames = json.loads((tmp_path / "frames.json").read_text())
    assert frames[0]["path"].endswith(".jpg") and (tmp_path / "frames" / "f0000.jpg").read_bytes().startswith(b"\xff\xd8")
