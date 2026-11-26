#!/usr/bin/env python3
"""Japanese speech in movie audio -> timed transcript draft (subtitle work). Runs Whisper locally (mlx-whisper).

Needs its own venv:  python3 -m venv work/asr-venv && work/asr-venv/bin/pip install mlx-whisper
usage: work/asr-venv/bin/python tools/asr.py OUT.json WAV [...]   (16 kHz mono WAV from the SFD: ffmpeg -vn -ac 1 -ar 16000)
OUT.json: {movie: [[start, end, text], ...]}. Machine transcript: check every line against the picture.
"""
import json, os, sys
import mlx_whisper

MODEL = 'mlx-community/whisper-large-v3-turbo'
out_path, wavs = sys.argv[1], sys.argv[2:]
out = json.load(open(out_path)) if os.path.exists(out_path) else {}
for w in wavs:
    name = os.path.basename(w)[:-4]
    if name in out: continue
    r = mlx_whisper.transcribe(w, path_or_hf_repo=MODEL, language='ja', condition_on_previous_text=False,
                               no_speech_threshold=0.5, logprob_threshold=-1.0)
    segs = [[round(s['start'], 2), round(s['end'], 2), s['text'].strip()] for s in r['segments']
            if s.get('no_speech_prob', 0) < 0.6 and s['text'].strip()]
    out[name] = segs
    print(name, len(segs), ' / '.join(s[2] for s in segs)[:150], flush=True)
    json.dump(out, open(out_path, 'w'), ensure_ascii=False, indent=1)
