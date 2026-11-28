# Save Garage - GNU GPL v3 with the additional terms in NOTICE; see LICENSE.
"""Edit both character-array slots and both stats for each long-term capacity."""
import featurelib as fl
import player

FIELDS = {'healthmax': (0, 'Health capacity'), 'staminamax': (1, 'Stamina capacity'),
          'meleestaminamax': (2, 'Melee stamina capacity'), 'specialabilitymax': (3, 'Focus capacity')}


def _copies(tokens, stats, who, qual, idx):
    owner = 'char' + who
    return [int(tokens[idx]), int(tokens[idx + 30]), stats.value('points', qual, owner), stats.value('rank', qual, owner)]


def _available(values):
    return all(type(v) is int and 0 <= v <= 100 for v in values)


def read(b):
    save = fl.Save(b)
    text = save.text(player.CHAR)
    sets = player._sets(text, player._root(text))
    stats = fl.Stats(save.text(fl.STATS))
    rows = {}
    for who in sets:
        try:
            _, tokens = player._attributes(text, sets[who])
        except fl.FeatureError:
            continue
        for qual, (idx, label) in FIELDS.items():
            copies = _copies(tokens, stats, who, qual, idx)
            if _available(copies):
                rows[who + '_' + qual] = {'label': label, 'copies': copies}
    return rows


def apply(b, edits):
    if not isinstance(edits, dict):
        raise fl.FeatureError('bad_request')
    requested = {}
    for key, value in edits.items():
        if not isinstance(key, str) or type(value) is not int or not 0 <= value <= 100:
            raise fl.FeatureError('bad_request')
        who, _, qual = key.partition('_')
        if who not in player.NAME or qual not in FIELDS:
            raise fl.FeatureError('bad_request')
        requested.setdefault(who, {})[qual] = value
    save = fl.Save(b)
    text = save.text(player.CHAR)
    stats = fl.Stats(save.text(fl.STATS))
    log = []
    for who, fields in requested.items():
        # Changing the preceding character can shift the array's byte offset.
        obj, tokens = player._attributes(text, player._sets(text, player._root(text))[who])
        for qual, value in fields.items():
            idx, label = FIELDS[qual]
            copies = _copies(tokens, stats, who, qual, idx)
            if not _available(copies):
                raise fl.FeatureError('attributes_layout')
            if all(v == value for v in copies):
                continue
            for slot in (idx, idx + 30):
                if int(tokens[slot]) != value:
                    text = fl.typed_set(text, obj, slot, tokens[slot], b'%d' % value)
            for base in ('points', 'rank'):
                stats.set(base, qual, value, label, 'char' + who)
            log.append({'what': 'world', 'label': '%s (%s)' % (label, player.NAME[who]),
                        'from': ' / '.join(map(str, copies)), 'to': value})
    if not log:
        return b, []
    save.set_text(player.CHAR, text)
    save.set_text(fl.STATS, stats.apply()[0])
    return save.build(), log
