"""Standalone test: listens on the mic using Mantella's actual STT/VAD code
and config, prints live speech-detection events, and prints the final
transcription. Run from the Mantella source dir:
    ./MantellaEnv/bin/python test_stt.py
Speak a full sentence when it says "Listening...".
"""
import sys
import time
sys.path.insert(0, '.')

from src.config.config_loader import ConfigLoader
from src.stt.stt import Transcriber

MYGAMES = "/home/allan/Documents/My Games/Mantella"

config = ConfigLoader(MYGAMES)
print(f"audio_threshold={config.audio_threshold}  pause_threshold={config.pause_threshold}  stt_service={config.stt_service}")

stt = Transcriber(config)

print("Listening... SPEAK A FULL SENTENCE NOW")
stt.start_listening()

start = time.time()
last_state = None
while time.time() - start < 15:
    detected = stt._speech_detected
    if detected != last_state:
        print(f"[{time.time()-start:.2f}s] speech_detected={detected}")
        last_state = detected
    if stt._has_unconsumed_transcription:
        break
    time.sleep(0.05)

text = stt.get_latest_transcription(silence_timeout=0.5)
print(f"Final transcription: {text!r}")
stt.stop_listening()
