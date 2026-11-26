#!/usr/bin/env python3
"""English captions for the opening movie (SYSARC sc0001.sfd: Japanese staff credits burned into the CG).

The game's own movie subtitles (AdxMovieSubtitleCreate @ 0x109a50, drawn by 0x109be0) read a timing file from
DATAARC (`*_st.cmp`: u32 start ms, u32 duration ms, u32 string index; ends with a zero triple) and a message
file + its .ofs from MESARC. The opening never had subtitles, so the build appends
  MESARC  #1919 sc0001mes.cmp, #1920 sc0001mes.ofs, #1921 sc0001mes.ofs.big
  DATAARC #1236 sc0001_st.cmp
and elfpatch plays the opening through a cave that creates the subtitle window (and makes the movie skippable).
The archive counts given to AdxVolEntry (0x13b06c DATAARC 0x4d4, 0x13b0c0 MESARC 0x77f) grow with them.
Captions: subs/sc0001.json.

Title cards (2026-11-24): ten dungeon arrival movies (MOVIEARC) show the place name burned in and have no speech.
The build also appends cardmes (.cmp/.ofs/.ofs.big, MESARC #1922-1924, one string per card) and one timing file
per card (DATAARC #1237+, cardNN_st.cmp). Their scripts never call EvMovieSubTitle, so elfpatch hooks both event
movie paths (FUN_00136988 / FUN_00137758): with no subtitles requested, a table keyed by the movie id supplies
(st, mes, ofs). Captions: subs/cards.json. The other 28 unsubtitled movies have no speech (Whisper, tools/asr.py).
"""
import json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cmp import compress

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTIONS = os.path.join(ROOT, 'subs', 'sc0001.json')
MES_NAME = 'sc0001mes'
ST_NAME = 'sc0001_st.cmp'
MESARC_N, DATAARC_N = 1919, 1236              # original entry counts = indices of the appended files
MES_IDX, OFS_IDX, ST_IDX = MESARC_N, MESARC_N + 1, DATAARC_N


CARDS = os.path.join(ROOT, 'subs', 'cards.json')
CARD_MES_NAME = 'cardmes'
CARD_MES_IDX, CARD_OFS_IDX = MESARC_N + 3, MESARC_N + 4
CARD_ST_IDX0 = DATAARC_N + 1                  # card k's timing file is DATAARC #CARD_ST_IDX0 + k
MESARC_ADDED, DATAARC_ADDED = 6, 1 + 10


def captions():
    return json.load(open(CAPTIONS, encoding='utf-8'))['captions']


def cards():
    d = json.load(open(CARDS, encoding='utf-8'))
    assert len(d['cards']) == DATAARC_ADDED - 1
    return d


def card_timings():
    """-> [(name, compressed st file)] one per card: card k shows string k of cardmes."""
    d = cards()
    return [(f'card{k:02d}_st.cmp', compress(struct.pack('<III', d['start'], d['end'] - d['start'], k)
                                             + struct.pack('<III', 0x7FFFFFFF, 0, 0))) for k in range(len(d['cards']))]


def card_table():
    """-> [(movie id, st, mes, ofs)] for elfpatch's lookup cave."""
    return [(c['movie'], CARD_ST_IDX0 + k, CARD_MES_IDX, CARD_OFS_IDX) for k, c in enumerate(cards()['cards'])]


def timing(caps=None):
    """-> compressed sc0001_st.cmp. The terminator starts at 0x7fffffff: the player shows the entry its pointer
    sits on once start <= time, so the original zero terminator would flash string 0 again at the end."""
    caps = caps or captions()
    out = b''.join(struct.pack('<III', c['start'], c['end'] - c['start'], k) for k, c in enumerate(caps))
    return compress(out + struct.pack('<III', 0x7FFFFFFF, 0, 0))
