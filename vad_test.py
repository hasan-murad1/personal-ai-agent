import queue
import time
import numpy as np

SAMPLE_RATE = 16000
CHUNK_MS = 30
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_MS // 1000  # 480 samples per chunk

CALIBRATION_SECONDS = 1.0     # measure room noise before listening
NOISE_MULTIPLIER = 3.0        # speech must be this many times louder than the room noise
MIN_SPEECH_RMS = 300          # never treat anything quieter than this as speech
START_SPEECH_SECONDS = 0.15   # this much continuous loud audio starts an utterance
END_SILENCE_SECONDS = 1.2     # this much quiet after speech ends the utterance
MAX_UTTERANCE_SECONDS = 30    # hard cap so noise can never keep recording forever
IDLE_TIMEOUT_SECONDS = 60     # stop listening if nobody speaks for this long
QUEUE_MAX_CHUNKS = 200        # about 6 seconds of audio; older chunks are dropped if the loop falls behind
UTTERANCES_TO_CAPTURE = 3


class EndpointDetector:
    """Decide from chunk loudness (RMS) when an utterance starts and when it has ended.

    feed() returns None while nothing has finished, or a finished utterance as a numpy array.
    """

    def __init__(self, threshold):
        self.threshold = threshold
        self.start_chunks = max(1, int(START_SPEECH_SECONDS * 1000 / CHUNK_MS))
        self.end_chunks = max(1, int(END_SILENCE_SECONDS * 1000 / CHUNK_MS))
        self.max_chunks = int(MAX_UTTERANCE_SECONDS * 1000 / CHUNK_MS)
        self.reset()

    def reset(self):
        """Forget the current utterance and wait for new speech."""
        self.in_speech = False
        self.loud_run = []
        self.chunks = []
        self.quiet_run = 0
        self.hit_max = False

    def feed(self, chunk):
        """Process one chunk and return a finished utterance, or None."""
        loud = rms(chunk) >= self.threshold

        if not self.in_speech:
            if loud:
                self.loud_run.append(chunk)
                if len(self.loud_run) >= self.start_chunks:
                    self.in_speech = True
                    self.chunks = list(self.loud_run)
                    self.loud_run = []
                    self.quiet_run = 0
            else:
                self.loud_run = []
            return None

        self.chunks.append(chunk)
        self.quiet_run = 0 if loud else self.quiet_run + 1

        if self.quiet_run >= self.end_chunks or len(self.chunks) >= self.max_chunks:
            self.hit_max = len(self.chunks) >= self.max_chunks
            speech = self.chunks[:-self.quiet_run] if self.quiet_run else self.chunks
            utterance = np.concatenate(speech)
            hit_max = self.hit_max
            self.reset()
            self.hit_max = hit_max
            return utterance
        return None


def rms(chunk):
    """Return the root-mean-square loudness of an int16 audio chunk."""
    samples = chunk.astype(np.float64)
    return float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0


def main():
    """Listen continuously, print each detected utterance, and report the CPU used while listening."""
    import sounddevice as sd
    import keyboard

    audio_queue = queue.Queue(maxsize=QUEUE_MAX_CHUNKS)
    dropped = {"count": 0}

    def callback(indata, frames, time_info, status):
        # Keep the audio thread light: copy the chunk and hand it over, nothing else.
        try:
            audio_queue.put_nowait(indata[:, 0].copy())
        except queue.Full:
            dropped["count"] += 1

    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                            blocksize=CHUNK_SAMPLES, callback=callback)
    stream.start()
    try:
        print(f"Calibrating room noise for {CALIBRATION_SECONDS:.0f} s - please stay quiet...")
        noise_levels = []
        calib_end = time.monotonic() + CALIBRATION_SECONDS
        while time.monotonic() < calib_end:
            try:
                noise_levels.append(rms(audio_queue.get(timeout=0.5)))
            except queue.Empty:
                pass
        noise = float(np.median(noise_levels)) if noise_levels else 0.0
        threshold = max(noise * NOISE_MULTIPLIER, MIN_SPEECH_RMS)
        print(f"Room noise RMS: {noise:.0f} -> speech threshold RMS: {threshold:.0f}")
        print(f"Say {UTTERANCES_TO_CAPTURE} short sentences with a pause after each. Press Esc to stop early.\n")

        detector = EndpointDetector(threshold)
        captured = 0
        last_activity = time.monotonic()
        cpu_start, wall_start = time.process_time(), time.monotonic()

        while captured < UTTERANCES_TO_CAPTURE:
            if keyboard.is_pressed("esc"):
                print("Esc pressed - stopping.")
                break
            if not detector.in_speech and time.monotonic() - last_activity > IDLE_TIMEOUT_SECONDS:
                print(f"No speech for {IDLE_TIMEOUT_SECONDS} s - stopping.")
                break
            try:
                chunk = audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            was_in_speech = detector.in_speech
            utterance = detector.feed(chunk)
            if detector.in_speech and not was_in_speech:
                print("  speech started...")
            if detector.in_speech:
                last_activity = time.monotonic()
            if utterance is not None:
                captured += 1
                last_activity = time.monotonic()
                peak = int(np.max(np.abs(utterance.astype(np.int32))))
                reason = "max length reached" if detector.hit_max else "silence detected"
                print(f"  utterance {captured}: {len(utterance) / SAMPLE_RATE:.1f} s, peak {peak}, ended by {reason}")

        cpu_used = time.process_time() - cpu_start
        wall_used = time.monotonic() - wall_start
    finally:
        stream.stop()
        stream.close()

    if wall_used > 0:
        print(f"\nListening time: {wall_used:.1f} s, CPU time used: {cpu_used:.2f} s "
              f"(about {100 * cpu_used / wall_used:.1f}% of one core)")
    print(f"Chunks dropped because the loop fell behind: {dropped['count']}")


if __name__ == "__main__":
    main()