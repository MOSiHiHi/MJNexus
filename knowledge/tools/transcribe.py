import sys, json, time, subprocess
import numpy as np
from faster_whisper import WhisperModel

# Decode with ffmpeg directly (avoids PyAV version issues): 16 kHz mono float32.
def load_audio(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)

audio, out, size = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "small")
t0 = time.time()
model = WhisperModel(size, device="cpu", compute_type="int8")
segs, info = model.transcribe(load_audio(audio), vad_filter=True)
rows = [{"start": round(s.start, 1), "end": round(s.end, 1), "text": s.text.strip()} for s in segs]
json.dump({"language": info.language, "prob": round(info.language_probability, 2), "model": size,
           "seconds": round(time.time() - t0, 1), "segments": rows}, open(out, "w"), ensure_ascii=False, indent=1)
print(info.language, round(info.language_probability, 2), len(rows), "segments in", round(time.time() - t0, 1), "s")
