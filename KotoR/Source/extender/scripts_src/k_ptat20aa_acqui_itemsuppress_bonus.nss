// Item-pickup wrapper -- runs tat_m20aa's real vanilla
// Mod_OnAcquirItem script (k_ptat20aa_acqui, preserved as apo_k_ptat20aa_acqui_orig)
// first, then applies this seed's pickup-handling mode.
#include "kse"

string GetRandomLootItem()
{
    int nRoll = Random(527);
    if (nRoll == 0) return "bast_temp_saber";
    else if (nRoll == 1) return "carth_temp_gun";
    else if (nRoll == 2) return "dan13_bluesaber";
    else if (nRoll == 3) return "dan13_goldsaber";
    else if (nRoll == 4) return "dan13_goldsabler";
    else if (nRoll == 5) return "dan13_grnsaber";
    else if (nRoll == 6) return "dan13_practice";
    else if (nRoll == 7) return "dan_mine_prop";
    else if (nRoll == 8) return "end_1damblast";
    else if (nRoll == 9) return "end_onedam";
    else if (nRoll == 10) return "g1_a_class5001";
    else if (nRoll == 11) return "g1_a_class5002";
    else if (nRoll == 12) return "g1_a_class6001";
    else if (nRoll == 13) return "g1_a_class8001";
    else if (nRoll == 14) return "g1_i_belt001";
    else if (nRoll == 15) return "g1_i_drdcomspk01";
    else if (nRoll == 16) return "g1_i_drdhvplat01";
    else if (nRoll == 17) return "g1_i_drdshld001";
    else if (nRoll == 18) return "g1_i_drdutldev01";
    else if (nRoll == 19) return "g1_i_drdutldev02";
    else if (nRoll == 20) return "g1_i_drdutldev03";
    else if (nRoll == 21) return "g1_i_gauntlet01";
    else if (nRoll == 22) return "g1_i_implant301";
    else if (nRoll == 23) return "g1_i_implant302";
    else if (nRoll == 24) return "g1_i_implant303";
    else if (nRoll == 25) return "g1_i_implant304";
    else if (nRoll == 26) return "g1_i_mask01";
    else if (nRoll == 27) return "g1_i_mask02";
    else if (nRoll == 28) return "g1_i_mask03";
    else if (nRoll == 29) return "g1_w_dblsbr001";
    else if (nRoll == 30) return "g1_w_dblsbr002";
    else if (nRoll == 31) return "g1_w_dsrptrfl001";
    else if (nRoll == 32) return "g1_w_hvrptbltr01";
    else if (nRoll == 33) return "g1_w_ionrfl01";
    else if (nRoll == 34) return "g1_w_lghtsbr01";
    else if (nRoll == 35) return "g1_w_lghtsbr02";
    else if (nRoll == 36) return "g1_w_rptnblstr01";
    else if (nRoll == 37) return "g1_w_sbrcrstl20";
    else if (nRoll == 38) return "g1_w_sbrcrstl21";
    else if (nRoll == 39) return "g1_w_shortsbr01";
    else if (nRoll == 40) return "g1_w_shortsbr02";
    else if (nRoll == 41) return "g1_w_vbroswrd01";
    else if (nRoll == 42) return "g_a_class4001";
    else if (nRoll == 43) return "g_a_class4002";
    else if (nRoll == 44) return "g_a_class4003";
    else if (nRoll == 45) return "g_a_class4004";
    else if (nRoll == 46) return "g_a_class4005";
    else if (nRoll == 47) return "g_a_class4006";
    else if (nRoll == 48) return "g_a_class4007";
    else if (nRoll == 49) return "g_a_class4008";
    else if (nRoll == 50) return "g_a_class4009";
    else if (nRoll == 51) return "g_a_class5001";
    else if (nRoll == 52) return "g_a_class5002";
    else if (nRoll == 53) return "g_a_class5003";
    else if (nRoll == 54) return "g_a_class5004";
    else if (nRoll == 55) return "g_a_class5005";
    else if (nRoll == 56) return "g_a_class5006";
    else if (nRoll == 57) return "g_a_class5007";
    else if (nRoll == 58) return "g_a_class5008";
    else if (nRoll == 59) return "g_a_class5009";
    else if (nRoll == 60) return "g_a_class5010";
    else if (nRoll == 61) return "g_a_class6001";
    else if (nRoll == 62) return "g_a_class6002";
    else if (nRoll == 63) return "g_a_class6003";
    else if (nRoll == 64) return "g_a_class6004";
    else if (nRoll == 65) return "g_a_class6005";
    else if (nRoll == 66) return "g_a_class6006";
    else if (nRoll == 67) return "g_a_class6007";
    else if (nRoll == 68) return "g_a_class6008";
    else if (nRoll == 69) return "g_a_class6009";
    else if (nRoll == 70) return "g_a_class7001";
    else if (nRoll == 71) return "g_a_class7002";
    else if (nRoll == 72) return "g_a_class7003";
    else if (nRoll == 73) return "g_a_class7004";
    else if (nRoll == 74) return "g_a_class7005";
    else if (nRoll == 75) return "g_a_class7006";
    else if (nRoll == 76) return "g_a_class8001";
    else if (nRoll == 77) return "g_a_class8002";
    else if (nRoll == 78) return "g_a_class8003";
    else if (nRoll == 79) return "g_a_class8004";
    else if (nRoll == 80) return "g_a_class8005";
    else if (nRoll == 81) return "g_a_class8006";
    else if (nRoll == 82) return "g_a_class8007";
    else if (nRoll == 83) return "g_a_class8009";
    else if (nRoll == 84) return "g_a_class9001";
    else if (nRoll == 85) return "g_a_class9002";
    else if (nRoll == 86) return "g_a_class9003";
    else if (nRoll == 87) return "g_a_class9004";
    else if (nRoll == 88) return "g_a_class9005";
    else if (nRoll == 89) return "g_a_class9006";
    else if (nRoll == 90) return "g_a_class9007";
    else if (nRoll == 91) return "g_a_class9009";
    else if (nRoll == 92) return "g_a_class9010";
    else if (nRoll == 93) return "g_a_class9011";
    else if (nRoll == 94) return "g_a_clothes01";
    else if (nRoll == 95) return "g_a_clothes02";
    else if (nRoll == 96) return "g_a_clothes03";
    else if (nRoll == 97) return "g_a_clothes04";
    else if (nRoll == 98) return "g_a_clothes05";
    else if (nRoll == 99) return "g_a_clothes06";
    else if (nRoll == 100) return "g_a_clothes07";
    else if (nRoll == 101) return "g_a_clothes08";
    else if (nRoll == 102) return "g_a_clothes09";
    else if (nRoll == 103) return "g_a_jedirobe002";
    else if (nRoll == 104) return "g_a_jedirobe003";
    else if (nRoll == 105) return "g_a_jedirobe007";
    else if (nRoll == 106) return "g_a_jedirobe01";
    else if (nRoll == 107) return "g_a_jedirobe02";
    else if (nRoll == 108) return "g_a_jedirobe03";
    else if (nRoll == 109) return "g_a_jedirobe04";
    else if (nRoll == 110) return "g_a_jedirobe05";
    else if (nRoll == 111) return "g_a_jedirobe06";
    else if (nRoll == 112) return "g_a_kghtrobe01";
    else if (nRoll == 113) return "g_a_kghtrobe02";
    else if (nRoll == 114) return "g_a_kghtrobe03";
    else if (nRoll == 115) return "g_a_kghtrobe04";
    else if (nRoll == 116) return "g_a_kghtrobe05";
    else if (nRoll == 117) return "g_a_mstrrobe01";
    else if (nRoll == 118) return "g_a_mstrrobe02";
    else if (nRoll == 119) return "g_a_mstrrobe03";
    else if (nRoll == 120) return "g_a_mstrrobe04";
    else if (nRoll == 121) return "g_a_mstrrobe05";
    else if (nRoll == 122) return "g_a_mstrrobe06";
    else if (nRoll == 123) return "g_a_mstrrobe07";
    else if (nRoll == 124) return "g_band";
    else if (nRoll == 125) return "g_i_adrnaline001";
    else if (nRoll == 126) return "g_i_adrnaline002";
    else if (nRoll == 127) return "g_i_adrnaline003";
    else if (nRoll == 128) return "g_i_adrnaline004";
    else if (nRoll == 129) return "g_i_adrnaline005";
    else if (nRoll == 130) return "g_i_adrnaline006";
    else if (nRoll == 131) return "g_i_belt001";
    else if (nRoll == 132) return "g_i_belt002";
    else if (nRoll == 133) return "g_i_belt003";
    else if (nRoll == 134) return "g_i_belt004";
    else if (nRoll == 135) return "g_i_belt005";
    else if (nRoll == 136) return "g_i_belt006";
    else if (nRoll == 137) return "g_i_belt007";
    else if (nRoll == 138) return "g_i_belt008";
    else if (nRoll == 139) return "g_i_belt009";
    else if (nRoll == 140) return "g_i_belt010";
    else if (nRoll == 141) return "g_i_belt011";
    else if (nRoll == 142) return "g_i_belt012";
    else if (nRoll == 143) return "g_i_belt013";
    else if (nRoll == 144) return "g_i_belt014";
    else if (nRoll == 145) return "g_i_bithitem002";
    else if (nRoll == 146) return "g_i_bithitem003";
    else if (nRoll == 147) return "g_i_bithitem004";
    else if (nRoll == 148) return "g_i_drdcomspk001";
    else if (nRoll == 149) return "g_i_drdcomspk002";
    else if (nRoll == 150) return "g_i_drdcomspk003";
    else if (nRoll == 151) return "g_i_drdhvplat001";
    else if (nRoll == 152) return "g_i_drdhvplat002";
    else if (nRoll == 153) return "g_i_drdhvplat003";
    else if (nRoll == 154) return "g_i_drdltplat001";
    else if (nRoll == 155) return "g_i_drdltplat002";
    else if (nRoll == 156) return "g_i_drdltplat003";
    else if (nRoll == 157) return "g_i_drdmdplat001";
    else if (nRoll == 158) return "g_i_drdmdplat002";
    else if (nRoll == 159) return "g_i_drdmdplat003";
    else if (nRoll == 160) return "g_i_drdmtnsen001";
    else if (nRoll == 161) return "g_i_drdmtnsen002";
    else if (nRoll == 162) return "g_i_drdmtnsen003";
    else if (nRoll == 163) return "g_i_drdrepeqp003";
    else if (nRoll == 164) return "g_i_drdsecspk001";
    else if (nRoll == 165) return "g_i_drdsecspk002";
    else if (nRoll == 166) return "g_i_drdsecspk003";
    else if (nRoll == 167) return "g_i_drdshld001";
    else if (nRoll == 168) return "g_i_drdshld002";
    else if (nRoll == 169) return "g_i_drdshld003";
    else if (nRoll == 170) return "g_i_drdshld005";
    else if (nRoll == 171) return "g_i_drdshld006";
    else if (nRoll == 172) return "g_i_drdshld007";
    else if (nRoll == 173) return "g_i_drdshld008";
    else if (nRoll == 174) return "g_i_drdsncsen001";
    else if (nRoll == 175) return "g_i_drdsncsen002";
    else if (nRoll == 176) return "g_i_drdsncsen003";
    else if (nRoll == 177) return "g_i_drdsrcscp001";
    else if (nRoll == 178) return "g_i_drdsrcscp002";
    else if (nRoll == 179) return "g_i_drdsrcscp003";
    else if (nRoll == 180) return "g_i_drdtrgcom001";
    else if (nRoll == 181) return "g_i_drdtrgcom002";
    else if (nRoll == 182) return "g_i_drdtrgcom003";
    else if (nRoll == 183) return "g_i_drdtrgcom004";
    else if (nRoll == 184) return "g_i_drdtrgcom005";
    else if (nRoll == 185) return "g_i_drdtrgcom006";
    else if (nRoll == 186) return "g_i_drdutldev001";
    else if (nRoll == 187) return "g_i_drdutldev002";
    else if (nRoll == 188) return "g_i_drdutldev003";
    else if (nRoll == 189) return "g_i_drdutldev004";
    else if (nRoll == 190) return "g_i_drdutldev005";
    else if (nRoll == 191) return "g_i_drdutldev006";
    else if (nRoll == 192) return "g_i_drdutldev007";
    else if (nRoll == 193) return "g_i_drdutldev008";
    else if (nRoll == 194) return "g_i_drdutldev009";
    else if (nRoll == 195) return "g_i_drdutldev010";
    else if (nRoll == 196) return "g_i_drdutldev011";
    else if (nRoll == 197) return "g_i_drdutldev012";
    else if (nRoll == 198) return "g_i_frarmbnds01";
    else if (nRoll == 199) return "g_i_frarmbnds010";
    else if (nRoll == 200) return "g_i_frarmbnds02";
    else if (nRoll == 201) return "g_i_frarmbnds03";
    else if (nRoll == 202) return "g_i_frarmbnds04";
    else if (nRoll == 203) return "g_i_frarmbnds05";
    else if (nRoll == 204) return "g_i_frarmbnds06";
    else if (nRoll == 205) return "g_i_frarmbnds07";
    else if (nRoll == 206) return "g_i_frarmbnds08";
    else if (nRoll == 207) return "g_i_frarmbnds09";
    else if (nRoll == 208) return "g_i_frarmbnds10";
    else if (nRoll == 209) return "g_i_frarmbnds11";
    else if (nRoll == 210) return "g_i_frarmbnds12";
    else if (nRoll == 211) return "g_i_frarmbnds13";
    else if (nRoll == 212) return "g_i_frarmbnds14";
    else if (nRoll == 213) return "g_i_frarmbnds15";
    else if (nRoll == 214) return "g_i_frarmbnds16";
    else if (nRoll == 215) return "g_i_frarmbnds17";
    else if (nRoll == 216) return "g_i_frarmbnds18";
    else if (nRoll == 217) return "g_i_frarmbnds19";
    else if (nRoll == 218) return "g_i_frarmbnds20";
    else if (nRoll == 219) return "g_i_frarmbnds21";
    else if (nRoll == 220) return "g_i_gauntlet01";
    else if (nRoll == 221) return "g_i_gauntlet02";
    else if (nRoll == 222) return "g_i_gauntlet03";
    else if (nRoll == 223) return "g_i_gauntlet04";
    else if (nRoll == 224) return "g_i_gauntlet05";
    else if (nRoll == 225) return "g_i_gauntlet06";
    else if (nRoll == 226) return "g_i_gauntlet07";
    else if (nRoll == 227) return "g_i_gauntlet08";
    else if (nRoll == 228) return "g_i_gauntlet09";
    else if (nRoll == 229) return "g_i_implant101";
    else if (nRoll == 230) return "g_i_implant102";
    else if (nRoll == 231) return "g_i_implant103";
    else if (nRoll == 232) return "g_i_implant104";
    else if (nRoll == 233) return "g_i_implant201";
    else if (nRoll == 234) return "g_i_implant202";
    else if (nRoll == 235) return "g_i_implant203";
    else if (nRoll == 236) return "g_i_implant204";
    else if (nRoll == 237) return "g_i_implant301";
    else if (nRoll == 238) return "g_i_implant302";
    else if (nRoll == 239) return "g_i_implant303";
    else if (nRoll == 240) return "g_i_implant304";
    else if (nRoll == 241) return "g_i_implant305";
    else if (nRoll == 242) return "g_i_implant306";
    else if (nRoll == 243) return "g_i_implant307";
    else if (nRoll == 244) return "g_i_implant308";
    else if (nRoll == 245) return "g_i_implant309";
    else if (nRoll == 246) return "g_i_implant310";
    else if (nRoll == 247) return "g_i_mask009";
    else if (nRoll == 248) return "g_i_mask01";
    else if (nRoll == 249) return "g_i_mask02";
    else if (nRoll == 250) return "g_i_mask023";
    else if (nRoll == 251) return "g_i_mask03";
    else if (nRoll == 252) return "g_i_mask04";
    else if (nRoll == 253) return "g_i_mask05";
    else if (nRoll == 254) return "g_i_mask06";
    else if (nRoll == 255) return "g_i_mask07";
    else if (nRoll == 256) return "g_i_mask08";
    else if (nRoll == 257) return "g_i_mask09";
    else if (nRoll == 258) return "g_i_mask10";
    else if (nRoll == 259) return "g_i_mask11";
    else if (nRoll == 260) return "g_i_mask12";
    else if (nRoll == 261) return "g_i_mask13";
    else if (nRoll == 262) return "g_i_mask14";
    else if (nRoll == 263) return "g_i_mask15";
    else if (nRoll == 264) return "g_i_mask16";
    else if (nRoll == 265) return "g_i_mask17";
    else if (nRoll == 266) return "g_i_mask18";
    else if (nRoll == 267) return "g_i_mask19";
    else if (nRoll == 268) return "g_i_mask20";
    else if (nRoll == 269) return "g_i_mask21";
    else if (nRoll == 270) return "g_i_mask22";
    else if (nRoll == 271) return "g_i_mask23";
    else if (nRoll == 272) return "g_i_mask24";
    else if (nRoll == 273) return "g_i_medeqpmnt01";
    else if (nRoll == 274) return "g_i_medeqpmnt06";
    else if (nRoll == 275) return "g_i_medeqpmnt07";
    else if (nRoll == 276) return "g_i_parts01";
    else if (nRoll == 277) return "g_i_pazcard_001";
    else if (nRoll == 278) return "g_i_pazcard_002";
    else if (nRoll == 279) return "g_i_pazcard_003";
    else if (nRoll == 280) return "g_i_pazcard_004";
    else if (nRoll == 281) return "g_i_pazcard_005";
    else if (nRoll == 282) return "g_i_pazcard_006";
    else if (nRoll == 283) return "g_i_pazcard_007";
    else if (nRoll == 284) return "g_i_pazcard_008";
    else if (nRoll == 285) return "g_i_pazcard_009";
    else if (nRoll == 286) return "g_i_pazcard_010";
    else if (nRoll == 287) return "g_i_pazcard_011";
    else if (nRoll == 288) return "g_i_pazcard_012";
    else if (nRoll == 289) return "g_i_pazcard_013";
    else if (nRoll == 290) return "g_i_pazcard_014";
    else if (nRoll == 291) return "g_i_pazcard_015";
    else if (nRoll == 292) return "g_i_pazcard_016";
    else if (nRoll == 293) return "g_i_pazcard_017";
    else if (nRoll == 294) return "g_i_pazcard_018";
    else if (nRoll == 295) return "g_i_trapkit001";
    else if (nRoll == 296) return "g_i_trapkit002";
    else if (nRoll == 297) return "g_i_trapkit003";
    else if (nRoll == 298) return "g_i_trapkit004";
    else if (nRoll == 299) return "g_i_trapkit005";
    else if (nRoll == 300) return "g_i_trapkit006";
    else if (nRoll == 301) return "g_i_trapkit007";
    else if (nRoll == 302) return "g_i_trapkit008";
    else if (nRoll == 303) return "g_i_trapkit009";
    else if (nRoll == 304) return "g_i_trapkit01";
    else if (nRoll == 305) return "g_i_trapkit010";
    else if (nRoll == 306) return "g_i_trapkit011";
    else if (nRoll == 307) return "g_i_trapkit012";
    else if (nRoll == 308) return "g_i_trapkit02";
    else if (nRoll == 309) return "g_i_trapkit03";
    else if (nRoll == 310) return "g_i_trapkit04";
    else if (nRoll == 311) return "g_w_adhsvgren001";
    else if (nRoll == 312) return "g_w_blstrcrbn001";
    else if (nRoll == 313) return "g_w_blstrcrbn002";
    else if (nRoll == 314) return "g_w_blstrcrbn003";
    else if (nRoll == 315) return "g_w_blstrcrbn004";
    else if (nRoll == 316) return "g_w_blstrcrbn005";
    else if (nRoll == 317) return "g_w_blstrcrbn006";
    else if (nRoll == 318) return "g_w_blstrcrbn007";
    else if (nRoll == 319) return "g_w_blstrcrbn008";
    else if (nRoll == 320) return "g_w_blstrcrbn009";
    else if (nRoll == 321) return "g_w_blstrcrbn020";
    else if (nRoll == 322) return "g_w_blstrpstl001";
    else if (nRoll == 323) return "g_w_blstrpstl002";
    else if (nRoll == 324) return "g_w_blstrpstl003";
    else if (nRoll == 325) return "g_w_blstrpstl004";
    else if (nRoll == 326) return "g_w_blstrpstl005";
    else if (nRoll == 327) return "g_w_blstrpstl006";
    else if (nRoll == 328) return "g_w_blstrpstl007";
    else if (nRoll == 329) return "g_w_blstrpstl008";
    else if (nRoll == 330) return "g_w_blstrpstl009";
    else if (nRoll == 331) return "g_w_blstrpstl010";
    else if (nRoll == 332) return "g_w_blstrpstl020";
    else if (nRoll == 333) return "g_w_blstrrfl001";
    else if (nRoll == 334) return "g_w_blstrrfl002";
    else if (nRoll == 335) return "g_w_blstrrfl003";
    else if (nRoll == 336) return "g_w_blstrrfl004";
    else if (nRoll == 337) return "g_w_blstrrfl005";
    else if (nRoll == 338) return "g_w_blstrrfl006";
    else if (nRoll == 339) return "g_w_blstrrfl007";
    else if (nRoll == 340) return "g_w_blstrrfl008";
    else if (nRoll == 341) return "g_w_blstrrfl009";
    else if (nRoll == 342) return "g_w_blstrrfl020";
    else if (nRoll == 343) return "g_w_bowcstr001";
    else if (nRoll == 344) return "g_w_bowcstr002";
    else if (nRoll == 345) return "g_w_bowcstr003";
    else if (nRoll == 346) return "g_w_cryobgren001";
    else if (nRoll == 347) return "g_w_dblsbr001";
    else if (nRoll == 348) return "g_w_dblsbr002";
    else if (nRoll == 349) return "g_w_dblsbr003";
    else if (nRoll == 350) return "g_w_dblsbr004";
    else if (nRoll == 351) return "g_w_dblsbr005";
    else if (nRoll == 352) return "g_w_dblsbr006";
    else if (nRoll == 353) return "g_w_dblsbr007";
    else if (nRoll == 354) return "g_w_dblswrd001";
    else if (nRoll == 355) return "g_w_dblswrd002";
    else if (nRoll == 356) return "g_w_dblswrd003";
    else if (nRoll == 357) return "g_w_dblswrd005";
    else if (nRoll == 358) return "g_w_drkjdisbr001";
    else if (nRoll == 359) return "g_w_drkjdisbr002";
    else if (nRoll == 360) return "g_w_dsrptpstl001";
    else if (nRoll == 361) return "g_w_dsrptpstl002";
    else if (nRoll == 362) return "g_w_dsrptrfl001";
    else if (nRoll == 363) return "g_w_dsrptrfl002";
    else if (nRoll == 364) return "g_w_firegren001";
    else if (nRoll == 365) return "g_w_fraggren01";
    else if (nRoll == 366) return "g_w_gaffi001";
    else if (nRoll == 367) return "g_w_hldoblstr003";
    else if (nRoll == 368) return "g_w_hldoblstr004";
    else if (nRoll == 369) return "g_w_hldoblstr01";
    else if (nRoll == 370) return "g_w_hldoblstr02";
    else if (nRoll == 371) return "g_w_hldoblstr03";
    else if (nRoll == 372) return "g_w_hldoblstr04";
    else if (nRoll == 373) return "g_w_hvrptbltr002";
    else if (nRoll == 374) return "g_w_hvrptbltr01";
    else if (nRoll == 375) return "g_w_hvrptbltr02";
    else if (nRoll == 376) return "g_w_hvyblstr002";
    else if (nRoll == 377) return "g_w_hvyblstr01";
    else if (nRoll == 378) return "g_w_hvyblstr02";
    else if (nRoll == 379) return "g_w_hvyblstr03";
    else if (nRoll == 380) return "g_w_hvyblstr04";
    else if (nRoll == 381) return "g_w_hvyblstr05";
    else if (nRoll == 382) return "g_w_hvyblstr06";
    else if (nRoll == 383) return "g_w_hvyblstr07";
    else if (nRoll == 384) return "g_w_hvyblstr08";
    else if (nRoll == 385) return "g_w_hvyblstr09";
    else if (nRoll == 386) return "g_w_ionblstr01";
    else if (nRoll == 387) return "g_w_ionblstr02";
    else if (nRoll == 388) return "g_w_iongren01";
    else if (nRoll == 389) return "g_w_ionrfl01";
    else if (nRoll == 390) return "g_w_ionrfl02";
    else if (nRoll == 391) return "g_w_ionrfl03";
    else if (nRoll == 392) return "g_w_lghtsbr002";
    else if (nRoll == 393) return "g_w_lghtsbr007";
    else if (nRoll == 394) return "g_w_lghtsbr008";
    else if (nRoll == 395) return "g_w_lghtsbr01";
    else if (nRoll == 396) return "g_w_lghtsbr012";
    else if (nRoll == 397) return "g_w_lghtsbr02";
    else if (nRoll == 398) return "g_w_lghtsbr03";
    else if (nRoll == 399) return "g_w_lghtsbr04";
    else if (nRoll == 400) return "g_w_lghtsbr05";
    else if (nRoll == 401) return "g_w_lghtsbr06";
    else if (nRoll == 402) return "g_w_lngswrd01";
    else if (nRoll == 403) return "g_w_lngswrd02";
    else if (nRoll == 404) return "g_w_lngswrd03";
    else if (nRoll == 405) return "g_w_null001";
    else if (nRoll == 406) return "g_w_null002";
    else if (nRoll == 407) return "g_w_null003";
    else if (nRoll == 408) return "g_w_null004";
    else if (nRoll == 409) return "g_w_null005";
    else if (nRoll == 410) return "g_w_null006";
    else if (nRoll == 411) return "g_w_null007";
    else if (nRoll == 412) return "g_w_poisngren01";
    else if (nRoll == 413) return "g_w_qtrstaff01";
    else if (nRoll == 414) return "g_w_qtrstaff02";
    else if (nRoll == 415) return "g_w_qtrstaff03";
    else if (nRoll == 416) return "g_w_rptnblstr004";
    else if (nRoll == 417) return "g_w_rptnblstr01";
    else if (nRoll == 418) return "g_w_rptnblstr02";
    else if (nRoll == 419) return "g_w_rptnblstr03";
    else if (nRoll == 420) return "g_w_sbrcrstl01";
    else if (nRoll == 421) return "g_w_sbrcrstl015";
    else if (nRoll == 422) return "g_w_sbrcrstl02";
    else if (nRoll == 423) return "g_w_sbrcrstl03";
    else if (nRoll == 424) return "g_w_sbrcrstl04";
    else if (nRoll == 425) return "g_w_sbrcrstl05";
    else if (nRoll == 426) return "g_w_sbrcrstl06";
    else if (nRoll == 427) return "g_w_sbrcrstl07";
    else if (nRoll == 428) return "g_w_sbrcrstl08";
    else if (nRoll == 429) return "g_w_sbrcrstl09";
    else if (nRoll == 430) return "g_w_sbrcrstl10";
    else if (nRoll == 431) return "g_w_sbrcrstl11";
    else if (nRoll == 432) return "g_w_sbrcrstl12";
    else if (nRoll == 433) return "g_w_sbrcrstl13";
    else if (nRoll == 434) return "g_w_sbrcrstl14";
    else if (nRoll == 435) return "g_w_sbrcrstl15";
    else if (nRoll == 436) return "g_w_sbrcrstl16";
    else if (nRoll == 437) return "g_w_sbrcrstl17";
    else if (nRoll == 438) return "g_w_sbrcrstl18";
    else if (nRoll == 439) return "g_w_sbrcrstl19";
    else if (nRoll == 440) return "g_w_shortsbr01";
    else if (nRoll == 441) return "g_w_shortsbr02";
    else if (nRoll == 442) return "g_w_shortsbr03";
    else if (nRoll == 443) return "g_w_shortsbr04";
    else if (nRoll == 444) return "g_w_shortsbr05";
    else if (nRoll == 445) return "g_w_shortswrd01";
    else if (nRoll == 446) return "g_w_shortswrd02";
    else if (nRoll == 447) return "g_w_shortswrd03";
    else if (nRoll == 448) return "g_w_sonicgren01";
    else if (nRoll == 449) return "g_w_sonicpstl01";
    else if (nRoll == 450) return "g_w_sonicpstl02";
    else if (nRoll == 451) return "g_w_sonicrfl01";
    else if (nRoll == 452) return "g_w_sonicrfl02";
    else if (nRoll == 453) return "g_w_sonicrfl03";
    else if (nRoll == 454) return "g_w_stunbaton005";
    else if (nRoll == 455) return "g_w_stunbaton01";
    else if (nRoll == 456) return "g_w_stunbaton02";
    else if (nRoll == 457) return "g_w_stunbaton03";
    else if (nRoll == 458) return "g_w_stunbaton04";
    else if (nRoll == 459) return "g_w_stunbaton05";
    else if (nRoll == 460) return "g_w_stunbaton06";
    else if (nRoll == 461) return "g_w_stunbaton07";
    else if (nRoll == 462) return "g_w_stungren01";
    else if (nRoll == 463) return "g_w_vbrdblswd01";
    else if (nRoll == 464) return "g_w_vbrdblswd02";
    else if (nRoll == 465) return "g_w_vbrdblswd03";
    else if (nRoll == 466) return "g_w_vbrdblswd04";
    else if (nRoll == 467) return "g_w_vbrdblswd05";
    else if (nRoll == 468) return "g_w_vbrdblswd06";
    else if (nRoll == 469) return "g_w_vbrdblswd07";
    else if (nRoll == 470) return "g_w_vbroshort002";
    else if (nRoll == 471) return "g_w_vbroshort01";
    else if (nRoll == 472) return "g_w_vbroshort02";
    else if (nRoll == 473) return "g_w_vbroshort03";
    else if (nRoll == 474) return "g_w_vbroshort04";
    else if (nRoll == 475) return "g_w_vbroshort05";
    else if (nRoll == 476) return "g_w_vbroshort06";
    else if (nRoll == 477) return "g_w_vbroshort07";
    else if (nRoll == 478) return "g_w_vbroshort08";
    else if (nRoll == 479) return "g_w_vbroshort09";
    else if (nRoll == 480) return "g_w_vbroswrd002";
    else if (nRoll == 481) return "g_w_vbroswrd01";
    else if (nRoll == 482) return "g_w_vbroswrd02";
    else if (nRoll == 483) return "g_w_vbroswrd03";
    else if (nRoll == 484) return "g_w_vbroswrd04";
    else if (nRoll == 485) return "g_w_vbroswrd05";
    else if (nRoll == 486) return "g_w_vbroswrd06";
    else if (nRoll == 487) return "g_w_vbroswrd07";
    else if (nRoll == 488) return "g_w_vbroswrd08";
    else if (nRoll == 489) return "g_w_waraxe001";
    else if (nRoll == 490) return "g_w_waraxe002";
    else if (nRoll == 491) return "g_w_warblade001";
    else if (nRoll == 492) return "g_w_warblade002";
    else if (nRoll == 493) return "geno_armor";
    else if (nRoll == 494) return "geno_blade";
    else if (nRoll == 495) return "geno_blaster";
    else if (nRoll == 496) return "geno_gloves";
    else if (nRoll == 497) return "geno_stealth";
    else if (nRoll == 498) return "geno_visor";
    else if (nRoll == 499) return "item001";
    else if (nRoll == 500) return "k37_itm_freednf1";
    else if (nRoll == 501) return "k37_itm_freednf2";
    else if (nRoll == 502) return "k37_itm_freedont";
    else if (nRoll == 503) return "kas22_longsword";
    else if (nRoll == 504) return "kas23_baccasword";
    else if (nRoll == 505) return "kas24_lightsaber";
    else if (nRoll == 506) return "kas25_longsword";
    else if (nRoll == 507) return "kor37_droidblast";
    else if (nRoll == 508) return "kor38a_gauntlet";
    else if (nRoll == 509) return "kor38b_mask";
    else if (nRoll == 510) return "lev40_supergun";
    else if (nRoll == 511) return "ptar_shockstick";
    else if (nRoll == 512) return "punk_rancorgren";
    else if (nRoll == 513) return "sta_light002";
    else if (nRoll == 514) return "sta_light1";
    else if (nRoll == 515) return "sta_shortligh001";
    else if (nRoll == 516) return "sta_shortlight1";
    else if (nRoll == 517) return "sta_temp_saber";
    else if (nRoll == 518) return "sta_temp_saber2";
    else if (nRoll == 519) return "tar03_brejikband";
    else if (nRoll == 520) return "tar03_brejikbelt";
    else if (nRoll == 521) return "tar03_brejikglov";
    else if (nRoll == 522) return "tar08_davikmask";
    else if (nRoll == 523) return "tar11_powerbelt";
    else if (nRoll == 524) return "tat20_gaffi02";
    else if (nRoll == 525) return "tat20_gaffistick";
    else if (nRoll == 526) return "w_bstrcrbn";
    return "";
}

void HandleAcquiredItem()
{
    object oItem = GetModuleItemAcquired();
    string sTag = GetStringLowerCase(GetTag(oItem));
    if (KSE_HasData("granted_exempt_" + sTag)) return;
    if (sTag == "bast_temp_saber" ||
        sTag == "carth_temp_gun" ||
        sTag == "dan13_bluesaber" ||
        sTag == "dan13_goldsaber" ||
        sTag == "dan13_goldsabler" ||
        sTag == "dan13_grnsaber" ||
        sTag == "dan13_practice" ||
        sTag == "dan14_nothing" ||
        sTag == "dan_mine_prop" ||
        sTag == "duronjournal" ||
        sTag == "end_1damblast" ||
        sTag == "end_onedam" ||
        sTag == "flash_gren" ||
        sTag == "g1_a_class5001" ||
        sTag == "g1_a_class5002" ||
        sTag == "g1_a_class6001" ||
        sTag == "g1_a_class8001" ||
        sTag == "g1_i_belt001" ||
        sTag == "g1_i_drdcomspk01" ||
        sTag == "g1_i_drdhvplat01" ||
        sTag == "g1_i_drdshld001" ||
        sTag == "g1_i_drdutldev01" ||
        sTag == "g1_i_drdutldev02" ||
        sTag == "g1_i_drdutldev03" ||
        sTag == "g1_i_gauntlet01" ||
        sTag == "g1_i_implant301" ||
        sTag == "g1_i_implant302" ||
        sTag == "g1_i_implant303" ||
        sTag == "g1_i_implant304" ||
        sTag == "g1_i_mask01" ||
        sTag == "g1_i_mask02" ||
        sTag == "g1_i_mask03" ||
        sTag == "g1_w_dblsbr001" ||
        sTag == "g1_w_dblsbr002" ||
        sTag == "g1_w_dsrptrfl001" ||
        sTag == "g1_w_hvrptbltr01" ||
        sTag == "g1_w_ionrfl01" ||
        sTag == "g1_w_lghtsbr01" ||
        sTag == "g1_w_lghtsbr02" ||
        sTag == "g1_w_rptnblstr01" ||
        sTag == "g1_w_sbrcrstl20" ||
        sTag == "g1_w_sbrcrstl21" ||
        sTag == "g1_w_shortsbr01" ||
        sTag == "g1_w_shortsbr02" ||
        sTag == "g1_w_vbroswrd01" ||
        sTag == "g_a_class4001" ||
        sTag == "g_a_class4002" ||
        sTag == "g_a_class4003" ||
        sTag == "g_a_class4004" ||
        sTag == "g_a_class4005" ||
        sTag == "g_a_class4006" ||
        sTag == "g_a_class4007" ||
        sTag == "g_a_class4008" ||
        sTag == "g_a_class4009" ||
        sTag == "g_a_class5001" ||
        sTag == "g_a_class5002" ||
        sTag == "g_a_class5003" ||
        sTag == "g_a_class5004" ||
        sTag == "g_a_class5005" ||
        sTag == "g_a_class5006" ||
        sTag == "g_a_class5007" ||
        sTag == "g_a_class5008" ||
        sTag == "g_a_class5009" ||
        sTag == "g_a_class5010" ||
        sTag == "g_a_class6001" ||
        sTag == "g_a_class6002" ||
        sTag == "g_a_class6003" ||
        sTag == "g_a_class6004" ||
        sTag == "g_a_class6005" ||
        sTag == "g_a_class6006" ||
        sTag == "g_a_class6007" ||
        sTag == "g_a_class6008" ||
        sTag == "g_a_class6009" ||
        sTag == "g_a_class7001" ||
        sTag == "g_a_class7002" ||
        sTag == "g_a_class7003" ||
        sTag == "g_a_class7004" ||
        sTag == "g_a_class7005" ||
        sTag == "g_a_class7006" ||
        sTag == "g_a_class8001" ||
        sTag == "g_a_class8002" ||
        sTag == "g_a_class8003" ||
        sTag == "g_a_class8004" ||
        sTag == "g_a_class8005" ||
        sTag == "g_a_class8006" ||
        sTag == "g_a_class8007" ||
        sTag == "g_a_class8009" ||
        sTag == "g_a_class9001" ||
        sTag == "g_a_class9002" ||
        sTag == "g_a_class9003" ||
        sTag == "g_a_class9004" ||
        sTag == "g_a_class9005" ||
        sTag == "g_a_class9006" ||
        sTag == "g_a_class9007" ||
        sTag == "g_a_class9009" ||
        sTag == "g_a_class9010" ||
        sTag == "g_a_class9011" ||
        sTag == "g_a_clothes01" ||
        sTag == "g_a_clothes02" ||
        sTag == "g_a_clothes03" ||
        sTag == "g_a_clothes04" ||
        sTag == "g_a_clothes05" ||
        sTag == "g_a_clothes06" ||
        sTag == "g_a_clothes07" ||
        sTag == "g_a_clothes08" ||
        sTag == "g_a_clothes09" ||
        sTag == "g_a_jedirobe002" ||
        sTag == "g_a_jedirobe003" ||
        sTag == "g_a_jedirobe007" ||
        sTag == "g_a_jedirobe01" ||
        sTag == "g_a_jedirobe02" ||
        sTag == "g_a_jedirobe03" ||
        sTag == "g_a_jedirobe04" ||
        sTag == "g_a_jedirobe05" ||
        sTag == "g_a_jedirobe06" ||
        sTag == "g_a_kghtrobe01" ||
        sTag == "g_a_kghtrobe02" ||
        sTag == "g_a_kghtrobe03" ||
        sTag == "g_a_kghtrobe04" ||
        sTag == "g_a_kghtrobe05" ||
        sTag == "g_a_mstrrobe01" ||
        sTag == "g_a_mstrrobe02" ||
        sTag == "g_a_mstrrobe03" ||
        sTag == "g_a_mstrrobe04" ||
        sTag == "g_a_mstrrobe05" ||
        sTag == "g_a_mstrrobe06" ||
        sTag == "g_a_mstrrobe07" ||
        sTag == "g_band" ||
        sTag == "g_i_adrnaline001" ||
        sTag == "g_i_adrnaline002" ||
        sTag == "g_i_adrnaline003" ||
        sTag == "g_i_adrnaline004" ||
        sTag == "g_i_adrnaline005" ||
        sTag == "g_i_adrnaline006" ||
        sTag == "g_i_asthitem001" ||
        sTag == "g_i_belt001" ||
        sTag == "g_i_belt002" ||
        sTag == "g_i_belt003" ||
        sTag == "g_i_belt004" ||
        sTag == "g_i_belt005" ||
        sTag == "g_i_belt006" ||
        sTag == "g_i_belt007" ||
        sTag == "g_i_belt008" ||
        sTag == "g_i_belt009" ||
        sTag == "g_i_belt010" ||
        sTag == "g_i_belt011" ||
        sTag == "g_i_belt012" ||
        sTag == "g_i_belt013" ||
        sTag == "g_i_belt014" ||
        sTag == "g_i_bithitem001" ||
        sTag == "g_i_bithitem002" ||
        sTag == "g_i_bithitem003" ||
        sTag == "g_i_bithitem004" ||
        sTag == "g_i_cmbtshot001" ||
        sTag == "g_i_cmbtshot002" ||
        sTag == "g_i_cmbtshot003" ||
        sTag == "g_i_collarlgt001" ||
        sTag == "g_i_credits001" ||
        sTag == "g_i_credits002" ||
        sTag == "g_i_credits003" ||
        sTag == "g_i_credits004" ||
        sTag == "g_i_credits005" ||
        sTag == "g_i_credits006" ||
        sTag == "g_i_credits007" ||
        sTag == "g_i_credits008" ||
        sTag == "g_i_credits009" ||
        sTag == "g_i_credits010" ||
        sTag == "g_i_credits011" ||
        sTag == "g_i_credits012" ||
        sTag == "g_i_credits013" ||
        sTag == "g_i_credits014" ||
        sTag == "g_i_credits015" ||
        sTag == "g_i_credits016" ||
        sTag == "g_i_credits017" ||
        sTag == "g_i_crhide001" ||
        sTag == "g_i_crhide002" ||
        sTag == "g_i_crhide003" ||
        sTag == "g_i_crhide004" ||
        sTag == "g_i_crhide005" ||
        sTag == "g_i_crhide006" ||
        sTag == "g_i_crhide007" ||
        sTag == "g_i_crhide008" ||
        sTag == "g_i_crhide009" ||
        sTag == "g_i_crhide010" ||
        sTag == "g_i_crhide011" ||
        sTag == "g_i_crhide012" ||
        sTag == "g_i_crhide013" ||
        sTag == "g_i_datapad001" ||
        sTag == "g_i_drdcomspk001" ||
        sTag == "g_i_drdcomspk002" ||
        sTag == "g_i_drdcomspk003" ||
        sTag == "g_i_drdhvplat001" ||
        sTag == "g_i_drdhvplat002" ||
        sTag == "g_i_drdhvplat003" ||
        sTag == "g_i_drdltplat001" ||
        sTag == "g_i_drdltplat002" ||
        sTag == "g_i_drdltplat003" ||
        sTag == "g_i_drdmdplat001" ||
        sTag == "g_i_drdmdplat002" ||
        sTag == "g_i_drdmdplat003" ||
        sTag == "g_i_drdmtnsen001" ||
        sTag == "g_i_drdmtnsen002" ||
        sTag == "g_i_drdmtnsen003" ||
        sTag == "g_i_drdrepeqp001" ||
        sTag == "g_i_drdrepeqp002" ||
        sTag == "g_i_drdrepeqp003" ||
        sTag == "g_i_drdsecspk001" ||
        sTag == "g_i_drdsecspk002" ||
        sTag == "g_i_drdsecspk003" ||
        sTag == "g_i_drdshld001" ||
        sTag == "g_i_drdshld002" ||
        sTag == "g_i_drdshld003" ||
        sTag == "g_i_drdshld005" ||
        sTag == "g_i_drdshld006" ||
        sTag == "g_i_drdshld007" ||
        sTag == "g_i_drdshld008" ||
        sTag == "g_i_drdsncsen001" ||
        sTag == "g_i_drdsncsen002" ||
        sTag == "g_i_drdsncsen003" ||
        sTag == "g_i_drdsrcscp001" ||
        sTag == "g_i_drdsrcscp002" ||
        sTag == "g_i_drdsrcscp003" ||
        sTag == "g_i_drdtrgcom001" ||
        sTag == "g_i_drdtrgcom002" ||
        sTag == "g_i_drdtrgcom003" ||
        sTag == "g_i_drdtrgcom004" ||
        sTag == "g_i_drdtrgcom005" ||
        sTag == "g_i_drdtrgcom006" ||
        sTag == "g_i_drdutldev001" ||
        sTag == "g_i_drdutldev002" ||
        sTag == "g_i_drdutldev003" ||
        sTag == "g_i_drdutldev004" ||
        sTag == "g_i_drdutldev005" ||
        sTag == "g_i_drdutldev006" ||
        sTag == "g_i_drdutldev007" ||
        sTag == "g_i_drdutldev008" ||
        sTag == "g_i_drdutldev009" ||
        sTag == "g_i_drdutldev010" ||
        sTag == "g_i_drdutldev011" ||
        sTag == "g_i_drdutldev012" ||
        sTag == "g_i_frarmbnds01" ||
        sTag == "g_i_frarmbnds010" ||
        sTag == "g_i_frarmbnds02" ||
        sTag == "g_i_frarmbnds03" ||
        sTag == "g_i_frarmbnds04" ||
        sTag == "g_i_frarmbnds05" ||
        sTag == "g_i_frarmbnds06" ||
        sTag == "g_i_frarmbnds07" ||
        sTag == "g_i_frarmbnds08" ||
        sTag == "g_i_frarmbnds09" ||
        sTag == "g_i_frarmbnds10" ||
        sTag == "g_i_frarmbnds11" ||
        sTag == "g_i_frarmbnds12" ||
        sTag == "g_i_frarmbnds13" ||
        sTag == "g_i_frarmbnds14" ||
        sTag == "g_i_frarmbnds15" ||
        sTag == "g_i_frarmbnds16" ||
        sTag == "g_i_frarmbnds17" ||
        sTag == "g_i_frarmbnds18" ||
        sTag == "g_i_frarmbnds19" ||
        sTag == "g_i_frarmbnds20" ||
        sTag == "g_i_frarmbnds21" ||
        sTag == "g_i_gauntlet01" ||
        sTag == "g_i_gauntlet02" ||
        sTag == "g_i_gauntlet03" ||
        sTag == "g_i_gauntlet04" ||
        sTag == "g_i_gauntlet05" ||
        sTag == "g_i_gauntlet06" ||
        sTag == "g_i_gauntlet07" ||
        sTag == "g_i_gauntlet08" ||
        sTag == "g_i_gauntlet09" ||
        sTag == "g_i_glowrod01" ||
        sTag == "g_i_implant101" ||
        sTag == "g_i_implant102" ||
        sTag == "g_i_implant103" ||
        sTag == "g_i_implant104" ||
        sTag == "g_i_implant201" ||
        sTag == "g_i_implant202" ||
        sTag == "g_i_implant203" ||
        sTag == "g_i_implant204" ||
        sTag == "g_i_implant301" ||
        sTag == "g_i_implant302" ||
        sTag == "g_i_implant303" ||
        sTag == "g_i_implant304" ||
        sTag == "g_i_implant305" ||
        sTag == "g_i_implant306" ||
        sTag == "g_i_implant307" ||
        sTag == "g_i_implant308" ||
        sTag == "g_i_implant309" ||
        sTag == "g_i_implant310" ||
        sTag == "g_i_mask009" ||
        sTag == "g_i_mask01" ||
        sTag == "g_i_mask02" ||
        sTag == "g_i_mask023" ||
        sTag == "g_i_mask03" ||
        sTag == "g_i_mask04" ||
        sTag == "g_i_mask05" ||
        sTag == "g_i_mask06" ||
        sTag == "g_i_mask07" ||
        sTag == "g_i_mask08" ||
        sTag == "g_i_mask09" ||
        sTag == "g_i_mask10" ||
        sTag == "g_i_mask11" ||
        sTag == "g_i_mask12" ||
        sTag == "g_i_mask13" ||
        sTag == "g_i_mask14" ||
        sTag == "g_i_mask15" ||
        sTag == "g_i_mask16" ||
        sTag == "g_i_mask17" ||
        sTag == "g_i_mask18" ||
        sTag == "g_i_mask19" ||
        sTag == "g_i_mask20" ||
        sTag == "g_i_mask21" ||
        sTag == "g_i_mask22" ||
        sTag == "g_i_mask23" ||
        sTag == "g_i_mask24" ||
        sTag == "g_i_medeqpmnt002" ||
        sTag == "g_i_medeqpmnt003" ||
        sTag == "g_i_medeqpmnt01" ||
        sTag == "g_i_medeqpmnt02" ||
        sTag == "g_i_medeqpmnt03" ||
        sTag == "g_i_medeqpmnt04" ||
        sTag == "g_i_medeqpmnt05" ||
        sTag == "g_i_medeqpmnt06" ||
        sTag == "g_i_medeqpmnt07" ||
        sTag == "g_i_medeqpmnt08" ||
        sTag == "g_i_parts01" ||
        sTag == "g_i_pazcard_001" ||
        sTag == "g_i_pazcard_002" ||
        sTag == "g_i_pazcard_003" ||
        sTag == "g_i_pazcard_004" ||
        sTag == "g_i_pazcard_005" ||
        sTag == "g_i_pazcard_006" ||
        sTag == "g_i_pazcard_007" ||
        sTag == "g_i_pazcard_008" ||
        sTag == "g_i_pazcard_009" ||
        sTag == "g_i_pazcard_010" ||
        sTag == "g_i_pazcard_011" ||
        sTag == "g_i_pazcard_012" ||
        sTag == "g_i_pazcard_013" ||
        sTag == "g_i_pazcard_014" ||
        sTag == "g_i_pazcard_015" ||
        sTag == "g_i_pazcard_016" ||
        sTag == "g_i_pazcard_017" ||
        sTag == "g_i_pazcard_018" ||
        sTag == "g_i_progspike002" ||
        sTag == "g_i_progspike003" ||
        sTag == "g_i_progspike01" ||
        sTag == "g_i_progspike02" ||
        sTag == "g_i_recordrod01" ||
        sTag == "g_i_secspike01" ||
        sTag == "g_i_secspike02" ||
        sTag == "g_i_torch01" ||
        sTag == "g_i_trapkit001" ||
        sTag == "g_i_trapkit002" ||
        sTag == "g_i_trapkit003" ||
        sTag == "g_i_trapkit004" ||
        sTag == "g_i_trapkit005" ||
        sTag == "g_i_trapkit006" ||
        sTag == "g_i_trapkit007" ||
        sTag == "g_i_trapkit008" ||
        sTag == "g_i_trapkit009" ||
        sTag == "g_i_trapkit01" ||
        sTag == "g_i_trapkit010" ||
        sTag == "g_i_trapkit011" ||
        sTag == "g_i_trapkit012" ||
        sTag == "g_i_trapkit02" ||
        sTag == "g_i_trapkit03" ||
        sTag == "g_i_trapkit04" ||
        sTag == "g_manaanvis" ||
        sTag == "g_scijournal" ||
        sTag == "g_unk_rancorclaw" ||
        sTag == "g_w_adhsvgren001" ||
        sTag == "g_w_blstrcrbn001" ||
        sTag == "g_w_blstrcrbn002" ||
        sTag == "g_w_blstrcrbn003" ||
        sTag == "g_w_blstrcrbn004" ||
        sTag == "g_w_blstrcrbn005" ||
        sTag == "g_w_blstrcrbn006" ||
        sTag == "g_w_blstrcrbn007" ||
        sTag == "g_w_blstrcrbn008" ||
        sTag == "g_w_blstrcrbn009" ||
        sTag == "g_w_blstrcrbn020" ||
        sTag == "g_w_blstrpstl001" ||
        sTag == "g_w_blstrpstl002" ||
        sTag == "g_w_blstrpstl003" ||
        sTag == "g_w_blstrpstl004" ||
        sTag == "g_w_blstrpstl005" ||
        sTag == "g_w_blstrpstl006" ||
        sTag == "g_w_blstrpstl007" ||
        sTag == "g_w_blstrpstl008" ||
        sTag == "g_w_blstrpstl009" ||
        sTag == "g_w_blstrpstl010" ||
        sTag == "g_w_blstrpstl020" ||
        sTag == "g_w_blstrrfl001" ||
        sTag == "g_w_blstrrfl002" ||
        sTag == "g_w_blstrrfl003" ||
        sTag == "g_w_blstrrfl004" ||
        sTag == "g_w_blstrrfl005" ||
        sTag == "g_w_blstrrfl006" ||
        sTag == "g_w_blstrrfl007" ||
        sTag == "g_w_blstrrfl008" ||
        sTag == "g_w_blstrrfl009" ||
        sTag == "g_w_blstrrfl020" ||
        sTag == "g_w_bowcstr001" ||
        sTag == "g_w_bowcstr002" ||
        sTag == "g_w_bowcstr003" ||
        sTag == "g_w_crgore001" ||
        sTag == "g_w_crgore002" ||
        sTag == "g_w_crslash001" ||
        sTag == "g_w_crslash002" ||
        sTag == "g_w_crslash003" ||
        sTag == "g_w_crslash004" ||
        sTag == "g_w_crslash005" ||
        sTag == "g_w_crslash006" ||
        sTag == "g_w_crslash007" ||
        sTag == "g_w_crslash008" ||
        sTag == "g_w_crslash009" ||
        sTag == "g_w_crslash010" ||
        sTag == "g_w_crslash011" ||
        sTag == "g_w_crslash012" ||
        sTag == "g_w_crslprc001" ||
        sTag == "g_w_crslprc002" ||
        sTag == "g_w_crslprc003" ||
        sTag == "g_w_crslprc004" ||
        sTag == "g_w_crslprc005" ||
        sTag == "g_w_cryobgren001" ||
        sTag == "g_w_dblsbr001" ||
        sTag == "g_w_dblsbr002" ||
        sTag == "g_w_dblsbr003" ||
        sTag == "g_w_dblsbr004" ||
        sTag == "g_w_dblsbr005" ||
        sTag == "g_w_dblsbr006" ||
        sTag == "g_w_dblsbr007" ||
        sTag == "g_w_dblswrd001" ||
        sTag == "g_w_dblswrd002" ||
        sTag == "g_w_dblswrd003" ||
        sTag == "g_w_dblswrd005" ||
        sTag == "g_w_drkjdisbr001" ||
        sTag == "g_w_drkjdisbr002" ||
        sTag == "g_w_dsrptpstl001" ||
        sTag == "g_w_dsrptpstl002" ||
        sTag == "g_w_dsrptrfl001" ||
        sTag == "g_w_dsrptrfl002" ||
        sTag == "g_w_firegren001" ||
        sTag == "g_w_flashgren001" ||
        sTag == "g_w_fraggren01" ||
        sTag == "g_w_gaffi001" ||
        sTag == "g_w_hldoblstr003" ||
        sTag == "g_w_hldoblstr004" ||
        sTag == "g_w_hldoblstr01" ||
        sTag == "g_w_hldoblstr02" ||
        sTag == "g_w_hldoblstr03" ||
        sTag == "g_w_hldoblstr04" ||
        sTag == "g_w_hvrptbltr002" ||
        sTag == "g_w_hvrptbltr01" ||
        sTag == "g_w_hvrptbltr02" ||
        sTag == "g_w_hvyblstr002" ||
        sTag == "g_w_hvyblstr01" ||
        sTag == "g_w_hvyblstr02" ||
        sTag == "g_w_hvyblstr03" ||
        sTag == "g_w_hvyblstr04" ||
        sTag == "g_w_hvyblstr05" ||
        sTag == "g_w_hvyblstr06" ||
        sTag == "g_w_hvyblstr07" ||
        sTag == "g_w_hvyblstr08" ||
        sTag == "g_w_hvyblstr09" ||
        sTag == "g_w_ionblstr01" ||
        sTag == "g_w_ionblstr02" ||
        sTag == "g_w_iongren01" ||
        sTag == "g_w_ionrfl01" ||
        sTag == "g_w_ionrfl02" ||
        sTag == "g_w_ionrfl03" ||
        sTag == "g_w_lghtsbr002" ||
        sTag == "g_w_lghtsbr007" ||
        sTag == "g_w_lghtsbr008" ||
        sTag == "g_w_lghtsbr01" ||
        sTag == "g_w_lghtsbr012" ||
        sTag == "g_w_lghtsbr02" ||
        sTag == "g_w_lghtsbr03" ||
        sTag == "g_w_lghtsbr04" ||
        sTag == "g_w_lghtsbr05" ||
        sTag == "g_w_lghtsbr06" ||
        sTag == "g_w_lngswrd01" ||
        sTag == "g_w_lngswrd02" ||
        sTag == "g_w_lngswrd03" ||
        sTag == "g_w_null001" ||
        sTag == "g_w_null002" ||
        sTag == "g_w_null003" ||
        sTag == "g_w_null004" ||
        sTag == "g_w_null005" ||
        sTag == "g_w_null006" ||
        sTag == "g_w_null007" ||
        sTag == "g_w_poisngren01" ||
        sTag == "g_w_qtrstaff01" ||
        sTag == "g_w_qtrstaff02" ||
        sTag == "g_w_qtrstaff03" ||
        sTag == "g_w_rptnblstr004" ||
        sTag == "g_w_rptnblstr01" ||
        sTag == "g_w_rptnblstr02" ||
        sTag == "g_w_rptnblstr03" ||
        sTag == "g_w_sbrcrstl01" ||
        sTag == "g_w_sbrcrstl015" ||
        sTag == "g_w_sbrcrstl02" ||
        sTag == "g_w_sbrcrstl03" ||
        sTag == "g_w_sbrcrstl04" ||
        sTag == "g_w_sbrcrstl05" ||
        sTag == "g_w_sbrcrstl06" ||
        sTag == "g_w_sbrcrstl07" ||
        sTag == "g_w_sbrcrstl08" ||
        sTag == "g_w_sbrcrstl09" ||
        sTag == "g_w_sbrcrstl10" ||
        sTag == "g_w_sbrcrstl11" ||
        sTag == "g_w_sbrcrstl12" ||
        sTag == "g_w_sbrcrstl13" ||
        sTag == "g_w_sbrcrstl14" ||
        sTag == "g_w_sbrcrstl15" ||
        sTag == "g_w_sbrcrstl16" ||
        sTag == "g_w_sbrcrstl17" ||
        sTag == "g_w_sbrcrstl18" ||
        sTag == "g_w_sbrcrstl19" ||
        sTag == "g_w_shortsbr01" ||
        sTag == "g_w_shortsbr02" ||
        sTag == "g_w_shortsbr03" ||
        sTag == "g_w_shortsbr04" ||
        sTag == "g_w_shortsbr05" ||
        sTag == "g_w_shortswrd01" ||
        sTag == "g_w_shortswrd02" ||
        sTag == "g_w_shortswrd03" ||
        sTag == "g_w_sonicgren01" ||
        sTag == "g_w_sonicpstl01" ||
        sTag == "g_w_sonicpstl02" ||
        sTag == "g_w_sonicrfl01" ||
        sTag == "g_w_sonicrfl02" ||
        sTag == "g_w_sonicrfl03" ||
        sTag == "g_w_stunbaton005" ||
        sTag == "g_w_stunbaton01" ||
        sTag == "g_w_stunbaton02" ||
        sTag == "g_w_stunbaton03" ||
        sTag == "g_w_stunbaton04" ||
        sTag == "g_w_stunbaton05" ||
        sTag == "g_w_stunbaton06" ||
        sTag == "g_w_stunbaton07" ||
        sTag == "g_w_stungren01" ||
        sTag == "g_w_thermldet002" ||
        sTag == "g_w_thermldet01" ||
        sTag == "g_w_vbrdblswd01" ||
        sTag == "g_w_vbrdblswd02" ||
        sTag == "g_w_vbrdblswd03" ||
        sTag == "g_w_vbrdblswd04" ||
        sTag == "g_w_vbrdblswd05" ||
        sTag == "g_w_vbrdblswd06" ||
        sTag == "g_w_vbrdblswd07" ||
        sTag == "g_w_vbroshort002" ||
        sTag == "g_w_vbroshort01" ||
        sTag == "g_w_vbroshort02" ||
        sTag == "g_w_vbroshort03" ||
        sTag == "g_w_vbroshort04" ||
        sTag == "g_w_vbroshort05" ||
        sTag == "g_w_vbroshort06" ||
        sTag == "g_w_vbroshort07" ||
        sTag == "g_w_vbroshort08" ||
        sTag == "g_w_vbroshort09" ||
        sTag == "g_w_vbroswrd002" ||
        sTag == "g_w_vbroswrd01" ||
        sTag == "g_w_vbroswrd02" ||
        sTag == "g_w_vbroswrd03" ||
        sTag == "g_w_vbroswrd04" ||
        sTag == "g_w_vbroswrd05" ||
        sTag == "g_w_vbroswrd06" ||
        sTag == "g_w_vbroswrd07" ||
        sTag == "g_w_vbroswrd08" ||
        sTag == "g_w_waraxe001" ||
        sTag == "g_w_waraxe002" ||
        sTag == "g_w_warblade001" ||
        sTag == "g_w_warblade002" ||
        sTag == "geno_armor" ||
        sTag == "geno_blade" ||
        sTag == "geno_blaster" ||
        sTag == "geno_gloves" ||
        sTag == "geno_stealth" ||
        sTag == "geno_visor" ||
        sTag == "grarwwaar_pad" ||
        sTag == "guunjournal" ||
        sTag == "item001" ||
        sTag == "k34_itm_terahide" ||
        sTag == "k37_itm_freednf1" ||
        sTag == "k37_itm_freednf2" ||
        sTag == "k37_itm_freedont" ||
        sTag == "k39_itm_terahide" ||
        sTag == "k_kor_koltadvmed" ||
        sTag == "k_kor_koltomed" ||
        sTag == "k_kor_teranclaw2" ||
        sTag == "kas22_kinra_claw" ||
        sTag == "kas22_longsword" ||
        sTag == "kas23_baccasword" ||
        sTag == "kas24_kinra_claw" ||
        sTag == "kas24_lightsaber" ||
        sTag == "kas25_datapad1" ||
        sTag == "kas25_datapad2" ||
        sTag == "kas25_longsword" ||
        sTag == "kor33a_credit150" ||
        sTag == "kor33a_credit450" ||
        sTag == "kor33a_credit600" ||
        sTag == "kor33b_credit150" ||
        sTag == "kor33b_credit600" ||
        sTag == "kor34_credits150" ||
        sTag == "kor34_credits450" ||
        sTag == "kor34_credits600" ||
        sTag == "kor34_credits900" ||
        sTag == "kor35_credits150" ||
        sTag == "kor35_credits450" ||
        sTag == "kor36_credits150" ||
        sTag == "kor37_credits450" ||
        sTag == "kor37_droidblast" ||
        sTag == "kor38a_credit450" ||
        sTag == "kor38a_credit600" ||
        sTag == "kor38a_gauntlet" ||
        sTag == "kor38b_assassin" ||
        sTag == "kor38b_credit150" ||
        sTag == "kor38b_credit450" ||
        sTag == "kor38b_mask" ||
        sTag == "kor39_credits150" ||
        sTag == "kor39_credits450" ||
        sTag == "kor39_credits600" ||
        sTag == "kor39_credits900" ||
        sTag == "lev40_supergun" ||
        sTag == "man28_firbite" ||
        sTag == "man28_selkclaw" ||
        sTag == "placeholder01" ||
        sTag == "ptar_rakalphacla" ||
        sTag == "ptar_rakclaw" ||
        sTag == "ptar_rakghoulser" ||
        sTag == "ptar_shockstick" ||
        sTag == "punk_rancorgren" ||
        sTag == "rakatanelderhide" ||
        sTag == "shaelajournal" ||
        sTag == "sonicattachment" ||
        sTag == "sta45a_credit150" ||
        sTag == "sta45a_credit200" ||
        sTag == "sta45a_credit300" ||
        sTag == "sta45a_credits50" ||
        sTag == "sta45b_credit150" ||
        sTag == "sta45b_credit200" ||
        sTag == "sta45b_credit300" ||
        sTag == "sta45c_credit150" ||
        sTag == "sta45c_credit200" ||
        sTag == "sta45c_credit300" ||
        sTag == "sta45d_credit300" ||
        sTag == "sta_light002" ||
        sTag == "sta_light1" ||
        sTag == "sta_shortligh001" ||
        sTag == "sta_shortlight1" ||
        sTag == "sta_temp_saber" ||
        sTag == "sta_temp_saber2" ||
        sTag == "tar03_brejikband" ||
        sTag == "tar03_brejikbelt" ||
        sTag == "tar03_brejikglov" ||
        sTag == "tar05_stampyclaw" ||
        sTag == "tar05_stampyhide" ||
        sTag == "tar08_davikmask" ||
        sTag == "tar11_powerbelt" ||
        sTag == "tat18_kraytclaw" ||
        sTag == "tat20_gaffi02" ||
        sTag == "tat20_gaffistick" ||
        sTag == "tempselk" ||
        sTag == "vorndata" ||
        sTag == "w_blhvy001" ||
        sTag == "w_blhvy002" ||
        sTag == "w_bstrcrbn" ||
        sTag == "w_lghtsbr001" ||
        sTag == "w_null")
    {
        object oPC = GetFirstPC();
        int nCurCredits = GetGold(oPC);
        if (KSE_HasData("last_credits"))
        {
            int nLastCredits = StringToInt(KSE_GetData("last_credits"));
            if (nCurCredits < nLastCredits)
            {
                KSE_SetData("last_credits", IntToString(nCurCredits));
                KSE_SetData("granted_exempt_" + sTag, "1");
                return;
            }
        }
        KSE_SetData("last_credits", IntToString(nCurCredits));
        int nHeld = 0;
        object oScan = GetFirstItemInInventory(oPC);
        while (GetIsObjectValid(oScan))
        {
            if (GetStringLowerCase(GetTag(oScan)) == sTag) nHeld = nHeld + GetItemStackSize(oScan);
            oScan = GetNextItemInInventory(oPC);
        }
        int nLastHeld = 0;
        if (KSE_HasData("qty_" + sTag)) nLastHeld = StringToInt(KSE_GetData("qty_" + sTag));
        KSE_SetData("qty_" + sTag, IntToString(nHeld));
        int nDelta = nHeld - nLastHeld;
        if (nDelta <= 0) return;
        int nCounter = 0;
        if (KSE_HasData("pickup_running_count")) nCounter = StringToInt(KSE_GetData("pickup_running_count"));
        int nOldMilestones = nCounter / 5;
        nCounter = nCounter + nDelta;
        int nNewMilestones = nCounter / 5;
        KSE_SetData("pickup_running_count", IntToString(nCounter));
        int i = nOldMilestones;
        while (i < nNewMilestones)
        {
            string sRandom = GetRandomLootItem();
            KSE_SetData("granted_exempt_" + GetStringLowerCase(sRandom), "1");
            CreateItemOnObject(sRandom, oPC, 1);
            KSE_Diag(87, "AP|BONUS_ITEM|milestone=" + IntToString(i + 1) + "|" + sRandom);
            i = i + 1;
        }
    }
}

void main()
{
    ExecuteScript("apo_k_ptat20aa_acqui_orig", OBJECT_SELF);
    HandleAcquiredItem();
}
