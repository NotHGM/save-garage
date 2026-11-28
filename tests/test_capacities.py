import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import capacities
import featurelib as fl
import money
import player
import savedit


def sample():
    people = ('jason', 'lucia')
    sets = []
    for who in people:
        values = [40] * player.N_ATTRS
        values[0] = values[30] = 65
        sets.append({player.K_NAME: {'$data': '0x%08x' % player.SET_NAME[who]},
                     player.K_ATTRS: {'$content': 'int_array', '$data': values}})
    stats = {savedit.T_BASE: [fl.h('points'), fl.h('rank')], savedit.T_QUAL: [fl.h('healthmax')],
             savedit.T_OWNER: [fl.h('char' + who) for who in people],
             '$0x085ee24c': {savedit.K_BASE: [0, 1, 0, 1], savedit.K_QUAL: [0] * 4,
                             savedit.K_OWNER: [0, 0, 1, 1], savedit.K_VAL: [85, 85, 65, 65]}}
    sections = [(player.CHAR, {player.K_SETS: sets}), (fl.STATS, stats)]
    texts = [json.dumps({fl.CODE: {fl.key(h): data}}, separators=(',', ':')).encode() for h, data in sections]
    head = struct.pack('<4sIII', b'JSAV', 3, len(sections), 0) + bytes(40)
    return money._rebuild(head, [[h, 0, 0, 0, 0] for h, _ in sections], texts, [b''], bytes(4), 0)


class CapacityTests(unittest.TestCase):
    def test_repair_even_if_requested_value_already_matches_first_copy(self):
        b = sample()
        before = capacities.read(b)
        self.assertEqual(before['jason_healthmax']['copies'], [65, 65, 85, 85])
        edits = {'jason_healthmax': 65}
        changed, log = capacities.apply(b, edits)
        self.assertEqual(len(log), 1)
        after = capacities.read(changed)
        self.assertEqual(after['jason_healthmax']['copies'], [65] * 4)
        self.assertEqual(after['lucia_healthmax'], before['lucia_healthmax'])
        self.assertEqual(capacities.apply(changed, edits), (changed, []))

    def test_both_characters_and_different_token_lengths(self):
        changed, _ = capacities.apply(sample(), {'jason_healthmax': 100, 'lucia_healthmax': 0})
        after = capacities.read(changed)
        self.assertEqual(after['jason_healthmax']['copies'], [100] * 4)
        self.assertEqual(after['lucia_healthmax']['copies'], [0] * 4)

    def test_missing_rows_and_invalid_edits(self):
        b = sample()
        self.assertNotIn('lucia_staminamax', capacities.read(b))
        for edit in ({'lucia_staminamax': 50}, {'jason_healthmax': True}, {'jason_healthmax': 101},
                     {'other_healthmax': 10}, {'jason_missing': 10}):
            with self.subTest(edit=edit), self.assertRaises(fl.FeatureError):
                capacities.apply(b, edit)
