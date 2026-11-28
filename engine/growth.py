# Save Garage - Copyright (C) 2026 NotHGM - GNU GPL v3 with the additional terms in NOTICE; see LICENSE.
"""Lucia's and Jason's health, stamina, melee-stamina and focus capacity (Save Garage feature module, World tab).

The four capacities are the length of the bars, as opposed to the levels in levels.py. Each is kept in four places:
two copies in PlayerCharacter's 37-value attributeSet (slots 0-3, repeated at 30-33) and the points and rank rows in
the stats. The game writes them alike in game-written saves; the four are set together here.

EVIDENCE (decrypted PS5 saves, checked after the game had written the edited save back)
  * The two attribute copies and the stats points and rank agree in every readable save.
  * The values run from 0 to 100; 100 is the highest value seen in a game save and the editor's ceiling.
  * The game kept four capacities at 100 after loading a save edited on a PS5 and saving again. Levels and the
    special meter are separate values: a level change does not move a capacity, and the meter (slot 24) is rewritten
    by the game when it saves.
  * The four copies are not always equal in game saves: Jason's health was 65 in the attributes but 95 in the stats
    in one of them. Setting all four alike kept the edited save working on a PS5. A capacity is offered whenever all
    four are known ints in range; a save with a different layout is left alone.

The names are the game's stat names. Attribute slots 0-3 and 30-33 are read-only in the Save data browser; this
module writes only those four pairs, after checking the old values and the two stats rows.

REFUSED (FeatureError, nothing written): growth_layout, bad_request, out_of_range, verify_failed.
RISK: tested on a PS5 by ShujiJaeger (value 100 stayed after the game saved); not part of the original release.
"""
import json
import re

import featurelib as fl

FEATURE = 'growth'
SEC = 0x22a87829                                     # PlayerCharacter
CODE = fl.CODE
PATH = (CODE, fl.key(SEC), fl.key('attributeSet'))
K_NAME, K_ATTRS = '$0xacec22be', '$0x749dbb9e'
NAMES = {'lucia': 'Lucia', 'jason': 'Jason'}
OWNER = {who: fl.h('char' + who) for who in NAMES}
CAPACITY = {'healthmax': 0, 'staminamax': 1, 'meleestaminamax': 2, 'specialabilitymax': 3}
LABEL = {'healthmax': 'Health capacity', 'staminamax': 'Stamina capacity',
         'meleestaminamax': 'Melee stamina capacity', 'specialabilitymax': 'Focus capacity'}
MAX = 100                                            # the game's highest written value
_HASH = re.compile(rb'"0x([0-9a-fA-F]{8})"')


def _hash(t, s, e):
    """The typed name hash at t[s:e] as an int, or None for anything else."""
    if t[s:s + 1] == b'{':
        m = {k: (vs, ve) for k, vs, ve in fl.members(t, s)}
        if set(m) != {'$data'}:
            return None
        s, e = m['$data']
    g = _HASH.fullmatch(t[s:e])
    return int(g.group(1), 16) if g else None


def _inspect(b):
    """(Save, {who: {'capacities': {...}}}, Stats), or growth_layout."""
    s = fl.Save(b)
    try:
        t = s.text(SEC)
        st = fl.Stats(s.text(fl.STATS))
        start, _ = fl.walk(t, *PATH)
        chars = {}
        for es, _ in fl.elements(t, start):
            name = _hash(t, *fl.member(t, es, K_NAME))
            who = next((w for w, h in ((w, fl.h(w)) for w in NAMES) if h == name), None)
            if who is None:
                continue
            attrs_s, _ = fl.member(t, es, K_ATTRS)
            data, tokens = fl.typed_values(t, attrs_s)
            if data is None or len(tokens) < 34:
                raise fl.FeatureError('growth_layout')
            values, spans, at = [], [], data[0]
            for tok in tokens:
                if not re.fullmatch(rb'-?(?:0|[1-9][0-9]*)', tok):
                    raise fl.FeatureError('growth_layout')
                values.append(int(tok))
                spans.append((at, at + len(tok)))
                at += len(tok) + 1
            caps = {}
            for qual, index in CAPACITY.items():
                value, mirror = values[index], values[index + 30]
                points = st.value('points', qual, OWNER[who])
                rank = st.value('rank', qual, OWNER[who])
                # Game saves don't always keep the four copies equal: Jason's health was 65 in the attributes but 95
                # in the stats in one save. All four are still known ints, and setting them alike was kept by the PS5.
                if not all(type(x) is int and 0 <= x <= MAX for x in (value, mirror, points, rank)):
                    continue                              # an unfamiliar save: leave those values alone
                caps[qual] = {'value': value, 'label': LABEL[qual], 'max': MAX,
                              'spans': (spans[index], spans[index + 30]),
                              'mirror': mirror, 'points': points, 'rank': rank,
                              'consistent': value == mirror == points == rank}
            chars[who] = {'capacities': caps}
        if set(chars) != set(NAMES):
            raise fl.FeatureError('growth_layout')
    except (fl.FeatureError, IndexError, ValueError, KeyError) as e:
        if isinstance(e, fl.FeatureError):
            raise
        raise fl.FeatureError('growth_layout') from e
    return s, chars, st


def read(b):
    try:
        _, chars, _ = _inspect(b)
        problem = None
    except fl.FeatureError as e:
        chars, problem = {}, str(e)
    return {'max': MAX, 'characters': [{'key': who, 'name': NAMES[who],
                                        'capacities': {q: {k: v for k, v in c.items() if k not in ('spans', 'mirror', 'points', 'rank')}
                                                       for q, c in chars[who]['capacities'].items()}}
                                       for who in NAMES if who in chars], 'problem': problem}


def _checked(choice):
    if not isinstance(choice, dict) or any(k not in NAMES for k in choice):
        raise fl.FeatureError('bad_request')
    out = {}
    for who, caps in choice.items():
        if not isinstance(caps, dict) or any(k not in CAPACITY for k in caps):
            raise fl.FeatureError('bad_request')
        for qual, v in caps.items():
            if type(v) is not int or not 0 <= v <= MAX:
                raise fl.FeatureError('out_of_range')
        out[who] = caps
    return out


def apply(b, choice):
    """choice: {who: {capacity: value}}. All four copies of each chosen capacity are set to the same value."""
    want = _checked(choice)
    s, chars, st = _inspect(b)
    edits, log = [], []
    for who, caps in want.items():
        for qual, v in caps.items():
            c = chars[who]['capacities'].get(qual)
            if c is None:
                raise fl.FeatureError('growth_layout')
            old = c['value']
            label = '%s (%s)' % (LABEL[qual], NAMES[who])
            if old != v:
                edits.extend((span, v) for span in c['spans'])
                log.append({'what': 'world', 'label': label, 'from': old, 'to': v})
            st.set('points', qual, v, label, owner=OWNER[who])
            st.set('rank', qual, v, label, owner=OWNER[who])
    if not log:
        return b, []
    t = s.text(SEC)
    for (vs, ve), v in sorted(edits, reverse=True):      # from the end, so earlier spans stay valid
        t = fl.splice(t, vs, ve, b'%d' % v)
    json.loads(t)
    s.set_text(SEC, t)
    s.set_text(fl.STATS, st.apply()[0])
    out = s.build()
    _, after_chars, after_st = _inspect(out)
    for who, caps in want.items():
        for qual, v in caps.items():
            c = after_chars[who]['capacities'].get(qual)
            if c is None or not (c['value'] == c['mirror'] == after_st.value('points', qual, OWNER[who])
                                 == after_st.value('rank', qual, OWNER[who]) == v):
                raise fl.FeatureError('verify_failed')
    return out, log
