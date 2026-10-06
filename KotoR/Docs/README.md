# KOTOR Archipelago Randomizer — Installation (Alpha)

> **Status: Alpha.** This rewrites live game files (see "Before you start,
> back up" below). Expect bugs. While no game crashes has occurred in this version, that doesn't mean a unique interaction with a scripted event can't cause interference and cause a crash. A live end-end playthrough with each scenario is unfeasible with current design. If you find an issue please report it with a brief description. If it was a crash, please also include `%LOCALAPPDATA%\KSE\kse.log`, `%LOCALAPPDATA%\KotorApExtender\extender.log`, the newest `logs\KotorClient_*.txt` and `kotor_delivery_log.jsonl` from your Client folder. Refer to `TESTING.md` for more information.

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
- **Archipelago 0.6.7 or newer, the "Source code" download, not the
  installer app** — [get it here](https://github.com/ArchipelagoMW/Archipelago/releases).
  `KotorClient.py` needs to sit inside a real Archipelago source folder to
  run, so the installer app (which has no source files in it) won't work
  for this part. Extract the source zip anywhere — that folder is your
  **Client folder** for everything below.

## Step 1 — Get the files

1. Download both zips from **[this project's Releases page](https://github.com/Firebringer92/Archipelago-Fire/releases)**
   (same release, don't mix versions): `KOTOR-AP-World-vX.Y.Z.zip`
   (contains `kotor.apworld`) and `KOTOR-AP-PlayerBundle-vX.Y.Z.zip`
   (everything else).
2. Extract the PlayerBundle zip's contents directly into your Client
   folder (the one from "What you'll need" above) — a plain "extract
   here," nothing to move around afterward.
3. Put `kotor.apworld` in two places:
   - `<Client folder>\custom_worlds\kotor.apworld`
   - `custom_worlds\kotor.apworld` inside the Archipelago Launcher app's
     own install folder (create `custom_worlds\` there if needed — find
     that folder via the Launcher's Start Menu shortcut → right-click →
     Open file location).

## Step 2 — Install

Double-click **`Install.bat`** in your Client folder. Press Enter to
install to the default Steam location, or paste your KOTOR folder path if
it's somewhere else. Leave the window open until it says "Install
finished."

To remove everything later, double-click **`Uninstall.bat`** the same way.

## Step 3 — Generate, host, and play

1. Get a player YAML: download
   **[`KotoR_TEMPLATE.yaml`](https://github.com/Firebringer92/Archipelago-Fire/blob/main/KotoR/Docs/KotoR_TEMPLATE.yaml)**,
   save it into the Launcher app's own `Players\` folder, rename it
   (e.g. `my_game.yaml`), and edit `name:` plus whatever options you want
   under `KotOR:`. **If someone else is hosting**, skip straight to step
   3 — send them your yaml instead.
2. In the Archipelago Launcher: click **Generate** and select your yaml,
   then click **Host** and select the seed zip it just made.
3. click **"KOTOR Client"** in the Archipelago Launcher to connect (Step 2's installer registers this
   button — it's the same client as running `KotorClient.py` directly,
   just no terminal needed). Then connect to server and your slot. As soon as you register into your slot you will have to wait as the client is finalizing your game files based on your seed. This might take 1-2 minutes. Connect before you start KOTOR: the first connect after an
   install or update also adds a few entries to the game's `dialog.tlk` once, which can't happen while the game is running.
4. Open the actual game. You should see on the client.py it switch status to `Extender: CONNECTED`  otherwise type   command  `/ap_status` to see if your client is talking to game. If it shows connected and your in the server. You are  good to go!

Note: If Kotor doesn't launch from archipelago launcher try launching it from your client folder instead.

Every option that changes game files (Loot Mode, Progression System, door
randomization, additional enemies, Galactic Shop, New Companion, boss datapads
and the Archipelago Vendor, whichever you enabled) applies itself automatically
the moment you connect — no separate patch step. See `TESTING.md` for client commands and what to
send if you hit a bug.


## Updating from an earlier version

Download both zips of the new release, close the Archipelago client and KOTOR,
extract the PlayerBundle zip over your Client folder and let it replace the
whole `extender\` and `scripts\` folders (copying over only the files you
recognize can leave out `extender\scripts_src\`), put the new `kotor.apworld`
in both places from Step 1, and double-click `Install.bat` again. Seeds
generated with an older world version have to be generated again when a release
changes the item or location tables (0.1.8 does). Then connect once with the
game closed, as in Step 3, before launching KOTOR.


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
  Progression System, additional enemies, boss datapads, Galactic Shop).
- If all else fails, Steam's **Verify integrity of game files** will
  restore any modified `modules\`/`Override\` content from scratch (this
  won't undo save-file changes, which is why saves need their own backup).


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
Due to nature of game, this mod has a specialized delivery/receipt pipeline to read and write to the game.
When you first launch KotorClient.py and connect to server you will see an "extender" along with status. 
This extender is what is used to get information from the game to report on current status and the client will 
then use this information to determine "Did you achieve requirements for a known check". If you did, it will then send back to AP Server to mark it as completed and the attached item is then sent by client to be delivered to your game.
You in game might not see the result check immediately. The delivery pipeline is designed to provide you items when you load into a new module (loading zone). Additionally because of how taxing some of the items are to the game client, there is a queuing system in place so you might not get all the items your supposed to get on your first transition. This is designed purposefully to prevent a game crash. A known issue where if more than 30 or so items being sent at once overwhelms the game. So if you see you should have gotten an item, it wsn't delivered ensure you check if its queued in the KotorClient status page or if it is marked as Completed/Received and you didn't get it that would be a bug. You will notice during playing that your KotorClient.py will get lots of messages, these are in game events that is being reported to client from game on current status and used to detect a check, this happens every 5 seconds. 
You will also see a few small quest items in your inventory: a "Location: <area>" item for each area you visit and,
on a new character, a "Player ID: <slot> <hash>" item. They are record-keeping the mod uses to remember which areas
you have seen and which seed a character belongs to, so don't drop or sell them (the Remove Half Inventory trap leaves them alone).
For more technical details on how it all works refer to DESIGN.md

## Known alpha limitations

- Door randomization, Loot Mode, Progression System, additional enemies, boss
  datapads and Galactic Shop directly rewrite game files — see the backup section
  above before enabling any of them.
- A handful of doors are structurally impossible to randomize and are left on their
  vanilla exit automatically. This is expected. Not a bug
- Door-randomization also doesn't begin until after tutorial (Endar Spire) until you leave Apartments on Taris.
  So you will go from Endar Spire > Hideout > Apartments and then next door is randomed. 
  additionally while game is set to try to couple doors, some may not be directly linked back ot previous. This is done to ensure you always are allowed to go to all areas and are never soft locked from reaching an area. If you have suggestions on a mapping system that is less random and more sane let me know of how  we can better map this. 
  Ebon hawk travel to all planets is enabled automatically in this mode to ensure you can still use it as a hub
  and travel to and from planets. Ebon-Hawk entrance/exit always leads to it.
  End game areas (leviathan/unknown world/star forge) are taken out of randomization on doors
- Death link will not kill the player if he has party members due to having a companion still up. Known issue.
  A received death is applied on your next area transition, and deaths that arrive while the client is closed are discarded.
- **Crash Confirmed In Game: opening a companion's Force Powers
  screen right after they've been granted a Jedi class, before they've
  reached level 2 in it.** A freshly-granted level-1 Jedi companion has
  zero known Force Powers yet (our grant mechanism doesn't run the normal
  "learn initial powers" step a real level-up would), and the Force
  Powers screen isn't built to render a completely empty list for a
  character it considers Jedi. DO NOT OPEN FORCE POWERS MENU ON COMPANION THATS LEVLE 1
- `starting_class` (`jedi_start` / `jedi_granted`) fixes a real, confirmed KOTOR 1 engine bug for the
  4 cutscenes known to trigger it — an undiscovered 5th could still hang
  at a "CutStart" object. If that happens, a full game restart (not just
  reloading) is needed regardless, so it isn't a lost save.
- `progression_system` can only be combined with `goal: defeat_malak` or
  `goal: reach_leviathan`, and not with `area_randomizer` — enforced at generation time, so an invalid
  combination just fails to generate rather than shipping a broken seed.
- Close an old KotorClient before starting a new one: a leftover client process can hold the game's connection, and the
  new client then connects to nothing without showing an error.
- The Remove a Companion trap is permanent for the rest of the run.
- Companions not following or fighting after some area transitions has not been confirmed fixed.
- Only tested against the Steam release of KOTOR 1.

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
- **[Kotor Randomizer](https://github.com/LaneDibello/Kotor-Randomizer)**
  by LaneDibello — an existing KOTOR randomizer whose approach to entrance/
  location randomization was referenced while designing this project's own
  door-randomization and location-detection systems.
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
