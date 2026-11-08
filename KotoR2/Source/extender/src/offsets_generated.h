// =============================================================================
// GENERATED FILE -- DO NOT EDIT.
//
//   source: data/k2se_addresses.csv
//   regen : python tools/gen_offsets.py
//
// Addresses for swkotor2.exe, Aspyr/Steam build, FileVersion 1.0.2.0,
// TimeDateStamp 0x5603005D. The executable is RELOCS_STRIPPED with no ASLR, so
// every value here is a stable absolute VA.
//
// Provenance is recorded per constant:
//   kpm-db       Kotor-Patch-Manager AddressDatabases/kotor2_steam_aspyr.db (MIT).
//                Data only -- no code from that project is used in K2SE.
//   k2se-ghidra  derived in this project.
//
// Verification is a claim about THIS binary, not about the source:
//   runtime      exercised in a live game session
//   disasm       the function body was read
//   callsite     reached via the rel32 of a verified E8 in a real handler
//   prologue     entry point is in .text and starts with 55 8B EC
//   unverified   imported but unchecked -- MUST NOT be called from shipping code
//
// tools/verify_offsets.py re-checks every row against the executable.
// =============================================================================

#pragma once
#include <cstdint>

namespace k2se {
namespace off {
namespace game {

// --- functions ---------------------------------------------------
// engine entry points

// CClientExoApp
constexpr uint32_t kCClientExoApp_GetClientObjectById = 0x0073F550;  // disasm -- ret 4; [this+4] -> 0x0078BDF0(id)
constexpr uint32_t kCClientExoApp_GetClientOptions    = 0x0072FB00;  // prologue

// CClientOptions
constexpr uint32_t kCClientOptions_SetCameraMode = 0x007B5E50;  // prologue

// CExoString
constexpr uint32_t kCExoString_CStrConstructor    = 0x00733570;  // prologue
constexpr uint32_t kCExoString_CStrLenConstructor = 0x00733680;  // prologue
constexpr uint32_t kCExoString_DefaultConstructor = 0x00733540;  // disasm -- zeroes CStr and Length, nothing else
constexpr uint32_t kCExoString_Destructor         = 0x00733780;  // disasm -- frees the game-owned buffer and nulls CStr

// CGameObjectArray
constexpr uint32_t kCGameObjectArray_GetGameObject = 0x0053DFB0;  // prologue

// CSWBehaviorCamera
constexpr uint32_t kCSWBehaviorCamera_ApplyPendingStyle   = 0x007DE740;  // disasm -- reloads the style from global 0x00A108F8 when it is not -1, then resets it (script SetCameraStyle path)
constexpr uint32_t kCSWBehaviorCamera_LoadAreaCameraStyle = 0x007E1BD0;  // disasm -- wrapper: row = clientApp->0x0073F430()->+0x48->+0xB8 (the area's CameraStyle field)
constexpr uint32_t kCSWBehaviorCamera_LoadCameraStyle     = 0x007E1CA0;  // disasm -- (int row) ret 4; camerastyle.2da DISTANCE->+0x16C SPEED->+0x170 PITCH->+0x178 HEIGHT->+0x17C TILTSPEED->+0x190; row->+0x5C; distance copy->+0x88; VIEWANGLE->+0x8C and Camera::SetFOV via [this+0x1C]->vtable[1](). camera.cpp redirects its 3 call sites
constexpr uint32_t kCSWBehaviorCamera_SetupFromDefinition = 0x007DDA10;  // disasm -- copies a camera definition (+0x10 style row, +0x14, +0x18) then LoadCameraStyle at 0x007DDC52
constexpr uint32_t kCSWBehaviorCamera_ctor                = 0x007DD380;  // disasm -- stores vtable 0x009A1F94 at 0x007DD3C3; loads the area style through 0x007E1BD0 at 0x007DD5D7

// CSWCAnimBase
constexpr uint32_t kCSWCAnimBase_GetModel    = 0x00861690;  // disasm -- vtable slot +0x98; (uint8 equipSlot, int flag); returns null unless [this+0xB8] is set and slot==0xFF
constexpr uint32_t kCSWCAnimBase_MapAnimCode = 0x00863650;  // disasm -- vtable +0xE0; (uint16 code) -> animations.2da row (0x290D -> 567)
constexpr uint32_t kCSWCAnimBase_PlayRow     = 0x00860280;  // disasm -- vtable +0x44; (uint16 row, int flag) ret 8 -> 0x008602C0(model, row, flag)

// CSWCAppearance
constexpr uint32_t kCSWCAppearance_CameraHookNode = 0x0085D260;  // disasm -- thiscall no args ret 0; model=[this+0x3C]->vt[0x98](0xFF,1); node=model->vt[0x10C](CAMERAHOOK); returns node->vt[0x18]() or the model. Class name is a hypothesis -- it is the object at CSWCCreature+0x224

// CSWCCreature
constexpr uint32_t kCSWCCreature_GetAnimBase       = 0x007ED830;  // callsite -- called by PlayOverlayAnimation handler 0x0068F440; returns CSWCAnimBase*
constexpr uint32_t kCSWCCreature_GetCameraHookNode = 0x00775930;  // disasm -- vtable slot +0xD0; thiscall no args; forwards to 0x0085D260 on [this+0x224]
constexpr uint32_t kCSWCCreature_GetDriveAccel     = 0x0077F600;  // disasm -- appearance+0x58, or const when stealthed without FEAT_STEALTH_RUN
constexpr uint32_t kCSWCCreature_GetModel          = 0x007747D0;  // disasm -- vtable slot +0x98; (uint8 equipSlot, int flag); 0xFF selects the body model; guards on [this+0x68] and [this+0x328]
constexpr uint32_t kCSWCCreature_SetDriveSpeed     = 0x00776E10;  // disasm -- ret 8: writes +0x3C8 speed, +0x3CC

// CSWCMessage
constexpr uint32_t kCSWCMessage_HandleServerToClientCreatureUpdate = 0x008079B0;  // disasm -- 3537 instructions; rewrites the client flag block +0x2E8..+0x2F4 (stealth bit at 0x00809E01)

// CSWCObject
constexpr uint32_t kCSWCObject_GetServerObject = 0x0077D800;  // disasm -- via 0x007F2540 then vtable+0x30

// CSWCameraFreeLook
constexpr uint32_t kCSWCameraFreeLook_Update = 0x007E2AA0;  // disasm -- vtable slot 2; (float dt) ret 4; asks [this+0x14]->vt[0x98](name,&pos,&ori) for FreeLookHook then CameraHook (nonzero = found), then feeds the position to [this+0x10]->vt[0x5C]

// CSWInventory
constexpr uint32_t kCSWInventory_GetItemInSlot = 0x006D0620;  // prologue

// CSWItem
constexpr uint32_t kCSWItem_GetBaseItem = 0x006D6E30;  // prologue

// CSWPlayerControlCamRelative
constexpr uint32_t kCSWPlayerControlCamRelative_GetAccel        = 0x00867CA0;  // disasm -- thiscall, float: CSWCCreature::GetDriveAccel of the player
constexpr uint32_t kCSWPlayerControlCamRelative_GetAcceleration = 0x00867AB0;  // disasm -- ret 0xC (out, vel, target); RK4 spring using GetAccel/GetMaxSpeed
constexpr uint32_t kCSWPlayerControlCamRelative_GetMaxSpeed     = 0x00867B40;  // disasm -- thiscall, float in ST0: appearance+0x5C or stealth speed +0x60; redirected by movement.cpp
constexpr uint32_t kCSWPlayerControlCamRelative_Update          = 0x00865830;  // disasm -- ret 4 (float dt); the driven-player frame

// CSWSArea
constexpr uint32_t kCSWSArea_GetGroundZ        = 0x0054B130;  // callsite -- (Vector* pos, int 1, int 0, int 0) -> float -- HYPOTHESIS from the mover
constexpr uint32_t kCSWSArea_TestMoveSegment   = 0x00550980;  // callsite -- (Vector* dst, Vector* src, float* radius, float hitradius, int, int) -> 1 when the move is free -- HYPOTHESIS from the mover
constexpr uint32_t kCSWSArea_TestPointWalkable = 0x0054B650;  // callsite -- (Vector*, CPathfindInformation*) -> 1 -- HYPOTHESIS from the mover

// CSWSCreature
constexpr uint32_t kCSWSCreature_CreateFromTemplate   = 0x00576750;  // disasm -- ret 8; LoadAppearance at 0x00576AAF; callers 0x00572F58, 0x005744CC, 0x00630E17, 0x00631500 (name is a hypothesis)
constexpr uint32_t kCSWSCreature_DriveMoverUpdate     = 0x005C6340;  // disasm -- ret 0x10; reads the client drive speed, runs the walkmesh state machine (0x005C7370..0x005CB190), commits with SetPosition at 0x005C6E87/0x005C6ED8/0x005C6F9E
constexpr uint32_t kCSWSCreature_GetClientCreature    = 0x0058AE90;  // prologue
constexpr uint32_t kCSWSCreature_HasModeFlag          = 0x00563D70;  // disasm -- ret 4; (this+0x1120 & mask) != 0; IsStealthed passes 1
constexpr uint32_t kCSWSCreature_LoadAppearance       = 0x0057FCE0;  // disasm -- thiscall (int) ret 4; reads the appearance.2da row from word [this+0x1184]; four E8 callers, all redirected by npcvariety.cpp
constexpr uint32_t kCSWSCreature_LoadFromGFF_A        = 0x006AFED0;  // disasm -- UTC/save reader: FirstName..Appearance_Type, Appearance_Head (no TextureVar for creatures)
constexpr uint32_t kCSWSCreature_LoadFromGFF_B        = 0x006B3D10;  // disasm -- second creature GFF reader, 78 fields, Appearance_Type at 0x006B4B0C
constexpr uint32_t kCSWSCreature_MovementUpdate       = 0x005C3F70;  // disasm -- ret 4; calls DriveMoverUpdate when [this+0x11B0]==3
constexpr uint32_t kCSWSCreature_SetAppearanceType    = 0x00585120;  // disasm -- ret 16; writes +0x1184 at 0x005851D1/0x00585208 then LoadAppearance at 0x00585241; 10 callers incl. the script command handler 0x0066B7EF and the GUI 0x0085D5xx
constexpr uint32_t kCSWSCreature_SetAppearanceVariant = 0x00585310;  // disasm -- ret 4; writes +0x1184 at 0x00585364 then LoadAppearance at 0x0058536E; callers 0x005A4C85, 0x005A4D5F

// CSWSCreatureStats
constexpr uint32_t kCSWSCreatureStats_AddFeat         = 0x006F5B40;  // prologue
constexpr uint32_t kCSWSCreatureStats_AddKnownSpell   = 0x006B86A0;  // prologue
constexpr uint32_t kCSWSCreatureStats_GetClass        = 0x00844E40;  // prologue
constexpr uint32_t kCSWSCreatureStats_GetSkillRank    = 0x006B7BB0;  // prologue
constexpr uint32_t kCSWSCreatureStats_HasFeat         = 0x006B83F0;  // prologue
constexpr uint32_t kCSWSCreatureStats_HasSpell        = 0x006BD9C0;  // prologue
constexpr uint32_t kCSWSCreatureStats_RemoveFeat      = 0x006B85F0;  // prologue
constexpr uint32_t kCSWSCreatureStats_SetCHABase      = 0x006B69A0;  // prologue
constexpr uint32_t kCSWSCreatureStats_SetCONBase      = 0x006B6850;  // prologue
constexpr uint32_t kCSWSCreatureStats_SetDEXBase      = 0x006B6810;  // prologue
constexpr uint32_t kCSWSCreatureStats_SetINTBase      = 0x006B6920;  // prologue
constexpr uint32_t kCSWSCreatureStats_SetMovementRate = 0x006BA320;  // prologue
constexpr uint32_t kCSWSCreatureStats_SetSTRBase      = 0x006B67D0;  // prologue
constexpr uint32_t kCSWSCreatureStats_SetSkillRank    = 0x006B81C0;  // prologue
constexpr uint32_t kCSWSCreatureStats_SetWISBase      = 0x006B6960;  // prologue

// CSWSObject
constexpr uint32_t kCSWSObject_AddActionToFront = 0x00540CA0;  // prologue
constexpr uint32_t kCSWSObject_GetArea          = 0x005453C0;  // callsite -- used as `this` for the area walkmesh tests in the drive mover
constexpr uint32_t kCSWSObject_SetDirtyBit      = 0x0054A430;  // disasm -- ret 4; bitset at +0x224
constexpr uint32_t kCSWSObject_SetOrientation   = 0x00543F10;  // disasm -- ret 4; writes +0xA0; dirty bit 2
constexpr uint32_t kCSWSObject_SetPosition      = 0x00543F50;  // disasm -- ret 0x10 (Vector*, int bClient, int, int bNoDirty); early-out if equal; dirty bit 1; redirected in the drive mover by movement.cpp

// CSWVirtualMachineCommands
constexpr uint32_t kCSWVirtualMachineCommands_ExecuteCommand         = 0x00668FD0;  // runtime -- vtable slot 2; the NWScript routine dispatcher. K2SE hooks this slot
constexpr uint32_t kCSWVirtualMachineCommands_InitializeCommands     = 0x00665F50;  // runtime -- vtable slot 1; allocates 877*4 and fills the routine table with literal stores
constexpr uint32_t kCSWVirtualMachineCommands_InitializeSWMGCommands = 0x006F5B80;  // disasm -- minigame installer; fills the remaining 103 routine slots

// CServerExoApp
constexpr uint32_t kCServerExoApp_GetCreatureByGameObjectID = 0x0051C100;  // prologue
constexpr uint32_t kCServerExoApp_GetObjectArray            = 0x0051C080;  // prologue
constexpr uint32_t kCServerExoApp_GetPlayerCreatureId       = 0x0051C8F0;  // prologue

// CVirtualMachine
constexpr uint32_t kCVirtualMachine_RunScript                = 0x006FD8D0;  // prologue
constexpr uint32_t kCVirtualMachine_StackPopCommand          = 0x006FDB30;  // prologue
constexpr uint32_t kCVirtualMachine_StackPopEngineStructure  = 0x006FDAB0;  // disasm -- ret 8: (int type, void** out). Type tag values still unverified
constexpr uint32_t kCVirtualMachine_StackPopFloat            = 0x006FD9E0;  // runtime -- exercised in a live K2SE session
constexpr uint32_t kCVirtualMachine_StackPopInteger          = 0x006FD9A0;  // runtime -- exercised in a live K2SE session
constexpr uint32_t kCVirtualMachine_StackPopObject           = 0x006FDAF0;  // runtime -- exercised in a live K2SE session
constexpr uint32_t kCVirtualMachine_StackPopString           = 0x006FDA70;  // disasm -- copy-assigns into the caller's CExoString, which must be constructed first
constexpr uint32_t kCVirtualMachine_StackPopVector           = 0x006FDA20;  // prologue
constexpr uint32_t kCVirtualMachine_StackPushEngineStructure = 0x006FDAD0;  // disasm -- ret 8: (int type, void* value). Type tag values still unverified
constexpr uint32_t kCVirtualMachine_StackPushFloat           = 0x006FDA00;  // runtime -- exercised in a live K2SE session
constexpr uint32_t kCVirtualMachine_StackPushInteger         = 0x006FD9C0;  // runtime -- exercised in a live K2SE session
constexpr uint32_t kCVirtualMachine_StackPushObject          = 0x006FDB10;  // runtime -- exercised in a live K2SE session
constexpr uint32_t kCVirtualMachine_StackPushString          = 0x006FDA90;  // disasm -- allocates its own CExoString and copies; the caller retains ownership
constexpr uint32_t kCVirtualMachine_StackPushVector          = 0x006FDA40;  // prologue

// Camera
constexpr uint32_t kCamera_ApplyProjection = 0x0047F320;  // disasm -- vtable slot 2; the only gluPerspective caller in the exe (E8 0x0047F6D7 -> thunk 0x0093B436 -> IAT 0x00986028); fovy = [this+0x204], near +0x210, far +0x214; also derives the culling frustum from +0x204
constexpr uint32_t kCamera_SetFOV          = 0x0047F190;  // disasm -- vtable slot 17; (float degrees) ret 4; writes +0x204
constexpr uint32_t kCamera_SetNearFar      = 0x0047F160;  // disasm -- vtable slot 16; (float near, float far) ret 8
constexpr uint32_t kCamera_Update          = 0x00480E40;  // disasm -- vtable slot 3; (float dt) ret 4; advances the FOV animation at +0x208 (0x14 bytes: duration, elapsed, from, to, easing 0..3) then 0x004E1D40(this+4, dt)

// ConsoleFunc
constexpr uint32_t kConsoleFunc_Destructor         = 0x004759B0;  // prologue
constexpr uint32_t kConsoleFunc_IntConstructor     = 0x00475910;  // prologue
constexpr uint32_t kConsoleFunc_NoParamConstructor = 0x004757D0;  // prologue
constexpr uint32_t kConsoleFunc_StringConstructor  = 0x00475870;  // prologue

// Other
constexpr uint32_t kOther_AurPostString                    = 0x00474C00;  // runtime -- exercised in a live K2SE session
constexpr uint32_t kOther_LoadAppearanceCaller_65A170      = 0x0065A170;  // disasm -- ret 8; LoadAppearance at 0x0065A9DD; single caller 0x0065FD17
constexpr uint32_t kOther_RoutineHandler_GetArea           = 0x0067A070;  // disasm -- routine 24; source of the verified StackPopObject call site
constexpr uint32_t kOther_RoutineHandler_GetFirstPC        = 0x006875E0;  // disasm -- routine 548; source of StackPushObject and of OBJECT_INVALID = 0x7F000000
constexpr uint32_t kOther_RoutineHandler_Math              = 0x0068C4A0;  // runtime -- shared handler for routines 67..77 (fabs..abs); K2SE's presence probe rides on it
constexpr uint32_t kOther_RoutineHandler_Random            = 0x0068F5D0;  // runtime -- routine 0, Random
constexpr uint32_t kOther_RoutineHandler_RebuildPartyTable = 0x0069C460;  // runtime -- routine 876, the last vanilla routine

// --- globals -----------------------------------------------------
// pointer variables; dereference to reach the object
constexpr uint32_t kGlobal_APP_MANAGER_PTR          = 0x00A1B4A4;  // unverified -- in .data; holds a runtime pointer, not statically checkable
constexpr uint32_t kGlobal_AURORA_PTR               = 0x00A1B4A0;  // unverified -- in .data; holds a runtime pointer, not statically checkable
constexpr uint32_t kGlobal_EXO_RESOURCE_MANAGER_PTR = 0x00A1B490;  // unverified -- in .data; holds a runtime pointer, not statically checkable
constexpr uint32_t kGlobal_GUI_MANAGER_PTR          = 0x00A1B49C;  // unverified -- in .data; holds a runtime pointer, not statically checkable
constexpr uint32_t kGlobal_IAT_glFogf               = 0x00986394;  // disasm -- OPENGL32.dll, by import name
constexpr uint32_t kGlobal_IAT_glFogfv              = 0x00986398;  // disasm -- OPENGL32.dll, by import name
constexpr uint32_t kGlobal_IAT_glFogi               = 0x009863B0;  // disasm -- OPENGL32.dll, by import name
constexpr uint32_t kGlobal_IAT_gluPerspective       = 0x00986028;  // disasm -- GLU32.dll, by import name
constexpr uint32_t kGlobal_PendingCameraStyleRow    = 0x00A108F8;  // disasm -- int; -1 = none; consumed by CSWBehaviorCamera::ApplyPendingStyle
constexpr uint32_t kGlobal_RENDER_AABB              = 0x00A73284;  // unverified -- in .data; holds a runtime pointer, not statically checkable
constexpr uint32_t kGlobal_RENDER_GOB_BBS           = 0x00A73740;  // unverified -- in .data; holds a runtime pointer, not statically checkable
constexpr uint32_t kGlobal_RENDER_GUI               = 0x00A32A30;  // unverified -- in .data; holds a runtime pointer, not statically checkable
constexpr uint32_t kGlobal_RENDER_PERSONAL_SPACE    = 0x00A2006C;  // unverified -- in .data; holds a runtime pointer, not statically checkable
constexpr uint32_t kGlobal_RENDER_QA_TRIGGERS       = 0x00A2003C;  // unverified -- in .data; holds a runtime pointer, not statically checkable
constexpr uint32_t kGlobal_RENDER_TRIGGERS          = 0x00A7E0E8;  // unverified -- in .data; holds a runtime pointer, not statically checkable
constexpr uint32_t kGlobal_RENDER_WIREFRAME         = 0x00A32A50;  // unverified -- in .data; holds a runtime pointer, not statically checkable
constexpr uint32_t kGlobal_RULES_PTR                = 0x00A1B4D0;  // unverified -- in .data; holds a runtime pointer, not statically checkable
constexpr uint32_t kGlobal_TLK_TABLE_PTR            = 0x00A1B4B0;  // unverified -- in .data; holds a runtime pointer, not statically checkable
constexpr uint32_t kGlobal_VIRTUAL_MACHINE_PTR      = 0x00A1B4A8;  // runtime -- exercised in a live K2SE session

// Other
constexpr uint32_t kGlobal_APPEARANCE_COL_CREPERSPACE     = 0x00A0FD9C;  // disasm
constexpr uint32_t kGlobal_APPEARANCE_COL_DRIVEACCL       = 0x00A0FDA4;  // disasm
constexpr uint32_t kGlobal_APPEARANCE_COL_DRIVEANIMRUN_PC = 0x00A0FDA8;  // disasm
constexpr uint32_t kGlobal_APPEARANCE_COL_DRIVEANIMWALK   = 0x00A0FDB4;  // disasm
constexpr uint32_t kGlobal_APPEARANCE_COL_DRIVEMAXSPEED   = 0x00A0FDB0;  // disasm
constexpr uint32_t kGlobal_APPEARANCE_COL_HITRADIUS       = 0x00A0FDD4;  // disasm
constexpr uint32_t kGlobal_APPEARANCE_COL_PERSPACE        = 0x00A0FDE4;  // disasm
constexpr uint32_t kGlobal_APPEARANCE_COL_RUNDIST         = 0x00A0FDEC;  // disasm
constexpr uint32_t kGlobal_CREATURESPEED_COL_RUNRATE      = 0x00A0FF10;  // disasm
constexpr uint32_t kGlobal_CREATURESPEED_COL_WALKRATE     = 0x00A0FF0C;  // disasm

// --- struct offsets ----------------------------------------------
// byte displacement from `this`

// CAppManager
constexpr uint32_t kOff_CAppManager_Client = 0x0004;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CAppManager_Server = 0x0008;  // unverified -- struct layout; confirm against a consuming handler

// CExoString
constexpr uint32_t kOff_CExoString_CStr   = 0x0000;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CExoString_Length = 0x0004;  // unverified -- struct layout; confirm against a consuming handler

// CGameObject
constexpr uint32_t kOff_CGameObject_Id         = 0x0004;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CGameObject_ObjectType = 0x0008;  // unverified -- struct layout; confirm against a consuming handler

// CPathfindInformation
constexpr uint32_t kOff_CPathfindInformation_cameraspace = 0x00000010;  // disasm
constexpr uint32_t kOff_CPathfindInformation_creperspace = 0x00000008;  // disasm
constexpr uint32_t kOff_CPathfindInformation_hitradius   = 0x00000014;  // disasm -- fallback 1.0
constexpr uint32_t kOff_CPathfindInformation_perspace    = 0x00000004;  // disasm -- read by the mover

// CSWBaseItem
constexpr uint32_t kOff_CSWBaseItem_WeaponWield = 0x0008;  // unverified -- struct layout; confirm against a consuming handler

// CSWBehaviorCamera
constexpr uint32_t kOff_CSWBehaviorCamera_AuroraCameraHolder = 0x0000001C;  // disasm -- pointer; its vtable[1]() returns the Aurora Camera
constexpr uint32_t kOff_CSWBehaviorCamera_Distance           = 0x0000016C;  // disasm -- float; read by the chase placement at 0x007E0D25, 0x007E22EF, 0x007E23D2; written by camera.cpp presets
constexpr uint32_t kOff_CSWBehaviorCamera_DistanceCopy       = 0x00000088;  // disasm -- float = distance at load time; read at 0x007DE26C
constexpr uint32_t kOff_CSWBehaviorCamera_Height             = 0x0000017C;  // disasm -- float; read at 0x007E152B, 0x007E2339, 0x007E2492
constexpr uint32_t kOff_CSWBehaviorCamera_Pitch              = 0x00000178;  // disasm -- float degrees; read at 0x007DD644, 0x007DDD72, 0x007DE199, 0x007DE83A
constexpr uint32_t kOff_CSWBehaviorCamera_Speed              = 0x00000170;  // disasm -- float
constexpr uint32_t kOff_CSWBehaviorCamera_StyleRow           = 0x0000005C;  // disasm -- int; -1 before the first load
constexpr uint32_t kOff_CSWBehaviorCamera_TiltSpeed          = 0x00000190;  // disasm -- float
constexpr uint32_t kOff_CSWBehaviorCamera_ViewAngle          = 0x0000008C;  // disasm -- float; the FOV handed to Camera::SetFOV (55 for DEFAULT, 60 EbonHawk)

// CSWCAppearance
constexpr uint32_t kOff_CSWCAppearance_AnimBase = 0x0000003C;  // disasm -- pointer to the CSWCAnimBase whose vtable[0x98] returns the Aurora model

// CSWCCreature
constexpr uint32_t kOff_CSWCCreature_Appearance  = 0x00000224;  // disasm -- pointer; player.cpp already resolves it; its CameraHookNode (0x0085D260) reaches the model
constexpr uint32_t kOff_CSWCCreature_Running     = 0x03F8;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CSWCCreature_appearance  = 0x00000224;  // disasm -- CSWCCreatureAppearance*
constexpr uint32_t kOff_CSWCCreature_drive_speed = 0x000003C8;  // disasm -- float
constexpr uint32_t kOff_CSWCCreature_flags       = 0x000002EC;  // disasm -- word; bit0 stealth (client)
constexpr uint32_t kOff_CSWCCreature_running     = 0x000003F8;  // disasm -- byte (IsRunning)

// CSWCCreatureAppearance
constexpr uint32_t kOff_CSWCCreatureAppearance_drive_accel     = 0x00000058;  // disasm
constexpr uint32_t kOff_CSWCCreatureAppearance_drive_max_speed = 0x0000005C;  // disasm
constexpr uint32_t kOff_CSWCCreatureAppearance_stealth_speed   = 0x00000060;  // disasm -- name is a hypothesis

// CSWCameraFreeLook
constexpr uint32_t kOff_CSWCameraFreeLook_Camera = 0x00000010;  // disasm -- pointer; receives the hook position through vtable slot 0x5C
constexpr uint32_t kOff_CSWCameraFreeLook_Model  = 0x00000014;  // disasm -- pointer; the object queried for node position+orientation by name via vtable slot 0x98

// CSWPlayerControlCamRelative
constexpr uint32_t kOff_CSWPlayerControlCamRelative_camera     = 0x00000008;  // disasm
constexpr uint32_t kOff_CSWPlayerControlCamRelative_enabled    = 0x0000000C;  // disasm
constexpr uint32_t kOff_CSWPlayerControlCamRelative_left_right = 0x00000014;  // disasm
constexpr uint32_t kOff_CSWPlayerControlCamRelative_player_id  = 0x00000004;  // disasm
constexpr uint32_t kOff_CSWPlayerControlCamRelative_up_down    = 0x00000010;  // disasm
constexpr uint32_t kOff_CSWPlayerControlCamRelative_walking    = 0x00000018;  // disasm -- walk modifier

// CSWSCombatRound
constexpr uint32_t kOff_CSWSCombatRound_OnHandAttacks = 0x0AE0;  // unverified -- struct layout; confirm against a consuming handler

// CSWSCreature
constexpr uint32_t kOff_CSWSCreature_AppearanceRow    = 0x00001184;  // disasm -- uint16 appearance.2da row; the only 16-bit stores are in SetAppearanceType/Variant
constexpr uint32_t kOff_CSWSCreature_CreatureStats    = 0x1198;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CSWSCreature_Inventory        = 0x1150;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CSWSCreature_appearance_type  = 0x00001184;  // disasm -- ushort
constexpr uint32_t kOff_CSWSCreature_combat_real_flag = 0x000011E8;  // disasm -- byte, GetIsInCombat bOnlyCountReal
constexpr uint32_t kOff_CSWSCreature_combat_round     = 0x00000520;  // disasm -- non-null in combat
constexpr uint32_t kOff_CSWSCreature_drive_accel      = 0x000011EC;  // disasm -- from DRIVEACCl
constexpr uint32_t kOff_CSWSCreature_mode_flags       = 0x00001120;  // disasm -- bit0 stealth
constexpr uint32_t kOff_CSWSCreature_move_flags       = 0x00001114;  // disasm -- word; bit1 cleared for Immobile
constexpr uint32_t kOff_CSWSCreature_orientation      = 0x000000A0;  // disasm -- Vector
constexpr uint32_t kOff_CSWSCreature_pathfind_info    = 0x00000380;  // disasm -- CPathfindInformation*
constexpr uint32_t kOff_CSWSCreature_position         = 0x00000094;  // disasm -- Vector

// CSWSCreatureStats
constexpr uint32_t kOff_CSWSCreatureStats_CHABase       = 0x00F7;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CSWSCreatureStats_CONBase       = 0x00F1;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CSWSCreatureStats_ClassCount    = 0x008D;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CSWSCreatureStats_DEXBase       = 0x00EF;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CSWSCreatureStats_INTBase       = 0x00F3;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CSWSCreatureStats_STRBase       = 0x00ED;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CSWSCreatureStats_WISBase       = 0x00F5;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CSWSCreatureStats_movement_rate = 0x000001A4;  // disasm -- creaturespeed row
constexpr uint32_t kOff_CSWSCreatureStats_runrate       = 0x000001AC;  // disasm -- float
constexpr uint32_t kOff_CSWSCreatureStats_walkrate      = 0x000001A8;  // disasm -- float

// CSWSObject
constexpr uint32_t kOff_CSWSObject_AreaId      = 0x0090;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CSWSObject_Orientation = 0x00A0;  // unverified -- struct layout; confirm against a consuming handler
constexpr uint32_t kOff_CSWSObject_Position    = 0x0094;  // unverified -- struct layout; confirm against a consuming handler

// CSWVirtualMachineCommands
constexpr uint32_t kOff_CSWVirtualMachineCommands_m_pCommands = 0x000C;  // runtime -- the routine table pointer; byte read at both 0x00665F71 and 0x00668FE7

// CTwoDimArrays
constexpr uint32_t kOff_CTwoDimArrays_camerastyle = 0x00000078;  // disasm -- table pointer

// CVirtualMachine
constexpr uint32_t kOff_CVirtualMachine_m_pInternal = 0x001C;  // disasm -- every stack accessor forwards through it (mov ecx,[ecx+1Ch] at 0x006FD9B0)

// Camera
constexpr uint32_t kOff_Camera_FOV          = 0x00000204;  // disasm -- float, vertical degrees; default 45.0 from [0x0098C274]
constexpr uint32_t kOff_Camera_FOVAnimation = 0x00000208;  // disasm -- pointer to a 0x14-byte lerp state or null
constexpr uint32_t kOff_Camera_Far          = 0x00000214;  // disasm -- float; default 100.0
constexpr uint32_t kOff_Camera_Near         = 0x00000210;  // disasm -- float; default 0.1

// --- constants ---------------------------------------------------
// values read out of instruction immediates

// CSWVirtualMachineCommands
constexpr uint32_t kCSWVirtualMachineCommands_RoutineTableAllocBytes = 0x00000DB4;  // runtime -- 877*4; the `push 0DB4h` at 0x00665F5A, unique in the whole 6.5MB image
constexpr uint32_t kCSWVirtualMachineCommands_VanillaRoutineCount    = 0x0000036D;  // runtime -- 877; the dispatcher's bound at 0x00668FDC and init's at 0x00665F87

// CVirtualMachine
constexpr uint32_t kCVirtualMachine_RunScript_ret = 0x0000000C;  // disasm -- RunScript(CExoString* name, uint32 objectId, int flag) pops 12 bytes; used by spawner.cpp

// CallSite
constexpr uint32_t kCallSite_GetAccel_1                = 0x00867ABC;  // disasm -- E8 in GetAcceleration
constexpr uint32_t kCallSite_GetMaxSpeed_1             = 0x0086603C;  // disasm -- E8 in Update; first call each frame
constexpr uint32_t kCallSite_GetMaxSpeed_2             = 0x00867336;  // disasm -- E8 in Update
constexpr uint32_t kCallSite_GetMaxSpeed_3             = 0x00867AC7;  // disasm -- E8 in GetAcceleration
constexpr uint32_t kCallSite_LoadAppearance_1          = 0x00576AAF;  // disasm -- E8 in CreateFromTemplate; redirected by npcvariety.cpp
constexpr uint32_t kCallSite_LoadAppearance_2          = 0x00585241;  // disasm -- E8 in SetAppearanceType; redirected by npcvariety.cpp
constexpr uint32_t kCallSite_LoadAppearance_3          = 0x0058536E;  // disasm -- E8 in SetAppearanceVariant; redirected by npcvariety.cpp
constexpr uint32_t kCallSite_LoadAppearance_4          = 0x0065A9DD;  // disasm -- E8 in 0x0065A170; redirected by npcvariety.cpp
constexpr uint32_t kCallSite_LoadCameraStyle_1         = 0x007E1C0B;  // disasm -- E8 in the wrapper 0x007E1BD0; redirected by camera.cpp
constexpr uint32_t kCallSite_LoadCameraStyle_2         = 0x007DDC52;  // disasm -- E8 in SetupFromDefinition; redirected by camera.cpp
constexpr uint32_t kCallSite_LoadCameraStyle_3         = 0x007DE7D6;  // disasm -- E8 in ApplyPendingStyle; redirected by camera.cpp
constexpr uint32_t kCallSite_SetDriveSpeed_update_tail = 0x00867A33;  // disasm -- E8 -> 0x00776E10 at the end of Update; once per frame; redirected by movement.cpp
constexpr uint32_t kCallSite_SetPosition_mover_1       = 0x005C6E87;  // disasm -- E8 in DriveMoverUpdate (free move)
constexpr uint32_t kCallSite_SetPosition_mover_2       = 0x005C6ED8;  // disasm -- E8 in DriveMoverUpdate (target reached)
constexpr uint32_t kCallSite_SetPosition_mover_3       = 0x005C6F9E;  // disasm -- E8 in DriveMoverUpdate (tiny move)
constexpr uint32_t kCallSite_gluPerspective_thunk      = 0x0047F6D7;  // disasm -- E8 -> 0x0093B436 (jmp [IAT 0x00986028]); the single gluPerspective call

// Camera
constexpr uint32_t kCamera_DefaultFOV = 0x0098C274;  // disasm -- float 45.0; default far 100.0 sits at 0x0098C270

// Const
constexpr uint32_t kConst_AnimRowDiveRoll        = 0x00000237;  // disasm -- animations.2da diveroll
constexpr uint32_t kConst_OverlayCodeDiveRoll    = 0x0000290D;  // disasm -- anim code -> row 567
constexpr uint32_t kConst_WalkModifierFactorAddr = 0x0098C014;  // disasm -- float 0.5, multiplies the input vector when walking

// NodeName
constexpr uint32_t kNodeName_CameraHook      = 0x009A2078;  // disasm -- the string CameraHook; second name CSWCameraFreeLook::Update tries
constexpr uint32_t kNodeName_CameraHookUpper = 0x0099F178;  // disasm -- the string CAMERAHOOK; spelling used by CSWCAppearance::CameraHookNode
constexpr uint32_t kNodeName_FreeLookHook    = 0x009A2084;  // disasm -- the string FreeLookHook; first name CSWCameraFreeLook::Update tries
constexpr uint32_t kNodeName_HeadHookUpper   = 0x0099EF88;  // disasm -- the string HEADHOOK; where the head model attaches to the body

// Other
constexpr uint32_t kOther_ObjectInvalid = 0x7F000000;  // disasm -- the engine's own sentinel, from GetFirstPC's default value

// --- vtables -----------------------------------------------------
// virtual function table addresses

// CAuroraModel
constexpr uint32_t kVtable_CAuroraModel = 0x009B9568;  // disasm -- RTTI .?AVCAuroraModel@@; the model object returned by GetModel

// CSWBehaviorCamera
constexpr uint32_t kVtable_CSWBehaviorCamera = 0x009A1F94;  // disasm -- RTTI .?AVCSWBehaviorCamera@@, 8 slots; the game's chase camera object, holder of the camerastyle.2da values

// CSWCAnimBase
constexpr uint32_t kVtable_CSWCAnimBase = 0x009A454C;  // disasm -- RTTI, 62 slots

// CSWCCreature
constexpr uint32_t kVtable_CSWCCreature = 0x0099EE14;  // disasm -- RTTI .?AVCSWCCreature@@; slot +0x98 GetModel(uint8,int), slot +0xD0 GetCameraHookNode

// CSWCameraFreeLook
constexpr uint32_t kVtable_CSWCameraFreeLook = 0x009A2034;  // disasm -- RTTI .?AVCSWCameraFreeLook@@; 8 slots; ctor writes base vtable 0x009A1F94 first then this one (0x007E2519/0x007E2712/0x007E2A4D); slot 2 = Update(float)

// CSWPlayerControlCamRelative
constexpr uint32_t kVtable_CSWPlayerControlCamRelative = 0x009A4818;  // disasm -- RTTI, 12 slots

// CSWSCreature
constexpr uint32_t kVtable_CSWSCreature = 0x00994F5C;  // disasm -- RTTI, 57 slots

// CSWVirtualMachineCommands
constexpr uint32_t kVtable_CSWVirtualMachineCommands = 0x009940D0;  // runtime -- found via the MSVC RTTI string .?AVCSWVirtualMachineCommands@@ at 0x00A0F4F8

// Camera
constexpr uint32_t kVtable_Camera = 0x0098C45C;  // disasm -- RTTI .?AVCamera@@, 37 slots; slot 2 ApplyProjection, slot 3 Update (fov.cpp swaps it), slot 16 SetNearFar, slot 17 SetFOV

// --- class sizes -------------------------------------------------
// sizeof, where it has been established

// CExoString
constexpr uint32_t kSizeof_CExoString = 0x0008;  // disasm -- two dwords; confirmed twice -- the default ctor writes only +0x00 and +0x04, and StackPushString's callee does push 8 / operator new

}  // namespace game
}  // namespace off
}  // namespace k2se
