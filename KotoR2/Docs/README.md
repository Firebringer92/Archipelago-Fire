# KOTOR 2 (TSL) Archipelago

An [Archipelago](https://archipelago.gg) multiworld randomizer for **Star Wars: Knights of the Old Republic II – The Sith Lords** (Steam/Aspyr, 1.0.2.0).

> **Status: in development, not released.** Nothing here is ready to play yet. This folder holds the source so that every file can be checked before the first release.
> Sister project: the KotoR folder of this repository (KOTOR 1).

## What it is

- **The world** (`Source/worlds/kotor2`): locations (quests, area visits, levels, alignment, recruits, influence, quest items, the Bazaar), items (story progression, companions, gear,
  skills, experience, credits, traps) and options. Generates with Archipelago 0.6.7 and later.
- **The client** (`Source/client`): connects to the Archipelago server, patches the game when it connects, and delivers items to the running game. Started from the Archipelago Launcher
  ("KOTOR 2 Client").
- **The extension** (`Source/extender`): a `version.dll` proxy that adds script routines to the game (forked from [K2SE](https://github.com/renanaugustomacena-ux/K2SE) by renanaugustomacena-ux).
- **The scripts** (`Source/nss`): the NWScript that runs inside the game.

Story progression is kept in journal quests, one per planet, so a loaded older save brings back the stage it had. Optional randomizers change shops, loot, enemies and doors.

## What you need

- A legitimate copy of KOTOR 2 (Steam). **Nothing from the game is distributed**: everything derived from it is built on your machine from your own install (see `PROVENANCE.md`).
- Archipelago, Python for the client's dependencies (`pykotor`, `numpy`, `pillow`).

## Checking the code

- `SECURITY.md` says what the software does on your computer and which checks limit it.
- `PROVENANCE.md` says where every file comes from.
- `RELEASE_CHECKLIST.md` is what has to be done before any release.
- GitHub runs four checks on every change (provenance, capabilities, world tests, client tests).

## AI usage

Much of the code was written with an AI model, directed and reviewed by the maintainer. `SECURITY.md` and the capability check exist because of that.

## Credits

- Archipelago (MIT) – the multiworld framework.
- [K2SE](https://github.com/renanaugustomacena-ux/K2SE) by [renanaugustomacena-ux](https://github.com/renanaugustomacena-ux) (MIT, as stated in its README) – the script extender the in-game extension is forked from. Much of the extension's core (the script-engine hooks, the routine table, the offsets and the offset-checking tools) is theirs, with our changes and additions on top.
- [Kotor-Patch-Manager](https://github.com/LaneDibello/Kotor-Patch-Manager) by LaneDibello (MIT) – part of the address table comes from its Steam/Aspyr database, and the 32-slot companion roster follows the design of its PartyRosterLimit32K2 mod by Vriff (our own implementation).
- K1SE (MIT) – the KOTOR 1 extender whose design this project follows.
- nwnsc 1.1.5 (MIT, Ken Johnson; BSD-3 compiler library) – the script compiler. Licence and credits in `Source/tools/nwnsc`.
- **[MDLOps](https://deadlystream.com/files/file/779-mdlops/)** v1.0.0, written by Chuck Chargin Jr., with animation support by JdNoa, version 1.0 by ndix UR and many other contributors (GPL; submitted to Deadly Stream by Fair Strides) – **planned**, for editing character models from your own game. Not used or shipped yet; when it is, it ships unchanged with its licence, readme and tutorials, as in the KOTOR 1 project.
- pykotor – reading and writing the game's file formats.
- [Ghidra](https://github.com/NationalSecurityAgency/ghidra) (NSA, Apache 2.0) – used to study the game's program when working out the extension's addresses. Nothing of it is shipped.
- [xoreos-tools](https://github.com/xoreos/xoreos-tools) (xoreos team) – used as a reference when cross-checking the game's script-engine behaviour. Nothing of it is shipped.
