import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wavfile
import re
from faster_whisper import WhisperModel
from piper import PiperVoice
import keyboard
import time

SAMPLE_RATE = 16000
TEMP_AUDIO_FILE = "temp_recording.wav"

# None = Windows default input. Set a device number (from mic_scan.py) to force a specific microphone.
INPUT_DEVICE = None

MIN_RECORDING_SECONDS = 0.3
MAX_RECORDING_SECONDS = 60  # audio after this is dropped, so a forgotten recording cannot grow RAM forever
SILENCE_PEAK_THRESHOLD = 300  # int16 peak below this means the microphone delivered almost nothing; set 0 to disable

WHISPER_LANGUAGE = "en"
WHISPER_INITIAL_PROMPT = (
    "A user talks to a personal AI assistant about files, calendar events, email, "
    "the current time and date, news, prices, and who holds positions such as prime minister."
)

print("Loading Whisper model (this happens once)...")
stt_model = WhisperModel("base", device="cpu", compute_type="int8")
print("Whisper model loaded.\n")

print("Loading TTS voice (this happens once)...")
tts_voice = PiperVoice.load("en_US-lessac-medium.onnx")
print("TTS voice loaded.\n")


def _input_device_name():
    """Return a readable name of the microphone that will be used."""
    try:
        index = INPUT_DEVICE if INPUT_DEVICE is not None else sd.default.device[0]
        return f"{index}: {sd.query_devices(index)['name']}"
    except Exception:
        return "unknown device"


def record_audio():
    """Record audio from the microphone using push-to-talk: Enter to start, Enter again to stop."""
    input("Press Enter to START recording...")
    print(f"Recording from [{_input_device_name()}]... press Enter again to STOP.")

    recorded_chunks = []
    max_frames = int(MAX_RECORDING_SECONDS * SAMPLE_RATE)
    state = {"frames": 0, "status_warned": False}

    def callback(indata, frames, time_info, status):
        if status and not state["status_warned"]:
            state["status_warned"] = True
            print(f"[Audio warning: {status}]")
        if state["frames"] < max_frames:
            recorded_chunks.append(indata.copy())
            state["frames"] += frames

    try:
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                device=INPUT_DEVICE, callback=callback)
    except Exception as e:
        input()
        print(f"Could not open the microphone ({e}). Check INPUT_DEVICE in voice.py.")
        return None

    stream.start()
    input()
    stream.stop()
    stream.close()

    if not recorded_chunks:
        print("Recording finished (no audio captured).")
        return None

    audio = np.concatenate(recorded_chunks, axis=0)
    duration = len(audio) / SAMPLE_RATE
    peak = int(np.max(np.abs(audio.astype(np.int32))))
    print(f"Recording finished ({duration:.1f} s, peak level {peak}).")

    if duration < MIN_RECORDING_SECONDS:
        print("(Recording too short)")
        return None

    if peak < SILENCE_PEAK_THRESHOLD:
        print("(Microphone is almost silent - check Windows mic permission, mute, input volume, "
              "or run mic_scan.py to find the right INPUT_DEVICE)")
        return None

    wavfile.write(TEMP_AUDIO_FILE, SAMPLE_RATE, audio)
    return TEMP_AUDIO_FILE


def transcribe_audio(file_path):
    """Transcribe a recorded audio file to English text using Whisper."""
    if not file_path:
        return ""

    segments, info = stt_model.transcribe(
        file_path,
        language=WHISPER_LANGUAGE,
        initial_prompt=WHISPER_INITIAL_PROMPT,
    )
    text = " ".join(segment.text for segment in segments).strip()
    print(f"[STT debug: language={info.language}, audio={info.duration:.1f} s]")
    return text


def clean_text_for_speech(text):
    """Strip markdown formatting and emoji from text before sending it to the TTS engine, since Piper reads them literally."""
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(
        r'[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E0-\U0001F1FF]',
        '',
        text
    )
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def speak_text(text):
    """Convert text to speech using Piper and play it, allowing the user to skip playback by pressing Space."""
    clean_text = clean_text_for_speech(text)
    if not clean_text:
        return
    print(f"[Speaking - press SPACE to skip]: {clean_text}")

    audio_chunks = []
    for audio_chunk in tts_voice.synthesize(clean_text):
        audio_chunks.append(audio_chunk.audio_int16_array)

    if not audio_chunks:
        return

    full_audio = np.concatenate(audio_chunks)
    sd.play(full_audio, samplerate=tts_voice.config.sample_rate)

    while sd.get_stream() and sd.get_stream().active:
        if keyboard.is_pressed('space'):
            sd.stop()
            print("(Speech skipped)")
            break
        time.sleep(0.05)