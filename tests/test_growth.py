"""A small synthetic save for the four capacity bars (engine/growth.py)."""
import json
import pathlib
import struct
import sys
import unittest

ENGINE = pathlib.Path(__file__).resolve().parents[1] / 'engine'
sys.path.insert(0, str(ENGINE))

import featurelib as fl
import growth
import money


def save_bytes(cap=50, who='jason', qual='healthmax', array_value=None, rank_value=None):
    """Two characters, each with the 37 attribute values and the eight stats rows growth.py writes."""
    attrs = [50] * 37
    for q, i in growth.CAPACITY.items():
        attrs[i] = attrs[i + 30] = 50
    if array_value is not None:
        attrs[growth.CAPACITY[qual]] = array_value
    players = []
    for name in ('lucia', 'jason'):
        a = list(attrs)
        if name != who:
            for q, i in growth.CAPACITY.items():
                a[i] = a[i + 30] = cap
        players.append({'$0xacec22be': {'$data': '0x%08x' % fl.h(name)}, '$0x749dbb9e': {'$content': 'int_array', '$data': a}})
    character = {'$0x7a47cb05': {'$0x22a87829': {'$0xdad204f6': players}}}

    qual_hashes = [0] + [fl.h(q) for q in growth.CAPACITY]
    base, qr, owner, values = [], [], [], []
    for o in (1, 2):
        for qi in range(1, len(qual_hashes)):
            for b in (0, 1):
                base.append(b); qr.append(qi); owner.append(o)
                v = cap if o == 1 or who != 'jason' else 50
                if o == 2 and growth.CAPACITY[qual] == qi - 1 and b == 1 and rank_value is not None:
                    v = rank_value
                values.append(v)
    stats = {'$0x7a47cb05': {'$0x0635cbd9': {
        '$0x085ee24c': {'$0x92f37a48': base, '$0x4d20ff5b': qr, '$0x46be9d78': owner, '$0x450ce2f0': values},
        '$0x50983a95': [fl.h('points'), fl.h('rank')],
        '$0x592f1d24': qual_hashes,
        '$0xe93457ea': [0, fl.h('charlucia'), fl.h('charjason')]}}}

    sections = [(growth.SEC, json.dumps(character, separators=(',', ':')).encode()),
                (fl.STATS, json.dumps(stats, separators=(',', ':')).encode())]
    head = bytearray(b'JSAV' + struct.pack('<III', 3, len(sections), 0) + b'\0' * (20 * len(sections)))
    entries = []
    for h, text in sections:
        entries.append([h, 1, 0, len(head), len(text)])
        head += text
    out = bytearray(head)
    for i, e in enumerate(entries):
        struct.pack_into('<IIIII', out, 16 + 20 * i, *e)
    return bytes(out)


class GrowthTest(unittest.TestCase):
    def test_read_and_max(self):
        b = save_bytes()
        r = growth.read(b)
        self.assertIsNone(r['problem'])
        self.assertEqual(r['max'], 100)
        for c in r['characters']:
            self.assertEqual(set(c['capacities']), set(growth.CAPACITY))
            self.assertTrue(all(x['value'] == 50 and x['consistent'] for x in c['capacities'].values()))
        choice = {c['key']: {q: 100 for q in growth.CAPACITY} for c in r['characters']}
        out, log = growth.apply(b, choice)
        self.assertEqual(len(log), 8)
        self.assertIsNone(growth.read(out)['problem'])
        for c in growth.read(out)['characters']:
            self.assertEqual([x['value'] for x in c['capacities'].values()], [100] * 4)
            self.assertTrue(all(x['consistent'] for x in c['capacities'].values()))
        again, log = growth.apply(out, choice)
        self.assertEqual(again, out)
        self.assertEqual(log, [])

    def test_disagreeing_copies_are_set_alike(self):
        b = save_bytes(array_value=65, rank_value=95)
        before = growth.read(b)
        jason = next(c for c in before['characters'] if c['key'] == 'jason')
        h = jason['capacities']['healthmax']
        self.assertEqual((h['value'], h['consistent']), (65, False))
        out, _ = growth.apply(b, {'jason': {'healthmax': 100}})
        after = next(c for c in growth.read(out)['characters'] if c['key'] == 'jason')
        self.assertTrue(after['capacities']['healthmax']['consistent'])
        self.assertEqual(after['capacities']['healthmax']['value'], 100)

    def test_refusals(self):
        b = save_bytes()
        with self.assertRaises(fl.FeatureError) as e:
            growth.apply(b, {'jason': {'healthmax': 101}})
        self.assertEqual(str(e.exception), 'out_of_range')
        with self.assertRaises(fl.FeatureError) as e:
            growth.apply(b, {'jason': {'meter': 100}})
        self.assertEqual(str(e.exception), 'bad_request')
        with self.assertRaises(fl.FeatureError) as e:
            growth.apply(b, {'nobody': {'healthmax': 100}})
        self.assertEqual(str(e.exception), 'bad_request')


if __name__ == '__main__':
    unittest.main()
