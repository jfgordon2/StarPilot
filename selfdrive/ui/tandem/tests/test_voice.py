"""Voice typing: the worker's audio and word handling (speech.py), the session that follows it (voice.py), and the mic key.

The model itself needs the 75 MB download, so it isn't run here; speech.py --file runs it on a recording."""
import json
import sys
import threading
import time

import numpy as np
import pytest

from openpilot.selfdrive.ui.tandem import keyboard as K, speech, voice


# ---- speech.py ----

def test_level_maps_quiet_to_zero_and_loud_to_one():
  assert speech.level(np.zeros(800, np.float32)) == 0.0
  assert speech.level(np.full(800, 0.5, np.float32)) == 1.0
  assert 0.2 < speech.level(np.full(800, 0.01, np.float32)) < 0.4          # -40 dB


def _feed(ends, levels):
  for value in levels:
    if reason := ends.add(value):
      return reason
  return None


def test_listening_ends_after_a_pause_once_someone_spoke():
  ends = speech.Endpointer(block_s=0.05)
  assert _feed(ends, [0.0] * 20 + [0.5] * 20) is None            # quiet, then talking
  assert _feed(ends, [0.0] * 29) is None                          # a short pause between words
  assert ends.add(0.0) == "pause"                                 # 1.5 s of quiet


def test_listening_gives_up_without_speech_and_has_a_limit():
  assert _feed(speech.Endpointer(block_s=0.05), [0.0] * 200) == "no_speech"
  assert _feed(speech.Endpointer(block_s=0.05), [0.5] * 400) == "max"


def test_spectrogram_is_whispers_shape():
  filters = speech.mel_filters()
  assert filters.shape == (80, 201) and filters.min() >= 0
  tone = (0.3 * np.sin(2 * np.pi * 440 * np.arange(32000) / 16000)).astype(np.float32)
  spec = speech.log_mel(tone)
  assert spec.shape == (1, 80, 3000) and spec.dtype == np.float32
  assert spec.max() - spec.min() <= 2.0 + 1e-6                    # Whisper clips to 8 decades, scaled by 4


def test_vocab_decodes_bytes_and_finds_the_special_tokens(tmp_path):
  import base64
  pieces = [b"hard", b"ware", b" store", "é".encode()]
  (tmp_path / "v.tiktoken").write_text("".join(f"{base64.b64encode(p).decode()} {i}\n" for i, p in enumerate(pieces)))
  vocab = speech.Vocab(tmp_path / "v.tiktoken")
  assert (vocab.eot, vocab.sot) == (4, 5)
  assert vocab.no_timestamps == 4 + 106                           # 50362 with GPT-2's 50256 pieces
  assert vocab.decode([0, 1, 2, vocab.eot, vocab.sot]) == "hardware store"
  assert vocab.decode([3]) == "é"


def test_clean_drops_whisper_habits():
  assert speech.clean(" Hardware store.") == "Hardware store"
  assert speech.clean("Thank you.") == ""
  assert speech.clean("you") == ""
  assert speech.clean("1 Main St. Springfield") == "1 Main St. Springfield"


def test_record_stops_on_a_pause_and_on_stop(capsys):
  def stream_of(levels):
    class Stream:
      def __init__(self, callback):
        self._callback = callback

      def __enter__(self):
        def run():
          for amp in levels:
            self._callback(np.full((speech.BLOCK, 1), amp, np.float32), speech.BLOCK, None, None)
        threading.Thread(target=run, daemon=True).start()
        return self

      def __exit__(self, *_):
        return False
    return Stream

  samples = speech.record(threading.Event(), stream_of([0.0] * 5 + [0.3] * 10 + [0.0] * 40))
  assert samples is not None and samples.size == speech.BLOCK * 45    # stopped 1.5 s into the pause
  lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
  assert lines[0] == {"state": "listening"} and all("level" in line for line in lines[1:])

  stop = threading.Event()
  stop.set()
  assert speech.record(stop, stream_of([0.3] * 10)).size == 0

  def broken(callback):
    raise OSError("no device")
  assert speech.record(threading.Event(), broken) is None


# ---- voice.py ----

def _worker(*lines, linger=0.0):
  script = "import json,time\n" + "".join(f"print({line!r}, flush=True)\ntime.sleep(0.02)\n" for line in lines)
  return [sys.executable, "-c", script + f"time.sleep({linger})\n"]


def _until(session, done, timeout=5.0):
  end = time.monotonic() + timeout
  while time.monotonic() < end:
    session.update()
    if done():
      return True
    time.sleep(0.02)
  return False


@pytest.fixture
def ready(monkeypatch):
  monkeypatch.setattr(speech, "model_ready", lambda folder=None: True)


def test_session_follows_the_worker_to_the_words(ready):
  heard = []
  lines = [json.dumps({"state": "listening"}), json.dumps({"level": 0.7}), json.dumps({"state": "transcribing"}),
           json.dumps({"text": "hardware store"})]
  session = voice.VoiceTyping(heard.append, _worker(*lines))
  session.start()
  assert session.state == "listening"
  assert _until(session, lambda: heard)
  assert heard == ["hardware store"] and session.state == "idle" and 0.7 in session.levels


def test_session_shows_download_progress_and_errors(monkeypatch):
  monkeypatch.setattr(speech, "model_ready", lambda folder=None: False)
  session = voice.VoiceTyping(lambda text: None, _worker(json.dumps({"state": "download", "progress": 0.42}),
                                                         json.dumps({"error": "no_speech"})))
  session.start()
  assert session.state == "download"
  assert _until(session, lambda: session.state == "message")
  assert session.message == voice.ERRORS["no_speech"]


def test_a_worker_that_dies_says_so(ready):
  session = voice.VoiceTyping(lambda text: None, [sys.executable, "-c", "raise SystemExit(1)"])
  session.start()
  assert _until(session, lambda: session.state == "message")
  assert session.message == voice.ERRORS["failed"]


def test_type_instead_and_closing_the_page_end_the_worker(ready, monkeypatch):
  session = voice.VoiceTyping(lambda text: None, _worker(json.dumps({"state": "listening"}), linger=30))
  session.start()
  process = session._process
  session.cancel()
  assert session.state == "idle" and process.wait(timeout=5) is not None

  monkeypatch.setattr(voice, "UNSEEN_S", 0.2)
  session.start()
  process = session._process                                      # nothing calls update(): the panel isn't drawn
  assert process.wait(timeout=5) is not None and session.state == "idle"


# ---- the mic key ----

@pytest.fixture
def keyboard(monkeypatch):
  monkeypatch.setattr(K.upstream, "Label", lambda *a, **k: None)
  monkeypatch.setattr(K.upstream, "Button", lambda *a, **k: None)
  monkeypatch.setattr(K.upstream.gui_app, "texture", lambda *a, **k: None)
  monkeypatch.setattr(voice, "available", lambda: True)
  started = []
  monkeypatch.setattr(voice.VoiceTyping, "start", lambda self: started.append(self))
  return started


def test_mic_key_only_for_plain_text_while_parked(keyboard, monkeypatch):
  assert K.EssentialsKeyboard().voice_offered()
  assert not K.EssentialsKeyboard(password_mode=True, show_password_toggle=True).voice_offered()
  monkeypatch.setattr(voice, "available", lambda: False)
  assert not K.EssentialsKeyboard().voice_offered()


def test_mic_key_starts_voice_typing_and_words_land_after_the_text(keyboard):
  pad = K.KeyPad(lambda: None, "Search", voice_hint="Say a place")
  pad._all_keys[K.MIC]._click_callback()
  assert keyboard == [pad._voice] and pad.text == ""              # the key types nothing itself
  pad._insert_spoken("hardware store")
  assert pad.text == "hardware store"
  pad.set_text("near ")
  pad._insert_spoken("the lake")
  assert pad.text == "near the lake"
  assert pad._voice_panel.hint == "Say a place"

  kb = K.EssentialsKeyboard()
  kb._all_keys[K.MIC]._click_callback()
  assert keyboard[-1] is kb._voice and kb.text == ""
