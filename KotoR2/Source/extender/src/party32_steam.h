#pragma once
#include <cstdint>

// Steam-build (swkotor2.exe, image base 0x400000) addresses used by the 32-slot party roster (party32.cpp).
// The names follow the ADDRESS_ constants of the Patch Manager mod PartyRosterLimit32K2 (MIT, by Vriff), whose GOG addresses were mapped to
// this exe by following the same calls through the stock code (research/patchmanager/ and docs/PARTY_SLOTS_32.md).

namespace k2se {
namespace party32 {
namespace steam {

// globals
constexpr uint32_t kAppManagerPtr = 0x00A1B4A4;   // [0xA1B4A4] -> app manager; +4 client, +8 server
constexpr uint32_t k2daRootPtr = 0x00A1B4D0;      // [..] -> +0x130 collection -> +0xF4 partynpc.2da table
constexpr uint32_t kEffectTypeWord = 0x00995F2C;  // read as a word by the post-load recovery effect
constexpr uint32_t kEffectSubtypeWord = 0x009967AC;

// party table (CSWPartyTable) module
constexpr uint32_t kGetNpcObject = 0x005FAAF0;
constexpr uint32_t kAddGameInProgress = 0x005FDCA0;
constexpr uint32_t kRemoveGameInProgress = 0x005FDD30;
constexpr uint32_t kTransferInventory = 0x005F8960;
constexpr uint32_t kPartyTableRemoveMember = 0x005F8B00;
constexpr uint32_t kPartyTableAddMember = 0x005F8D80;
constexpr uint32_t kPartyTableSpawnNpc = 0x005FD480;

// server application
constexpr uint32_t kGetCurrentPartyTable = 0x0051C8D0;
constexpr uint32_t kGetPlayerCreatureId = 0x0051C8F0;
constexpr uint32_t kGetCreatureByObjectId = 0x0051C100;
constexpr uint32_t kGetAiMaster = 0x0051C280;
constexpr uint32_t kAiMasterSetAiLevel = 0x0051E120;

// creature
constexpr uint32_t kCreatureCtor = 0x00561F30;
constexpr uint32_t kCreatureLoadFromTemplate = 0x00572A70;
constexpr uint32_t kCreatureSaveCreature = 0x00574500;
constexpr uint32_t kStatsGetLevel = 0x006A4E00;
constexpr uint32_t kReceiveExperience = 0x0058A9F0;
constexpr uint32_t kStatsSetMovementRate = 0x006BA320;
constexpr uint32_t kGameEffectCtor = 0x005E4920;
constexpr uint32_t kObjectApplyEffect = 0x00544210;

// generic engine
constexpr uint32_t kOperatorNew = 0x00919723;
constexpr uint32_t kCExoStringCtorCStr = 0x00733570;
constexpr uint32_t kCExoStringDtor = 0x00733780;

// GFF / 2DA
constexpr uint32_t kGffGetList = 0x00718760;
constexpr uint32_t kGffGetListCount = 0x00718810;
constexpr uint32_t kGffGetListElement = 0x00718890;
constexpr uint32_t kGffReadFieldByte = 0x00718A00;
constexpr uint32_t kGffReadFieldInt = 0x00718C80;
constexpr uint32_t kGffAddListElement = 0x00719800;
constexpr uint32_t kGffWriteFieldByte = 0x007199D0;
constexpr uint32_t kGffWriteFieldInt = 0x00719BF0;
constexpr uint32_t kResGffCtor = 0x00716E60;
constexpr uint32_t kResGffCreateFile = 0x0071A3D0;
constexpr uint32_t kResGffWriteFile = 0x0071A5A0;
constexpr uint32_t k2daGetIntEntry = 0x0071BCF0;

// creature / client side (resolved by following the stock party code; see research/patchmanager/map_creature.csv)
constexpr uint32_t kObjectClearAllActions = 0x00541080;
constexpr uint32_t kGetFaction = 0x005D0CB0;
constexpr uint32_t kFactionAddMember = 0x006D3330;
constexpr uint32_t kHandleAlignmentInfluence = 0x0056AE40;
constexpr uint32_t kServerCreatureSetInParty = 0x0058A330;
constexpr uint32_t kPathfindResetWaypointData = 0x006F9F70;
constexpr uint32_t kGetVisibleListElement = 0x005D1750;
constexpr uint32_t kAddToVisibleList = 0x005D1400;
constexpr uint32_t kServerToClientObjectId = 0x0073FEC0;
constexpr uint32_t kClientGetCreatureByObjectId = 0x0073F550;
constexpr uint32_t kClientGetParty = 0x0073FB90;
constexpr uint32_t kPartyGetCharacter = 0x007E5DA0;
constexpr uint32_t kPartyGetIndex = 0x007E6BE0;
constexpr uint32_t kClientCreatureSetInParty = 0x00775860;
constexpr uint32_t kClientCreatureGetServerCreature = 0x0077D800;
constexpr uint32_t kPartyRecalculateFollowPoint = 0x007E8720;

// GUI helpers for the paged party selection screen (map_gui.csv)
constexpr uint32_t kGuiPanelStopLoadFromLayout = 0x0040F5A0;
constexpr uint32_t kGuiPanelInitControl = 0x0040F620;
constexpr uint32_t kGuiPanelAddControl = 0x0040FD80;
constexpr uint32_t kGuiPanelSetActiveControl = 0x0040EC00;
constexpr uint32_t kExoArrayListPointerDelIndex = 0x0049B840;
constexpr uint32_t kGuiControlAddEvent = 0x00418AF0;
constexpr uint32_t kGuiButtonSetEnabled = 0x0041A210;
constexpr uint32_t kGuiSetMoveToControl = 0x004186F0;
constexpr uint32_t kGuiButtonCtor = 0x0041A510;
constexpr uint32_t kGuiButtonDtor = 0x0041A3D0;
constexpr uint32_t kGuiBorderSetFillImage = 0x00414840;
constexpr uint32_t kGuiBorderSetPulsingAlpha = 0x004149F0;
constexpr uint32_t kPartySelectionButtonSetSelected = 0x0089CE20;
constexpr uint32_t kPartySelectionRecordCtor = 0x0089DAC0;
constexpr uint32_t kPartySelectionRecordDtor = 0x0089DB40;
constexpr uint32_t kPartySelectionOnToggled = 0x0089EB50;
constexpr uint32_t kPartySelectionOnEnter = 0x0089EFF0;
constexpr uint32_t kPartySelectionOnExit = 0x0089F9B0;
constexpr uint32_t kPartySelectionUpdateCount = 0x0089FA10;
constexpr uint32_t kObjectGetPortrait = 0x0058BEE0;

}  // namespace steam
}  // namespace party32
}  // namespace k2se
