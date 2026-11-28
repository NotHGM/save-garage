# Local API

Save Garage serves its web UI and a JSON API from the same address, `http://127.0.0.1:7283` by default. Requests
are accepted only from allowed client networks (this computer by default) with a matching `Host` header, and POST
bodies are JSON. Long tasks run in the background: a POST returns at once and progress appears in `state.job`.

## GET /api/state

The whole app state, polled about once a second by the UI.

```jsonc
{
  "console": {"host": "192.168.1.20", "name": "PS5", "hostId": "AABBCCDDEEFF", "firmware": "14230000", "sameSubnet": true} | null,
  "paired": true,
  "network": {"ok": true, "proxy": false} | null,     // set after POST /api/network
  "hasSession": true,                                 // a save has been downloaded
  "readyToUpload": false,                             // edits are saved and waiting to be sent
  "slots": [{
    "file": "sdimg_SAVEDATASARC0001",                 // or sdimg_sce_sdmemory, the autosave
    "subtitle": "Mission name",
    "items": [{"inv": 0, "idx": 384, "kind": "bank", "value": 85000, "max": 223844, "maxStacks": 8723844, "spendable": 85000,
               "stuck": 0, "boxMax": 223844, "stacks": 0, "stackCap": 100, "foreignBoxes": 0, "extraLimit": 0}],
    "ammo": [{"inv": 0, "idx": 120, "type": "rifle", "label": "Assault rifle ammo", "value": 280, "full": 300, "max": 300}],
    "modified": false,
    "changes": [{"kind": "bank", "from": 5000, "to": 85000}],
    "applied": {"money": [], "ammo": [], "stats": []} | null
  }],
  "job": {"id": 3, "kind": "download", "status": "running", "stage": "need_power", "needPower": true,
          "progress": {"files": 2, "total": 5} | null, "hint": null, "error": null, "wait": null, "log": []},
  "skipped": [{"file": "sdimg_SAVEDATASARC0003", "subtitle": "Mission name", "why": "damaged"}],   // story saves left out: "damaged" or "layout"
  "users": [{"id": "1447854d", "name": "Name"}],   // the users of the PS5 the session came from (its transfer data)
  "fileCount": 11,                                    // saves of the downloaded account, all of which go back to the PS5
  "version": "1.33.1",
  "canQuit": false,                                   // true in the desktop builds
  "update": {"auto": true, "mode": "install", "why": null, "flavour": "windows", "status": "ready", "current": "1.30.0",
             "latest": "1.30.1", "error": null, "progress": null, "total": null, "checked": 1795651200, "installed": null,
             "notes": "https://github.com/NotHGM/save-garage/releases/tag/v1.30.1", "canRestart": true, "restarting": false},
  "garlic": {"signedIn": true, "username": "name", "stored": true, "devKey": false, "refused": false,
             "signin": {"status": "idle", "code": null, "link": null, "expiresIn": null, "error": null, "http": null}}
}
```

`update` is the updater's state; see [Updates](#updates) below. `garlic` is the GarlicSaves sign-in; see
[Signing in to GarlicSaves](#signing-in-to-garlicsaves).

## GET /api/slot?file=…

Editor data for one save: featured stats with the exact rows to edit, ammo and the weapons each character carries.
For the bank, `max` is what the bank's own money boxes hold at this point in the story, which shops spend from; an edit
goes no higher unless it asks for the extra stacks (`stacks`, under `/api/patch` below). `maxStacks` is the limit with
them: a $85,000 stack under the bank's $85,000 box for every inventory slot left above the 300 kept free, at most
`stackCap` (100) stacks in all, and equal to `max` when the save has no $85,000 box yet. The stacks are experimental
and may not be spendable (issue #8), and thousands of them made the game nearly freeze whenever it paid (issue #21);
stacks past the cap that a bank already has don't count, so `value` can be above `maxStacks` until it is edited.
`stacks` counts the extra stacks the bank already has, and `boxMax`, kept for compatibility, is
where new stacks would start: `max` plus $85,000 for each of them (equal to `max` without any). `stuck` is money an older
version left in Family Savings boxes under the bank (shown by BuckMe, not spendable; editing the bank moves it),
`foreignBoxes` counts those boxes and `extraLimit` is how much they add to BuckMe's limit even when empty (issue #19), and
`spendable` is the rest of `value`, extra stacks included. Without `stuck` money, a `value` above `max` is money in extra
stacks, as versions 1.26.0 to 1.30.0 wrote it, or as the experimental option wrote it since 1.30.1.
For ammo, `full` is a full load in the game (`null` where it isn't known) and `max` is the most Save Garage writes: the
full load where it's known (a PS5 cut larger amounts back to it), otherwise 9,999.
Each weapon is
`{"inv": 0, "id": "5dd5e66d", "name": "weaponspec_autorifle_assault_default", "label": "Kozlov KZ-59", "kind": "Assault rifle"}`:
`label` is what the game calls it (empty while the weapon isn't identified) and `kind` is the type of weapon when the
label doesn't say it.

`guns` lists the guns each character can be given (`null`, with the reason in `errors.guns`, when the save can't show
them): `characters`, one per character (`key` `lucia` or `jason`, `name`), with `problem` (a refusal code, below, while
no gun can be added), `items` (the inventory's Items entries) and `itemsFree` (entries left above the 300 kept free),
and three lists of guns: `offered` (can be added), `owned` (already there) and `left` (a grenade or sticky bomb whose
ammo the character has without the weapon, a state no save has shown, so it is left alone). Each gun is
`{"id": "5ea6e528", "name": "weaponspec_smg_heavy_default", "label": "BZI Vatra", "kind": "Heavy SMG", "rows": 11,
"thrown": false, "ammo": null, "discovered": true}`: `rows` is the inventory entries it takes, `ammo` the grenades or
sticky bombs that come with a thrown weapon, `discovered` whether the compendium lists it already. `notOffered` names,
per character, the guns seen in game saves that can't be added yet, and `itemLimit` and `itemReserve` are 4,095 and 300.

## GET /api/stats?file=…

Every stat in the save as compact columns per typed group (`base`, `qual`, `owner`, `value`), the readable names
that are known, the rows that change between the downloaded saves (`varies`) and the protected rows.

## GET /api/completion?file=…

Everything the Completion tab shows, one key per part: `stunts`, `compendium`, `discovery`, `challenges`, `gyms`,
`activities`, `checklist` (the game's 100% checklist: `lines` with `key`, `label`, `section`, `value`, `of`, `percent`,
`weight`, `grade`, `module`, `done`, plus `overall`), `tasks`, `gangs`, `robberies`, `fencing`, `activities2`, `hoops`,
`vehicles`, `collectibles` and `cheats`. A part a save can't show yet (an early save lacks some records) is `null`, and
`errors` says why, so the other parts still work.

`cheats` is the cheat unlock trackers (challenge set `d6d53427`, 62 records): `done` of `of` complete, `problem` (a
refusal code, then `entries` is empty) and `entries` in the order the tab lists them. Each entry is one pick:
`{"key": "0c7d4ae2", "kind": "single" | "pair" | "unmatched", "ids": ["0c7d4ae2"], "done": 0, "of": 1, "cheats":
[{"name": "Super Jump", "effect": "Increases the height of your jump by 10x with no fall damage.", "unlock": "Jump a
vehicle 15 meters or more over a drawbridge 50 times."}]}`. `effect` and `unlock` are the game's words; `name` is the
game's name for the cheat where its text has one that plainly matches, else `null`. A `pair` is a challenge category's
two trackers (5 challenges and all of them), which the save can't tell apart; `unmatched` is the 23 trackers that held
no progress in any save checked, with the 23 cheats they are between them.

## GET /api/world?file=…

The time of day (`clock`), `health` and `healthMax` (250, the game's overpowered maximum), and the armour of both
characters' outfits (`armour`, `armourMax`). Two more parts are read on their own; one a save can't show is `null`,
and `errors` says why:

- `player`: `characters`, one per character (`key` `lucia` or `jason`, `name`), with `meter` (attribute slot 24),
  `skills` (the values of slots 9, 10, 13, 14, 15, 19, 20 and 35), `profile` (the criminal profile score),
  `attributesProblem` (a refusal code when the attributes can't be edited) and `vest`
  (`{"state": "can_add" | "worn" | "no_vest" | "unknown", "armour", "max", "owned"}`); `relationship` (`value`,
  `lowerCap` and `cap`, the range the story allows now, `level`, `locked`, `disabled` and `problem`, a refusal code
  while it can't be changed); and the limits: `meterFull` (100), `skillMin` and `skillMax` (1 and 99),
  `skillChoices` (60 and 99), `profileMin` and `profileMax` (-100 and 0.25), `profileNewGame` (-25), `vestArmour` (150).
- `levels`: `characters`, one per character (`key`, `name` and `levels`: `muscle` (strength), `cardio` and `focus`, each
  `{"value", "stat", "max"}`, counted from 0 as the save keeps them: `value` is the level the game reads, `stat` the
  copy in the stats, `max` 4 for strength and 3 for the others); `max` and `problem` (a refusal code).
- `growth`: `characters`, one per character (`key`, `name` and `capacities`: `healthmax`, `staminamax`,
  `meleestaminamax` and `specialabilitymax`, each `{"value", "label", "max", "consistent"}`); `max` (100) and
  `problem` (a refusal code). `consistent` says whether the save's four copies of that capacity agree.
- `fog`: the map's fog of war. `regions` uncovered in the save (`named` and `cells`), `known` (the 722 regions Save
  Garage knows: `knownNamed` 52, `knownCells` 670), `mapTotal` (889), `missing` (known regions the save still lacks),
  `unknown` (regions in the save that Save Garage doesn't know, kept as they are) and `problem` (a refusal code).

## GET /api/savedata?file=…[&section=…&path=…&offset=…]

Without `section`: every section of the save (`hash`, `name` where known, `bytes`, `readOnly` reason, `risky`).
With `section` and a JSON `path`: up to 200 members of that object or list, each with its `key`, `label`, `kind` and
`raw` value, or `count` for an object or list. `means` names what a value stands for when it is the ID of something
known (`{"kind": "Item", "text": "…"}`), and `readOnly` or `min` and `max` mark single fields with their own rule,
the same limits the World tab keeps to: maximum health is read-only; health is 1 to 250; the criminal profile is -100
to 0.25; the relationship stays within the story's caps and is read-only while the story has it locked or switched
off, and those caps and flags are read-only themselves; the skill slots of a character's attributes go up to 99 and
slot 24 to 100; an armour part's fArmour goes up to its fMaxArmour, and fMaxArmour up to 150. FogOfWar is read-only
(the World tab reveals the map), and so is ScriptCharacterPhysique (the World tab sets the levels in it).

## POST endpoints

| Path | Body | What it does |
|---|---|---|
| `/api/network` | none | Checks that GarlicSaves is reachable |
| `/api/discover` | none | Searches the network for PS5 consoles |
| `/api/console` | `{"host": "192.168.1.20"}` | Selects a console |
| `/api/pair` | none | Starts pairing (once per console) |
| `/api/download` | none | Downloads, backs up and decrypts the GTA VI saves |
| `/api/choose-account` | `{"owner": "<account id>"}` | Answers the download's question when several PS5 accounts have a GTA VI save: while the job's stage is `choose_account`, `job.accounts` lists `{id, name, saves}` and only those ids are accepted |
| `/api/stunt-edits` | `{"file": "…", "groups": ["jumps", "base", "bridges"]}` | The stat edits that mark those stunt types found and completed, for the page to add to `stats` |
| `/api/preview` | `{"file": "…", "stats": [...], "completion": {...}, "guns": {...}}` | Works out the 100% checklist as it would be after these edits, without writing anything: `{"ok": true, "overall": {...}, "lines": [{key, value, of, percent, done}]}`, or `{"ok": false, "failed": [part names]}` naming the parts that fail on this save (`guns` among them) |
| `/api/patch` | `{"slot": "…", "money": [...], "ammo": [...], "stats": [...], "guns": {...}, "completion": {...}, "world": {...}, "raw": [...]}` | Applies every edit for one save to its original, re-encrypts it and gets it ready to send. `guns` the Ammo tab's guns to add (below), `completion` holds one choice per part (see the Completion tab, and the cheats below), `world` the World tab's edits (below), `raw` single Save data values |
| `/api/restore` | none | Puts the original saves back, ready to send |
| `/api/upload` | none | Starts sending the save back to the PS5 |
| `/api/cancel` | none | Stops the current task |
| `/api/quit` | none | Closes Save Garage (refused while a transfer is running) |
| `/api/update/check` | none | Checks GitHub for a new version now, in the background (a check less than 10 s after the last one, or while one runs, is skipped). Answers `state.update` |
| `/api/update/settings` | `{"auto": false}` | Turns automatic updates on or off, saved as `autoUpdate` in `config.json` in the data folder (its other settings are kept). Turning them off ends a download in progress and drops a staged update. Answers `state.update` |
| `/api/update/restart` | none | Starts Save Garage again, so the staged update installs; answers `{"ok": true}` first. Refused with `busy` while a task runs and `no_update` when nothing is staged |
| `/api/signin` | none | Starts signing in to GarlicSaves, in the background, or goes on with the sign-in under way. Answers `state.garlic` |
| `/api/signin/cancel` | none | Stops the sign-in under way; a key GarlicSaves gives after that isn't kept. Answers `state.garlic` |
| `/api/signout` | none | Forgets the GarlicSaves sign-in on this computer: its entry in `config.json` and its key. Refused with `busy` while a task runs. Answers `state.garlic` |

Each edit names the value it replaces (`value`) and the new one (`newValue`); an edit whose `value` no longer matches
the save is refused. A money edit is `{"inv": 0, "idx": 384, "value": 85000, "newValue": 223844}`, and a value above the
item's `max` is written as `max`. A bank edit with `"stacks": true` goes up to `maxStacks` instead, putting what is past
the bank's own boxes in extra $85,000 stacks (experimental: the game may not let you spend them); `stacks` must be `true`
or `false` (HTTP 400 otherwise). A lower bank balance is always written and empties the stacks it no longer needs, so an
edit without `stacks` brings a bank that is in stacks back within its own boxes. `"repair": true` on a bank change (`true`
or `false`, bank only) also takes those Family Savings boxes and their money rows out of the bank once they are empty,
so BuckMe's limit is the game's own again; with the same amount it changes nothing else. Errors come back as HTTP 409
`{"error": "<code>", "detail": "…"}`. `/api/pair`, `/api/download`, `/api/patch` and `/api/upload` go through
GarlicSaves and are refused with `not_signed_in` until Save Garage is signed in.

### Download errors

A download that fails ends with `job.status` `error` and `job.error` `{"code": "…", "detail": "…"}`, where `detail` is
the transfer code's own error, such as `TimeoutError: timed out`. Save Garage sends its GarlicSaves jobs with the
worker key of its GarlicSaves sign-in, and GarlicSaves takes only so many jobs a minute from one key. A transfer-key
request it turns down decides the code, since the transfer code can't go on without those keys: `key_rate_limited` when
it answered 429 (rate limited) and `key_disabled` when it answered 401, or 403 from its API (a Cloudflare 403 page
doesn't count): the sign-in was turned off or has expired, or key requests are turned off for its key. Their `detail` is
the derivation's line below rather than the closed connection the transfer code saw. Pairing and sending back end the
same way when one of their key requests is turned down. Once a request is refused no more go out for that derivation,
and while a rate limit is known (its Retry-After, else 60 s) no hedged request does.

Otherwise a timeout gets its code from when it came and from what GarlicSaves' key service did: `power_timeout` while
the power prompt was up (stage `need_power`), `key_timeout` when a transfer-key derivation didn't give the transfer code
its keys within its 30 s wait (it gave up, was still waiting or answered later), and `console_timeout` otherwise, for a
PS5 that didn't answer.

Before the power prompt, with nothing downloaded yet, the download starts once more by itself: 5 s after a
`key_timeout` (stage `key_retry`), and after a `key_rate_limited` once the Retry-After GarlicSaves gave is over (60 s
when it gave none, 75 s at most; stage `key_rate_wait`). Meanwhile `job.wait` holds the seconds left and `/api/cancel`
ends the download. A second failure, a `key_disabled` and any failure after the power prompt end it. Decrypting the
saves at the end of a download, and encrypting edits (`/api/patch`), use the same key: a decrypt or encrypt job
GarlicSaves turns down ends with `garlic_rate_limited` (429) or `garlic_key_disabled` (401, or 403 from its API),
without an automatic retry, and a `detail` such as `GarlicSaves is limiting requests (HTTP 429, retry after 60 s)`. A 401
or 403 also sets `state.garlic.refused`, so the page says the sign-in was refused and offers to sign in again. The other
codes are `not_paired`, `not_signed_in`, `garlic_unreachable`, `console_rejected`, `download_failed`, `no_gta_save` and
`no_story_slot`.

Each story save is decrypted and checked: a copy that isn't a JSAV save (GarlicSaves has sent back damaged copies now and
then, GitHub issue #11) is asked for again, up to three decrypts in all. A save that still can't be read is left out and
listed in `state.skipped` (`why` is `damaged`, or `layout` for a JSAV save the reader can't follow); its file goes back
to the PS5 unchanged. When no story save can be read the download ends with `decrypt_bad` (a damaged copy among them) or
`save_layout_changed`. While sending back, a PS5 that asked for its data over IPv6 (a console that sends `01000000` at
bytes 52-55 of its power request, issue #7) when the computer's network adapter for it has no link-local IPv6 address
sets `job.hint` to `{"code": "local_ipv6", "adapter": "<adapter name, or empty>", "platform": "win32" | "darwin" | "linux"}`
(pull request #14); the job keeps waiting (stage `waiting_console`), and the next connection from the PS5 clears it.
The adapter's addresses come from psutil; on Windows, when psutil can't be loaded, from Windows itself (PowerShell's
`Get-NetIPAddress`, pull request #18). Sending back ends with `adapter_query_failed` when that fails too, and with
`tool_failed` when psutil is missing on another system.

`/api/upload` takes `{"to": "<user ID>"}` (one of `state.users`) to send the session's saves to another account on the same
PS5. Every file of the save is re-signed for that account's PSN account ID (from the PS5's transfer data) with
GarlicSaves' `resign` job, one job a file (stage `resigning`, with `progress`), and one copy is decrypted again to
check it carries the new account (stage `resign_check`). The copy becomes a new library entry under the other
user's save folder, keeping the PS5's own file headers with only the entry ID and the user in the path changed,
and is sent like any other save. A copy made earlier in the session from the same files is used again. With `to`
the upload doesn't need edits. It ends with `resign_failed` when GarlicSaves can't sign the saves or the copy
doesn't check out; nothing is sent then.

The details (`job.log`, `job.error.detail`) show the data folder as `<data>`, the home folder as `~` and a PS5's ID in a
path as `<console>`, since they get pasted into bug reports.

The job's `log` has a line for each derivation, saying why it gave no keys when it didn't: `Key service: answered in
4.2 s (1 request)`, `answered too late, after 31.0 s (2 requests)`, `rate limited by GarlicSaves (retry after 60 s)` (or
`no retry time given`), `refused (key requests turned off for this key)`, `refused (GarlicSaves called the request
invalid)`, `no worker free after 30 s (3 requests queued)` (no GarlicSaves console took a request), `worker took too
long (running after 30 s, 3 requests)`, `worker failed (no keys after 30 s, 3 requests)`, `could not reach GarlicSaves
(no keys after 30 s, 3 requests)`, or `no answer after 30 s (3 requests)` while none of that is known yet. Timings,
counts and reasons only: never the worker key, key material, the client or server values or an account ID.

### The World tab's edits

```jsonc
"world": {
  "time": {"hour": 21, "minute": 30},       // the date stays the same
  "health": 250,                            // 1 to 250
  "armour": "full",                         // every armour part of both characters up to its maximum
  "fog": "known",                           // reveal every map region Save Garage knows
  "lucia": {"meter": "full", "skills": 99, "profile": -25.0, "vest": true},
  "jason": {"skills": 60},                  // any of the four, for either character
  "relationship": 69,                       // within the story's caps
  "levels": {"lucia": {"muscle": 4, "cardio": 3, "focus": 3}, "jason": {"cardio": 1}},   // counted from 0
  "growth": {"lucia": {"specialabilitymax": 100}, "jason": {"healthmax": 100, "staminamax": 100,
             "meleestaminamax": 100, "specialabilitymax": 100}}
}
```

Every key may be left out, and every edit is checked against the save before anything is written:

- `fog` appends each known region the save lacks, the way the game writes one, and never changes, removes or moves
  an entry. It is refused when the map data's version isn't 9 (`fog_version`), an entry has other keys, a type other
  than 1 or 2 or a known region with the other type (`fog_entry`), or a region is listed twice (`fog_repeat`).
- `meter` fills attribute slot 24 to 100; `skills` raises slots 9, 10, 13, 14, 15, 19, 20 and 35 to the value given
  (1 to 99). Both only ever raise, and slots 17 and 23 are never written. `player.py` never touches the core slots
  0-3 and 30-33; `growth` below writes four pairs there. The attributes must have their 37 values (`attributes_layout`).
- `profile` sets the criminal profile, -100 to 0.25, written as the game writes it (float32 with six decimals).
- `vest` puts on the vest a character owns when that character wears no armour: armour part 1 becomes 150 of 150
  and the outfit's cached-armour flag true. Refused when the character has no vest in the wardrobe (`no_vest`); a
  character who already wears armour is left as is.
- `relationship` is refused while the story has it locked (`relationship_locked`) or switched off
  (`relationship_disabled`), and outside its caps (`out_of_range`). Its level isn't changed.
- `levels` sets strength (`muscle`, 0 to 4), `cardio` and `focus` (0 to 3), counted from 0 as the save keeps them (the
  game shows them from 1). Both copies are written: the character's record in ScriptCharacterPhysique, which the game
  reads when the save loads, and `currentlevel` in the stats, with `numlevelups` for cardio and focus so that ups minus
  downs still gives the level. A level that changes has its progress points set to 0. Refused when a record or stat
  isn't where Save Garage expects (`levels_layout`).
- `growth` sets a health, stamina, melee-stamina or focus capacity (0 to 100), the length of the bar rather than the
  level. All four copies are set alike: attribute slots 0-3 and their repeats at 30-33, plus the `points` and `rank`
  rows in the stats. A game save can hold different values in those copies; in that case all four are set to the
  chosen value. Refused when a copy is missing or not an int in range (`growth_layout`). The game kept 100 after a
  PS5 loaded an edited save and wrote it back.

Out-of-range values are `out_of_range`, wrong types `bad_value`, and unknown keys in a character's object
`bad_request` (other keys of `world` are ignored); in the job's error they carry the `save_` prefix. Applying the
same edits again changes nothing.

### Guns to add (Ammo tab)

```jsonc
"guns": {
  "lucia": ["5ea6e528", "c24e18bf"],        // weapon ids from guns.characters[].offered, or "all"
  "jason": "all"
}
```

Each gun a character doesn't have (no row of that weapon in its weapons list) is added the way the game writes a gun
you buy, row for row as the game itself wrote bought guns in a save: the weapon row under the character's weapon
container, its `_001` kit and default `regular_01` parts under it, their ParentGuids and Items entries, and the weapon in
OwnedWeaponsHistory (not for the grenade and sticky bomb, which the game leaves out). The grenade and sticky bomb come
with the ammo row the game added with them (5 and 4). A weapon the compendium doesn't list yet is added to it, with its
counters, and the 100% figure is worked out again. Nothing a character has is changed: guns it has are skipped, so the
same edit applied again changes nothing. No money is spent, and the purchase counters stay as they are.

Refused, with nothing written: `guns_layout` (the inventory isn't shaped as the game writes it: InventoryId, list
columns, one character root with one weapon container, a sorted OwnedWeaponsHistory), `inventory_damaged` (a Guid used
twice, Items not listing every row exactly once, a parent index that dangles or a ParentGuids entry without a child),
`item_limit` (Items would pass 4,095 less the 300 kept free), `not_offered` (a gun that can't be added to that
character), `bad_request`, `verify_failed` (the result isn't the old inventory plus exactly the new rows).

### Cheats (Completion tab)

```jsonc
"completion": {"cheats": {"trackers": ["0c7d4ae2", "d40c07aa", "c2737d73"]}}     // or {"trackers": "all"}
```

Each chosen cheat tracker that isn't complete is completed the way the game completes one when its condition is met:
`isComplete` true and the empty parameter, nothing else. No counter or 100% line counts these trackers, so the
checklist and the 100% figure stay as they are; the profile-wide awards, the goals and the unlock catalogs aren't
touched. Tested on a PS5, that doesn't unlock the cheats: when the game unlocks one it also sets the cheat's entry in
the unlock catalog (block 6df5d2cf) from 0 to 2, and that entry is known for only one cheat so far. So the page lists
the cheats read-only and doesn't send this edit; the API keeps it for research. Refused: `cheats_layout` (the set isn't the 62 known trackers, or a
record isn't shaped as the game writes it), `not_editable` (a record of another challenge set), `unknown_challenge`,
`bad_request`, `verify_failed`. Errors carry the `save_` prefix in the job's error.

## Signing in to GarlicSaves

GarlicSaves authorises each installation with the user's own GarlicSaves account (device authorisation, as GarlicTransfer
0.4.0 does it), and every GarlicSaves job carries the worker key it gives, in the `X-Worker-Key` header. There is no
built-in key. `state.garlic` says where things are:

- `signedIn`: Save Garage has a worker key: the stored sign-in's, or `SAVEGARAGE_DEV_WORKER_KEY`'s (`devKey` true;
  for development and tests only, it comes before a stored sign-in and is never passed on to the transfer tools).
- `username`: the GarlicSaves account of the stored sign-in, for the page to show (`null` when GarlicSaves named none,
  or with a development key). The key itself is never in the state, the job log, a job's details or an error.
- `stored`: a sign-in is stored (Sign out forgets it).
- `refused`: GarlicSaves turned the key in use down in its latest answer (HTTP 401, or 403 from its API): the sign-in
  was turned off or has expired. Cleared by an answer that goes through, or by signing in again.
- `signin`: the sign-in under way. `status` is `idle`, `starting` (asking GarlicSaves for a code), `waiting` (with the
  `code` to enter on GarlicSaves, the `link` to open, always an `http` or `https` address, and `expiresIn`, the seconds
  left), `done`, or `error`, with `error` saying why and `http` the HTTP status of the answer it stopped at:
  `unreachable` (no answer to the first request, or to three checks in a row), `rate_limited` (429 to the first
  request), `unavailable` (a 5xx to the first request, or to three checks in a row), `expired` (the code ran out,
  after `expires_in` or 10 minutes, or GarlicSaves said so), `refused` (GarlicSaves turned the sign-in down),
  `bad_link` (a sign-in link that isn't an http or https address), `bad_answer` (an answer Save Garage doesn't
  understand), `not_saved` (`config.json` couldn't be written) or `internal`.

`POST /api/signin` runs the flow in the background: `POST <server>/api/v1/device/code` with `{"name": "Save Garage"}`
(nothing about the computer), which must answer a `device_code`, a `user_code` (letters, digits, spaces and hyphens, at
most 32), a `verification_uri` (an `http` or `https` address, ASCII, with a host and no user name) and, optionally, the
numbers `expires_in` (1 to 86,400 s) and `interval` (0 to 3,600 s). Then `POST <server>/api/v1/device/token` with
`{"device_code": "…"}`, every `interval` seconds but never more often than every 3 s: `authorization_pending` (HTTP 202,
or as RFC 8628's 400 error) waits on, a 429 or `slow_down` adds 5 s to the interval (or waits what `Retry-After` asks),
up to two missing answers or 5xx in a row are tried again, and an HTTP 2xx with `"status": "authorized"` must carry a
`worker_key` (16 to 512 printable characters without spaces, quotes or backslashes) and an `installation_id`, and may
carry a `username`. Anything else ends the sign-in with the error above. Only those three fields are kept; nothing else
GarlicSaves answers is logged or shown. These requests go without a worker key, through the same curl, proxy and
User-Agent as every other GarlicSaves request; the key and the request bodies go to curl on its standard input, not on
its command line.

The sign-in is stored as `"garlicSaves": {"workerKey", "installationId", "username"}` in `config.json` in the data
folder, written with mode 600 (a `config.json` holding a sign-in that others can read is set back to 600 at start-up);
`POST /api/signout` takes it out again and keeps the other settings. The update install and rollback
(engine/bootstrap.py) never write to the data folder's `config.json`. The `workerKey` setting of versions before 1.30.0
is no longer read.

## Updates

`state.update` is what engine/updater.py reports (README.md, "Updates", tells users the same):

- `auto`: the "Update automatically" setting (`autoUpdate` in `config.json` in the data folder, on unless it is
  `false`). While it is on, Save Garage checks `https://api.github.com/repos/NotHGM/save-garage/releases/latest` at
  start-up and every 6 hours; while it is off, only `POST /api/update/check` does, and nothing is downloaded or
  installed.
- `mode`: `install` for a release build the updater may update, `notify` for anything else, which only shows that a
  new version is out; then `why` says why: `checkout` (a `.git` in the app's folder or one above it), `not_desktop`
  (not started by the build's launcher), `read_only` (a folder it can't write to) or `unknown` (another layout, or a
  `build.json` that doesn't match the running version). `flavour` is `windows`, `macos` or `linux` from `build.json`.
- `status`: `idle` (no check yet), `checking`, `current` (up to date), `downloading` (`progress` bytes of `total`),
  `ready` (staged: installs at the next start or with `/api/update/restart`), `available` (a newer version that this
  copy doesn't install: notify mode, automatic updates off, or a version needing a new Python runtime, `error`
  `runtime`, not downloaded again), `failed` (`error` says why) or `check_failed` (GitHub couldn't be read; `error`
  `check_failed`).
- `current` is this version, `latest` the newest one found. `notes` is the GitHub release page of `latest` (or of this
  version), for the release notes and the downloads. `installed` is set in the first run of a version the updater
  just installed. `canRestart` is true while an update is staged and no task runs; `restarting` once it restarts.

A newer version is installed only when `SHA256SUMS.txt.sig` is a valid Ed25519 signature of `SHA256SUMS.txt` by the
release key pinned in engine/updater.py, the build's file matches its SHA-256 there, every name in the list carries
that version, and the archive passes the unpacking checks. Otherwise `status` is `failed` with `error`: `unsigned`
(no signature or no list), `bad_signature`, `bad_version` (a list for another version, or a malformed one),
`no_asset` (no file for this build), `bad_checksum`, `too_large` (over 100 MB, or unpacking to more than 400 MB),
`bad_archive` (a link, device, absolute path, `..` or a file outside its `SaveGarage` folder), `bad_package` (not
this build, or files missing), `network` (the download didn't finish), `disk`, `install_failed` (cut short twice),
`start_failed` (the new version didn't answer `/api/state` within 90 s, or stopped before it did, so the old version
was put back) or `internal`. A version that didn't start or couldn't be installed (`start_failed`, `install_failed`)
is not tried again; the other failures are retried at the next check.
