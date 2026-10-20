import sounddevice as sd
import numpy as np

SAMPLE_RATE = 16000
SECONDS = 3

print("Input devices (the one marked '>' is the default input):")
print(sd.query_devices())
print()

default_input = sd.default.device[0]
print(f"Default input device index: {default_input}")
print(f"Default input device name: {sd.query_devices(default_input)['name']}")
print()

input(f"Press Enter, then speak normally for {SECONDS} seconds...")
print("Recording...")
audio = sd.rec(int(SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
sd.wait()
print("Recording finished.\n")

samples = audio.astype(np.float64).flatten()
peak = int(np.max(np.abs(samples)))
rms = float(np.sqrt(np.mean(samples ** 2)))

print(f"Peak level: {peak} (max possible 32767)")
print(f"RMS level:  {rms:.0f}")

if peak < 300:
    print("Verdict: almost silent. Likely wrong microphone, muted mic, or blocked mic permission.")
elif peak < 2000:
    print("Verdict: very quiet. Raise the microphone volume in Windows sound settings.")
else:
    print("Verdict: level looks normal for speech.")

print("\nPlaying the recording back so you can hear it...")
sd.play(audio, samplerate=SAMPLE_RATE)
sd.wait()
print("Done.")