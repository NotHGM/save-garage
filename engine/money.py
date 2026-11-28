# Save Garage - Copyright (C) 2026 CoreyLyu76 (gta6-save-editor) and NotHGM - GNU GPL v3; NotHGM's parts also carry
# the additional terms in NOTICE. See LICENSE.
"""Read and edit money in decrypted GTA VI JSAV saves.

How money is stored (each part checked on a real PS5, November 2026):

  Inventories[n] (n = 0 / 1, the two protagonists) have a main list of six parallel arrays:
    Guids / ParentGuidIndices / ItemIds / SlotIds / Quantities / EquippedFlags
  ParentGuidIndices index into ParentGuids; ParentGuids[index] is the parent item's Guid.
  Every row must also be registered in the Items array as (row << 4) | 1; the game ignores unregistered rows.

  Money is the item currency_cash and its quantity is the amount. It sits in a money box, and boxes hang under an account:

    bank_checking - money box - currency_cash      checking
    bank_savings  - money box - currency_cash      Family Savings; the game adds a box for each savings goal
    wallet        - money box - currency_cash      cash (slot slotid_currency_cash_20000)

  The game's limit is the total capacity of the boxes: an amount above it is cut back when the save loads.
  Item and slot ids are joaat hashes of their names.

  Checking (BuckMe) has boxes of its own, which the game adds as the story raises the limit:
  0x26457c8e (15,000), 0x33894998 (85,000), 0x00fc0216 and 0xdb44180c. The game fills them in that order when money
  comes in and empties them in that order when money goes out. Only money in these boxes counts as BuckMe funds:
  the balance the game spends from (and writes to stat 262) leaves out any other box under checking, while the BuckMe
  app still shows it. So checking stays within the capacity of its own boxes. The 85,000 box can also take extra 85,000
  stacks (money rows under it), which BuckMe shows in the balance, but they may not be spendable (see STACK_BOX), so
  they are only written when a change asks for them. The large 400,000 / 500,000 / 1,000,000
  boxes belong to Family Savings, and earlier versions that put them under checking made money that shows but cannot
  be spent (GitHub issue #3). Editing the bank now empties such boxes and puts the money in checking's own boxes.

  Three mirrors must change too or the numbers disagree: the stats block (ids 262 checking, 274 cash plus checking,
  275 Family Savings), the last checking-ledger entry and the last savings-ledger entry. Checking is one account
  shared by both protagonists: its ledger is one running balance, so the mirror is the last entry of either of them.
"""
import json, struct


def joaat(name):
    h = 0
    for c in name.encode():
        h = (h + c) & 0xffffffff; h = (h + (h << 10)) & 0xffffffff; h ^= h >> 6
    h = (h + (h << 3)) & 0xffffffff; h ^= h >> 11
    return (h + (h << 15)) & 0xffffffff


MONEY_CAT = joaat('currency_cash')                      # 2084597891
BOX_SLOT = joaat('slotid_currency_cash_container')      # slot a money box takes under an account
CASH_SLOT = joaat('slotid_currency_cash_20000')         # 4163145158
CASH_MAX = 20000
# The three large boxes (box item, money slot, capacity): Family Savings' third to fifth boxes, one numbered family with
# its first two. Under checking they show in the BuckMe app but the game does not spend from them (issue #3).
BIG_BOXES = ((0xa61b8949, joaat('slotid_currency_cash_400000'), 400000),
             (0x6ab81283, joaat('slotid_currency_cash_500000'), 500000),
             (0x88e64edf, joaat('slotid_currency_cash_1000000'), 1000000))
# Checking's own boxes in the game's fill order (box item, money slot, capacity). The slot names are unknown, the ids
# come from game-written saves. 15,000 is exact (the box sits full at 15,000). 85,000 is the capacity known so far
# (a PS5 kept it). The third box's real capacity is unknown: 123,844 is the most natural play is known to have put in
# it, so a box that already holds more counts as that much. The fourth own box, 0xdb44180c, has never held money in a
# save, so its money slot and capacity are unknown; like any other box not listed here, its money is kept as it is.
CHECKING_BOXES = ((0x26457c8e, 0x006854cf, 15000),
                  (0x33894998, 0x81cc2559, 85000),
                  (0x00fc0216, 0x9e5f7b71, 123844))
# Checking's 85,000 box takes any number of stacks: every money row under it holds up to 85,000 and the game counts them
# all, in the balance and in the limit. GarlicSaves' GTA VI editor fills a bank this way (reported tested in game), but
# no game-written save seen so far has a second row under the box, and Save Garage's stacks were never tested on a PS5:
# a player on 1.30.0 with about $2,000,000 in the bank couldn't make a phone payment with them (GitHub issue #8). So they
# may not be spendable: scan's 'max' is the own boxes, and patch only goes past them, up to 'maxStacks', for a change
# that asks with 'stacks': True. Every new row needs an Items entry, and an inventory's Items array holds at most 4,095,
# so ITEM_RESERVE entries are always left free for items the game adds later. BANK_CEILING keeps the signed 32-bit
# ledger and stats far from overflowing. Rows emptied by a lower balance stay in place (at 0) and are filled again first.
STACK_BOX, STACK_SLOT, STACK_MAX = 0x33894998, 0x81cc2559, 85000
# At most STACK_CAP extra stacks count toward the limit. A player who filled the bank to $273,630,000 (its own $100,000
# and 3,218 stacks) found the game nearly froze whenever it paid, buying or customising a weapon, until the bank went
# back to its own boxes (GitHub issue #21); a PS5 with 12 stacks ($1,000,000) ran normally. Stacks past the cap that a
# save already has (versions up to 1.32.0 made them) don't count, so any edit of such a bank brings it under the cap,
# and the rows it no longer needs are emptied.
STACK_CAP = 100
ITEM_LIMIT, ITEM_RESERVE = 4095, 300
BANK_CEILING = 999999999
# Family Savings' boxes. Under checking (where only earlier versions of this editor put them) the game does not spend from them.
SAVINGS_BOXES = {0xcfefdcf1, 0xb84a2da6} | {box for box, _, _ in BIG_BOXES}
ACCOUNTS = {
    'bank': (joaat('bank_checking'), CHECKING_BOXES),
    'savings': (joaat('bank_savings'), ((0xcfefdcf1, joaat('slotid_currency_cash_5000'), 5000),
                                        (0xb84a2da6, joaat('slotid_currency_cash_95000'), 95000)) + BIG_BOXES),
}
STAT_CASH = (552, 3273)
STAT_CHECKING, STAT_CASH_PLUS_CHECKING, STAT_SAVINGS = 262, 274, 275
SEC_INV, SEC_STAT, SEC_LEDGER = 0xd3f59a5e, 0x0635cbd9, 0x6296c122
K_MAIN, K_GUID, K_PARENT, K_ITEM, K_SLOT, K_QTY, K_FLAG = '$0xfc8f2620', '$0xb4bfeab1', '$0xc5730137', '$0xbe8e255c', '$0x12ae4287', '$0xe3fead7a', '$0x63b44f39'
K_ITEMS, K_PARENTS = '$0xabb1e011', '$0xd558e4da'
K_SUBLISTS = ('$0x6ebbccb1', '$0xc500ddf4', '$0x9098d12e', '$0x1085013f')
LEDGER_CHECKING, LEDGER_SAVINGS = '$0x1e1e8a08', '$0xf4a14422'
K_ENTRY, K_OWNER, K_DELTA, K_BALANCE = '$0x9d8e7980', '$0x6d0bd92f', '$0xa662d8be', '$0x818f6f6d'


class SaveError(Exception):
    pass


def _load(b):
    if b[:4] != b'JSAV':
        raise SaveError('not_jsav')
    n = sum(struct.unpack_from('<II', b, 8))
    ents = [list(struct.unpack_from('<IIIII', b, 16 + 20 * i)) for i in range(n)]
    secs = [b[e[3]:e[3] + e[4]] for e in ents]
    gaps = [b[ents[i][3] + ents[i][4]:ents[i + 1][3]] for i in range(n - 1)]
    end = ents[-1][3] + ents[-1][4]
    return ents, secs, gaps, b[:ents[0][3]], b[end:end + 4]


def _rebuild(head, ents, secs, gaps, tail, min_len):
    out = bytearray(head)
    for i, s in enumerate(secs):
        json.loads(s)
        ents[i][3], ents[i][4] = len(out), len(s); out += s
        if i < len(secs) - 1:
            out += gaps[i]
    out += tail
    for i, e in enumerate(ents):
        struct.pack_into('<IIIII', out, 16 + 20 * i, *e)
    out += b'\0' * ((-len(out)) % 16)
    if len(out) < min_len:
        out += b'\0' * (min_len - len(out))
    return bytes(out)


def _sec(ents, h):
    for i, e in enumerate(ents):
        if e[0] == h:
            return i
    raise SaveError('layout_changed')


# ---- edit bytes in place instead of re-serialising JSON: the game is format-sensitive, so the original text stays as it was ----

def _main(txt, nth):
    """Start of the nth inventory's main list."""
    p = txt.index(b'"$0x789bdd41":')
    for _ in range(nth + 1):
        p = txt.index(b'"%s":' % K_MAIN.encode(), p + 1)
    return p


def _array_end(txt, nth, key):
    """Position of the closing bracket of the first `key` array in the nth inventory, from the main list on."""
    return txt.index(b']', txt.index(b'"%s":' % key.encode(), _main(txt, nth)))


def _append(txt, nth, key, value):
    e = _array_end(txt, nth, key)
    return txt[:e] + b',' + value + txt[e:]


def _set(txt, span, idx, old, new):
    it = txt[span[0]:span[1]].split(b',')
    if it[idx] != str(old).encode():
        raise SaveError('verify_failed')
    it[idx] = str(new).encode()
    return txt[:span[0]] + b','.join(it) + txt[span[1]:]


def _qty_span(txt, nth):
    e = _array_end(txt, nth, K_QTY)
    return txt.rindex(b'[', 0, e) + 1, e


def _stat_span(txt):
    p = txt.index(b'"$0x97232209":'); p = txt.index(b'"$0x450ce2f0":', p)
    s = txt.index(b'[', p) + 1
    return s, txt.index(b']', s)


def _ledger_set(txt, list_key, entry_id, delta, balance, new_delta, new_balance):
    s = txt.index(b'"%s":[' % list_key.encode()); e = txt.index(b']', s)
    k = txt.rfind(b'"%s":%d,' % (K_ENTRY.encode(), entry_id), s, e)
    old = b'"%s":%d,"%s":%d}' % (K_DELTA.encode(), delta, K_BALANCE.encode(), balance)
    k = txt.find(old, k, e) if k >= 0 else -1
    if k < 0:
        raise SaveError('ledger_not_found')
    return txt[:k] + b'"%s":%d,"%s":%d}' % (K_DELTA.encode(), new_delta, K_BALANCE.encode(), new_balance) + txt[k + len(old):]


# ---- read ----

def _data(x):
    return (x.get('$data') or []) if isinstance(x, dict) else (x or [])


def _inventory(sec_txt, nth):
    inv = json.loads(sec_txt)['$0x7a47cb05']['$0xd3f59a5e']['$0x789bdd41'][nth]
    f = inv.get(K_MAIN) or {}
    v = {'guid': _data(f.get(K_GUID)), 'parent': _data(f.get(K_PARENT)), 'item': _data(f.get(K_ITEM)), 'slot': _data(f.get(K_SLOT)),
         'qty': _data(f.get(K_QTY)), 'parents': _data(inv.get(K_PARENTS))}
    v['items_n'] = len(_data(inv.get(K_ITEMS)))
    v['used'] = set(v['guid']) | set(v['parents'])
    for k in K_SUBLISTS:
        v['used'] |= set(_data((inv.get(k) or {}).get(K_GUID)))
    return v


def _children(v, row):
    """Rows of the items under row `row`."""
    g = v['guid'][row]
    if g not in v['parents']:
        return []
    p = v['parents'].index(g)
    return [r for r in range(len(v['guid'])) if v['parent'][r] == p and r != row]


def _account(v, kind):
    """Money boxes under an account: [{box, box_row, money_row or None, rows, qty, first, cap or None, foreign}], or None
    without the account. rows: every money row of the box (the 85,000 box can have many stacks), money_row the first;
    qty: their total; first: the first row's amount. foreign: a Family Savings box under checking (the game does not
    spend from it)."""
    root_item, table = ACCOUNTS[kind]
    if root_item not in v['item']:
        return None
    caps = {box: cap for box, _, cap in table}
    out = []
    for r in _children(v, v['item'].index(root_item)):
        if v['slot'][r] != BOX_SLOT:
            continue
        rows = [c for c in _children(v, r) if v['item'][c] == MONEY_CAT]
        m = rows[0] if rows else None
        out.append({'box': v['item'][r], 'box_row': r, 'money_row': m, 'rows': rows, 'qty': sum(v['qty'][c] for c in rows),
                    'first': v['qty'][m] if m is not None else 0, 'cap': caps.get(v['item'][r]),
                    'foreign': kind == 'bank' and v['item'][r] in SAVINGS_BOXES})
    return out


def _checking_caps(boxes):
    """{box: capacity} for checking's own boxes that the save has: the known capacity, or what the box already holds if more."""
    caps = {}
    for box, _, cap in CHECKING_BOXES:
        held = [x['first'] for x in boxes if x['box'] == box]
        if held:
            caps[box] = max([cap] + held)
    return caps


def _own_limit(boxes):
    """Checking within its own boxes, what shops spend from: their first rows and any other box as it is, no extra stacks."""
    return sum(_checking_caps(boxes).values()) + sum(x['qty'] for x in boxes if x['cap'] is None and not x['foreign'])


def _stack_count(boxes):
    """How many extra stacks checking's 85,000 box has: its rows after the first."""
    stack = next((x for x in boxes if x['box'] == STACK_BOX), None)
    return len(stack['rows'][1:]) if stack else 0


def _box_limit(boxes):
    """Checking without new stacks: its own boxes and the stacks it already has."""
    return _own_limit(boxes) + STACK_MAX * _stack_count(boxes)


def _new_stacks(boxes, items_n):
    """How many new 85,000 stacks fit: Items entries left above the reserve, less the rows the own boxes still need.
    None when the save has no 85,000 box (the game adds it later in the story; Save Garage never adds one)."""
    if not any(x['box'] == STACK_BOX for x in boxes):
        return None
    need = sum(1 for box in _checking_caps(boxes) for x in boxes if x['box'] == box and x['money_row'] is None)
    return max(0, ITEM_LIMIT - ITEM_RESERVE - items_n - need)


def _limit(kind, boxes, items_n=0):
    """The most an account can hold. Checking with stacks (scan's 'maxStacks'): the capacity of the own boxes the save has
    (it gets no new boxes) and of the stacks it has, plus 85,000 for every stack that still fits under its 85,000 box,
    with at most STACK_CAP stacks in all and at most BANK_CEILING. Savings: every box it can have, since missing ones are
    added."""
    if kind == 'bank':
        have = _stack_count(boxes)
        lim = _own_limit(boxes) + STACK_MAX * min(have, STACK_CAP)
        n = _new_stacks(boxes, items_n)
        if n:
            n = min(n, max(0, STACK_CAP - have))
            lim = max(min(lim + STACK_MAX * n, BANK_CEILING), lim)
        return lim
    return sum(cap for _, _, cap in ACCOUNTS[kind][1]) + sum(x['qty'] for x in boxes if x['cap'] is None)


def scan(b):
    ents, secs, _, _, _ = _load(b)
    inv_txt = secs[_sec(ents, SEC_INV)]
    n_inv = len(json.loads(inv_txt)['$0x7a47cb05']['$0xd3f59a5e']['$0x789bdd41'])
    items = []
    for n in range(n_inv):
        v = _inventory(inv_txt, n)
        if not v['qty']:
            continue
        seen = set()
        for kind in ('bank', 'savings'):
            boxes = _account(v, kind)
            rows = [x['money_row'] for x in boxes or [] if x['money_row'] is not None]
            if not rows:
                continue
            seen |= {r for x in boxes for r in x['rows']}
            item = {'inv': n, 'idx': rows[0], 'type': v['slot'][rows[0]], 'kind': kind, 'value': sum(x['qty'] for x in boxes),
                    'max': _own_limit(boxes) if kind == 'bank' else _limit(kind, boxes, v['items_n'])}
            if kind == 'bank':      # value is what the BuckMe app shows; spendable is all but stuck, the Family Savings boxes
                item['maxStacks'] = _limit(kind, boxes, v['items_n'])     # with extra 85,000 stacks, for a change that asks
                item['spendable'] = sum(x['qty'] for x in boxes if not x['foreign'])
                item['stuck'] = item['value'] - item['spendable']
                item['boxMax'] = _box_limit(boxes)        # above this, the balance goes into new 85,000 stacks
                item['stacks'] = sum(len(x['rows'][1:]) for x in boxes if x['box'] == STACK_BOX)
                item['stackCap'] = STACK_CAP              # the most extra stacks maxStacks counts
                foreign = [x for x in boxes if x['foreign']]  # Family Savings boxes an old version put under the bank
                caps = {box: cap for box, _, cap in ACCOUNTS['savings'][1]}
                item['foreignBoxes'] = len(foreign)
                item['extraLimit'] = sum(caps.get(x['box'], 0) for x in foreign)   # what they add to BuckMe's limit
            items.append(item)
        for k, q in enumerate(v['qty']):
            if v['item'][k] == MONEY_CAT and k not in seen:
                cash = v['slot'][k] == CASH_SLOT
                items.append(dict({'inv': n, 'idx': k, 'type': v['slot'][k], 'kind': 'cash' if cash else 'other', 'value': q}, **({'max': CASH_MAX} if cash else {})))
    items.sort(key=lambda x: (x['inv'], x['idx']))
    st = json.loads(secs[_sec(ents, SEC_STAT)])['$0x7a47cb05']['$0x0635cbd9']['$0x97232209']
    stats = st['$0x450ce2f0']['$data']
    info = {'items': items, 'stats': stats, 'statIds': st['$0x92f37a48']['$data'], 'statChars': st['$0x46be9d78']['$data'],
            'statCash': [stats[i] for i in STAT_CASH], 'ledger': None, 'savings': None, 'ledgers': {}, 'ledger_last': None}
    try:
        book = json.loads(secs[_sec(ents, SEC_LEDGER)])['$0x24d043f2']['$0x6296c122']['$0x45a134ec']
        for l in book[LEDGER_CHECKING]:                     # both protagonists' checking entries are mixed; take the last one of each
            info['ledgers'][l[K_OWNER] - 0xc0000002] = {'entry': l[K_ENTRY], 'amount': l[K_DELTA], 'balance': l[K_BALANCE]}
        info['ledger'] = info['ledgers'].get(0)
        both = [l for l in book[LEDGER_CHECKING] if l[K_OWNER] in (0xc0000002, 0xc0000003)]
        if both:                                            # one running balance for the shared account: the newest entry of either
            l = max(both, key=lambda l: l[K_ENTRY])
            info['ledger_last'] = {'entry': l[K_ENTRY], 'amount': l[K_DELTA], 'balance': l[K_BALANCE]}
        l = book[LEDGER_SAVINGS][-1]
        info['savings'] = {'entry': l[K_ENTRY], 'amount': l[K_DELTA], 'balance': l[K_BALANCE]}
    except Exception:
        pass
    return info


def same_item(item, change):
    return item.get('src', 'inv') == change.get('src', 'inv') and item['inv'] == change['inv'] and item['idx'] == change['idx']


# ---- edit ----

def _fresh_guid(v):
    g = max(v['guid']) + 1
    while g in v['used']:
        g += 1
    v['used'].add(g)
    return g


def _add_row(txt, nth, v, parent_idx, item, slot, qty, equipped=False):
    """Add a row to the main list and register it in Items; returns (new text, row, Guid). Money rows are not
    equipped; a gun's kit and parts are (guns.py)."""
    g = _fresh_guid(v); row = len(v['guid'])
    for key, val in ((K_GUID, g), (K_PARENT, parent_idx), (K_ITEM, item), (K_SLOT, slot), (K_QTY, qty)):
        txt = _append(txt, nth, key, b'%d' % val)
    txt = _append(txt, nth, K_FLAG, b'true' if equipped else b'false')
    txt = _append(txt, nth, K_ITEMS, b'%d' % ((row << 4) | 1))
    return txt, row, g


def _parent_index(txt, nth, guid):
    """Index of a Guid in ParentGuids, appended when missing."""
    v = _inventory(txt, nth)
    if guid in v['parents']:
        return txt, v['parents'].index(guid)
    return _append(txt, nth, K_PARENTS, b'%d' % guid), len(v['parents'])


def _set_account(txt, nth, kind, target):
    """Set an account total to target: fill existing boxes first, then add boxes from smallest to largest.
    Checking is filled only in its own boxes, in the game's order, and gets no new boxes. Boxes under it that are not its
    own (left by earlier versions) are emptied, since the game does not spend from them."""
    root_item, table = ACCOUNTS[kind]
    boxes = _account(_inventory(txt, nth), kind)
    left = target - sum(x['qty'] for x in boxes if x['cap'] is None and not x['foreign'])
    if left < 0:
        raise SaveError('out_of_range')
    v = _inventory(txt, nth)
    zero = {r: (v['qty'][r], 0) for x in boxes if x['foreign'] for r in x['rows'] if v['qty'][r]}
    if zero:
        txt = _set_many(txt, _qty_span(txt, nth), zero)
    own = _checking_caps(boxes) if kind == 'bank' else None
    for box, slot, cap in table:
        if own is not None:
            if box not in own:
                continue                # the game adds checking's boxes as the story raises the limit; one it has not added may not count
            cap = own[box]
        amount = min(cap, left); left -= amount
        v = _inventory(txt, nth)
        cur = next((x for x in _account(v, kind) if x['box'] == box), None)
        if cur and cur['money_row'] is not None:
            if cur['first'] != amount:
                txt = _set(txt, _qty_span(txt, nth), cur['money_row'], cur['first'], amount)
            continue
        if not amount:
            continue
        if cur:
            box_guid = v['guid'][cur['box_row']]
        else:
            txt, root_idx = _parent_index(txt, nth, v['guid'][v['item'].index(root_item)])
            txt, _, box_guid = _add_row(txt, nth, _inventory(txt, nth), root_idx, box, BOX_SLOT, 1)
        txt, box_idx = _parent_index(txt, nth, box_guid)
        txt, _, _ = _add_row(txt, nth, _inventory(txt, nth), box_idx, MONEY_CAT, slot, amount)
    if kind == 'bank':
        txt, left = _fill_stacks(txt, nth, left)
    if left:
        raise SaveError('out_of_range')
    return txt


def _set_many(txt, span, changes):
    """Several values of one comma list at once: changes {idx: (old, new)}, each old value checked."""
    it = txt[span[0]:span[1]].split(b',')
    for idx, (old, new) in changes.items():
        if it[idx] != str(old).encode():
            raise SaveError('verify_failed')
        it[idx] = str(new).encode()
    return txt[:span[0]] + b','.join(it) + txt[span[1]:]


def _add_rows(txt, nth, v, parent_idx, item, slot, amounts):
    """Add one main-list row per amount, all under the same parent and each registered in Items."""
    row0, guids, g = len(v['guid']), [], max(v['used']) + 1
    for _ in amounts:
        while g in v['used']:
            g += 1
        if g >= 2 ** 63:
            raise SaveError('out_of_range')
        v['used'].add(g); guids.append(g)
    n = len(amounts)
    for key, vals in ((K_GUID, [b'%d' % x for x in guids]), (K_PARENT, [b'%d' % parent_idx] * n), (K_ITEM, [b'%d' % item] * n),
                      (K_SLOT, [b'%d' % slot] * n), (K_QTY, [b'%d' % q for q in amounts]), (K_FLAG, [b'false'] * n),
                      (K_ITEMS, [b'%d' % (((row0 + k) << 4) | 1) for k in range(n)])):
        txt = _append(txt, nth, key, b','.join(vals))
    return txt


def _remove_rows(txt, nth, rows):
    """Take main-list rows out of the nth inventory the way the game keeps the list: the six parallel arrays lose the
    rows, Items loses their entries and renumbers the main-list entries after them ((row << 4) | 1; the sublists' entries,
    with other low bits, stay as they are), and ParentGuids loses the entries no remaining row points to any more, with
    every ParentGuidIndices value (main list and sublists) renumbered. In every game-written save each ParentGuids entry
    is used by some row and Items lists each row once (dev_scratch/check_row_removal.py), so the result keeps both.
    Refused (layout_changed) when a row outside `rows` still hangs under a removed one, or the arrays don't line up."""
    import featurelib as fl                     # imported here: featurelib imports this module
    rows = set(rows)
    if not rows:
        return txt
    s, _ = fl.walk(txt, '$0x7a47cb05', '$0xd3f59a5e', '$0x789bdd41')
    inv_s, _ = fl.elements(txt, s)[nth]
    inv = {k: (vs, ve) for k, vs, ve in fl.members(txt, inv_s)}

    def span(vs, ve):
        """(start, end) of an array's comma list inside a plain list or a typed {"$data": [...]} object, or None."""
        if txt[vs:vs + 1] == b'[':
            return vs + 1, ve - 1
        m = {k: (a, z) for k, a, z in fl.members(txt, vs)}
        return (m['$data'][0] + 1, m['$data'][1] - 1) if '$data' in m else None

    def toks(sp):
        return [] if sp is None or sp[0] == sp[1] else txt[sp[0]:sp[1]].split(b',')

    main = {k: span(vs, ve) for k, vs, ve in fl.members(txt, inv[K_MAIN][0])}
    keys = (K_GUID, K_PARENT, K_ITEM, K_SLOT, K_QTY, K_FLAG)
    if set(main) != set(keys) or any(main[k] is None for k in keys):
        raise SaveError('layout_changed')
    cols = {k: toks(main[k]) for k in keys}
    n = len(cols[K_GUID])
    if any(len(c) != n for c in cols.values()) or not rows <= set(range(n)):
        raise SaveError('layout_changed')
    subs = []                                   # (span, tokens) of each sublist's ParentGuidIndices
    for k in K_SUBLISTS:
        if k in inv and txt[inv[k][0]:inv[k][0] + 1] == b'{':
            m = {kk: (a, z) for kk, a, z in fl.members(txt, inv[k][0])}
            if K_PARENT in m:
                sp = span(*m[K_PARENT])
                subs.append((sp, toks(sp)))
    items_sp, parents_sp = span(*inv[K_ITEMS]), span(*inv[K_PARENTS])
    items, parents = toks(items_sp), toks(parents_sp)
    gone = {int(cols[K_GUID][r]) for r in rows}
    gone_idx = {i for i, g in enumerate(parents) if int(g) in gone}
    keep = [r for r in range(n) if r not in rows]
    kept_refs = {int(cols[K_PARENT][r]) for r in keep} | {int(x) for _, t in subs for x in t}
    if kept_refs & gone_idx or any(not 0 <= i < len(parents) for i in kept_refs):
        raise SaveError('layout_changed')         # something else still hangs under a removed row
    before = kept_refs | {int(cols[K_PARENT][r]) for r in rows}
    drop = gone_idx | (before - kept_refs)
    new_idx, k = {}, 0
    for i in range(len(parents)):
        if i not in drop:
            new_idx[i] = k; k += 1
    shift = sorted(rows)

    def new_row(r):
        lo, hi = 0, len(shift)
        while lo < hi:
            mid = (lo + hi) // 2
            if shift[mid] < r: lo = mid + 1
            else: hi = mid
        return r - lo

    new_items, seen = [], []
    for x in items:
        v = int(x)
        if v & 0xf == 1:
            if v >> 4 in rows:
                continue
            nr = new_row(v >> 4)
            seen.append(nr)
            new_items.append(b'%d' % ((nr << 4) | 1))
        else:
            new_items.append(x)
    if sorted(seen) != list(range(len(keep))):
        raise SaveError('layout_changed')         # Items didn't list each main row exactly once
    edits = []
    for key in keys:
        vals = [cols[key][r] for r in keep]
        if key == K_PARENT:
            vals = [b'%d' % new_idx[int(x)] for x in vals]
        edits.append((main[key], b','.join(vals)))
    for sp, t in subs:
        if sp is not None:
            edits.append((sp, b','.join(b'%d' % new_idx[int(x)] for x in t)))
    edits.append((items_sp, b','.join(new_items)))
    edits.append((parents_sp, b','.join(parents[i] for i in range(len(parents)) if i not in drop)))
    for (a, z), new in sorted(edits, key=lambda e: -e[0][0]):     # from the end, so earlier spans stay valid
        txt = txt[:a] + new + txt[z:]
    json.loads(txt)
    return txt


def _remove_foreign(txt, nth):
    """Take the Family Savings boxes that versions before 1.24 put under checking out of the bank account, with their
    money rows (GitHub issue #19). The game counts every box under an account in its limit, an empty one too, so they
    left BuckMe's limit up to $1,900,000 too high. Only empty boxes go: setting the bank first moves any money out of
    them. Returns (text, the boxes taken out)."""
    v = _inventory(txt, nth)
    boxes = [x for x in (_account(v, 'bank') or []) if x['foreign']]
    if not boxes:
        return txt, []
    if any(v['qty'][r] for x in boxes for r in x['rows']):
        raise SaveError('verify_failed')
    for x in boxes:
        if set(_children(v, x['box_row'])) - set(x['rows']):
            raise SaveError('layout_changed')     # only its money rows may hang under a box
    rows = [x['box_row'] for x in boxes] + [r for x in boxes for r in x['rows']]
    return _remove_rows(txt, nth, rows), boxes


def _fill_stacks(txt, nth, left):
    """Put what is left into checking's extra 85,000 stacks: the rows under the 85,000 box after its first, in order
    (emptied when nothing is left), then new rows under the box. Returns (text, what still did not fit)."""
    v = _inventory(txt, nth)
    stack = next((x for x in _account(v, 'bank') or [] if x['box'] == STACK_BOX), None)
    if stack is None:
        return txt, left
    changes = {}
    for r in stack['rows'][1:]:
        amount = min(STACK_MAX, left); left -= amount
        if v['qty'][r] != amount:
            changes[r] = (v['qty'][r], amount)
    if changes:
        txt = _set_many(txt, _qty_span(txt, nth), changes)
    n = -(-left // STACK_MAX)
    if n <= 0:
        return txt, left
    if _inventory(txt, nth)['items_n'] + n > ITEM_LIMIT - ITEM_RESERVE:
        return txt, left
    txt, box_idx = _parent_index(txt, nth, v['guid'][stack['box_row']])
    amounts = [STACK_MAX] * (n - 1) + [left - STACK_MAX * (n - 1)]
    return _add_rows(txt, nth, _inventory(txt, nth), box_idx, MONEY_CAT, STACK_SLOT, amounts), 0


def patch(b, changes):
    """changes: [{inv, idx, value (old), newValue, stacks (optional, true or false), repair (optional, true or false)}]
    -> (new file bytes, log). Values above the limit are written as the limit: 'max', or for the bank with 'stacks': True,
    'maxStacks', its extra 85,000 stacks included. A lower bank balance is always allowed, and empties the extra stacks
    it no longer needs. 'repair': True (bank only) also takes the Family Savings boxes an old version put under the bank
    out of it (_remove_foreign), so BuckMe's limit is the game's again; with the same total it changes nothing else."""
    ents, secs, gaps, head, tail = _load(b)
    info = scan(b); log = []
    i_inv, i_stat = _sec(ents, SEC_INV), _sec(ents, SEC_STAT)

    def stat(si, old, new):
        secs[i_stat] = _set(secs[i_stat], _stat_span(secs[i_stat]), si, old, new)

    for ch in changes:
        it = next((x for x in info['items'] if same_item(x, ch)), None)
        if not it or it['value'] != ch['value']:
            raise SaveError('stale_item')
        stacks, repair = ch.get('stacks', False), ch.get('repair', False)
        if not isinstance(stacks, bool) or not isinstance(repair, bool) or (repair and it['kind'] != 'bank'):
            raise SaveError('bad_request')
        nv = int(round(ch['newValue']))
        if not 0 <= nv <= 2147483647:
            raise SaveError('out_of_range')
        lim = it.get('max', nv)
        if stacks:                  # the bank's extra stacks, asked for (other kinds have no maxStacks)
            lim = it.get('maxStacks', lim)
        nv = min(nv, lim); old = it['value']
        if nv == old and not it.get('stuck'):      # same total, but money the game cannot spend still has to be moved
            if repair:
                secs[i_inv], gone = _remove_foreign(secs[i_inv], it['inv'])
                if gone:
                    log.append({'what': 'inventory', 'kind': 'bank_repair', 'from': it.get('extraLimit', 0), 'to': 0,
                                'label': 'BuckMe limit fixed', 'boxes': len(gone)})
            continue
        if it['kind'] in ACCOUNTS:
            secs[i_inv] = _set_account(secs[i_inv], it['inv'], it['kind'], nv)
            if repair:
                secs[i_inv], gone = _remove_foreign(secs[i_inv], it['inv'])
                if gone:
                    log.append({'what': 'inventory', 'kind': 'bank_repair', 'from': it.get('extraLimit', 0), 'to': 0,
                                'label': 'BuckMe limit fixed', 'boxes': len(gone)})
        else:
            secs[i_inv] = _set(secs[i_inv], _qty_span(secs[i_inv], it['inv']), it['idx'], old, nv)
        log.append({'what': 'inventory', 'kind': it['kind'], 'from': old, 'to': nv})
        ids, chars, vals = info['statIds'], info['statChars'], info['stats']
        if it['kind'] == 'bank':
            spend = it.get('spendable', old)    # the game writes stat 262 from checking's own boxes: after an earlier edit it is this, not old
            for si, sid in enumerate(ids):                  # stats owners 1 / 2 are inventories 0 / 1
                if chars[si] != it['inv'] + 1:
                    continue
                if sid == STAT_CHECKING and vals[si] in (old, spend):
                    stat(si, vals[si], nv); log.append({'what': 'stat_bank'})
                elif sid == STAT_CASH_PLUS_CHECKING and vals[si] >= spend:
                    basis = old if vals[si] >= old else spend
                    stat(si, vals[si], vals[si] - basis + nv); log.append({'what': 'stat_bank'})
            led = info['ledger_last']
            if led:     # the newest ledger entry's balance must equal checking (the account is shared); also fixes mismatches left by older inventory-only edits
                i_led = _sec(ents, SEC_LEDGER)
                secs[i_led] = _ledger_set(secs[i_led], LEDGER_CHECKING, led['entry'], led['amount'], led['balance'], led['amount'] + nv - led['balance'], nv)
                log.append({'what': 'ledger'})
            else:
                log.append({'what': 'ledger_skipped'})
        elif it['kind'] == 'savings':
            for si, sid in enumerate(ids):
                if sid == STAT_SAVINGS and vals[si] == old:
                    stat(si, old, nv); log.append({'what': 'stat_savings'})
            sav = info['savings']
            if sav:
                i_led = _sec(ents, SEC_LEDGER)
                secs[i_led] = _ledger_set(secs[i_led], LEDGER_SAVINGS, sav['entry'], sav['amount'], sav['balance'], sav['amount'] + nv - sav['balance'], nv)
                log.append({'what': 'savings_ledger'})
        elif it['kind'] == 'cash':
            for j, si in enumerate(STAT_CASH):
                if info['statCash'][j] == old:
                    stat(si, old, nv); log.append({'what': 'stat_cash'})
    return _rebuild(head, ents, secs, gaps, tail, len(b)), log
