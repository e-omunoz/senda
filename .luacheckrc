-- luacheck para Senda (WoW Forever, cliente moderno). Ver tools/README.md.
std = "lua51"
max_line_length = false
codes = true
allow_defined_top = true
unused_args = false          -- manejadores de eventos con firmas fijas
self = false

ignore = {
  "212",   -- argumento sin usar
  "432",   -- sombrear un upvalue (self en callbacks)
  "542",   -- rama if vacía
  "211/ADDON",     -- `local ADDON, Senda = ...` (nombre del addon, a veces sin usar)
  "131/SLASH_.*",  -- variables de comandos de barra: las lee el cliente
}

globals = {
  "Senda", "SendaDB", "SendaRecorderDB",
  "SLASH_SENDA1", "SLASH_SENDA2", "SLASH_SENDA3", "SLASH_SENDAWAY1", "SLASH_SENDAWAY2",
  "SlashCmdList", "StaticPopupDialogs", "UISpecialFrames", "BINDING_HEADER_SENDA",
  "BINDING_NAME_SENDA_TOGGLE", "BINDING_NAME_SENDA_NEXT", "BINDING_NAME_SENDA_PREV",
}

read_globals = {
  -- API usada con comprobación de existencia (puede faltar en el cliente moderno)
  "ClassTrainerFrame", "GetItemSpell", "GetMerchantItemMaxStack", "GetNumQuestLogChoices",
  "GetNumQuestLogRewards", "GetQuestLogItemLink", "GetQuestLogSelection", "GetTaxiMapID",
  "GetTrainerServiceCost", "GetTrainerServiceIcon", "HasPetSpells", "IsMouseButtonDown",
  "IsPassiveSpell", "IsTradeskillTrainer", "MAX_ACCOUNT_MACROS", "MAX_CHARACTER_MACROS",
  "NUM_BANKBAGSLOTS", "NUM_TOTAL_EQUIPPED_BAG_SLOTS", "SelectQuestLogEntry",
  -- Lua / utilidades de WoW
  "bit", "date", "time", "debugstack", "debugprofilestop", "geterrorhandler", "seterrorhandler",
  "strsplit", "strjoin", "strtrim", "strmatch", "strfind", "strsub", "strlower", "strupper", "strlen",
  "strrep", "strrev", "strbyte", "strchar", "format", "gsub", "tostringall", "string", "table", "math",
  "wipe", "tinsert", "tremove", "tContains", "tInvert", "tIndexOf", "CopyTable", "Mixin", "CreateFromMixins",
  "floor", "ceil", "abs", "min", "max", "sqrt", "random", "fastrandom", "sort", "issecretvalue",
  "issecure", "securecall", "securecallfunction", "hooksecurefunc", "InCombatLockdown",
  "C_Timer", "GetTime", "GetServerTime", "GetFramerate", "Round", "Clamp", "Lerp", "FormatLargeNumber",
  "GetLocale", "GetBuildInfo", "GetCVar", "SetCVar", "GetCVarBool", "C_CVar", "IsAddOnLoaded",
  "C_AddOns", "GetAddOnMetadata", "LoadAddOn", "EnableAddOn", "ReloadUI", "PlaySound", "PlaySoundFile",
  "SOUNDKIT", "StopSound", "Ambiguate", "Settings", "SettingsPanel", "InterfaceOptions_AddCategory",
  "InterfaceOptionsFrame_OpenToCategory", "EventRegistry", "CallbackRegistryMixin", "EventUtil",
  -- Marcos y UI
  "CreateFrame", "UIParent", "WorldFrame", "Minimap", "MinimapCluster", "GameTooltip", "ItemRefTooltip",
  "GameTooltip_Hide", "GameTooltip_SetDefaultAnchor", "GameFontNormal", "GameFontNormalSmall",
  "GameFontNormalLarge", "GameFontHighlight", "GameFontHighlightSmall", "GameFontHighlightLarge",
  "GameFontDisable", "GameFontDisableSmall", "GameFontWhite", "GameFontRed", "GameFontGreen",
  "NumberFontNormal", "ChatFontNormal", "SystemFont_Shadow_Med1", "STANDARD_TEXT_FONT", "UNIT_NAME_FONT",
  "DEFAULT_CHAT_FRAME", "ChatFrame1", "ChatFrame_AddMessageEventFilter", "ChatEdit_InsertLink",
  "ChatEdit_GetActiveWindow", "UIErrorsFrame", "RaidNotice_AddMessage", "RaidWarningFrame",
  "StaticPopup_Show", "StaticPopup_Hide", "ToggleDropDownMenu", "UIDropDownMenu_Initialize",
  "UIDropDownMenu_AddButton", "UIDropDownMenu_CreateInfo", "UIDropDownMenu_SetWidth",
  "UIDropDownMenu_SetText", "UIDropDownMenu_SetSelectedValue", "CloseDropDownMenus", "MenuUtil",
  "BackdropTemplateMixin", "BACKDROP_TOOLTIP_16_16_5555", "PanelTemplates_SetNumTabs",
  "PanelTemplates_SetTab", "PanelTemplates_TabResize", "ScrollUtil", "CreateScrollBoxListLinearView",
  "CreateDataProvider", "WorldMapFrame", "ShowUIPanel", "HideUIPanel", "ToggleFrame", "CloseAllWindows",
  "IsShiftKeyDown", "IsControlKeyDown", "IsAltKeyDown", "IsModifiedClick", "GetCursorPosition",
  "GetCursorInfo", "ClearCursor", "SetCursor", "ResetCursor", "GetScreenWidth", "GetScreenHeight",
  "GetMouseFocus", "GetMouseFoci", "MouseIsOver", "CreateColor", "RAID_CLASS_COLORS",
  "CUSTOM_CLASS_COLORS", "NORMAL_FONT_COLOR", "HIGHLIGHT_FONT_COLOR", "RED_FONT_COLOR", "GREEN_FONT_COLOR",
  "YELLOW_FONT_COLOR", "GRAY_FONT_COLOR", "ORANGE_FONT_COLOR", "WHITE_FONT_COLOR", "ITEM_QUALITY_COLORS",
  "SetPortraitTexture", "SetPortraitToTexture", "CreateTextureMarkup", "CreateAtlasMarkup",
  "ActionButton_ShowOverlayGlow", "ActionButton_HideOverlayGlow", "ActionButtonUtil",
  "GetBindingKey", "SetBinding", "SetBindingClick", "SetOverrideBindingClick", "ClearOverrideBindings",
  "SaveBindings", "GetCurrentBindingSet", "GameMenuFrame", "CharacterFrame", "SpellBookFrame",
  "PlayerTalentFrame", "ClassTalentFrame", "MerchantFrame", "TaxiFrame", "QuestFrame", "GossipFrame",
  "TradeSkillFrame", "MailFrame", "BankFrame", "ContainerFrame1", "PaperDollFrame",
  "QuestFrameAcceptButton", "QuestFrameCompleteButton", "QuestFrameCompleteQuestButton",
  "QuestInfoRewardsFrame", "QuestMapFrame", "ObjectiveTrackerFrame", "AlertFrame",
  -- Unidades
  "UnitName", "UnitGUID", "UnitLevel", "UnitClass", "UnitClassBase", "UnitRace", "UnitSex",
  "UnitFactionGroup", "UnitExists", "UnitIsDead", "UnitIsGhost", "UnitIsDeadOrGhost", "UnitHealth",
  "UnitHealthMax", "UnitPower", "UnitPowerMax", "UnitPowerType", "UnitXP", "UnitXPMax", "GetXPExhaustion",
  "UnitAffectingCombat", "UnitInParty", "UnitInRaid", "UnitIsPlayer", "UnitIsUnit", "UnitIsFriend",
  "UnitIsEnemy", "UnitCanAttack", "UnitReaction", "UnitCreatureType", "UnitClassification",
  "UnitPosition", "UnitOnTaxi", "UnitIsAFK", "UnitBuff", "UnitDebuff", "UnitAura", "UnitStat",
  "UnitArmor", "UnitAttackPower", "UnitRangedAttackPower", "UnitDamage", "UnitCastingInfo",
  "UnitChannelInfo", "UnitIsTapDenied", "UnitIsQuestBoss", "UnitPlayerControlled", "UnitIsConnected",
  "GetUnitName", "GetRealmName", "GetNormalizedRealmName", "IsInGroup", "IsInRaid", "IsInInstance",
  "GetNumGroupMembers", "GetNumSubgroupMembers", "IsResting", "IsMounted", "IsFlying", "IsSwimming",
  "IsFalling", "IsIndoors", "IsOutdoors", "GetUnitSpeed", "GetPlayerFacing", "CheckInteractDistance",
  "C_PlayerInfo", "C_PlayerInteractionManager", "PlayerUtil", "GetMaxPlayerLevel", "C_UnitAuras",
  "C_DeathInfo", "GetCorpseRecoveryDelay", "RepopMe", "RetrieveCorpse", "AcceptResurrect",
  "C_ClassTrainer", "C_ClassColor", "GetClassColor", "GetClassInfo", "C_CreatureInfo",
  "C_ChallengeMode", "C_PartyInfo", "C_GossipInfo", "C_Reputation", "GetFactionInfo", "GetFactionInfoByID",
  -- Misiones
  "C_QuestLog", "C_QuestInfoSystem", "C_TaskQuest", "QuestUtils_GetQuestName", "GetQuestID",
  "GetQuestLogTitle", "GetQuestLogIndexByID", "GetNumQuestLogEntries", "GetQuestsCompleted",
  "IsQuestFlaggedCompleted", "GetQuestReward", "GetNumQuestChoices", "GetQuestItemInfo",
  "GetQuestItemLink", "GetNumQuestRewards", "GetTitleText", "GetObjectiveText", "GetProgressText",
  "GetRewardText", "AcceptQuest", "DeclineQuest", "CompleteQuest", "IsQuestCompletable",
  "GetNumActiveQuests", "GetNumAvailableQuests", "GetActiveTitle", "GetAvailableTitle",
  "SelectActiveQuest", "SelectAvailableQuest", "GetActiveQuestID", "GetAvailableQuestInfo",
  "QuestGetAutoAccept", "AcknowledgeAutoAcceptQuest", "ShowQuestComplete", "ShowQuestOffer",
  "AbandonQuest", "SetAbandonQuest", "QUEST_LOG_UPDATE", "C_QuestOffer",
  -- Mapas y vuelo
  "C_Map", "C_MapExplorationInfo", "C_SuperTrack", "C_Navigation", "C_TaxiMap", "C_Minimap",
  "CreateVector2D", "GetZoneText", "GetSubZoneText", "GetRealZoneText", "GetMinimapZoneText",
  "NumTaxiNodes", "TaxiNodeName", "TaxiNodeGetType", "TaxiNodePosition", "TakeTaxiNode", "TaxiNodeCost",
  "GetBindLocation", "ConfirmBinder", "C_Housing",
  -- Hechizos, objetos, contenedores, comercio
  "C_Spell", "C_SpellBook", "C_Item", "C_Container", "C_TradeSkillUI", "C_Professions", "C_MerchantFrame",
  "C_PetJournal", "C_ToyBox", "C_MountJournal", "C_ActionBar", "C_EquipmentSet", "C_PaperDollInfo",
  "C_Macro", "C_ChatInfo", "C_FriendList", "C_BattleNet", "C_LFGList", "C_Texture", "C_CurrencyInfo",
  "C_Bank", "C_Tooltip", "C_TooltipInfo", "TooltipDataProcessor", "C_NewItems", "C_EncodingUtil",
  "Enum", "Constants", "GetSpellInfo", "GetSpellLink", "GetSpellTexture", "IsSpellKnown",
  "IsPlayerSpell", "GetSpellCooldown", "GetSpellBookItemInfo", "GetNumSpellTabs", "GetSpellTabInfo",
  "GetItemInfo", "GetItemInfoInstant", "GetItemCount", "GetItemIcon", "GetItemQualityColor",
  "GetItemStats", "GetDetailedItemLevelInfo", "GetInventoryItemLink", "GetInventoryItemID",
  "GetInventoryItemTexture", "GetInventorySlotInfo", "GetInventoryItemDurability", "EquipItemByName",
  "PickupInventoryItem", "PickupContainerItem", "UseContainerItem", "UseItemByName", "IsEquippableItem",
  "IsEquippedItem", "GetContainerNumSlots", "GetContainerItemInfo", "GetContainerItemLink",
  "GetMoney", "GetCoinTextureString", "GetMoneyString", "GetMerchantNumItems", "GetMerchantItemInfo",
  "GetMerchantItemLink", "GetMerchantItemID", "BuyMerchantItem", "CanMerchantRepair", "RepairAllItems",
  "GetRepairAllCost", "CloseMerchant", "GetNumTrainerServices", "GetTrainerServiceInfo",
  "BuyTrainerService", "GetProfessions", "GetProfessionInfo", "GetSkillLineInfo", "GetNumSkillLines",
  "GetTradeSkillLine", "GetNumTradeSkills", "GetTradeSkillInfo", "CastSpellByName", "CastSpellByID",
  "GetMacroInfo", "GetNumMacros", "CreateMacro", "EditMacro", "GetMacroIndexByName", "PickupMacro",
  "GetActionInfo", "PickupAction", "PlaceAction", "PickupSpell", "HasAction", "GetActionTexture",
  "GetTalentInfo", "GetNumTalentTabs", "GetNumTalents", "GetTalentTabInfo", "LearnTalent",
  "C_ClassTalents", "C_Traits", "C_SpecializationInfo", "GetSpecialization", "GetSpecializationInfo",
  "GetActiveTalentGroup", "GetNumTalentGroups", "GetUnspentTalentPoints", "UnitCharacterPoints",
  "GetAverageItemLevel", "GetCombatRating", "GetCombatRatingBonus", "GetCritChance", "GetSpellCritChance",
  "GetHitModifier", "GetSpellBonusDamage", "GetSpellBonusHealing", "GetDodgeChance", "GetParryChance",
  "GetBlockChance", "GetExpertise", "GetHaste", "GetRangedCritChance", "GetManaRegen",
  "GetNumLootItems", "GetLootSlotInfo", "GetLootSlotLink", "LootSlot", "CloseLoot",
  "SendChatMessage", "GetGuildInfo", "InviteUnit", "C_Social",
  -- Eventos/constantes útiles
  "MAX_PLAYER_LEVEL", "NUM_BAG_SLOTS", "BACKPACK_CONTAINER", "BANK_CONTAINER", "INVSLOT_FIRST_EQUIPPED",
  "INVSLOT_LAST_EQUIPPED", "LE_PARTY_CATEGORY_HOME", "ERR_QUEST_ACCEPTED_S", "ERR_QUEST_COMPLETE_S",
  "YES", "NO", "OKAY", "CANCEL", "ACCEPT", "CLOSE", "NONE", "UNKNOWN", "LEVEL", "LOCALIZED_CLASS_NAMES_MALE",
  "LOCALIZED_CLASS_NAMES_FEMALE", "CLASS_ICON_TCOORDS",
  -- Otros addons opcionales
  "Questie", "QuestieLoader", "TomTom", "LibStub",
}
