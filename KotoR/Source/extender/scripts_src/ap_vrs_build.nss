#include "kse"

void main()
{
    object oPC = GetPCSpeaker();
    int nOff = StringToInt(KSE_GetData("vrs_off"));
    int nPos = 0;
    int nSlot = 0;
    int nClear = 0;
    while (nClear < 16)
    {
        KSE_SetData("vslot" + IntToString(nClear), "0");
        nClear = nClear + 1;
    }
    if (KSE_GetFeatAcquired(1, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "1");
            SetCustomToken(101 + nSlot, GetStringByStrRef(148));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(3, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "3");
            SetCustomToken(101 + nSlot, GetStringByStrRef(150));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(4, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "4");
            SetCustomToken(101 + nSlot, GetStringByStrRef(153));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(5, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "5");
            SetCustomToken(101 + nSlot, GetStringByStrRef(151));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(6, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "6");
            SetCustomToken(101 + nSlot, GetStringByStrRef(152));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(7, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "7");
            SetCustomToken(101 + nSlot, GetStringByStrRef(154));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(8, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "8");
            SetCustomToken(101 + nSlot, GetStringByStrRef(155));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(9, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "9");
            SetCustomToken(101 + nSlot, GetStringByStrRef(157));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(10, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "10");
            SetCustomToken(101 + nSlot, GetStringByStrRef(158));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(11, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "11");
            SetCustomToken(101 + nSlot, GetStringByStrRef(160));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(12, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "12");
            SetCustomToken(101 + nSlot, GetStringByStrRef(161));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(13, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "13");
            SetCustomToken(101 + nSlot, GetStringByStrRef(162));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(14, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "14");
            SetCustomToken(101 + nSlot, GetStringByStrRef(164));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(15, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "15");
            SetCustomToken(101 + nSlot, GetStringByStrRef(165));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(16, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "16");
            SetCustomToken(101 + nSlot, GetStringByStrRef(166));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(17, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "17");
            SetCustomToken(101 + nSlot, GetStringByStrRef(167));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(18, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "18");
            SetCustomToken(101 + nSlot, GetStringByStrRef(168));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(19, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "19");
            SetCustomToken(101 + nSlot, GetStringByStrRef(169));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(20, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "20");
            SetCustomToken(101 + nSlot, GetStringByStrRef(170));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(21, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "21");
            SetCustomToken(101 + nSlot, GetStringByStrRef(171));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(22, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "22");
            SetCustomToken(101 + nSlot, GetStringByStrRef(172));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(24, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "24");
            SetCustomToken(101 + nSlot, GetStringByStrRef(174));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(26, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "26");
            SetCustomToken(101 + nSlot, GetStringByStrRef(176));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(28, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "28");
            SetCustomToken(101 + nSlot, GetStringByStrRef(178));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(29, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "29");
            SetCustomToken(101 + nSlot, GetStringByStrRef(179));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(30, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "30");
            SetCustomToken(101 + nSlot, GetStringByStrRef(180));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(31, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "31");
            SetCustomToken(101 + nSlot, GetStringByStrRef(181));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(32, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "32");
            SetCustomToken(101 + nSlot, GetStringByStrRef(182));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(33, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "33");
            SetCustomToken(101 + nSlot, GetStringByStrRef(183));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(35, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "35");
            SetCustomToken(101 + nSlot, GetStringByStrRef(185));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(36, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "36");
            SetCustomToken(101 + nSlot, GetStringByStrRef(186));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(37, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "37");
            SetCustomToken(101 + nSlot, GetStringByStrRef(187));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(39, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "39");
            SetCustomToken(101 + nSlot, GetStringByStrRef(189));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(40, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "40");
            SetCustomToken(101 + nSlot, GetStringByStrRef(190));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(42, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "42");
            SetCustomToken(101 + nSlot, GetStringByStrRef(192));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(43, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "43");
            SetCustomToken(101 + nSlot, GetStringByStrRef(193));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(44, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "44");
            SetCustomToken(101 + nSlot, GetStringByStrRef(194));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(46, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "46");
            SetCustomToken(101 + nSlot, GetStringByStrRef(196));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(47, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "47");
            SetCustomToken(101 + nSlot, GetStringByStrRef(197));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(49, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "49");
            SetCustomToken(101 + nSlot, GetStringByStrRef(199));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(50, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "50");
            SetCustomToken(101 + nSlot, GetStringByStrRef(200));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(51, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "51");
            SetCustomToken(101 + nSlot, GetStringByStrRef(201));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(53, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "53");
            SetCustomToken(101 + nSlot, GetStringByStrRef(203));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(55, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "55");
            SetCustomToken(101 + nSlot, GetStringByStrRef(156));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(56, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "56");
            SetCustomToken(101 + nSlot, GetStringByStrRef(159));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(57, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "57");
            SetCustomToken(101 + nSlot, GetStringByStrRef(163));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(60, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "60");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1032));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(61, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "61");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1033));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(62, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "62");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1034));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(63, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "63");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1035));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(64, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "64");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1036));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(65, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "65");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1037));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(66, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "66");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1038));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(67, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "67");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1039));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(68, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "68");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1040));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(69, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "69");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1041));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(77, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "77");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1049));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(78, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "78");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1050));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(79, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "79");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1051));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(80, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "80");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1052));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(81, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "81");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1190));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(82, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "82");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1191));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(83, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "83");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1192));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(84, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "84");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1193));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(85, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "85");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1194));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(88, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "88");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1197));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(89, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "89");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1198));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(90, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "90");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1199));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(91, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "91");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1200));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(92, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "92");
            SetCustomToken(101 + nSlot, GetStringByStrRef(1201));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(93, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "93");
            SetCustomToken(101 + nSlot, GetStringByStrRef(32077));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(94, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "94");
            SetCustomToken(101 + nSlot, GetStringByStrRef(32079));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(95, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "95");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38526));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(96, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "96");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38527));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(97, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "97");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38528));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(98, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "98");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38530));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(99, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "99");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38529));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(100, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "100");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38531));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(101, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "101");
            SetCustomToken(101 + nSlot, GetStringByStrRef(280));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(102, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "102");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38532));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(103, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "103");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38533));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(104, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "104");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38584));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(105, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "105");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38585));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(106, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "106");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38586));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(107, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "107");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38587));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(108, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "108");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38588));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(109, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "109");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38589));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(110, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "110");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38590));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(111, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "111");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38591));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(112, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "112");
            SetCustomToken(101 + nSlot, GetStringByStrRef(38592));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(113, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "113");
            SetCustomToken(101 + nSlot, GetStringByStrRef(41858));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(114, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "114");
            SetCustomToken(101 + nSlot, GetStringByStrRef(41859));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(115, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "115");
            SetCustomToken(101 + nSlot, GetStringByStrRef(41860));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(116, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "116");
            SetCustomToken(101 + nSlot, GetStringByStrRef(41861));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(117, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "117");
            SetCustomToken(101 + nSlot, GetStringByStrRef(41994));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(118, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "118");
            SetCustomToken(101 + nSlot, GetStringByStrRef(41993));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(119, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "119");
            SetCustomToken(101 + nSlot, GetStringByStrRef(42001));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(120, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "120");
            SetCustomToken(101 + nSlot, GetStringByStrRef(42002));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(121, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "121");
            SetCustomToken(101 + nSlot, GetStringByStrRef(41995));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(122, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "122");
            SetCustomToken(101 + nSlot, GetStringByStrRef(41996));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(123, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "123");
            SetCustomToken(101 + nSlot, GetStringByStrRef(41986));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    if (KSE_GetFeatAcquired(124, oPC))
    {
        if (nPos >= nOff && nSlot < 16)
        {
            KSE_SetData("vslot" + IntToString(nSlot), "124");
            SetCustomToken(101 + nSlot, GetStringByStrRef(41987));
            nSlot = nSlot + 1;
        }
        nPos = nPos + 1;
    }
    KSE_SetData("vrs_total", IntToString(nPos));
}
