"""可插拔语音交互：STT（语音识别） + TTS（语音合成） + 双工编排。

设计原则（对齐 src/llm_backend.py 的「可插拔」模式）：
- 统一抽象：STTProvider.listen() -> str，TTSProvider.speak(text)
- mock：纯标准库，离线零依赖，用于 demo / 无麦无网环境；证明语音编排链路可闭环
- 真实后端全部「懒加载」：仅当选择该 backend 才 import 对应第三方库，
  保证核心运行时仍是零硬性第三方依赖（不破坏隐私铁律 / 离线铁律）
- 真实 STT：vosk（轻量离线，~50MB 模型，嵌入式友好）/ whisper（faster-whisper，离线高精度）
- 真实 TTS：pyttsx3（离线系统语音）/ edge-tts（微软神经语音，需网络，音质佳）
- 麦克风采集用 sounddevice（懒加载）写入临时 WAV，再交给 STT 引擎识别
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
import wave


class STTProvider:
    """语音识别抽象：把声音变成文字。"""

    def listen(self, timeout: float | None = None) -> str:
        raise NotImplementedError

    @staticmethod
    def from_config(cfg: dict | None = None):
        v = ((cfg or {}).get("voice") or {}) if isinstance(cfg, dict) else {}
        stt_cfg = v.get("stt") or {}
        backend = (stt_cfg.get("backend") or v.get("backend") or "mock").lower()
        if backend in ("mock", "offline_mock"):
            return MockSTT(stt_cfg.get("mock") or {})
        if backend == "vosk":
            return VoskSTT(stt_cfg.get("vosk") or {})
        if backend in ("whisper", "faster-whisper"):
            return WhisperSTT(stt_cfg.get("whisper") or {})
        raise ValueError(f"未知 STT backend: {backend!r}（可选 mock|vosk|whisper）")


class MockSTT(STTProvider):
    """离线语音识别占位：按预设脚本逐句「念出」候选人回答，末尾返回 /finish 结束。"""

    def __init__(self, opts: dict | None = None):
        self.opts = opts or {}
        self.script = list(
            self.opts.get(
                "script",
                [
                    "我在这个项目里主要负责特征工程和模型训练，用的 PyTorch 和 DGL。",
                    "整体效果还行吧，具体指标我记不太清了。",
                    "/finish",
                ],
            )
        )
        self.idx = 0

    def listen(self, timeout: float | None = None) -> str:
        if self.idx >= len(self.script):
            return "/finish"
        line = self.script[self.idx]
        self.idx += 1
        return line


class VoskSTT(STTProvider):
    """离线 STT（Kaldi/Vosk）。需 pip install vosk + 下载语言模型目录。"""

    def __init__(self, opts: dict | None = None):
        o = opts or {}
        self.model_path = o.get("model_path") or os.environ.get("VOSK_MODEL_PATH", "")
        self.rate = int(o.get("rate", 16000))
        self.phrase_timeout = float(o.get("phrase_timeout", 3.0))
        self.language = o.get("language", "cn")
        if not self.model_path:
            raise RuntimeError(
                "VoskSTT 需要 model_path（离线模型目录）。请在配置 voice.stt.vosk.model_path "
                "或环境变量 VOSK_MODEL_PATH 指定，例如 vosk-model-small-cn-0.22。"
            )
        try:
            from vosk import Model, KaldiRecognizer  # 懒加载
        except ImportError:
            raise RuntimeError(
                "未安装 vosk。请先 `pip install vosk` 并下载对应语言模型（如 vosk-model-small-cn-0.22）。"
            )
        if not os.path.isdir(self.model_path):
            raise RuntimeError(f"Vosk 模型目录不存在：{self.model_path}")
        self._Model = Model
        self._Recognizer = KaldiRecognizer

    def listen(self, timeout: float | None = None) -> str:
        wav = _capture_mic_wav(self.rate, seconds=self.phrase_timeout)
        rec = self._Recognizer(self._Model(self.model_path), self.rate)
        rec.AcceptWaveFile(wav)
        try:
            res = json.loads(rec.Result())
        except Exception:
            return ""
        return (res.get("text") or "").strip()


class WhisperSTT(STTProvider):
    """离线高精度 STT（faster-whisper，CTranslate2）。需 pip install faster-whisper。"""

    def __init__(self, opts: dict | None = None):
        o = opts or {}
        self.model_size = o.get("model_size", "base")
        self.device = o.get("device", "cpu")
        self.compute_type = o.get("compute_type", "int8")
        self.language = o.get("language", "zh")
        try:
            from faster_whisper import WhisperModel  # 懒加载
        except ImportError:
            raise RuntimeError(
                "未安装 faster-whisper。请先 `pip install faster-whisper`"
                "（GPU 可用时可选安装 CUDA / onnxruntime-gpu 提速）。"
            )
        self._WhisperModel = WhisperModel

    def listen(self, timeout: float | None = None) -> str:
        wav = _capture_mic_wav(16000, seconds=float(timeout or 5.0))
        model = self._WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        segments, _ = model.transcribe(wav, language=self.language)
        return "".join(getattr(s, "text", "") for s in segments).strip()


class TTSProvider:
    """语音合成抽象：把文字变成声音。"""

    def speak(self, text: str) -> None:
        raise NotImplementedError

    @staticmethod
    def from_config(cfg: dict | None = None):
        v = ((cfg or {}).get("voice") or {}) if isinstance(cfg, dict) else {}
        tts_cfg = v.get("tts") or {}
        backend = (tts_cfg.get("backend") or v.get("backend") or "mock").lower()
        if backend in ("mock", "offline_mock"):
            return MockTTS(tts_cfg.get("mock") or {})
        if backend == "pyttsx3":
            return Pyttsx3TTS(tts_cfg.get("pyttsx3") or {})
        if backend in ("edge", "edge-tts"):
            return EdgeTTSTTS(tts_cfg.get("edge") or {})
        raise ValueError(f"未知 TTS backend: {backend!r}（可选 mock|pyttsx3|edge）")


class MockTTS(TTSProvider):
    """离线语音合成占位：打印到 stdout（带标记），不依赖任何发声设备。"""

    def __init__(self, opts: dict | None = None):
        self.opts = opts or {}
        self.prefix = self.opts.get("prefix", "[VOICE·TTS]")

    def speak(self, text: str) -> None:
        print(f"{self.prefix} {text}", flush=True)


class Pyttsx3TTS(TTSProvider):
    """离线 TTS（系统原生语音引擎，Windows SAPI / macOS NSSpeech / Linux espeak）。"""

    def __init__(self, opts: dict | None = None):
        o = opts or {}
        try:
            import pyttsx3  # 懒加载
        except ImportError:
            raise RuntimeError("未安装 pyttsx3。请先 `pip install pyttsx3`（离线系统语音）。")
        self.engine = pyttsx3.init()
        if o.get("rate"):
            self.engine.setProperty("rate", int(o["rate"]))
        if o.get("volume") is not None:
            self.engine.setProperty("volume", float(o["volume"]))
        if o.get("voice"):
            self.engine.setProperty("voice", o["voice"])

    def speak(self, text: str) -> None:
        self.engine.say(text)
        self.engine.runAndWait()


class EdgeTTSTTS(TTSProvider):
    """云端神经 TTS（微软 Edge 语音，需网络，音质佳）。密钥/额度由 Edge 服务侧管理，无需 BYOK。"""

    def __init__(self, opts: dict | None = None):
        o = opts or {}
        try:
            import edge_tts  # 懒加载
        except ImportError:
            raise RuntimeError("未安装 edge-tts。请先 `pip install edge-tts`（需网络）。")
        self._edge = edge_tts
        self.voice = o.get("voice", "zh-CN-XiaoxiaoNeural")
        self.rate = o.get("rate", "+0%")
        self.volume = o.get("volume", "+0%")

    def speak(self, text: str) -> None:
        import asyncio

        async def _gen():
            comm = self._edge.Communicate(text, self.voice, rate=self.rate, volume=self.volume)
            fd, path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            with open(path, "wb") as f:
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
            # 优先尝试用 playsound 直接播放；否则告知已生成文件
            try:
                from playsound import playsound  # 懒加载

                playsound(path)
            except ImportError:
                print(f"[edge-tts] 已生成语音文件：{path}（安装 playsound 后可自动播放）", flush=True)
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass

        asyncio.run(_gen())


class DuplexVoice:
    """双工语音：组合一个 STT 与一个 TTS，对外提供 speak / listen。"""

    def __init__(self, stt: STTProvider, tts: TTSProvider):
        self.stt = stt
        self.tts = tts

    def speak(self, text: str) -> None:
        self.tts.speak(text)

    def listen(self, timeout: float | None = None) -> str:
        return self.stt.listen(timeout)

    @staticmethod
    def from_config(cfg: dict | None = None):
        stt = STTProvider.from_config(cfg)
        tts = TTSProvider.from_config(cfg)
        return DuplexVoice(stt, tts)


def _capture_mic_wav(rate: int = 16000, seconds: float = 3.0, channels: int = 1) -> str:
    """采集麦克风音频，写入临时 WAV 并返回路径（依赖 sounddevice + numpy，懒加载）。"""
    try:
        import sounddevice as sd  # 懒加载
        import numpy as np  # 懒加载
    except ImportError:
        raise RuntimeError(
            "麦克风采集需要 sounddevice + numpy。请先 `pip install sounddevice numpy`"
            "（仅在启用真实语音识别时需要，mock 模式无需）。"
        )
    frames = int(seconds * rate)
    data = sd.rec(frames, samplerate=rate, channels=channels, dtype="int16")
    sd.wait()
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.asarray(data).tobytes())
    return path


if __name__ == "__main__":
    # 自检：mock 双工离线跑通
    v = DuplexVoice.from_config({"voice": {"backend": "mock"}})
    print("mock 语音自检：")
    v.speak("你好，我是考官。")
    said = v.listen()
    print("mock 识别到：", said)
