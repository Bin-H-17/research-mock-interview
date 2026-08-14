"""语音可插拔模块离线测试（无麦克风、无第三方语音库也可跑）。

验证：
1) mock 双工离线闭环（listen 按脚本逐句返回，/finish 结束；speak 打印标记）
2) DuplexVoice.from_config(mock) 工厂
3) 真实后端「缺失依赖 / 缺失配置」守卫：构造即抛 RuntimeError，证明链路已正确接线
"""
import io
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from voice_io import (
    MockSTT, MockTTS, DuplexVoice, VoskSTT, WhisperSTT, Pyttsx3TTS, EdgeTTSTTS,
)


def _lib_missing(name: str) -> bool:
    try:
        __import__(name)
        return False
    except ImportError:
        return True


def test_mock_duplex():
    v = DuplexVoice.from_config({"voice": {"backend": "mock"}})
    assert isinstance(v.stt, MockSTT) and isinstance(v.tts, MockTTS)

    # speak 打印到 stdout，带标记
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        v.speak("你好")
    finally:
        sys.stdout = old
    assert "[VOICE·TTS]" in buf.getvalue()

    # listen 按脚本逐句返回，末尾 /finish
    out = []
    for _ in range(5):
        out.append(v.listen())
    assert "/finish" in out
    assert out[0].startswith("我在这个项目里")


def test_real_provider_guards():
    # VoskSTT 缺 model_path 必抛（与 vosk 是否安装无关）
    try:
        VoskSTT({})
        raise AssertionError("VoskSTT 应在缺 model_path 时抛 RuntimeError")
    except RuntimeError:
        pass

    # 其余仅在对应库缺失时验证守卫（环境已装则跳过，避免误报）
    if _lib_missing("faster_whisper"):
        try:
            WhisperSTT({})
            raise AssertionError("WhisperSTT 应在缺 faster_whisper 时抛 RuntimeError")
        except RuntimeError:
            pass
    if _lib_missing("pyttsx3"):
        try:
            Pyttsx3TTS({})
            raise AssertionError("Pyttsx3TTS 应在缺 pyttsx3 时抛 RuntimeError")
        except RuntimeError:
            pass
    if _lib_missing("edge_tts"):
        try:
            EdgeTTSTTS({})
            raise AssertionError("EdgeTTSTTS 应在缺 edge_tts 时抛 RuntimeError")
        except RuntimeError:
            pass


if __name__ == "__main__":
    test_mock_duplex()
    test_real_provider_guards()
    print("ALL VOICE TESTS PASSED")
