# KOTOR Archipelago Randomizer — Installation (Alpha)

> **Status: Alpha.** This rewrites live game files (see "Before you start,
> back up" below). Expect bugs. While no game crashes has occured in this version, that doesn't mean a unique interaction with a scripted event can't cause interference and cause a crash. A live end-end playthrough with each scenario is unfeasable with current design. I ask testers to focus on efforts on random_areas, no_companion/ap_companion gating as while these options have been tested to work, I firmly believe they may have bugs and/or soft locks present in them. If you find an issue please report to me  with a brief description and if crash please also include kise logs, and recent delivery list at time of crash. Refer to `TESTING.md` for more information.

This mod needs two pieces working together: **this project's own extender**
(a single compiled DLL — it merges K1SE's dispatcher-hook source directly in,
so there's no separate third-party script extender to install any more —
plus generated NWScript that talks to Archipelago) and **Python** (to
generate your seed and run a couple of small setup scripts). Neither is
optional — skipping either means the mod won't work.

## What you'll need

- **Knights of the Old Republic, Steam version.** Other copies (GOG, disc,
  patched, localized) aren't supported yet.
- **Windows.**
- **Python 3.12 or 3.13**, from [python.org](https://www.python.org/) —
  needed to run the installer and `KotorClient.py`.
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
3. Launch KOTOR and load into a save, then click **"KOTOR Client"** in
   the Archipelago Launcher to connect (Step 2's installer registers this
   button — it's the same client as running `KotorClient.py` directly,
   just no terminal needed). `/ap_status` should switch to
   `Extender: CONNECTED` once the game is up.

Door randomization, item suppression, and additional enemies (whichever
you enabled) apply themselves automatically the moment you connect — no
separate patch step. See `TESTING.md` for client commands and what to
send if you hit a bug.


## Before you start: back up

This mod repacks real game files in place — `modules\*.rim` and
`Override\` are both modified directly, not just added to.

- Back up your **saves** (`%LOCALAPPDATA%\KotOR\saves` or similar) before
  playing a randomized seed.
- Back up your **`modules\` folder and `Override\` folder** (or your whole
  game install) before running any of the setup scripts, in case something
  goes wrong beyond what the built-in restore covers.
- **`Uninstall.bat`** reverts everything the installer touched, including
  restoring any module RIMs door randomization/item suppression edited.
- If all else fails, Steam's **Verify integrity of game files** will
  restore any modified `modules\`/`Override\` content from scratch (this
  won't undo save-file changes, which is why saves need their own backup).

## How do checks/locations work in this mod?
Due to nature of game, this mod has a specialized delivery/receipt pipeline to read and write to the game.
When you first launch KotorClient.py and connect to server you will see an "extender" along with status. 
This extender is what is used to get information from the game to report on current status and the client will 
then use this information to determine "Did you achieve requirements for a known check". If you did, it will then send back to AP Server to mark it as completed and the attached item is then sent by client to be delivered to your game.
You in game might not see the result check immediately. The delivery pipeline is designed to provide you items when you load into a new module (loading zone). Additionally because of how taxing some of the items are to the game client, there is a queuing system in place so you might not get all the items your supposed to get on your first transition. This is designed purposefully to prevent a game crash. A known issue where if more than 30 or so items being sent at once overwhelms the game. So if you see you should have gotten an item, it wsn't delivered ensure you check if its queued in the KotorClient status page or if it is marked as Completed/Received and you didn't get it that would be a bug. You will notice during playing that your KotorClient.py will get lots of messages, these are in game events that is being reported to client from game on current status and used to detect a check, this happens every 5 seconds. 
For more technical details on how it all works refer to DESIGN.md

## Known alpha limitations

- Door randomization and item suppression both directly rewrite game
  files — see the backup section above before enabling either.
- A handful of doors are structurally impossible to randomize and are left on their
  vanilla exit automatically. This is expected. Not a bug
= Door-randomization also doesn't begin until after tutorial (Endar Spire) until you leave Apartments on Taris.
  So you will go from Endar Spire > Hideout > Apartments and then next door is randomed. 
  additionally while game is set to try to couple doors, some may not be directly linked back ot previous. This is done to ensure you always are allowed to go to all areas and are never soft locked from reaching an area. If you have suggestions on a mapping system that is less random and more sane let me know of how  we can better map this. 
  Ebon hawk travel to all planets is enabled automatically in this mode to ensure you can still use it as a hub
  and travel to and from planets. Ebon-Hawk entrance/exit always leads to it.
  End game areas (leviathan/unknown world/star forge) are taken out of randomization on doors
- Death link will not kill the player if he has party members due to having a companion still up. Known issue.
- **Crash Confirmed In Game: opening a companion's Force Powers
  screen right after they've been granted a Jedi class, before they've
  reached level 2 in it.** A freshly-granted level-1 Jedi companion has
  zero known Force Powers yet (our grant mechanism doesn't run the normal
  "learn initial powers" step a real level-up would), and the Force
  Powers screen isn't built to render a completely empty list for a
  character it considers Jedi. **Workaround: don't open that screen for a
  companion who was just converted until they've leveled up at least
  once** (companion leveling happens only through real combat XP —
  confirmed no scriptable way to grant a companion levels or XP directly
  in this engine build). No code fix yet; this is still very real. Note will only happen when
  `companion_class`'s `jedi_companion`/`randomize_all` modes are selected. DO NOT OPEN FORCE POWERS MENU ON COMPANION
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
= **[Bioware]** For making an amazing game, I loved it as a kid growing up and its been interesting learning about the
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