# Save Garage - Copyright (C) 2026 NotHGM - GNU GPL v3 with the additional terms in NOTICE; see LICENSE.
"""Editing for decrypted GTA VI story saves beyond money: ammo and stats.

Works the same way as money.py: values are replaced in place inside a section's JSON text, so everything else
stays byte-for-byte as the game wrote it, and every edit is checked against the value it replaces.
All edits for a slot are applied together to the ORIGINAL decrypted file (money first, through money.patch),
so applying the same set twice gives the same file.

Stats section layout (worked out from real saves, see research notes):
  $0x7a47cb05.$0x0635cbd9.<group> holds four parallel arrays per typed group:
    $0x92f37a48 base-name index, $0x4d20ff5b qualifier index, $0x46be9d78 owner index, $0x450ce2f0 value.
  $0x50983a95 / $0x592f1d24 / $0xe93457ea are the base / qualifier / owner name tables (joaat hashes).
  Owner 0 is the game-wide total, 1 is Lucia, 2 is Jason. For most counters total = Lucia + Jason.
  Floats are written with six decimals ("32.670002"), bools as true/false.
"""
import json, math, re
from collections import namedtuple

import gamelabels
import hashnames
import itemnames
import meanings
import money
import statnames

M32 = 0xffffffff
joaat = money.joaat


class SaveError(money.SaveError):
    pass


# ---------------------------------------------------------------- stats
STAT_PATH = ('$0x7a47cb05', '$0x0635cbd9')
K_BASE, K_QUAL, K_OWNER, K_VAL = '$0x92f37a48', '$0x4d20ff5b', '$0x46be9d78', '$0x450ce2f0'
T_BASE, T_QUAL, T_OWNER = '$0x50983a95', '$0x592f1d24', '$0xe93457ea'
GROUP_TYPES = {
    '$0x085ee24c': 'int32', '$0x0d49085d': 'float', '$0x77096582': 'bool', '$0x21b27639': 'bool',
    '$0x456ae73c': 'u8', '$0xa17a2c2b': 'int16', '$0x40ee3695': 'u32', '$0x97232209': 'int64', '$0x35e4daa8': 'int64',
}
# Values are kept non-negative: no stat in a real save is negative, and counters below zero make no sense.
TYPE_RANGE = {'int32': (0, 2**31 - 1), 'u32': (0, 2**32 - 1), 'int64': (0, 2**63 - 1), 'int16': (0, 2**15 - 1),
              'u8': (0, 127), 'float': (0.0, 1e12)}
# Rows that money.py keeps in sync with the bank, savings and cash balances: never edited here.
MONEY_GROUP = '$0x97232209'
MONEY_BASES = (money.STAT_CHECKING, money.STAT_CASH_PLUS_CHECKING, money.STAT_SAVINGS, 265)
VAL_RE = re.compile(rb'"\$0x450ce2f0":(?:\{"\$content":"[a-z0-9_]+","\$data":)?\[')

_BASE_NAMES = {joaat(n): n for n in statnames.BASE_NAMES}
_QUAL_NAMES = {joaat(n): n for n in statnames.QUALIFIER_NAMES}
_OWNER_NAMES = {joaat(n): n for n in statnames.OWNER_NAMES}


def _arr(x):
    if isinstance(x, dict):
        return x.get('$data') or []
    return x or []


def stat_rows(sec_txt):
    """-> (groups, tables). groups: {key: {type, base, qual, owner, value}}; tables: {base, qual, owner} hash lists."""
    root = json.loads(sec_txt)[STAT_PATH[0]][STAT_PATH[1]]
    groups = {}
    for g, t in GROUP_TYPES.items():
        v = root.get(g)
        if not isinstance(v, dict):
            continue
        cols = [_arr(v.get(k)) for k in (K_BASE, K_QUAL, K_OWNER, K_VAL)]
        if any(len(c) != len(cols[0]) for c in cols):
            raise SaveError('layout_changed')
        groups[g] = {'type': t, 'base': cols[0], 'qual': cols[1], 'owner': cols[2], 'value': cols[3]}
    tables = {k: [h & M32 for h in _arr(root.get(key))] for k, key in (('base', T_BASE), ('qual', T_QUAL), ('owner', T_OWNER))}
    return groups, tables


def table_names(tables):
    """Readable names for the three name tables (None where unknown) and which of them are inferred."""
    base = [_BASE_NAMES.get(h) or statnames.INFERRED_BASE.get(h) for h in tables['base']]
    qual = [_QUAL_NAMES.get(h) or statnames.INFERRED_QUALIFIER.get(h) for h in tables['qual']]
    owner = [statnames.OWNER_LABELS.get(i) or _OWNER_NAMES.get(h) for i, h in enumerate(tables['owner'])]
    inferred = {'base': [i for i, h in enumerate(tables['base']) if h not in _BASE_NAMES and h in statnames.INFERRED_BASE],
                'qual': [i for i, h in enumerate(tables['qual']) if h not in _QUAL_NAMES and h in statnames.INFERRED_QUALIFIER]}
    return {'base': base, 'qual': qual, 'owner': owner, 'inferred': inferred}


def is_protected(group, base_index):
    return group == MONEY_GROUP and base_index in MONEY_BASES


def _fmt(t, v):
    if t == 'bool':
        return b'true' if v else b'false'
    if t == 'float':
        return b'%.6f' % v
    return b'%d' % v


def _parse_tok(t, tok):
    tok = tok.strip()
    if t == 'bool':
        if tok in (b'true', b'false'):
            return tok == b'true'
        raise SaveError('verify_failed')
    return float(tok) if t == 'float' else int(tok)


def _same(t, a, b):
    if t == 'bool':
        return bool(a) == bool(b)
    if t == 'float':
        return abs(float(a) - float(b)) <= max(1e-6, abs(float(b)) * 1e-6)
    return int(a) == int(b)


def coerce(t, v):
    """Check a new value against the stat's type and return it in the right Python type."""
    if t == 'bool':
        if isinstance(v, bool):
            return v
        if v in (0, 1):
            return bool(v)
        raise SaveError('bad_value')
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise SaveError('bad_value')
    lo, hi = TYPE_RANGE[t]
    if t == 'float':
        f = float(v)
        if not math.isfinite(f) or not lo <= f <= hi:
            raise SaveError('out_of_range')
        return f
    if isinstance(v, float) and not v.is_integer():
        raise SaveError('bad_value')
    i = int(v)
    if not lo <= i <= hi:
        raise SaveError('out_of_range')
    return i


def _val_span(txt, group, count):
    """(start, end) of the value array of one stats group inside the section text."""
    key = b'"%s":' % group.encode()
    g = txt.find(key)
    if g < 0 or txt.find(key, g + 1) >= 0:
        raise SaveError('layout_changed')
    k = txt.find(b'"$0x450ce2f0":', g)
    m = VAL_RE.match(txt, k) if k >= 0 else None
    if not m:
        raise SaveError('layout_changed')
    s = m.end()
    e = txt.index(b']', s)
    if (txt[s:e].count(b',') + 1 if e > s else 0) != count:
        raise SaveError('layout_changed')
    return s, e


# Money earned: TOTAL EARNED and each character's MONEY EARNED are lifetimemoneyearned without a qualifier. They rise
# with every source of money (tasks, robberies, safes, tills, pickups, fencing), so an edit to a source moves them too.
# BuckMe is how money was paid, not where it came from, so it isn't added again.
LIFETIME_EARNED = 0xd5188146
EARN_SOURCES = {joaat(q) for q in ('tasks', 'robberies', 'safe', 'till', 'pickups')}


def _apply_stats(txt, changes):
    groups, tables = stat_rows(txt)
    final, explicit_total, log = {}, set(), []
    for ch in changes:
        g = ch.get('group')
        G = groups.get(g)
        r = int(ch['row'])
        if not G or not 0 <= r < len(G['value']):
            raise SaveError('stale_item')
        if (G['base'][r], G['qual'][r], G['owner'][r]) != (int(ch['base']), int(ch['qual']), int(ch['owner'])):
            raise SaveError('stale_item')
        if not _same(G['type'], G['value'][r], ch['value']):
            raise SaveError('stale_item')
        if is_protected(g, G['base'][r]):
            raise SaveError('protected_stat')
        nv = coerce(G['type'], ch['newValue'])
        if _same(G['type'], nv, G['value'][r]):
            continue
        final[(g, r)] = nv
        if G['owner'][r] == 0:
            explicit_total.add((g, r))
        log.append({'what': 'stat', 'group': g, 'row': r, 'label': ch.get('label') or '', 'from': G['value'][r], 'to': nv})

    # Keep the game-wide total (owner 0) equal to Lucia + Jason, but only where it was equal before the edit.
    where = {}
    for g, G in groups.items():
        for r in range(len(G['value'])):
            where[(g, G['base'][r], G['qual'][r], G['owner'][r])] = r
    for (g, r) in list(final):
        G = groups[g]
        if G['type'] == 'bool' or G['owner'][r] not in (1, 2):
            continue
        k = (g, G['base'][r], G['qual'][r])
        r0, r1, r2 = (where.get(k + (o,)) for o in (0, 1, 2))
        if None in (r0, r1, r2) or (g, r0) in explicit_total:
            continue
        v0, v1, v2 = (G['value'][x] for x in (r0, r1, r2))
        if not _same(G['type'], v0, v1 + v2):
            continue
        total = coerce(G['type'], final.get((g, r1), v1) + final.get((g, r2), v2))
        if not _same(G['type'], total, v0):
            final[(g, r0)] = total
            log.append({'what': 'stat_total', 'group': g, 'row': r0, 'from': v0, 'to': total})

    # keep the money-earned totals in step with the sources edited (unless a total was edited itself)
    A, Q = tables['base'], tables['qual']
    delta = {1: 0, 2: 0}
    for (g, r), nv in list(final.items()):
        G = groups[g]
        if A[G['base'][r]] == LIFETIME_EARNED and G['qual'][r] and Q[G['qual'][r]] in EARN_SOURCES and G['owner'][r] in (1, 2):
            delta[G['owner'][r]] += nv - G['value'][r]
    if delta[1] or delta[2]:
        for g, G in groups.items():
            for r in range(len(G['value'])):
                if A[G['base'][r]] != LIFETIME_EARNED or G['qual'][r] != 0 or (g, r) in final:
                    continue
                o = G['owner'][r]
                add = delta[1] + delta[2] if o == 0 else delta.get(o, 0)
                if add:
                    nv = coerce(G['type'], max(0, G['value'][r] + add))
                    final[(g, r)] = nv
                    log.append({'what': 'stat_total', 'group': g, 'row': r, 'from': G['value'][r], 'to': nv})

    for g in sorted({g for g, _ in final}):
        G = groups[g]
        s, e = _val_span(txt, g, len(G['value']))
        toks = txt[s:e].split(b',')
        for (gg, r), nv in final.items():
            if gg != g:
                continue
            if not _same(G['type'], _parse_tok(G['type'], toks[r]), G['value'][r]):
                raise SaveError('verify_failed')
            toks[r] = _fmt(G['type'], nv)
        txt = txt[:s] + b','.join(toks) + txt[e:]
    return txt, log


# ---------------------------------------------------------------- ammo
AMMO_TYPES = ('pistol', 'revolver', 'smg', 'rifle', 'shotgun', 'sniper', 'marksman', 'mg', 'minigun', 'sporting',
              'thrown_grenade', 'thrown_bomb', 'launched_rpg')
AMMO_ITEMS = {joaat('ammo_' + t): t for t in AMMO_TYPES}
AMMO_ITEMS[0x785b097b] = 'speargun'          # its ID isn't known as a name, but the game's text calls it Speargun Ammo


def _sentence(text):
    """'Assault Rifle Ammo' -> 'Assault rifle ammo'. Words in capitals, such as SMG, stay as they are."""
    words = text.split(' ')
    return ' '.join(words[:1] + [w.lower() if w[:1].isupper() and w[1:].islower() else w for w in words[1:]])


# What the game calls each ammo type, from its text.
AMMO_LABELS = {t: _sentence(itemnames.ITEM_LABELS.get(h, t.capitalize() + ' ammo')) for h, t in AMMO_ITEMS.items()}
SLOT_AMMO = joaat('slotid_ammo')
# A full load of each ammo type: the game won't sell or refill past these, and nothing in it raises them. Pistol,
# shotgun, tactical rifle, assault rifle and sniper are published figures; the rest are what a full refill of every
# standard type leaves in a real save. The full amount of grenades, sticky bombs, RPG and speargun ammo isn't known.
AMMO_FULL = {'pistol': 100, 'shotgun': 100, 'marksman': 120, 'rifle': 300, 'sniper': 80,
             'revolver': 100, 'smg': 300, 'mg': 200, 'minigun': 300, 'sporting': 200}
# The most Save Garage writes where the full load isn't known. Where it is, the full load is the limit: tested on a PS5,
# the game cut 9,999 rounds back to a full load when it loaded the save.
AMMO_MAX = 9999


def ammo(sec_txt):
    """Ammo rows the two protagonists currently carry. inv 0 = Lucia, inv 1 = Jason."""
    root = json.loads(sec_txt)['$0x7a47cb05']['$0xd3f59a5e']['$0x789bdd41']
    out = []
    for n in range(min(2, len(root))):
        v = money._inventory(sec_txt, n)
        for r, item in enumerate(v['item']):
            if item & M32 in AMMO_ITEMS and v['slot'][r] & M32 == SLOT_AMMO:
                t = AMMO_ITEMS[item & M32]
                out.append({'inv': n, 'idx': r, 'type': t, 'label': AMMO_LABELS[t], 'value': v['qty'][r],
                            'full': AMMO_FULL.get(t), 'max': AMMO_FULL.get(t) or AMMO_MAX})
    return out


def _apply_ammo(txt, changes):
    current = {(a['inv'], a['idx']): a for a in ammo(txt)}
    log = []
    for ch in changes:
        a = current.get((int(ch['inv']), int(ch['idx'])))
        if not a or a['value'] != ch['value']:
            raise SaveError('stale_item')
        nv = ch['newValue']
        if isinstance(nv, bool) or not isinstance(nv, (int, float)) or (isinstance(nv, float) and not nv.is_integer()):
            raise SaveError('bad_value')
        nv = int(nv)
        if not 1 <= nv <= a['max']:
            raise SaveError('out_of_range')
        if nv == a['value']:
            continue
        txt = money._set(txt, money._qty_span(txt, a['inv']), a['idx'], a['value'], nv)
        log.append({'what': 'ammo', 'inv': a['inv'], 'type': a['type'], 'label': a['label'], 'from': a['value'], 'to': nv})
    return txt, log


# ---------------------------------------------------------------- whole-file
def apply(b, edits):
    """edits: {'money': [...], 'ammo': [...], 'stats': [...], 'guns': {...}, 'completion': {...}, 'world': {...}} applied to
    the original file -> (bytes, log). 'guns' is guns.py's choice ({'lucia': [...], 'jason': [...]}); 'completion' holds
    one choice per Completion part, 'cheats' (challenges.apply_cheats) among them; 'world' holds world.py's time, health
    and armour, player.py's 'lucia', 'jason' and 'relationship', levels.py's 'levels' and fog.py's 'fog'."""
    b, log = _apply_core(b, edits)
    if edits.get('raw'):
        import savebrowse
        try:
            b, rlog = savebrowse.apply(b, edits['raw'])
        except (KeyError, ValueError, TypeError) as e:
            raise SaveError('bad_request') from e
        except savebrowse.BrowseError as e:
            raise SaveError(str(e)) from e
        except Exception as e:                       # a path that no longer exists, for example
            raise SaveError('stale_item') from e
        log += rlog
    if edits.get('guns'):                            # before the Completion parts: its compendium entries count there too
        import guns
        try:
            b, glog = guns.apply(b, edits['guns'])
        except SaveError:
            raise
        except (KeyError, ValueError, TypeError, IndexError) as e:
            raise SaveError('bad_request') from e
        log += glog
    comp = edits.get('completion') or {}
    if comp:
        import compendium, discovery, challenges, gyms, activities, checklist, robberies, fencing, activities2, hoops, vehicles_compendium
        import collectibles2 as collectibles
        steps = [(compendium.apply, comp.get('compendium')), (discovery.apply, comp.get('discovery')), (challenges.apply, comp.get('challenges')),
                 (challenges.apply_cheats, comp.get('cheats')), (gyms.apply, comp.get('gyms')),
                 (activities.apply, comp.get('activities')), (robberies.apply, comp.get('robberies')), (fencing.apply, comp.get('fencing')),
                 (activities2.apply, comp.get('activities2')), (hoops.apply, comp.get('hoops')), (vehicles_compendium.apply, comp.get('vehicles')),
                 (collectibles.apply, comp.get('collectibles'))]
        if comp.get('stuntDiscovery'):         # the stunt categories in the map's Discovery section follow the stunts
            steps.append((discovery.apply, {'categories': [STUNT_DISCOVERY[i] for g in comp['stuntDiscovery'] for i in STUNT_DISCOVERY_IDS.get(g, ())],
                                            'allow_stunt': True}))
        for fn, choice in steps:
            if choice:
                try:
                    b, clog = fn(b, choice)
                except SaveError:
                    raise
                except (KeyError, ValueError, TypeError) as e:
                    raise SaveError('bad_request') from e
                log += [dict(x, what='completion', step=x.get('what')) for x in clog]
        if any(comp.get(k) for k in COMPLETION_PARTS + ('stuntDiscovery',)):
            b, clog = checklist.apply(b, {'overall': 'recompute'})     # the 100% figure, as the game works it out
            log += [dict(x, what='completion', step=x.get('what'), label='100% completion') for x in clog]
    if edits.get('world'):
        import world, player, levels, capacities, fog
        w = edits['world']
        try:
            b, wlog = world.apply(b, w)
        except (world.WorldError, KeyError, ValueError, TypeError) as e:
            raise SaveError(str(e) if isinstance(e, world.WorldError) else 'bad_request') from e
        log += wlog
        # the characters (attributes, criminal profile, relationship, vest), their levels and the map, on the same tab
        for mod, choice in ((player, {k: w[k] for k in player.KEYS if w.get(k) is not None}), (levels, w.get('levels')), (capacities, w.get('capacities')), (fog, w.get('fog'))):
            if choice:
                try:
                    b, plog = mod.apply(b, choice)
                except SaveError:
                    raise
                except (KeyError, ValueError, TypeError, IndexError) as e:
                    raise SaveError('bad_request') from e
                log += plog
    return b, log


def _apply_core(b, edits):
    log = []
    if edits.get('money'):
        try:
            b, mlog = money.patch(b, edits['money'])
        except money.SaveError as e:
            raise SaveError(str(e))
        log += [dict(x, what='money' if x.get('what') == 'inventory' else x.get('what')) for x in mlog]
    if not edits.get('ammo') and not edits.get('stats'):
        return b, log
    ents, secs, gaps, head, tail = money._load(b)
    try:
        if edits.get('ammo'):
            i = money._sec(ents, money.SEC_INV)
            secs[i], alog = _apply_ammo(secs[i], edits['ammo'])
            log += alog
        if edits.get('stats'):
            i = money._sec(ents, money.SEC_STAT)
            secs[i], slog = _apply_stats(secs[i], edits['stats'])
            log += slog
        return money._rebuild(head, ents, secs, gaps, tail, len(b)), log
    except (KeyError, ValueError, IndexError, TypeError) as e:
        raise SaveError('bad_request') from e


def section(b, sec_hash):
    ents, secs, _, _, _ = money._load(b)
    return secs[money._sec(ents, sec_hash)]


# ---------------------------------------------------------------- featured stats for the editor UI
Spec = namedtuple('Spec', 'id category label help risk unit base qual owners')
LUCIA_JASON = (0, 1, 2)
STARS = lambda n: '%d star%s' % (n, '' if n == 1 else 's')
TROPHY_NOTE = ''          # the shared warning for trophy counters is shown once, in the UI's section intro
OVERPOWERS, BUFFS = 0xdef0d42f, 0x53f5b035          # shown in the game as OVERPOWERS and BUFFS (names not cracked yet)
# Labels and rows below follow the game's own stats screens, matched value for value against a real save.
FEATURED = [
    Spec('overall_pct', 'progress', '100% completion', 'Overall completion, shown in the game as 100% COMPLETION. Changing it does not unlock anything.', 'caution', 'percent', 'totalprogressmade', 0, (0,)),
    Spec('story_pct', 'progress', 'Story completion', 'The story part of 100% completion. Changing it does not unlock or skip missions.', 'caution', 'percent', 'totalprogressmade', 'story', (0,)),
    Spec('styles_pct', 'progress', 'Styles completion', 'The styles part of 100% completion.', 'caution', 'percent', 'totalprogressmade', 'styles', (0,)),
    Spec('side_tasks', 'progress', 'Side tasks completed', 'Side tasks finished.', 'caution', 'count', 'sidetaskscompleted', 0, LUCIA_JASON),
    Spec('overpowers_health', 'skills', 'Health overpowers', 'Shown in the game as HEALTH OVERPOWERS. Tested on PS5: the game keeps an edited value.', 'tested', 'count', OVERPOWERS, 'health', LUCIA_JASON),
    Spec('overpowers_stamina', 'skills', 'Stamina overpowers', 'Shown in the game as STAMINA OVERPOWERS. Tested on PS5: the game keeps an edited value.', 'tested', 'count', OVERPOWERS, 'stamina', LUCIA_JASON),
    Spec('overpowers_focus', 'skills', 'Focus overpowers', 'Shown in the game as FOCUS OVERPOWERS.', 'caution', 'count', OVERPOWERS, 'focus', LUCIA_JASON),
    Spec('buffs_health', 'skills', 'Health buffs', 'Shown in the game as HEALTH BUFFS. Tested on PS5: the game keeps an edited value.', 'tested', 'count', BUFFS, 'health', LUCIA_JASON),
    Spec('buffs_stamina', 'skills', 'Stamina buffs', 'Shown in the game as STAMINA BUFFS. Tested on PS5: the game keeps an edited value.', 'tested', 'count', BUFFS, 'stamina', LUCIA_JASON),
    Spec('buffs_focus', 'skills', 'Focus buffs', 'Shown in the game as FOCUS BUFFS.', 'caution', 'count', BUFFS, 'focus', LUCIA_JASON),
    Spec('workouts', 'skills', 'Workouts completed', 'Gym workouts finished. Tested on PS5: the game keeps an edited value and counts on from it.', 'tested', 'count', 'numworkoutscompleted', 0, LUCIA_JASON),
    Spec('meditations', 'skills', 'Meditations', 'Meditation sessions. Tested on PS5: the game keeps an edited value.', 'tested', 'count', 'totalmeditations', 0, LUCIA_JASON),
    Spec('time_played', 'time', 'Time played', 'Shown in the game as TIME PLAYED. The total is Lucia plus Jason.', 'caution', 'ms', 'totalplayingtimems', 0, LUCIA_JASON),
    Spec('time_onfoot', 'time', 'Time on foot', 'Time spent out of vehicles.', 'caution', 'ms', 'time', 'travelledfoot', LUCIA_JASON),
    Spec('time_invehicle', 'time', 'Time in vehicles', 'Time spent in any vehicle.', 'caution', 'ms', 'time', 'invehicle', LUCIA_JASON),
    Spec('dist_total', 'time', 'Distance travelled', 'All distance, on foot and in vehicles. The game-wide figure includes vehicles; the per-character ones are on foot.', 'caution', 'distance', 'dist', 'travelled', LUCIA_JASON),
    Spec('dist_onfoot', 'time', 'Distance on foot', 'Distance covered out of vehicles.', 'caution', 'distance', 'dist', 'travelledfoot', LUCIA_JASON),
    Spec('dist_invehicle', 'time', 'Distance in vehicles', 'Distance covered in any vehicle.', 'caution', 'distance', 'dist', 'invehicle', LUCIA_JASON),
] + [Spec('time_' + q, 'time', 'Time spent ' + label, 'Recorded time for this activity.', 'caution', 'ms', 'time', q, LUCIA_JASON)
     for q, label in (('walking', 'walking'), ('jogging', 'jogging'), ('running', 'running'), ('sprinting', 'sprinting'),
                      ('swimming', 'swimming'), ('underwater', 'underwater'), ('aircraft', 'flying'), ('watercraft', 'on boats'),
                      ('stealth', 'in stealth'), ('cover', 'in cover'), ('parachute', 'parachuting'), ('dancing', 'dancing'))] + [
    Spec('earned_' + q, 'earnings', label, 'A record of money earned. It does not add money: use the Money tab for that.', 'tested', 'money', 0xd5188146, q, LUCIA_JASON)
    for q, label in (('buckme', 'Earned through BuckMe'), ('tasks', 'Earned from tasks'), ('robberies', 'Earned from robberies'),
                     ('safe', 'Taken from safes'), ('till', 'Taken from tills'), ('pickups', 'Picked up'))] + [
    Spec('times_wanted', 'wanted', 'Times wanted', 'Shown in the game as TIMES WANTED.', 'caution', 'count', 'reachedwantedlevel', 'level1', LUCIA_JASON),
    Spec('stars_gained', 'wanted', 'Wanted stars gained', 'Shown in the game as TOTAL WANTED STARS GAINED.', 'caution', 'count', 'reachedwantedlevel', 'any', LUCIA_JASON),
    Spec('stars_lost', 'wanted', 'Wanted stars lost', 'Shown in the game as WANTED STARS LOST.', 'caution', 'count', 'evadedwantedlevel', 'any', LUCIA_JASON),
] + [Spec('evaded_l%d' % n, 'wanted', '%d-star wanted levels evaded' % n, 'How often you got away at this wanted level.', 'caution', 'count', 'evadedwantedlevel', 'level%d' % n, LUCIA_JASON) for n in range(1, 7)] + [
    Spec('wanted_time_any', 'wanted', 'Time wanted', 'Total time with a wanted level.', 'caution', 'ms', 'timeinwantedlevel', 'any', LUCIA_JASON),
] + [Spec('wanted_time_l%d' % n, 'wanted', 'Time at ' + STARS(n), 'Total time spent at this wanted level.', 'caution', 'ms', 'timeinwantedlevel', 'level%d' % n, LUCIA_JASON) for n in range(1, 7)] + [
    Spec('weapon_kills', 'records', 'Weapon kills', 'Shown in the game as WEAPON KILLS.', 'caution', 'count', 'kills', 'armed', LUCIA_JASON),
    Spec('runover_kills', 'records', 'Hit and run kills', 'Shown in the game as HIT & RUN KILLS.', 'caution', 'count', 'kills', 'runover', LUCIA_JASON),
    Spec('driveby_kills', 'records', 'Drive-by kills', 'Shown in the game as DRIVE-BY KILLS.', 'caution', 'count', 'kills', 'driveby', LUCIA_JASON),
    Spec('vehicleweapon_kills', 'records', 'Weaponized vehicle kills', 'Shown in the game as WEAPONIZED VEHICLE KILLS.', 'caution', 'count', 'kills', 'vehicleweapon', LUCIA_JASON),
    Spec('kills', 'records', 'Kills, all kinds', 'Every kill together.', 'caution', 'count', 'kills', 0, LUCIA_JASON),
    Spec('headshots', 'records', 'Headshots', 'Combat record.', 'caution', 'count', 'headshots', 0, LUCIA_JASON),
    Spec('shots', 'records', 'Shots fired', 'Shown in the game as SHOTS FIRED.', 'caution', 'count', 'numused', 'ammo', LUCIA_JASON),
    Spec('deaths', 'records', 'Deaths', 'Shown in the game as TOTAL DEATHS.', 'caution', 'count', 'deaths', 0, LUCIA_JASON),
    Spec('busted', 'records', 'Times busted', 'How often you were arrested.', 'caution', 'count', 'busted', 0, LUCIA_JASON),
    Spec('stolen', 'records', 'Vehicles stolen', 'Shown in the game as VEHICLES STOLEN.', 'caution', 'count', 'stolen', 'vehicle', LUCIA_JASON),
    Spec('stolen_slimjim', 'records', 'Vehicles stolen with a slim jim', 'Shown in the game as VEHICLES STOLEN WITH SLIM JIM.', 'caution', 'count', 'stolenvehiclesbymethod', 'slimjim', LUCIA_JASON),
    Spec('stolen_window', 'records', 'Vehicles stolen by breaking in', 'Shown in the game as VEHICLES STOLEN BY BREAKING IN.', 'caution', 'count', 'stolenvehiclesbymethod', 'smashedwindow', LUCIA_JASON),
    Spec('carjackings', 'records', 'Carjackings', 'Vehicle record.', 'caution', 'count', 'carjackings', 0, LUCIA_JASON),
    Spec('holdups', 'records', 'Holdups', 'Store holdups.', 'caution', 'count', 'holdups', 0, LUCIA_JASON),
    Spec('fish', 'records', 'Fish caught', 'Shown in the game as FISH CAUGHT.', 'caution', 'count', 'totalcaught', 'fish', LUCIA_JASON),
    Spec('photo_animal', 'records', 'Animals photographed', 'Wildlife photos taken.', 'caution', 'count', 'photographed', 'animal', LUCIA_JASON),
    Spec('rentals', 'records', 'Vehicles rented', 'Shown in the game as VEHICLES RENTED.', 'caution', 'count', 'numpurchased', 'rentals', LUCIA_JASON),
    Spec('taxis', 'records', 'Taxi rides', 'Taxis paid for.', 'caution', 'count', 'numpurchased', 'taxis', LUCIA_JASON),
    Spec('masks', 'records', 'Masks equipped', 'Shown in the game as MASKS EQUIPPED.', 'caution', 'count', 'numtimesused', 'masks', LUCIA_JASON),
    Spec('armor', 'records', 'Armor equipped', 'Shown in the game as ARMOR EQUIPPED.', 'caution', 'count', 'numtimesused', 'armor', LUCIA_JASON),
    Spec('fenced_packages', 'records', 'Packages fenced', 'Items sold to fences.', 'caution', 'count', 'fenced', 'packages', LUCIA_JASON),
    Spec('fenced_doubloons', 'records', 'Doubloons fenced', 'Items sold to fences.', 'caution', 'count', 'fenced', 'doubloons', LUCIA_JASON),
    Spec('fenced_meteorites', 'records', 'Meteorites fenced', 'Items sold to fences.', 'caution', 'count', 'fenced', 'meteorites', LUCIA_JASON),
    Spec('stunts_total', 'trophies', 'Stunt completions, repeats included', 'Counts a stunt again each time you redo it. The game shows unique stunts, from the completion percentage.', 'danger', 'count', 'stuntscompleted', 'totalstunts', (0,)),
    Spec('stunt_jumps', 'trophies', 'Stunt jumps', 'Stunt jumps completed.', 'danger', 'count', 'stuntscompleted', 'stuntjumps', (0,)),
    Spec('base_jumps', 'trophies', 'Base jumps', 'Base jumps completed.', 'danger', 'count', 'stuntscompleted', 'basejumps', (0,)),
    Spec('knife_flights', 'trophies', 'Knife flights', 'Knife flights completed.', 'danger', 'count', 'stuntscompleted', 'knifeflights', (0,)),
    Spec('under_bridges', 'trophies', 'Under the bridge', 'Under-the-bridge flights completed.', 'danger', 'count', 'stuntscompleted', 'underthebridge', (0,)),
    Spec('challenges', 'trophies', 'Challenges completed', 'All challenges together.', 'danger', 'count', 'challengescompleted', 0, (0,)),
    Spec('discoverables', 'trophies', 'Discoverables found', 'Places and things discovered.', 'danger', 'count', 'discoverablesfound', 0, (0,)),
    Spec('collectibles', 'trophies', 'Collectibles collected', 'The collectibles counter.', 'danger', 'count', 'numcollected', 'collectibles', (0,)),
    Spec('collectible_cards', 'trophies', 'Collectible cards', 'Cards collected.', 'danger', 'count', 'numcollected', 'collectiblecards', (0,)),
    Spec('collectible_sets', 'trophies', 'Complete collectible sets', 'Finished collectible sets.', 'danger', 'count', 'numcollected', 'allsets', (0,)),
    Spec('vaults', 'trophies', 'Vaults robbed', 'Shown in the game as VAULTS ROBBED.', 'danger', 'count', 'robbedvaults', 0, (0,)),
] + [Spec('gadget_' + q, 'gadgets', label, 'Marks the gadget as obtained. It may not put the gadget in your inventory.', 'tested' if q in ('headphones', 'metaldetector', 'masks') else 'caution', 'flag', 'acquired', q, (0, 1, 2))
     for q, label in (('metaldetector', 'Metal detector'), ('binoculars', 'Binoculars'), ('flashlight', 'Flashlight'),
                      ('masks', 'Masks'), ('headphones', 'Headphones'))]


# ---------------------------------------------------------------- weapons each character carries (read only)
_ITEMS = {joaat(n): n for n in itemnames.ITEM_NAMES}
_WEAPON_GROUP = {'pistol': 'pistol', 'revolver': 'revolver', 'smg': 'SMG', 'autorifle': 'rifle', 'tacrifle': 'tactical rifle', 'shotgun': 'shotgun',
                 'sniper': 'sniper rifle', 'launched': 'launcher'}
_WEAPON_WORD = {'fiftycal': '.50', 'combatpdw': 'combat PDW', 'combatmg': 'combat MG', 'pumpaction': 'pump-action', 'sbs': 'short-barrel', 'gpmg': 'GPMG',
                'hunter': 'hunting', 'unarmed': 'fists'}


def weapon_label(name):
    """weaponspec_autorifle_assault_default -> 'Assault rifle'."""
    parts = name.split('_')
    if len(parts) < 3 or parts[0] != 'weaponspec':
        return name
    group, word = parts[1], parts[2] if len(parts) > 3 or parts[1] != 'unarmed' else 'unarmed'
    variant = parts[3] if len(parts) > 3 else 'default'
    text = ' '.join(x for x in (_WEAPON_WORD.get(word, word), _WEAPON_GROUP.get(group, '')) if x)
    if variant not in ('default', group) and variant not in text:
        text += ' (%s)' % variant
    return text[:1].upper() + text[1:]


def weapons(sec_txt):
    """Weapons in each protagonist's weapon list: [{inv, id, name, label, kind}]. inv 0 = Lucia, inv 1 = Jason.
    label is what the game calls the weapon; kind is the type of weapon when the label doesn't say it."""
    root = json.loads(sec_txt)['$0x7a47cb05']['$0xd3f59a5e']['$0x789bdd41']
    out = []
    for n in range(min(2, len(root))):
        seen = set()
        for it in _arr((root[n].get('$0xc500ddf4') or {}).get('$0xbe8e255c')):
            h = it & M32
            if h in seen:
                continue
            seen.add(h)
            name = _ITEMS.get(h)
            if name == 'weaponspec_unarmed_default':
                continue
            kind = weapon_label(name) if name else ''
            label = itemnames.ITEM_LABELS.get(h)
            if not label:                     # '' when the weapon isn't known yet
                label, kind = kind, ''
            elif kind.split(' ')[0].lower() in label.lower().replace(' ', ''):
                kind = ''
            out.append({'inv': n, 'id': '%08x' % h, 'name': name, 'label': label, 'kind': kind})
    return out


def _h(x):
    return joaat(x) if isinstance(x, str) else x


# Stats a PS5 kept after loading an edited save, shown on its stats screens and written back on its next save (24-25 Nov
# 2026). Tested values ran from 10 to 2,222,222, including counters set above the game's own totals, and the game kept
# counting on from them.
TESTED_ON_PS5 = {
    'overall_pct', 'side_tasks', 'overpowers_health', 'overpowers_stamina', 'overpowers_focus', 'buffs_health', 'buffs_stamina',
    'buffs_focus', 'workouts', 'meditations', 'time_played', 'earned_buckme', 'earned_pickups', 'earned_robberies', 'earned_safe',
    'earned_till', 'times_wanted', 'stars_gained', 'stars_lost', 'evaded_l1', 'evaded_l2', 'evaded_l3', 'evaded_l4', 'evaded_l5',
    'evaded_l6', 'weapon_kills', 'runover_kills', 'driveby_kills', 'vehicleweapon_kills', 'kills', 'headshots', 'shots', 'deaths',
    'busted', 'stolen', 'stolen_slimjim', 'stolen_window', 'carjackings', 'holdups', 'fish', 'photo_animal', 'rentals', 'taxis',
    'masks', 'armor', 'fenced_packages', 'fenced_doubloons', 'fenced_meteorites', 'stunts_total', 'stunt_jumps', 'base_jumps',
    'knife_flights', 'under_bridges', 'challenges', 'discoverables', 'collectibles', 'collectible_cards', 'collectible_sets', 'vaults',
    'gadget_metaldetector', 'gadget_masks', 'gadget_headphones',
    # seen on the stats screens of a fresh save with every edit (25 Nov): the focus totals, task rewards, time at 6 stars
    'buffs_focus', 'overpowers_focus', 'earned_tasks', 'wanted_time_l6'}
EXTRA_HELP = {
    'overall_pct': 'The game shows the value you set; it is not counted again on load.',
    'challenges': 'It also changes CHALLENGES COMPLETED on the 100% checklist.',
    'stunts_total': 'The 100% checklist reads a separate count of unique stunts, so this does not change it.',
    'stunt_jumps': 'The 100% checklist reads a separate count of unique stunts, so this does not change it.',
}
FEATURED = [s if s.id not in TESTED_ON_PS5 else s._replace(
                risk='tested', help=' '.join(x for x in (s.help if 'Tested on PS5' in s.help else s.help + ' Tested on PS5: the game keeps an edited value.',
                                                         EXTRA_HELP.get(s.id, '')) if x))
            for s in FEATURED]


# The most each featured stat should be set to: the game's own total where it has one (from its stats screens and
# 100% checklist), otherwise a limit far above what a long playthrough reaches and far below where a counter could
# overflow as the game keeps adding to it. Raw units: milliseconds, metres, dollars or a count.
HOUR, KM = 3600000, 1000
# Time is the exception: the game counts it in 32-bit milliseconds, which wraps past 1,193 hours (9,999 hours came back
# from a PS5 as 454:37:42). Each character gets at most 596 hours, so the game-wide total, Lucia's plus Jason's, still fits.
DEFAULT_MAX = {'percent': 100, 'ms': 596 * HOUR, 'distance': 99999 * KM, 'money': 99999999, 'count': 99999}
SPEC_MAX = {
    'side_tasks': (100, 'the number of optional tasks in the game'),
    'overpowers_health': (999, ''), 'overpowers_stamina': (999, ''), 'overpowers_focus': (999, ''),
    'buffs_health': (9999, ''), 'buffs_stamina': (9999, ''), 'buffs_focus': (9999, ''),
    'workouts': (9999, ''), 'meditations': (999, ''),
    'shots': (9999999, ''), 'deaths': (9999, ''), 'busted': (9999, ''),
    'carjackings': (9999, ''), 'holdups': (9999, ''), 'fish': (9999, ''), 'photo_animal': (9999, ''), 'rentals': (9999, ''),
    'taxis': (9999, ''), 'masks': (9999, ''), 'armor': (9999, ''),
    'fenced_packages': (999, ''), 'fenced_doubloons': (999, ''), 'fenced_meteorites': (999, ''),
    'stunts_total': (397, 'the number of stunts in the game'),
    'stunt_jumps': (130, 'the number of stunt jumps in the game'),
    'base_jumps': (25, 'the number of base jumps in the game'),
    'knife_flights': (40, 'the number of knife flights in the game'),
    'under_bridges': (202, 'the number of under-the-bridge flights in the game'),
    'challenges': (80, 'the number of challenges in the game'),
    'discoverables': (999, ''), 'collectibles': (999, ''),
    'collectible_cards': (480, 'the number of cards in the game'),
    'collectible_sets': (18, 'the number of card sets in the game'),
    'vaults': (8, 'the number of bank vaults in the game'),
}


def featured(sec_txt):
    """Featured stats present in this save, with the exact rows to edit."""
    groups, tables = stat_rows(sec_txt)
    bidx = {h: i for i, h in enumerate(tables['base'])}
    qidx = {h: i for i, h in enumerate(tables['qual'])}
    where = {}
    for g, G in groups.items():
        for r in range(len(G['value'])):
            where[(G['base'][r], G['qual'][r], G['owner'][r])] = (g, r)
    out = []
    for spec in FEATURED:
        b, q = bidx.get(_h(spec.base)), qidx.get(_h(spec.qual))
        if b is None or q is None:
            continue
        entries = []
        for o in spec.owners:
            loc = where.get((b, q, o))
            if not loc:
                continue
            g, r = loc
            G = groups[g]
            if is_protected(g, b):
                continue
            entries.append({'owner': o, 'group': g, 'row': r, 'base': b, 'qual': q, 'type': G['type'], 'value': G['value'][r]})
        if not entries:
            continue
        vals = {e['owner']: e['value'] for e in entries}
        auto = (entries[0]['type'] != 'bool' and {0, 1, 2} <= set(vals) and _same(entries[0]['type'], vals[0], vals[1] + vals[2]))
        cap, why = SPEC_MAX.get(spec.id, (DEFAULT_MAX.get(spec.unit), ''))
        out.append({'id': spec.id, 'category': spec.category, 'label': spec.label, 'help': spec.help, 'risk': spec.risk,
                    'unit': spec.unit, 'autoTotal': bool(auto), 'entries': entries, 'max': cap, 'maxWhy': why})
    return out


def stats_table(sec_txt):
    """Every stat row (compact columns) with readable names, for the full stats browser."""
    groups, tables = stat_rows(sec_txt)
    A, Q, O = tables['base'], tables['qual'], tables['owner']
    labels = {}
    for g, G in groups.items():
        for r in range(len(G['value'])):
            lab = gamelabels.GAME_LABELS.get((A[G['base'][r]], Q[G['qual'][r]], O[G['owner'][r]]))
            if lab:
                labels['%s:%d' % (g, r)] = lab
    names = table_names(tables)
    names['qual_labels'] = {i: gamelabels.QUALIFIER_LABELS[h] for i, h in enumerate(Q) if h in gamelabels.QUALIFIER_LABELS}
    names['owner_labels'] = {i: gamelabels.OWNER_LABELS[h] for i, h in enumerate(O) if i > 2 and h in gamelabels.OWNER_LABELS}
    # keys whose real name is unknown: what they hold, worked out from the saves (the UI marks these as descriptions)
    names['base_meanings'] = {i: meanings.BASE[h] for i, h in enumerate(A) if names['base'][i] is None and h in meanings.BASE}
    qm = {i: meanings.QUALIFIER[h] for i, h in enumerate(Q) if names['qual'][i] is None and i not in names['qual_labels'] and h in meanings.QUALIFIER}
    om = {i: meanings.OWNER[h] for i, h in enumerate(O) if names['owner'][i] is None and i not in names['owner_labels'] and h in meanings.OWNER}
    names['qual_labels'].update(qm)
    names['owner_labels'].update(om)
    names['meaning'] = {'base': sorted(names['base_meanings']), 'qual': sorted(qm), 'owner': sorted(om)}
    # values that are IDs of something with a known name (favourite vehicle or station, gang item, biggest fish, …)
    means = {'%s:%d' % (g, r): m for g, G in groups.items() if G['type'] in ('u32', 'int32', 'int64')
             for r, v in enumerate(G['value']) for m in [hashnames.lookup(v)] if m}
    return {'groups': [{'key': g, 'type': G['type'], 'base': G['base'], 'qual': G['qual'], 'owner': G['owner'], 'value': G['value']}
                       for g, G in groups.items() if G['value']],
            'names': names, 'labels': labels, 'means': means,
            'protected': {MONEY_GROUP: list(MONEY_BASES)}}


# ---------------------------------------------------------------- stunts (Completion tab)
import completiondata

# (id, label, stunt hashes, unique-counter qualifiers with the game's total for each, game total)
STUNT_GROUPS = (
    ('jumps', 'Stunt jumps', completiondata.STUNT_JUMPS, (('stuntjumps', 130),), 130),
    ('base', 'Base jumps', completiondata.BASE_JUMPS, (('basejumps', 25),), 25),
    ('bridges', 'Under the bridge and knife flights', completiondata.BRIDGES_AND_KNIFE_FLIGHTS, (('underthebridge', 202), ('knifeflights', 40)), 242),
)
STUNTS_FOR_100 = 300            # the 100% checklist asks for any 300 of the game's 397 stunts
COMPLETION_PARTS = ('compendium', 'discovery', 'challenges', 'gyms', 'activities', 'robberies', 'fencing', 'activities2', 'hoops', 'vehicles', 'collectibles')
# Every key a Completion edit may hold. The cheat trackers are counted by no 100% line, so 'cheats' alone doesn't make
# the 100% figure be worked out again (COMPLETION_PARTS and the stunts do).
COMPLETION_KEYS = COMPLETION_PARTS + ('stuntDiscovery', 'cheats')
# Discovery section categories for each stunt type (their found bits mirror numfound.<type> in every game save)
STUNT_DISCOVERY = {'jumps': 0x07b59c95, 'base': 0xec841e35, 'bridges': 0x0f25b442, 'knife': 0xc8c1866f}
STUNT_DISCOVERY_IDS = {'jumps': ('jumps',), 'base': ('base',), 'bridges': ('bridges', 'knife')}


def _stunt_index(sec_txt):
    groups, tables = stat_rows(sec_txt)
    A, Q, O = tables['base'], tables['qual'], tables['owner']
    where = {}
    for g, G in groups.items():
        for r in range(len(G['value'])):
            where[(A[G['base'][r]], Q[G['qual'][r]], O[G['owner'][r]])] = {
                'group': g, 'row': r, 'base': G['base'][r], 'qual': G['qual'][r], 'owner': G['owner'][r], 'type': G['type'], 'value': G['value'][r]}
    o0 = O[0]
    return lambda base, qual: where.get((_h(base), _h(qual), o0))


def stunts(sec_txt):
    """How many stunts of each type are done, out of the stunts in this save and the game's total."""
    ref = _stunt_index(sec_txt)
    out = []
    for gid, label, hashes, _, game_total in STUNT_GROUPS:
        states = [ref('completionstate', h) for h in hashes]
        states = [s for s in states if s]
        out.append({'id': gid, 'label': label, 'count': len(states), 'gameTotal': game_total,
                    'done': sum(1 for s in states if s['value'])})
    pct = ref('totalprogressmade', 'totalstunts')
    unique = ref('uniquestuntscompleted', 'totalstunts')
    return {'groups': out, 'uniqueTotal': unique['value'] if unique else None, 'pct': pct['value'] if pct else None,
            'for100': STUNTS_FOR_100}


def _split(n, totals):
    """Share n done stunts between counters in proportion to the game's totals (the under-the-bridge flights and
    knife flights can't be told apart in the save)."""
    if len(totals) == 1:
        return [n]
    whole = sum(totals)
    if n == whole:
        return list(totals)
    parts = [n * t // whole for t in totals]
    parts[0] += n - sum(parts)
    return parts


def stunt_edits(sec_txt, ids):
    """Stat edits that mark every stunt of the given types found and completed, with the game's counters to match:
    the unique counts per type and in total (the 100% checklist reads these), the repeat counts, and the cached
    completion percentage for stunts."""
    ref = _stunt_index(sec_txt)
    edits = {}

    def put(r, nv, label):
        if r and not _same(r['type'], r['value'], nv):
            edits[(r['group'], r['row'])] = dict({k: r[k] for k in ('group', 'row', 'base', 'qual', 'owner')}, value=r['value'], newValue=nv, label=label)

    unique_now = {}
    for gid, label, hashes, counters, _ in STUNT_GROUPS:
        rows = [(ref('found', h), ref('completionstate', h), ref('numtimescompleted', h)) for h in hashes]
        rows = [x for x in rows if x[1]]
        if gid in ids:
            for found, state, times in rows:
                put(found, True, label + ': found')
                if not state['value']:
                    put(state, 1, label + ': completed')
                if times and not times['value']:
                    put(times, 1, label + ': times completed')
            share = _split(len(rows), [t for _, t in counters])   # every stunt of the type in this save is now done
            for (q, _), n in zip(counters, share):
                unique_now[q] = n
        else:
            for q, _ in counters:
                r = ref('uniquestuntscompleted', q)
                unique_now[q] = r['value'] if r else 0
    for gid, label, hashes, counters, _ in STUNT_GROUPS:
        if gid in ids:
            for q, _ in counters:
                put(ref('uniquestuntscompleted', q), unique_now[q], 'Unique stunts completed: ' + q)
                put(ref('numfound', q), unique_now[q], 'Stunts discovered: ' + q)
                r = ref('stuntscompleted', q)
                if r:
                    put(r, max(r['value'], unique_now[q]), 'Stunts completed, repeats included: ' + q)
    total_unique = sum(unique_now.values())
    put(ref('uniquestuntscompleted', 'totalstunts'), total_unique, 'Unique stunts completed')
    r = ref('stuntscompleted', 'totalstunts')
    if r:
        put(r, max(r['value'], total_unique), 'Stunts completed, repeats included')
    pct = ref('totalprogressmade', 'totalstunts')
    if pct:
        put(pct, round(min(100.0, total_unique * 100.0 / STUNTS_FOR_100), 6), 'Stunts, part of 100% completion')
    return list(edits.values())
