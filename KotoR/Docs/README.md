# KOTOR Archipelago Randomizer — Installation (Alpha)

> **Status: Alpha.** This rewrites live game files (see "Before you start,
> back up" below). A unique interaction with a scripted event can interfere with the mod and crash the game, and a live end-to-end playthrough of every scenario is not feasible with the current design. If you find an issue please report it with a brief description. If it was a crash, please also include `%LOCALAPPDATA%\KSE\kse.log`, `%LOCALAPPDATA%\KotorApExtender\extender.log`, the newest `logs\KotorClient_*.txt` and `kotor_delivery_log.jsonl` from your Client folder. Refer to `TESTING.md` for more information.

This mod needs two pieces working together: **this project's own extender**
(a single compiled DLL — it merges K1SE's dispatcher-hook source directly in,
so there's no separate third-party script extender to install any more —
plus generated NWScript that talks to Archipelago) and **Python** (to
run the installer and the KOTOR client). Neither is
optional — skipping either means the mod won't work.

## What you'll need

- **Knights of the Old Republic, Steam version.** Other copies (GOG, disc,
  patched, localized) aren't supported yet.
- **Windows.**
- **Python 3.12 or 3.13**, from [python.org](https://www.python.org/) —
  needed to run the installer and `KotorClient.py`. 3.11.9 or a newer 3.11
  also works; **Python 3.14 does not** (the Archipelago client refuses to run
  on it), so install 3.12 or 3.13 alongside it if that is what you have.
- **The Archipelago Launcher, 0.6.7 or newer (the normal Windows installer)** — only to **generate or host** a seed yourself. To
  play a seed someone else hosts you do not need it: the KOTOR download already contains the Archipelago files the client runs on, so
  there is no Archipelago source code to download any more.
- **Git for Windows**, if the installer says it needs it (it offers to install it for you).
- **An internet connection for the first install:** `Install.bat` downloads the Python packages the client needs (kivy, pykotor, numpy, pillow and others).

## Step 1 — Get the files

1. Download both zips from **[this project's Releases page](https://github.com/Firebringer92/Archipelago-Fire/releases)**
   (same release, don't mix versions): `KOTOR-AP-World-vX.Y.Z.zip`
   (contains only `kotor.apworld`) and `KOTOR-AP-PlayerBundle-vX.Y.Z.zip`
   (everything else).
2. Right-click the PlayerBundle zip, choose **Extract All**, and pick a new folder
   (for example `C:\KOTOR-AP`; not inside Program Files and not inside the zip). This is your **Client folder** for everything below.
3. Only if you generate or host seeds: put `kotor.apworld` in the `custom_worlds` folder of your Archipelago Launcher install
   (create `custom_worlds\` there if needed — find that folder via the Launcher's Start Menu shortcut → right-click →
   Open file location). Do not put it in the Client folder. The client checks that its release matches the seed's
   and stops with a message if it does not, so keep both zips on the same release.

## Step 2 — Install

Double-click **`Install.bat`** in your Client folder. Press Enter to
install to the default Steam location, or paste your KOTOR folder path if
it's somewhere else. Leave the window open until it says "Install
finished."

The download contains no scripts, conversations, models, textures or icons from the game itself. Install builds the ones the mod needs from **your own
copy of KOTOR** (about half a minute): the original scripts the mod wraps, the edited cutscene conversations, the six extra lightsaber crystal colors and the
game's script definitions. The client tops them up on every connect, and `Uninstall.bat` removes them.

To remove everything later, double-click **`Uninstall.bat`** the same way.

## Step 3 — Generate, host, and play

1. Get a player YAML: download
   **[`KotoR_TEMPLATE.yaml`](https://github.com/Firebringer92/Archipelago-Fire/blob/main/KotoR/Docs/KotoR_TEMPLATE.yaml)**,
   save it into the Launcher app's own `Players\` folder, rename it
   (e.g. `my_game.yaml`), and edit `name:` plus whatever options you want
   under `KotOR:`. **If someone else is hosting**, skip straight to step
   3 — send them your yaml instead.
2. In the Archipelago Launcher: click **Generate** and select your yaml,
   then click **Host** and select the seed zip it just made (or upload it to archipelago.gg).
3. Double-click **`Start KOTOR Client.bat`** in your Client folder (or click **"KOTOR Client"** in the Archipelago Launcher, if you
   put `kotor.apworld` there: it starts the same client). Then connect to the server and your slot. As soon as you register into your slot you will have to wait as the client is finalizing your game files based on your seed. This might take 1-2 minutes. The client prints `[patching] ...` while it prepares the game files and a `Finished` line when you can start the game; if KOTOR was already running, relaunch it, because the game reads some of the tables the patches replace (the droid options) only at startup. The first time an option needs them (Darth Malak as an extra companion, the droid options) it also builds the Malak and droid models from your game
   with a small model tool, about half a minute each; they are kept and reused. Connect before you start KOTOR: the first connect after an
   install or update also adds a few entries to the game's `dialog.tlk` once, which can't happen while the game is running.
4. Open the actual game. You should see on the client.py it switch status to `Extender: CONNECTED`  otherwise type   command  `/ap_status` to see if your client is talking to game. If it shows connected and your in the server. You are  good to go!

Note: If Kotor doesn't launch from archipelago launcher try launching it from your client folder instead.

Every option that changes game files (Loot Mode, Progression System, door
randomization, additional enemies, Galactic Shop, extra and AP companions, the droid options, boss datapads,
the Archipelago Vendor and the Bazaar, whichever you enabled) applies itself automatically
the moment you connect — no separate patch step. See `TESTING.md` for client commands and what to
send if you hit a bug.

New in 0.2.1:
- **Extra companions** (`extra_companions`, `extra_companion_random_class`): a Mystery Companion, Darth Malak, Calo Nord, Yuthura Ban, Darth Bandon and Trask Ulgo each arrive as
  their own item and keep their own party slot. The party screen now holds 32 slots in pages, and the **Party Console** item opens it. They replace the New Companion
  console and the `new_companion` option, which are gone.
- **AP companions** (`ap_companions`, 0 to 8): generated companions named after players in the multiworld, with a random class, look and portrait.
- **Randomize Dialogue and Randomize Alignment** (`randomize_dialogue`, `randomize_alignment`, both off by default).
- **The Vendor's feat training is a menu:** it lists your feats, lets you remove one for free when the list is full, and charges only when training succeeds.
- **Companions are never deleted.** One you have not unlocked yet stays in the world but cannot join. When an item adds a companion and your party is full, the companion
  in the second slot leaves.
- **Companions do not start fights on their own;** they join in as soon as your party is fighting.
- **You no longer have to gather your party** to leave an area.
- `KotoR_TEMPLATE.yaml` documents every option. Seeds generated with 0.2.0.x do not work with 0.2.1.



## Updating from an earlier version

Download both zips of the new release and close the client and KOTOR. Extract the new PlayerBundle zip into a **new folder** and run its
`Install.bat` (you no longer need the Archipelago source folder an older release asked for; delete it if you like). If you
keep using the same Client folder instead, extract over it and let it replace the whole `extender\`, `scripts\`, `worlds\` and `data\`
folders (copying over only the files you recognize can leave out `extender\scripts_src\`). Put the new `kotor.apworld` in the Launcher's
`custom_worlds` (replace the old one). Seeds
generated with an older world version have to be generated again when a release
changes the item or location tables (0.1.8, 0.1.9, 0.2.0 and 0.2.1 do); the client refuses a seed from a different world release. Then connect once with the
game closed, as in Step 3, before launching KOTOR.

**Switching to a new seed on the same install:** quit and restart the client first (a grant still waiting in the client from the
previous seed can hold up the new seed's companion and class grants for up to 10 minutes), then run `/ap_restore_all` in the client and
reconnect (or run `/ap_patch_all`). Door changes and extra enemies from the previous seed are not removed by the new seed's patches
(a seed with vanilla doors or no extra enemies leaves the old ones in place). The client prints a reminder when it sees the install was
last patched for a different seed or option set.


## Before you start: back up

This mod repacks real game files in place — `modules\*.rim` and
`Override\` are both modified directly, not just added to.

- Back up your **saves** (`%LOCALAPPDATA%\KotOR\saves` or similar) before
  playing a randomized seed.
- Back up your **`modules\` folder and `Override\` folder** (or your whole
  game install) before installing, in case something
  goes wrong beyond what the built-in restore covers.
- **`Uninstall.bat`** reverts everything the installer touched, including
  restoring every module file the per-seed patches edited (doors, Loot Mode,
  additional enemies, boss datapads, Galactic Shop), removing the Progression System's story gates and the droid assets, deleting the files Install built from your game, and
  removing what the client wrote into `Override\` and `dialog.tlk` while you were connected (the Jedi-trial suppressor, the shop price fixes, the extra and AP companion files and the
  tracker journal). It removes only files it recorded writing, and only while they are still the files it wrote. Files written by an older release were not recorded, so
  a game last patched by an older release may keep some.
- `/ap_restore_all` in the client undoes the same things without uninstalling. A reconnect writes them again.
- If all else fails, Steam's **Verify integrity of game files** restores the game's own files in `modules\` (this
  won't undo save-file changes, which is why saves need their own backup). It does **not** remove extra files that were added to `Override\`, so it is not a substitute for `Uninstall.bat`.


## Other Notes
Kotor on steam defaults to a fullscreen mode that is horrible. I suggest all players modify their settings file, `swkotor.ini`, which is stored in the swkotor folder at "C:\Program Files (x86)\Steam\steamapps\common\swkotor". Find section for graphics and change the settings for FullScreen Mode to 0 and also add the following:
AllowWindowedMode=1
Width=1680
Height=1050

**If your character can't move during or after a fight:** this is a known vanilla
KOTOR bug, far more likely with an uncapped frame rate or a high-refresh monitor,
and it is not caused by this mod. Turn V-Sync on (Options → Graphics → Advanced
Options) and cap the game at 60 FPS, for example in the NVIDIA Control Panel:
Manage 3D settings → Program Settings → `swkotor.exe` → Max Frame Rate 60 and
Vertical sync On. If it still happens, hold forward while panning the camera (map
a key to Pan Camera Left or Right in Options → Controls) for a second or two,
click an object or another party member, or quicksave and quickload.

**If you crash, these are the two known culprits and they're both vanilla
engine issues, not this mod** — worth ruling out before reporting a bug:
- **Crash during a cutscene/dialogue, especially with a lot of VO
  playing:** a known old-engine audio crash (Miles Sound System, the same
  library other 2003-era BioWare games use) on modern multi-core CPUs.
  Try the Steam launch option `-affinity 0` (right-click KOTOR in your
  Steam library → Properties → General → Launch Options) to restrict it
  to one CPU core.
- **Crash on Taris, especially in the Undercity:** looks like an Intel
  integrated graphics driver issue. Try lowering or disabling dynamic
  lighting/particle effects and anti-aliasing, or run in windowed mode
  (see above).



## How do checks/locations work in this mod?
Because of how the game works, this mod has its own pipeline for reading from and writing to the game.
When you launch KotorClient.py and connect to a server you will see an "extender" along with its status.
The extender reports what is happening in the game (every 5 seconds or so), and the client uses those reports to decide "did you achieve the requirements for a known check".
If you did, it tells the Archipelago server, and the item attached to that check goes to whoever it belongs to.
Items that come to you are delivered by a **dispatcher**: the client sends one job at a time (an item, credits, XP, a skill, a class, a trap, a message) and the game applies it as soon as it is calm: never during a conversation, a cutscene or a fight.
 Usually that is within a few seconds, and a message box lists what you received after all jobs are done. If you have a lot of checks (30 or more) this can take a few minutes. If you are in a long fight or a long scene, the deliveries wait until it ends. Each job has a number, so a repeat is dropped, and if you load an older save the client sends again what that save is missing, once. A death from DeathLink is the one thing that is never sent again after a reload. The client's Status tab and `/ap_status` list "Deliveries waiting", the job in flight and the
last results; if an item you expect has not arrived, look there first, and a failed job says why. If the client shows it as applied and you did not get it, that is a bug: report it.

The client's log fills with lines from the game: those are the game's reports, used to detect checks.
You will also see a few small quest items in your inventory: a "Location: <area>" item for each area you visit and,
on a new character, a "Player ID: <slot> <hash>" item. They are record-keeping the mod uses to remember which areas
you have seen and which seed a character belongs to, so don't drop or sell them (the Remove Half Inventory trap leaves them alone). The Progression items ("Taris Progression 2" and so on) are plot items as well: they cannot be sold or dropped, and a lost one is given back.
For more technical details on how it all works refer to DESIGN.md

## Known alpha limitations

- A handful of doors are structurally impossible to randomize and are left on their
  vanilla exit automatically. This is expected. Not a bug
- Door-randomization also doesn't begin until after tutorial (Endar Spire) until you leave Apartments on Taris.
  So you will go from Endar Spire > Hideout > Apartments and then next door is randomed. 
  In coupled mode the shuffle cannot place its last two doors on its own: those are paired with each other and, if an area would still be cut off, two pairs swap partners, so every door still leads back the way you came and no area is unreachable. The layout can still look unusual. If you have suggestions on a mapping system that is less random and more sane let me know of how we can better map this. 
  Ebon hawk travel to all planets is enabled automatically in this mode to ensure you can still use it as a hub
  and travel to and from planets. Ebon-Hawk entrance/exit always leads to it.
  End game areas (leviathan/unknown world/star forge) are taken out of randomization on doors
- DeathLink: an incoming death waits until you are out of a conversation, cutscene or fight, then kills you once; loading an older save does not repeat it, and a death caused by an
  incoming one is not sent on to the others. Deaths that arrive while the client is closed are discarded.
- Extra and AP companions have no personal quest, only a greeting. Darth Bandon and AP companions cannot wear body armor or robes (equipping them crashed the game), so
  they have armor built in instead.
- **Crash Confirmed In Game: opening a companion's Force Powers
  screen right after they've been granted a Jedi class, before they've
  reached level 2 in it.** A freshly-granted level-1 Jedi companion has
  zero known Force Powers yet (our grant mechanism doesn't run the normal
  "learn initial powers" step a real level-up would), and the Force
  Powers screen isn't built to render a completely empty list for a
  character it considers Jedi. DO NOT OPEN FORCE POWERS MENU ON COMPANION IF THEY ARE LEVEL 1
- `starting_class` (`jedi_start` / `jedi_granted`) fixes a real, confirmed KOTOR 1 engine bug for the
  4 cutscenes known to trigger it — an undiscovered 5th could still hang
  at a "CutStart" object. If that happens, a full game restart (not just
  reloading) is needed regardless, so it isn't a lost save.
- `progression_system` holds story events (not doors or travel) until you own enough of that planet's Progression items, and the game says why a gate
  is closed. It works with every goal and with both area randomizer modes.
- The Remove a Companion trap is permanent for the rest of the run.
- Companions join the fights your party is in but do not start them. Once a fight is on, they may go after any enemy they can see, including one farther off.
  Companions not following or fighting after some area transitions has not been confirmed fixed.
- The mod replaces four of the game's companion scripts in `Override\` (`k_hen_percept01`, `k_hen_combend01`, `k_hen_dialogue01`, `k_hen_heartbt01`); another mod that
  replaces them will conflict.
- `randomize_dialogue`: some conversations take several tries before you land on the reply that ends them. Computer consoles and droid terminals are left alone.
- Loading an older save and then a newer one within a few seconds can apply some deliveries a second time, and a delayed level correction can set your current Force
  points to an earlier value.
- After escaping the Leviathan, the conversation that lets the Ebon Hawk take off is started by a trigger that fires before Carth has appeared,
  so the game falls back to a sensor console: use it to start the scene. Skipping the Dantooine council with the area randomizer can also
  keep Carth and Bastila off the Hawk.
- The Unknown World may never appear on the galaxy map if the Dantooine ruins star map is never found (an area randomizer run): the game counts
  five star map activations, Dantooine's included, before it opens the Unknown World.
- The Taris Hideout escape-plan scene starts after a long black screen (about 25 seconds); the scene plays when you move.
- If the client log shows `[game assets] FAILED` (or a model build fails), check that your KOTOR folder is complete (Steam: Verify integrity of game files), close KOTOR and
  connect again. Some antivirus programs block the small helper programs the download runs, `tools\nwnsc\nwnsc.exe` (the script compiler) and `tools\mdlops\mdlops.exe`
  (the model tool); allow them if yours does.
- The war droid and assassin droid are the only droid looks that display melee weapons; the other droid looks keep their class's
  proficiency but show no weapon.
- With the area randomizer, a planet you have left resets when a shuffled door takes you back to it: the base game deletes a planet's saved areas once you enter the next planet
  (Taris when you enter the Jedi Enclave, Dantooine when you go on to the Leviathan, and so on), so enemies, loot containers, fog and first-entry scenes come back. Quest and
  story progress are kept; only the areas reset. Without the area randomizer you cannot return to those planets, so it never shows.

## Provenance and checks

[![KotoR checks](https://github.com/Firebringer92/Archipelago-Fire/actions/workflows/kotor-checks.yml/badge.svg)](https://github.com/Firebringer92/Archipelago-Fire/actions/workflows/kotor-checks.yml)

Nothing in this repository or in a release download is a copy or an edit of the game's own files: those are built on your machine from your own copy of KOTOR.
`PROVENANCE.md` lists where every kind of file comes from. Every push is checked automatically (the badge above): no game-format file, no file without a described origin, every
included program registered with its hash, and the full test suite. Every release follows `RELEASE_CHECKLIST.md`, and the published zips are checked again after they are uploaded.

## Credits

This project leans heavily on work by other people in the KOTOR modding
and Archipelago communities. It would not exist without:

- **[K1SE (KOTOR Script Extender)](https://www.nexusmods.com/kotor/mods/1852)**
  by Brandon Guffey ([source, MIT-licensed](https://github.com/Brotaku-Vengeant/Kotor-Script-Extender-Public-))
  — this mod's whole delivery/reporting pipeline is built on top of K1SE's
  dispatcher-hook mechanism, and (as of this project's alpha) K1SE's own
  source is merged directly into this project's compiled extender rather
  than installed as a separate third-party mod, per its MIT license. Its
  persistent heartbeat, diagnostic channel, and skill/feat-grant natives
  are what let this project actually see and change what's happening
  inside a running game.
- **[Holocron Toolset](https://github.com/Bagelboi/HolocronToolset)** and
  the underlying PyKotor library — used constantly during research and
  development to inspect and understand KOTOR's own file formats
  (GFF/RIM/2DA/journal data) well enough to build on top of them.
- **[KotOR Patch Manager](https://github.com/LaneDibello/Kotor-Patch-Manager)** by Lane Dibello and contributors, MIT licence. The 32-slot party roster is ported from
  its PartyRosterLimit32K1 mod (author: Vriff). The licence text ships in `THIRD_PARTY_NOTICES.txt`.
- **[Kotor Randomizer](https://github.com/LaneDibello/Kotor-Randomizer)**
  by LaneDibello — an existing KOTOR randomizer whose approach to entrance/
  location randomization was referenced while designing this project's own
  door-randomization and location-detection systems.
- **[MDLOps](https://deadlystream.com/files/file/779-mdlops/)** v1.0.0, written by Chuck Chargin Jr., with animation support by JdNoa, version 1.0 by ndix UR and many
  other contributors (GPL; submitted to Deadly Stream by Fair Strides). It ships unchanged in `tools\mdlops`, with its licence, readme and tutorials, and builds the
  Malak and droid models from your own game.
- **[nwnsc](https://github.com/nwneetools/nwnsc)** by Ken Johnson (Skywing), MIT licence, built on the NWScript compiler library by Edward T. Smith (Torlack) and
  The Open Knights Consortium (BSD licence). It compiles the scripts the client generates for your seed. The licences are in `tools\nwnsc\LICENSE.txt` and
  `THIRD_PARTY_NOTICES.txt`.
- **[Archipelago](https://archipelago.gg/)** itself, obviously — this
  project is built as an Archipelago world/client 
- **[Bioware]** For making an amazing game, I loved it as a kid growing up and its been interesting learning about the
  inner working of the engine that made this game  (the good and bad)

## AI usage

This project is largely vibecoded.
What do you mean by vibe coded?
Almost all of the code in this project is created by AI. The AI responsibilities
for this project included building the extender, apworld and python client. AI was also used both with asisting in research and diagnostics during testing. 
So what were you responsibities?
I built out testing ncs scripts to validate functionality.
I performed a review over all code files.
I performed live in game testing of both my own scripts and AI drafted code and fixes.
Validated my understanding of the code by questioning any functions/tracing code paths when documentation was unclear or not specific. As well as clarified my understanding for areas of the code I wasn't sure what it was used for and ensured was inline with design of the features and or project goal. 
I was responsible for all game design decisions. 

If you're evaluating this project's code quality, it is primarily AI built with human gudiance and reviewed by human for accuracy to functionality it was designed for.
I am not a professional coder, but I do audit code for a living.
