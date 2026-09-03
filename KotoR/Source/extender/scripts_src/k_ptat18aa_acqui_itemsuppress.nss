// Item-suppression wrapper -- runs tat_m18aa's real vanilla
// Mod_OnAcquirItem script (k_ptat18aa_acqui, preserved as apo_k_ptat18aa_acqui_orig)
// first, then checks the acquired item against the AP suppression list.
#include "kse"

void SuppressIfNotAllowed()
{
    object oItem = GetModuleItemAcquired();
    string sTag = GetStringLowerCase(GetTag(oItem));
    if (sTag == "dan14_nothing" ||
        sTag == "duronjournal" ||
        sTag == "flash_gren" ||
        sTag == "g_i_asthitem001" ||
        sTag == "g_i_cmbtshot001" ||
        sTag == "g_i_cmbtshot002" ||
        sTag == "g_i_cmbtshot003" ||
        sTag == "g_i_collarlgt001" ||
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
        sTag == "g_i_drdrepeqp001" ||
        sTag == "g_i_drdrepeqp002" ||
        sTag == "g_i_glowrod01" ||
        sTag == "g_i_medeqpmnt002" ||
        sTag == "g_i_medeqpmnt003" ||
        sTag == "g_i_medeqpmnt02" ||
        sTag == "g_i_medeqpmnt03" ||
        sTag == "g_i_medeqpmnt04" ||
        sTag == "g_i_medeqpmnt05" ||
        sTag == "g_i_medeqpmnt08" ||
        sTag == "g_i_progspike002" ||
        sTag == "g_i_progspike003" ||
        sTag == "g_i_progspike01" ||
        sTag == "g_i_progspike02" ||
        sTag == "g_i_recordrod01" ||
        sTag == "g_i_secspike01" ||
        sTag == "g_i_secspike02" ||
        sTag == "g_i_torch01" ||
        sTag == "g_manaanvis" ||
        sTag == "g_scijournal" ||
        sTag == "g_unk_rancorclaw" ||
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
        sTag == "g_w_flashgren001" ||
        sTag == "g_w_thermldet002" ||
        sTag == "g_w_thermldet01" ||
        sTag == "grarwwaar_pad" ||
        sTag == "guunjournal" ||
        sTag == "k34_itm_terahide" ||
        sTag == "k39_itm_terahide" ||
        sTag == "k_kor_koltadvmed" ||
        sTag == "k_kor_koltomed" ||
        sTag == "k_kor_teranclaw2" ||
        sTag == "kas22_kinra_claw" ||
        sTag == "kas24_kinra_claw" ||
        sTag == "kas25_datapad1" ||
        sTag == "kas25_datapad2" ||
        sTag == "kor38b_assassin" ||
        sTag == "man28_firbite" ||
        sTag == "man28_selkclaw" ||
        sTag == "placeholder01" ||
        sTag == "ptar_rakalphacla" ||
        sTag == "ptar_rakclaw" ||
        sTag == "ptar_rakghoulser" ||
        sTag == "rakatanelderhide" ||
        sTag == "shaelajournal" ||
        sTag == "sonicattachment" ||
        sTag == "tar05_stampyclaw" ||
        sTag == "tar05_stampyhide" ||
        sTag == "tat18_kraytclaw" ||
        sTag == "tempselk" ||
        sTag == "vorndata" ||
        sTag == "w_blhvy001" ||
        sTag == "w_blhvy002" ||
        sTag == "w_lghtsbr001" ||
        sTag == "w_null")
    {
        KSE_Diag(86, "AP|SUPPRESSED_ITEM|" + sTag);
        DestroyObject(oItem);
    }
}

void main()
{
    ExecuteScript("apo_k_ptat18aa_acqui_orig", OBJECT_SELF);
    SuppressIfNotAllowed();
}
