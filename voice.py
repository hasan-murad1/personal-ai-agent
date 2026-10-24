import collections
import queue
import time
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wavfile
import re
from faster_whisper import WhisperModel
from piper import PiperVoice
import keyboard
import term_colors as tc

SAMPLE_RATE = 16000
TEMP_AUDIO_FILE = "temp_recording.wav"

# None = Windows default input. Set a device number to force a specific microphone.
INPUT_DEVICE = None

# Push-to-talk settings
MIN_RECORDING_SECONDS = 0.3
MAX_RECORDING_SECONDS = 60  # audio after this is dropped, so a forgotten recording cannot grow RAM forever
SILENCE_PEAK_THRESHOLD = 300  # int16 peak below this means the microphone delivered almost nothing; set 0 to disable

# Session mode settings (automatic end-of-speech detection)
CHUNK_MS = 30
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_MS // 1000  # 480 samples per chunk
CALIBRATION_SECONDS = 1.0     # measure room noise at the start of a session
NOISE_MULTIPLIER = 3.0        # speech must be this many times louder than the room noise
MIN_SPEECH_RMS = 300          # never treat anything quieter than this as speech
START_SPEECH_SECONDS = 0.15   # this much continuous loud audio starts an utterance
PRE_ROLL_SECONDS = 0.3        # audio kept from just before speech started, so soft first sounds are not cut
END_SILENCE_SECONDS = 1.2     # this much quiet after speech ends the utterance
MAX_UTTERANCE_SECONDS = 30    # hard cap so noise can never keep recording forever
IDLE_TIMEOUT_SECONDS = 60     # end the session if nobody speaks for this long
QUEUE_MAX_CHUNKS = 200        # about 6 seconds; chunks are dropped if the loop falls behind, so RAM stays bounded
SESSION_END_KEY = "esc"

# Text-to-speech settings
MAX_SPOKEN_WORDS = 60        # longer replies are cut at a sentence boundary when spoken; the full text stays on screen
SPOKEN_CUT_NOTE = "The full answer is on the screen."

WHISPER_LANGUAGE = "en"
WHISPER_INITIAL_PROMPT = (
    "A user talks to a personal AI assistant about files, calendar events, email, "
    "the current time and date, news, prices, and who holds positions such as prime minister."
)

print(tc.dim("Loading Whisper model (this happens once)..."))
stt_model = WhisperModel("base", device="cpu", compute_type="int8")
print(tc.dim("Whisper model loaded.") + "\n")

print(tc.dim("Loading TTS voice (this happens once)..."))
tts_voice = PiperVoice.load("en_US-lessac-medium.onnx")
print(tc.dim("TTS voice loaded.") + "\n")


def _input_device_name():
    """Return a readable name of the microphone that will be used."""
    try:
        index = INPUT_DEVICE if INPUT_DEVICE is not None else sd.default.device[0]
        return f"{index}: {sd.query_devices(index)['name']}"
    except Exception:
        return "unknown device"


def _rms(chunk):
    """Return the root-mean-square loudness of an int16 audio chunk."""
    samples = chunk.astype(np.float64)
    return float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0


# ---------------------------------------------------------------- push-to-talk

def record_audio():
    """Record audio from the microphone using push-to-talk: Enter to start, Enter again to stop."""
    input("Press Enter to START recording...")
    print(tc.dim(f"Recording from [{_input_device_name()}]... press Enter again to STOP."))

    recorded_chunks = []
    max_frames = int(MAX_RECORDING_SECONDS * SAMPLE_RATE)
    state = {"frames": 0, "status_warned": False}

    def callback(indata, frames, time_info, status):
        if status and not state["status_warned"]:
            state["status_warned"] = True
            print(tc.warn(f"[Audio warning: {status}]"))
        if state["frames"] < max_frames:
            recorded_chunks.append(indata.copy())
            state["frames"] += frames

    try:
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                device=INPUT_DEVICE, callback=callback)
    except Exception as e:
        input()
        print(tc.bad(f"Could not open the microphone ({e}). Check INPUT_DEVICE in voice.py."))
        return None

    stream.start()
    input()
    stream.stop()
    stream.close()

    if not recorded_chunks:
        print(tc.warn("Recording finished (no audio captured)."))
        return None

    audio = np.concatenate(recorded_chunks, axis=0)
    duration = len(audio) / SAMPLE_RATE
    peak = int(np.max(np.abs(audio.astype(np.int32))))
    print(tc.dim(f"Recording finished ({duration:.1f} s, peak level {peak})."))

    if duration < MIN_RECORDING_SECONDS:
        print(tc.dim("(Recording too short)"))
        return None

    if peak < SILENCE_PEAK_THRESHOLD:
        print(tc.warn("(Microphone is almost silent - check Windows mic permission, mute, input volume, "
                      "or set INPUT_DEVICE)"))
        return None

    wavfile.write(TEMP_AUDIO_FILE, SAMPLE_RATE, audio)
    return TEMP_AUDIO_FILE


# ---------------------------------------------------------------- session mode

class EndpointDetector:
    """Decide from chunk loudness (RMS) when an utterance starts and when it has ended.

    feed() returns None while nothing has finished, or a finished utterance as a numpy array.
    """

    def __init__(self, threshold):
        self.threshold = threshold
        self.start_chunks = max(1, int(START_SPEECH_SECONDS * 1000 / CHUNK_MS))
        self.end_chunks = max(1, int(END_SILENCE_SECONDS * 1000 / CHUNK_MS))
        self.max_chunks = int(MAX_UTTERANCE_SECONDS * 1000 / CHUNK_MS)
        pre_roll_chunks = max(0, int(PRE_ROLL_SECONDS * 1000 / CHUNK_MS))
        self.pre_roll = collections.deque(maxlen=pre_roll_chunks + self.start_chunks)
        self.hit_max = False
        self.reset()

    def reset(self):
        """Forget the current utterance and wait for new speech."""
        self.in_speech = False
        self.loud_run = 0
        self.chunks = []
        self.quiet_run = 0
        self.pre_roll.clear()

    def feed(self, chunk):
        """Process one chunk and return a finished utterance, or None."""
        loud = _rms(chunk) >= self.threshold

        if not self.in_speech:
            self.pre_roll.append(chunk)
            self.loud_run = self.loud_run + 1 if loud else 0
            if self.loud_run >= self.start_chunks:
                self.in_speech = True
                self.chunks = list(self.pre_roll)
                self.quiet_run = 0
            return None

        self.chunks.append(chunk)
        self.quiet_run = 0 if loud else self.quiet_run + 1

        hit_max = len(self.chunks) >= self.max_chunks
        if self.quiet_run >= self.end_chunks or hit_max:
            speech = self.chunks[:-self.quiet_run] if self.quiet_run else self.chunks
            utterance = np.concatenate(speech)
            self.reset()
            self.hit_max = hit_max
            return utterance
        return None


def _open_session_stream(audio_queue, dropped):
    """Open a microphone stream whose callback only copies chunks into a bounded queue."""
    def callback(indata, frames, time_info, status):
        # Keep the audio thread light: copy the chunk and hand it over, nothing else.
        try:
            audio_queue.put_nowait(indata[:, 0].copy())
        except queue.Full:
            dropped["count"] += 1

    return sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", device=INPUT_DEVICE,
                          blocksize=CHUNK_SAMPLES, callback=callback)


def calibrate_session():
    """Measure the room noise for a moment and return the loudness threshold for speech, or None on failure."""
    audio_queue = queue.Queue(maxsize=QUEUE_MAX_CHUNKS)
    dropped = {"count": 0}
    print(tc.dim(f"Calibrating room noise for {CALIBRATION_SECONDS:.0f} s - please stay quiet..."))
    try:
        stream = _open_session_stream(audio_queue, dropped)
    except Exception as e:
        print(tc.bad(f"Could not open the microphone ({e}). Check INPUT_DEVICE in voice.py."))
        return None

    levels = []
    stream.start()
    try:
        end_time = time.monotonic() + CALIBRATION_SECONDS
        while time.monotonic() < end_time:
            try:
                levels.append(_rms(audio_queue.get(timeout=0.2)))
            except queue.Empty:
                pass
    finally:
        stream.stop()
        stream.close()

    noise = float(np.median(levels)) if levels else 0.0
    threshold = max(noise * NOISE_MULTIPLIER, MIN_SPEECH_RMS)
    print(tc.dim(f"Room noise RMS {noise:.0f} -> speech threshold {threshold:.0f}"))
    return threshold


def listen_for_utterance(threshold):
    """Listen until one utterance has ended, the session-end key is pressed, or nobody speaks for a while.

    Returns (status, file_path): ("speech", path), ("end_key", None), ("idle", None) or ("error", None).
    The microphone is only open inside this function, so it is off while the agent speaks or
    while the user types a confirmation.
    """
    audio_queue = queue.Queue(maxsize=QUEUE_MAX_CHUNKS)
    dropped = {"count": 0}
    detector = EndpointDetector(threshold)

    try:
        stream = _open_session_stream(audio_queue, dropped)
    except Exception as e:
        print(tc.bad(f"Could not open the microphone ({e}). Check INPUT_DEVICE in voice.py."))
        return "error", None

    print(tc.dim(f"Listening... (speak, or press {SESSION_END_KEY.upper()} to end the session)"))
    stream.start()
    utterance = None
    status = "idle"
    try:
        last_activity = time.monotonic()
        while True:
            if keyboard.is_pressed(SESSION_END_KEY):
                status = "end_key"
                break
            if not detector.in_speech and time.monotonic() - last_activity > IDLE_TIMEOUT_SECONDS:
                status = "idle"
                break
            try:
                chunk = audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            was_in_speech = detector.in_speech
            utterance = detector.feed(chunk)
            if detector.in_speech and not was_in_speech:
                print(tc.dim("  (hearing you...)"))
            if detector.in_speech:
                last_activity = time.monotonic()
            if utterance is not None:
                status = "speech"
                break
    finally:
        stream.stop()
        stream.close()

    if dropped["count"]:
        print(tc.warn(f"[Audio warning: {dropped['count']} chunks dropped]"))
    if status != "speech":
        return status, None

    peak = int(np.max(np.abs(utterance.astype(np.int32))))
    reason = ", max length reached" if detector.hit_max else ""
    print(tc.dim(f"  (got {len(utterance) / SAMPLE_RATE:.1f} s, peak {peak}{reason})"))
    wavfile.write(TEMP_AUDIO_FILE, SAMPLE_RATE, utterance)
    return "speech", TEMP_AUDIO_FILE


# ---------------------------------------------------------------- speech to text and text to speech

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
    print(tc.dim(f"[STT debug: language={info.language}, audio={info.duration:.1f} s]"))
    return text


def clean_text_for_speech(text):
    """Turn a markdown reply into plain sentences for Piper, which would otherwise read symbols literally.

    Removes headings, bullets, bold/italic markers, code ticks, links, URLs, emoji and a trailing
    "(Sources: ...)" note. The full reply, with sources, is still printed on screen.
    """
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)                # [label](url) -> label
    text = re.sub(r'https?://\S+', '', text)                           # bare URLs
    text = re.sub(r'\(\s*sources?\s*:[^)]*\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^\s*sources?\s*:.*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r'^\s{0,3}#{1,6}\s*', '', text, flags=re.MULTILINE)   # headings
    text = re.sub(r'^\s*(?:[*\-\u2022]|\d+[.)])\s+', '', text, flags=re.MULTILINE)  # bullets, numbered lists
    text = re.sub(r'(\*\*|__)(.*?)\1', r'\2', text)                   # bold
    text = re.sub(r'(?<!\w)[*_](\S(?:.*?\S)?)[*_](?!\w)', r'\1', text)  # italic
    text = text.replace('`', '').replace('*', '')
    text = re.sub(
        r'[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E0-\U0001F1FF]',
        '',
        text
    )
    # A heading or bullet line without final punctuation becomes its own sentence.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    lines = [line if line[-1] in '.!?:;' else line + '.' for line in lines]
    text = ' '.join(lines)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def shorten_for_speech(text, max_words=MAX_SPOKEN_WORDS):
    """Keep only the first whole sentences that fit in max_words, so long replies are not read out in full."""
    words = text.split()
    if len(words) <= max_words:
        return text
    sentences = re.split(r'(?<=[.!?])\s+', text)
    kept, count = [], 0
    for sentence in sentences:
        n = len(sentence.split())
        if kept and count + n > max_words:
            break
        kept.append(sentence)
        count += n
    if count > max_words:  # a single very long first sentence
        kept = [' '.join(words[:max_words]) + '...']
    while len(kept) > 1 and len(kept[-1].split()) <= 4:  # do not end on a dangling heading such as "Career at Microsoft."
        kept.pop()
    return ' '.join(kept) + ' ' + SPOKEN_CUT_NOTE


def speak_text(text):
    """Convert text to speech using Piper and play it, allowing the user to skip playback by pressing Space."""
    clean_text = shorten_for_speech(clean_text_for_speech(text))
    if not clean_text:
        return
    print(tc.dim(f"[Speaking - press SPACE to skip]: {clean_text}"))

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
            print(tc.dim("(Speech skipped)"))
            break
        time.sleep(0.05)