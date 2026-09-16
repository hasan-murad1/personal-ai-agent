import sounddevice as sd
import sounddevice as sd_playback
import numpy as np
import scipy.io.wavfile as wavfile
import re
from faster_whisper import WhisperModel
from piper import PiperVoice

SAMPLE_RATE = 16000
TEMP_AUDIO_FILE = "temp_recording.wav"

print("Loading Whisper model (this happens once)...")
stt_model = WhisperModel("tiny", device="cpu", compute_type="int8")
print("Whisper model loaded.\n")

print("Loading TTS voice (this happens once)...")
tts_voice = PiperVoice.load("en_US-lessac-medium.onnx")
print("TTS voice loaded.\n")


def record_audio():
    input("Press Enter to START recording...")
    print("Recording... press Enter again to STOP.")

    recorded_chunks = []

    def callback(indata, frames, time_info, status):
        recorded_chunks.append(indata.copy())

    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=callback)
    stream.start()

    input()

    stream.stop()
    stream.close()

    audio = np.concatenate(recorded_chunks, axis=0)
    wavfile.write(TEMP_AUDIO_FILE, SAMPLE_RATE, audio)
    print("Recording finished.")
    return TEMP_AUDIO_FILE


def transcribe_audio(file_path):
    segments, info = stt_model.transcribe(
        file_path,
        initial_prompt="This is a conversation about an AI agent with a sandbox folder, workspace, files, and automation tools."
    )
    text = " ".join(segment.text for segment in segments)
    return text.strip()

def clean_text_for_speech(text):
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
    clean_text = clean_text_for_speech(text)
    print(f"[Speaking]: {clean_text}")

    audio_chunks = []
    for audio_chunk in tts_voice.synthesize(clean_text):
        audio_chunks.append(audio_chunk.audio_int16_array)

    full_audio = np.concatenate(audio_chunks)
    sd_playback.play(full_audio, samplerate=tts_voice.config.sample_rate)
    sd_playback.wait()


if __name__ == "__main__":
    audio_file = record_audio()
    text = transcribe_audio(audio_file)
    print(f"\nTranscribed text: {text}")

    speak_text(f"You said: {text}")