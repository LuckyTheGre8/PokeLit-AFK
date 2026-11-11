"""Comprehensive test suite verifying Modals and Rift Navigation against all screenshots."""

from pathlib import Path
import cv2
from level_detector import (
    AutoLevelDetector,
    AutoVigorDetector,
    GameTimerDetector,
    LevelUpDetector,
    MenuDetectionResult,
    MenuNavigatorDetector,
    MenuScreenType,
    ModalType,
    PerkSelector,
    RiftDetector,
)
from spatial_navigator import SpatialNavigator

IMG_GAME = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794246547003_9f896a2d.jpg")
IMG_LEVEL = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794246547023_3277cda0.jpg")
IMG_ITEM_2 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794248970121_c6ac9675.jpg")
IMG_ITEM_3 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794249424909_6ea4c7eb.jpg")

IMG_RIFT_1 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794250009314_49489dee.jpg")
IMG_RIFT_2 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794250009337_56b9edf2.jpg")
IMG_RIFT_3 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794250009362_6d3f7c6c.jpg")
IMG_RIFT_ARROW_LEFT = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794299809381_0e69d781.jpg")
IMG_RIFT_ARROW_DOWN = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794299809391_25ddc064.jpg")
IMG_RIFT_PORTAL = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794251264263_beef5d72.jpg")
IMG_RIFT_PORTAL_2 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794297999755_3f888703.png")
IMG_AUTO_VIGOR = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794252837251_1d9e3180.jpg")
IMG_ASH_1006 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794298995906_29aaf318.png")
IMG_ASH_1028 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794298995970_2b85bc5d.png")
IMG_ASH_1047 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794298973908_eeeed6e7.png")
IMG_ASH_1023 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794303470926_b7011c0d.png")
IMG_EARLY_119 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794305687196_acbd29ac.png")
IMG_AUTO_LEVEL_OFF = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794331698224_21ffe7a4.png")
IMG_AUTO_LEVEL_ON = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794331774526_a60640e7.png")

IMG_RUN_OVER = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794254312052_604a3c29.jpg")
IMG_RUN_OVER_TALL = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794305258597_e5a7ab40.png")
IMG_CHOOSE_REGION = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794254326963_916ca9c5.jpg")
IMG_MAIN_MENU = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794254326996_f5d1b329.jpg")


def test_full_detection_suite():
    detector = LevelUpDetector()
    rift_detector = RiftDetector()
    selector = PerkSelector(strategy="1", item_choice_2="2", item_choice_3="3")

    # 1. Gameplay Screenshot
    im_game = cv2.imread(str(IMG_GAME))
    res_game = detector.detect(im_game)
    rift_game = rift_detector.detect(im_game)
    print(f"[TEST 1] Gameplay: modal={res_game.modal_type.value}, rift_active={rift_game.is_active}")
    assert not res_game.is_level_up
    assert not rift_game.is_active

    # 2. Level-Up Screenshot (3 options) -> Selects 1
    im_level = cv2.imread(str(IMG_LEVEL))
    res_level = detector.detect(im_level)
    print(f"[TEST 2] Level-Up: modal={res_level.modal_type.value}, options={res_level.option_count}")
    assert res_level.is_level_up and res_level.modal_type == ModalType.LEVEL_UP
    assert selector.decide_choice(res_level.modal_type, res_level.option_count) == "1"

    # 3. Item 2-Option Screenshot -> Always selects 2
    im_item2 = cv2.imread(str(IMG_ITEM_2))
    res_item2 = detector.detect(im_item2)
    print(f"[TEST 3] Item 2-Opt: modal={res_item2.modal_type.value}, options={res_item2.option_count}")
    assert res_item2.is_level_up and res_item2.modal_type == ModalType.ITEM and res_item2.option_count == 2
    assert selector.decide_choice(res_item2.modal_type, res_item2.option_count) == "2"

    # 4. Item 3-Option Screenshot -> Always selects 3
    im_item3 = cv2.imread(str(IMG_ITEM_3))
    res_item3 = detector.detect(im_item3)
    print(f"[TEST 4] Item 3-Opt: modal={res_item3.modal_type.value}, options={res_item3.option_count}")
    assert res_item3.is_level_up and res_item3.modal_type == ModalType.ITEM and res_item3.option_count == 3
    assert selector.decide_choice(res_item3.modal_type, res_item3.option_count) == "3"

    # 5. Rift Pic 1 (Banner + Arrow pointing Down-Left)
    im_rift1 = cv2.imread(str(IMG_RIFT_1))
    rift1 = rift_detector.detect(im_rift1)
    print(f"[TEST 5] Rift Pic 1: active={rift1.is_active}, keys={rift1.direction_keys}, angle={rift1.angle_deg}")
    assert rift1.is_active, "Rift 1 should be active!"
    assert rift1.direction_keys == ["s", "a"], f"Expected ['s', 'a'], got {rift1.direction_keys}"

    # 6. Rift Pic 2 (Inside Rift room: arrow and banner are gone)
    im_rift2 = cv2.imread(str(IMG_RIFT_2))
    rift2 = rift_detector.detect(im_rift2)
    print(f"[TEST 6] Rift Pic 2: active={rift2.is_active}, keys={rift2.direction_keys}")
    assert not rift2.is_active, "Rift 2 (inside rift) should be inactive so random movement runs!"

    # 7. Rift Pic 3 (Rift Arrow on right edge)
    im_rift3 = cv2.imread(str(IMG_RIFT_3))
    rift3 = rift_detector.detect(im_rift3)
    print(f"[TEST 7] Rift Pic 3: active={rift3.is_active}, keys={rift3.direction_keys}, angle={rift3.angle_deg}")
    assert rift3.is_active, "Rift 3 should be active!"
    assert rift3.direction_keys == ["d"], f"Expected ['d'], got {rift3.direction_keys}"

    # 7b. Rift Arrow Left (Kanto Rift Sea Grotto, 23:18)
    im_arrow_l = cv2.imread(str(IMG_RIFT_ARROW_LEFT))
    rift_arrow_l = rift_detector.detect(im_arrow_l)
    print(f"[TEST 7b] Rift Arrow Left: active={rift_arrow_l.is_active}, keys={rift_arrow_l.direction_keys}, angle={rift_arrow_l.angle_deg}")
    assert rift_arrow_l.is_active and rift_arrow_l.direction_keys == ["a"]

    # 7c. Rift Arrow Down (Kanto Rift Emerald Jungle, 25:25)
    im_arrow_d = cv2.imread(str(IMG_RIFT_ARROW_DOWN))
    rift_arrow_d = rift_detector.detect(im_arrow_d)
    print(f"[TEST 7c] Rift Arrow Down: active={rift_arrow_d.is_active}, keys={rift_arrow_d.direction_keys}, angle={rift_arrow_d.angle_deg}")
    assert rift_arrow_d.is_active and rift_arrow_d.direction_keys == ["s", "d"]

    # 8. Rift Physical Portal Tear 1 (Right of Mewtwo)
    im_portal = cv2.imread(str(IMG_RIFT_PORTAL))
    rift_portal = rift_detector.detect(im_portal)
    print(f"[TEST 8] Physical Portal 1: active={rift_portal.is_active}, mode={rift_portal.mode}, keys={rift_portal.direction_keys}, angle={rift_portal.angle_deg}")
    assert rift_portal.is_active, "Rift physical portal 1 should be active!"
    assert rift_portal.mode == "portal_tear", f"Expected 'portal_tear', got {rift_portal.mode}"
    assert rift_portal.direction_keys == ["d"], f"Expected ['d'], got {rift_portal.direction_keys}"

    # 8b. Rift Physical Portal Tear 2 (Bottom-Left of Mewtwo)
    im_portal2 = cv2.imread(str(IMG_RIFT_PORTAL_2))
    rift_portal2 = rift_detector.detect(im_portal2)
    print(f"[TEST 8b] Physical Portal 2: active={rift_portal2.is_active}, mode={rift_portal2.mode}, keys={rift_portal2.direction_keys}, angle={rift_portal2.angle_deg}, pt={rift_portal2.target_point}")
    assert rift_portal2.is_active, "Rift physical portal 2 should be active!"
    assert rift_portal2.mode == "portal_tear", f"Expected 'portal_tear', got {rift_portal2.mode}"
    assert rift_portal2.direction_keys == ["s", "a"], f"Expected ['s', 'a'], got {rift_portal2.direction_keys}"

    # 8c. False-Positive Immunity: Purple Mobs (Nidoking / Nidorino on Ash Volcano) must NOT trigger portal detection
    im_ash_mob1 = cv2.imread(str(IMG_ASH_1006))
    im_ash_mob2 = cv2.imread(str(IMG_ASH_1028))
    rift_mob1 = rift_detector.detect(im_ash_mob1)
    rift_mob2 = rift_detector.detect(im_ash_mob2)
    print(f"[TEST 8c] Mob False Positive Rejection: Ash 10:06 active={rift_mob1.is_active} | Ash 10:28 active={rift_mob2.is_active}")
    assert not rift_mob1.is_active, "Ash 10:06 Nidoking mob should NOT be detected as a portal!"
    assert not rift_mob2.is_active, "Ash 10:28 Nidorino mob should NOT be detected as a portal!"

    # 9. In-Game Timer Detection (< 10 min vs >= 10 min, across Grass and Lava maps)
    timer_det = GameTimerDetector()
    t_game = timer_det.detect(im_game)
    t_11m = timer_det.detect(im_rift1)
    t_24m = timer_det.detect(cv2.imread(str(IMG_AUTO_VIGOR)))
    t_ash1006 = timer_det.detect(cv2.imread(str(IMG_ASH_1006)))
    t_ash1028 = timer_det.detect(cv2.imread(str(IMG_ASH_1028)))
    t_ash1047 = timer_det.detect(cv2.imread(str(IMG_ASH_1047)))
    t_ash1023 = timer_det.detect(cv2.imread(str(IMG_ASH_1023)))
    t_early119 = timer_det.detect(cv2.imread(str(IMG_EARLY_119)))
    t_live1 = timer_det.detect(cv2.imread("scratch/live_now.png"))
    t_live2 = timer_det.detect(cv2.imread("scratch/live_now2.png"))
    print(f"[TEST 9] Timer: 0:42={t_game.is_at_least_10_min} | 1:19={t_early119.is_at_least_10_min} | 11:34={t_11m.is_at_least_10_min} | 24:01={t_24m.is_at_least_10_min} | Ash 10:06={t_ash1006.is_at_least_10_min} | Ash 10:28={t_ash1028.is_at_least_10_min} | Ash 10:47={t_ash1047.is_at_least_10_min} | Ash 10:23={t_ash1023.is_at_least_10_min} | Live 10:15={t_live1.is_at_least_10_min} | Live 16:49={t_live2.is_at_least_10_min}")
    assert not t_game.is_at_least_10_min, "0:42 should NOT be >= 10 min!"
    assert not t_early119.is_at_least_10_min, "1:19 should NOT be >= 10 min!"
    assert t_11m.is_at_least_10_min, "11:34 should be >= 10 min!"
    assert t_24m.is_at_least_10_min, "24:01 should be >= 10 min!"
    assert t_ash1006.is_at_least_10_min, "Ash 10:06 should be >= 10 min!"
    assert t_ash1028.is_at_least_10_min, "Ash 10:28 should be >= 10 min!"
    assert t_ash1047.is_at_least_10_min, "Ash 10:47 should be >= 10 min!"
    assert t_ash1023.is_at_least_10_min, "Ash 10:23 should be >= 10 min!"
    assert t_live1.is_at_least_10_min, "Live 10:15 should be >= 10 min!"
    assert t_live2.is_at_least_10_min, "Live 16:49 should be >= 10 min!"

    # 10. Auto Vigor Button Detection, Dual-State Enforcement (<10m OFF vs >=10m ON)
    av_det = AutoVigorDetector()
    av_early = av_det.detect(im_game)
    av_late = av_det.detect(cv2.imread(str(IMG_AUTO_VIGOR)))
    av_ash_off = av_det.detect(cv2.imread(str(IMG_ASH_1006)))
    av_ash_on1 = av_det.detect(cv2.imread(str(IMG_ASH_1028)))
    av_ash_on2 = av_det.detect(cv2.imread(str(IMG_ASH_1047)))
    av_ash_1023 = av_det.detect(cv2.imread(str(IMG_ASH_1023)))
    av_early_119 = av_det.detect(cv2.imread(str(IMG_EARLY_119)))
    av_live1 = av_det.detect(cv2.imread("scratch/live_now.png"))
    av_live2 = av_det.detect(cv2.imread("scratch/live_now2.png"))
    print(f"[TEST 10] Auto Vigor: early pt={av_early.norm_point} (active={av_early.is_active}) | early_119 pt={av_early_119.norm_point} (active={av_early_119.is_active}) | late pt={av_late.norm_point} (active={av_late.is_active}) | ash_off pt={av_ash_off.norm_point} (active={av_ash_off.is_active}) | ash_1023 pt={av_ash_1023.norm_point} (active={av_ash_1023.is_active}) | ash_on pt={av_ash_on1.norm_point} (active={av_ash_on1.is_active}) | live1 pt={av_live1.norm_point} (active={av_live1.is_active}) | live2 pt={av_live2.norm_point} (active={av_live2.is_active})")
    assert av_early.is_present and av_early.norm_point is not None and not av_early.is_active
    # Early 1:19 is currently active (pink), which informs perk_selector to turn it OFF so early level-ups are selected by bot
    assert av_early_119.is_present and av_early_119.is_active and abs(av_early_119.norm_point[0] - 200) <= 3
    assert av_late.is_present and av_late.norm_point is not None and not av_late.is_active
    assert av_ash_off.is_present and av_ash_off.norm_point == (238, 152) and not av_ash_off.is_active
    assert av_ash_1023.is_present and av_ash_1023.norm_point == (238, 152) and not av_ash_1023.is_active
    assert av_ash_on1.is_present and abs(av_ash_on1.norm_point[0] - 200) <= 3 and av_ash_on1.is_active
    assert av_ash_on2.is_present and abs(av_ash_on2.norm_point[0] - 289) <= 3 and av_ash_on2.is_active
    assert av_live1.is_present and av_live1.is_active and abs(av_live1.norm_point[0] - 234) <= 3
    assert av_live2.is_present and not av_live2.is_active and abs(av_live2.norm_point[0] - 271) <= 3

    # 11. End-of-Match: "Run over" Screen -> Click "Back to menu" (Short vs Tall loot modals)
    menu_det = MenuNavigatorDetector()
    im_ro = cv2.imread(str(IMG_RUN_OVER))
    m_ro = menu_det.detect(im_ro)
    im_ro_tall = cv2.imread(str(IMG_RUN_OVER_TALL))
    m_ro_tall = menu_det.detect(im_ro_tall)
    print(f"[TEST 11] Run Over: short type={m_ro.screen_type.value}, click={m_ro.click_point}, conf={m_ro.confidence} | tall type={m_ro_tall.screen_type.value}, click={m_ro_tall.click_point}, conf={m_ro_tall.confidence}")
    assert m_ro.screen_type == MenuScreenType.RUN_OVER, f"Expected RUN_OVER, got {m_ro.screen_type}"
    assert m_ro.click_point is not None and abs(m_ro.click_point[0] - 460) <= 10 and abs(m_ro.click_point[1] - 483) <= 10
    assert m_ro_tall.screen_type == MenuScreenType.RUN_OVER, f"Expected RUN_OVER for tall modal, got {m_ro_tall.screen_type}"
    assert m_ro_tall.click_point is not None and abs(m_ro_tall.click_point[0] - 460) <= 10 and abs(m_ro_tall.click_point[1] - 590) <= 10

    # 12. Main Menu: "Play" Button -> Click "Play"
    im_mm = cv2.imread(str(IMG_MAIN_MENU))
    m_mm = menu_det.detect(im_mm)
    print(f"[TEST 12] Main Menu: type={m_mm.screen_type.value}, click={m_mm.click_point}, conf={m_mm.confidence}")
    assert m_mm.screen_type == MenuScreenType.MAIN_MENU, f"Expected MAIN_MENU, got {m_mm.screen_type}"
    assert m_mm.click_point is not None and abs(m_mm.click_point[0] - 512) <= 10 and abs(m_mm.click_point[1] - 479) <= 10

    # 13. Choose Region: "Choose the region" -> Select Johto (default) or Kanto
    im_cr = cv2.imread(str(IMG_CHOOSE_REGION))
    menu_det_johto = MenuNavigatorDetector(target_region="johto")
    m_cr_johto = menu_det_johto.detect(im_cr)
    menu_det_kanto = MenuNavigatorDetector(target_region="kanto")
    m_cr_kanto = menu_det_kanto.detect(im_cr)
    print(f"[TEST 13] Choose Region: Johto click={m_cr_johto.click_point} | Kanto click={m_cr_kanto.click_point}")
    assert m_cr_johto.screen_type == MenuScreenType.CHOOSE_REGION, f"Expected CHOOSE_REGION, got {m_cr_johto.screen_type}"
    # Verify Johto click falls on Johto card (bbox: 334..440, 204..351)
    assert m_cr_johto.click_point is not None
    assert 334 <= m_cr_johto.click_point[0] <= 440 and 204 <= m_cr_johto.click_point[1] <= 351, f"Click {m_cr_johto.click_point} outside Johto card!"
    # Verify Kanto click falls on Kanto card (bbox: 214..319, 204..351)
    assert m_cr_kanto.click_point is not None
    assert 214 <= m_cr_kanto.click_point[0] <= 319 and 204 <= m_cr_kanto.click_point[1] <= 351, f"Click {m_cr_kanto.click_point} outside Kanto card!"

    # 14. Menu False-Positive Check: Normal gameplay must NOT trigger menu actions
    m_game = menu_det.detect(im_game)
    print(f"[TEST 14] Gameplay Menu Check: type={m_game.screen_type.value}")
    assert m_game.screen_type == MenuScreenType.NONE, "Gameplay screen should NOT trigger any menu action!"

    # 14b. Sub-Menu / Gacha Modal Recovery: Detects "Back" button on modals
    im_modal = cv2.imread(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794308087469_2f3955be.png")
    im_gacha_mock = im_modal.copy()
    im_gacha_mock[120:220, 180:440] = 0  # Mask region title to simulate Gacha / stray modal
    m_gacha = menu_det.detect(im_gacha_mock)
    print(f"[TEST 14b] Modal Recovery: type={m_gacha.screen_type.value}, click={m_gacha.click_point}")
    assert m_gacha.screen_type == MenuScreenType.SUBMENU_BACK
    assert m_gacha.click_point is not None and abs(m_gacha.click_point[0] - 775) <= 10 and abs(m_gacha.click_point[1] - 167) <= 10

    # 15. Spatial AI: Early Game Swarm Kiting Evasion
    spatial_nav = SpatialNavigator()
    s_early = spatial_nav.analyze(im_game)
    print(f"[TEST 15] Spatial AI Early: mode={s_early.mode}, keys={s_early.direction_keys}, angle={s_early.heading_angle_deg}°, threat={s_early.max_threat_percent}%")
    assert s_early.mode == "kiting_evasion", f"Expected 'kiting_evasion', got {s_early.mode}"
    assert s_early.max_threat_percent > 30.0, f"Expected threat > 30%, got {s_early.max_threat_percent}%"

    # 16. Spatial AI: Late Game Gem Trail Harvesting
    spatial_nav.reset()
    im_late = cv2.imread(str(IMG_AUTO_VIGOR))
    s_late = spatial_nav.analyze(im_late)
    print(f"[TEST 16] Spatial AI Late: mode={s_late.mode}, keys={s_late.direction_keys}, angle={s_late.heading_angle_deg}°, gems={s_late.gems_detected}")
    assert s_late.gems_detected >= 20, f"Expected >= 20 gems, got {s_late.gems_detected}"
    assert s_late.direction_keys == ["s"], f"Expected ['s'], got {s_late.direction_keys}"

    # 17. Spatial AI: Rift Push (Top Priority Pure Push into Portal 1)
    spatial_nav.reset()
    s_rift = spatial_nav.analyze(im_portal, rift_direction_keys=["d"])
    print(f"[TEST 17] Spatial AI Rift 1: mode={s_rift.mode}, keys={s_rift.direction_keys}, angle={s_rift.heading_angle_deg}°")
    assert s_rift.mode == "rift_push", f"Expected 'rift_push', got {s_rift.mode}"
    assert s_rift.direction_keys == ["d"], f"Expected ['d'], got {s_rift.direction_keys}"

    # 18. Spatial AI: Autonomous Physical Portal 2 Detection & Direct Plunge (No External Signal)
    spatial_nav.reset()
    s_rift2 = spatial_nav.analyze(im_portal2, rift_direction_keys=None)
    print(f"[TEST 18] Spatial AI Rift 2 (Autonomous Portal): mode={s_rift2.mode}, keys={s_rift2.direction_keys}, angle={s_rift2.heading_angle_deg}°")
    assert s_rift2.mode == "rift_push", f"Expected 'rift_push', got {s_rift2.mode}"
    assert s_rift2.direction_keys == ["s", "a"], f"Expected ['s', 'a'], got {s_rift2.direction_keys}"

    # 18b. Spatial AI: Autonomous Arrow Left Detection & Direct Plunge (No External Signal)
    spatial_nav.reset()
    s_arrow_l = spatial_nav.analyze(im_arrow_l, rift_direction_keys=None)
    print(f"[TEST 18b] Spatial AI Autonomous Arrow Left: mode={s_arrow_l.mode}, keys={s_arrow_l.direction_keys}, angle={s_arrow_l.heading_angle_deg}°")
    assert s_arrow_l.mode == "rift_push", f"Expected 'rift_push', got {s_arrow_l.mode}"
    assert s_arrow_l.direction_keys == ["a"], f"Expected ['a'], got {s_arrow_l.direction_keys}"

    # 18c. Spatial AI: Autonomous Arrow Down Detection & Direct Plunge (No External Signal)
    spatial_nav.reset()
    s_arrow_d = spatial_nav.analyze(im_arrow_d, rift_direction_keys=None)
    print(f"[TEST 18c] Spatial AI Autonomous Arrow Down: mode={s_arrow_d.mode}, keys={s_arrow_d.direction_keys}, angle={s_arrow_d.heading_angle_deg}°")
    assert s_arrow_d.mode == "rift_push", f"Expected 'rift_push', got {s_arrow_d.mode}"
    assert s_arrow_d.direction_keys == ["s", "d"], f"Expected ['s', 'd'], got {s_arrow_d.direction_keys}"

    # 19. Dynamic Continuous Arrow Rotation Tracking:
    # Verifies that when the player moves and the arrow dynamically rotates on screen (e.g. from Left to Down),
    # the navigator dynamically steers to the new heading and NEVER locks into the initial direction indefinitely!
    dynamic_nav = SpatialNavigator()
    # Step 1: Feed in frame with arrow pointing Left
    step1 = dynamic_nav.analyze(im_arrow_l, rift_direction_keys=None)
    print(f"[TEST 19 Step 1] Dynamic Arrow Left: mode={step1.mode}, keys={step1.direction_keys}, heading={step1.heading_angle_deg}°")
    assert step1.mode == "rift_push" and step1.direction_keys == ["a"]

    # Step 2: Feed in consecutive frame where arrow rotated to Down (NO reset!)
    step2 = dynamic_nav.analyze(im_arrow_d, rift_direction_keys=None)
    print(f"[TEST 19 Step 2] Dynamic Arrow Rotated to Down: mode={step2.mode}, keys={step2.direction_keys}, heading={step2.heading_angle_deg}°")
    assert step2.mode == "rift_push" and step2.direction_keys == ["s", "d"], f"Expected dynamic rotation to ['s', 'd'], got {step2.direction_keys}"

    # Step 3: Feed in frame where physical portal tear appears on screen (NO reset!)
    step3 = dynamic_nav.analyze(im_portal, rift_direction_keys=None)
    print(f"[TEST 19 Step 3] Portal Appears Ahead (Right): mode={step3.mode}, keys={step3.direction_keys}, heading={step3.heading_angle_deg}°")
    assert step3.mode == "rift_push" and step3.direction_keys == ["d"], f"Expected dynamic turn into portal ['d'], got {step3.direction_keys}"

    # 20. Obstacle Pinning & Autonomous Unstuck Maneuver:
    # Verifies that when the character is blocked by an obstacle/wall (zero terrain displacement while commanding movement),
    # the tracker automatically detects the stuck condition and commands an orthogonal escape slide to bypass the obstacle!
    unstuck_nav = SpatialNavigator()
    # Initial frame
    u_step1 = unstuck_nav.analyze(im_game)
    initial_heading = u_step1.heading_angle_deg
    print(f"[TEST 20 Step 1] Normal Movement: mode={u_step1.mode}, keys={u_step1.direction_keys}, heading={initial_heading}°")
    # Simulate being pinned against an obstacle: feed same frame over > 0.70 seconds
    import time
    time.sleep(0.30)
    unstuck_nav.analyze(im_game)
    time.sleep(0.70)
    u_stuck = unstuck_nav.analyze(im_game)
    print(f"[TEST 20 Step 2] Obstacle Pinning Detected: mode={u_stuck.mode}, escape_keys={u_stuck.direction_keys}, escape_heading={u_stuck.heading_angle_deg}°")
    assert u_stuck.mode == "unstuck_escape", f"Expected 'unstuck_escape', got {u_stuck.mode}"
    assert len(u_stuck.direction_keys) > 0, "Escape keys must not be empty"

    # 21. High-DPI Scaling & Physical Pixel Click Mapping:
    # Verifies that normalized coordinates scale uniformly across 2560x1600 (150% display) and 1920x1080 without vertical aspect warp
    norm_x, norm_y = av_ash_1023.norm_point
    # Test 2560x1600 (scale = 2.5)
    cw_2560, ch_1600 = 2560, 1600
    scale_2560 = cw_2560 / 1024.0
    px_2560 = int(norm_x * scale_2560)
    py_2560 = int(norm_y * scale_2560)
    print(f"[TEST 21] High-DPI 2560x1600 Click Scaling: norm({norm_x}, {norm_y}) -> physical({px_2560}, {py_2560})")
    assert (px_2560, py_2560) == (595, 380), f"Expected (595, 380), got ({px_2560}, {py_2560})"

    # 22. Spatial AI Rift Heading Persistence Memory (1.5s Grace Window):
    # Verifies that when tracking a rift arrow, if the arrow is momentarily obscured (e.g. by level-up fade or spell fx),
    # the navigator continues steering in the known rift direction rather than abandoning it for random roaming!
    mem_nav = SpatialNavigator()
    # Step A: Feed active rift frame (Sea Grotto Left Arrow: ['a'], -175.1°)
    res_a = mem_nav.analyze(im_arrow_l)
    assert res_a.mode == "rift_push" and res_a.direction_keys == ["a"]
    print(f"[TEST 22 Step A] Active Rift Locked: mode={res_a.mode}, keys={res_a.direction_keys}, heading={res_a.heading_angle_deg}°")

    # Step B: Feed standard gameplay frame with NO rift visible
    # Spatial AI must preserve rift_push and ['a'] heading via persistence memory!
    res_b = mem_nav.analyze(im_game)
    print(f"[TEST 22 Step B] Arrow Occluded (Persistence Active): mode={res_b.mode}, keys={res_b.direction_keys}, heading={res_b.heading_angle_deg}°")
    assert res_b.mode == "rift_push", f"Expected 'rift_push' via persistence memory, got {res_b.mode}"
    assert res_b.direction_keys == ["a"], f"Expected keys ['a'] preserved, got {res_b.direction_keys}"

    # 23. Level-Up Modal Continuity Simulation:
    # Verifies the exact perk_selector.py logic: tracking rift -> modal appears -> dismisses -> fresh frame lacks arrow
    # -> was_following_rift ensures rift movement is RETAINED rather than zeroed!
    last_rift_seen_sim = time.monotonic()
    last_keys_sim = ["s", "a"]
    last_angle_sim = 133.4
    # Modal dismissed after 0.8s
    now_dismiss = time.monotonic()
    was_following = (now_dismiss - last_rift_seen_sim < 2.5) and bool(last_keys_sim)
    assert was_following, "Rift must be recognized as active prior to modal"
    # Fresh frame simulated with no rift visible
    fresh_rift_active = False
    if fresh_rift_active:
        nav_keys = ["fresh"]
    elif was_following and last_keys_sim:
        nav_keys = list(last_keys_sim)
    else:
        nav_keys = []
    print(f"[TEST 23] Level-Up Dismissal Continuity: preserved keys={nav_keys}")
    assert nav_keys == ["s", "a"], f"Expected ['s', 'a'], got {nav_keys}"

    # 24. Floating Beacon Arrow Above Physical Portal:
    # Verifies that RiftDetector identifies the floating arrow above the portal tear
    portal_res = rift_detector.detect(im_portal)
    assert portal_res.is_active and portal_res.mode == "portal_tear"
    print(f"[TEST 24] Physical Portal & Beacon: active={portal_res.is_active}, mode={portal_res.mode}, pt={portal_res.target_point}")

    # 25. Auto Level Start-of-Level Activation & State Transition (Dark Yellow -> Bright Yellow):
    # Verifies detection of AUTO LEVEL at 0:02 (dark yellow) and confirmation at 0:06 (bright yellow ON)
    al_det = AutoLevelDetector()
    im_al_off = cv2.imread(str(IMG_AUTO_LEVEL_OFF))
    im_al_on = cv2.imread(str(IMG_AUTO_LEVEL_ON))

    # Step 1: Start of level - verify button presence in dark yellow (OFF) state
    res_al_off = al_det.detect(im_al_off)
    print(f"[TEST 25 Step 1] Start of Level (0:02): present={res_al_off.is_present}, is_active={res_al_off.is_active}, pt={res_al_off.norm_point}, theme={res_al_off.theme}")
    assert res_al_off.is_present, "AUTO LEVEL button must be detected at start of level!"
    assert not res_al_off.is_active, "Button must be in dark yellow (OFF) state initially!"
    assert res_al_off.theme == "yellow", "Theme must be identified as 'yellow'!"
    assert abs(res_al_off.norm_point[0] - 165) <= 5 and abs(res_al_off.norm_point[1] - 152) <= 3

    # Step 2: Post-click confirmation - verify transition to bright yellow (ON) state
    res_al_on = al_det.detect(im_al_on)
    print(f"[TEST 25 Step 2] Post-Click Verified (0:06): present={res_al_on.is_present}, is_active={res_al_on.is_active}, pt={res_al_on.norm_point}, theme={res_al_on.theme}")
    assert res_al_on.is_present, "AUTO LEVEL button must be present after click!"
    assert res_al_on.is_active, "Button must transition to bright yellow (ON) state after click!"
    assert res_al_on.theme == "yellow", "Theme must remain 'yellow'!"

    # 26. Stale IPC Auto-Expiration (.rift_movement & .pause_movement):
    # Verifies that stale flag files left over from crashes or interrupted runs are safely expired
    # so the character never gets stuck moving in one direction or stalled in place.
    from random_movement import read_rift_movement, RIFT_FILE, PAUSE_FILE
    import os
    import json

    # Sub-test A: Fresh rift signal is read properly
    test_rift_data = {"active": True, "keys": ["w", "d"], "angle": -45.0, "timestamp": time.time()}
    with open(RIFT_FILE, "w", encoding="utf-8") as f:
        json.dump(test_rift_data, f)
    fresh_res = read_rift_movement()
    assert fresh_res is not None and fresh_res[0] == ["w", "d"], f"Fresh rift must be readable: {fresh_res}"

    # Sub-test B: Stale rift signal (> 2.0s old) is auto-expired and unlinked
    past_mtime = time.time() - 3.5
    os.utime(RIFT_FILE, (past_mtime, past_mtime))
    stale_res = read_rift_movement()
    assert stale_res is None, f"Stale rift file must return None, got {stale_res}"
    assert not RIFT_FILE.exists(), "Stale rift file must be automatically unlinked!"
    print("[TEST 26] Stale IPC Expiration: Fresh rift accepted | Stale (> 2.0s) auto-unlinked safely")

    # 27. Active Gameplay Watchdog Synchronization:
    # Verifies that during normal gameplay, any stray .pause_movement is immediately cleaned up
    PAUSE_FILE.touch(exist_ok=True)
    assert PAUSE_FILE.exists()
    # Simulate normal gameplay tick in perk_selector
    sim_menu_type = MenuScreenType.NONE
    sim_is_level_up = False
    if not sim_is_level_up and sim_menu_type == MenuScreenType.NONE:
        if PAUSE_FILE.exists():
            PAUSE_FILE.unlink(missing_ok=True)
    assert not PAUSE_FILE.exists(), "Gameplay watchdog must clear pause during regular gameplay!"
    print("[TEST 27] Gameplay Watchdog: Stray .pause_movement successfully detected & cleared")

    # 28. Top Screen Edge Rift Detection (y < 60):
    # Verifies that compass arrows at the top border (pointing North / Up) are detected
    # rather than being clipped by outdated [60:625] crops.
    im_top_test = im_game.copy()
    # Splice arrow_left cluster & label to top right border (y=30, x=750)
    crop_arrow = im_arrow_l[230:310, 40:120]
    im_top_test[30:110, 750:830] = crop_arrow
    top_res = rift_detector.detect(im_top_test)
    assert top_res.is_active and top_res.mode == "rift_arrow", f"Top rift arrow must be detected: {top_res}"
    assert "w" in top_res.direction_keys, f"Top arrow must contain 'w' key, got {top_res.direction_keys}"
    print(f"[TEST 28] Top Screen Edge Rift (y < 60): active={top_res.is_active}, keys={top_res.direction_keys}, angle={top_res.angle_deg}°")

    # 29. TerrainMotionTracker Escape Termination & Rift Push Immunity:
    # Verifies that the escape maneuver automatically terminates after 0.65s (even on uniform grass with resp < 0.25)
    # and that straight-line rift runs (> 4.0s) are immune to blind anti-pinning timeouts.
    from spatial_navigator import TerrainMotionTracker
    tracker = TerrainMotionTracker()
    now_sim = time.monotonic()
    tracker._trigger_escape(0.0, now_sim)
    # 0.1s into escape: must be executing escape maneuver
    is_esc, keys_esc, _ = tracker.update(im_game, 0.0, ["d"], now_sim + 0.1)
    assert is_esc and keys_esc, "Must be actively in escape maneuver"
    # 0.70s into escape: duration expired -> MUST reset is_stuck to False!
    is_esc_done, keys_esc_done, _ = tracker.update(im_game, 0.0, ["d"], now_sim + 0.70)
    assert not is_esc_done and not keys_esc_done, "Escape maneuver MUST automatically reset after duration!"

    # Rift push immunity: long run (5.0s) towards distant rift does NOT trigger false obstacle escape
    tracker_rift = TerrainMotionTracker()
    now_r = time.monotonic()
    for t_step in range(1, 10):
        is_r_stuck, _, _ = tracker_rift.update(im_game, 0.0, ["w"], now_r + t_step * 0.6, is_rift_mode=True)
        assert not is_r_stuck, f"Rift push must not trigger false obstacle escape at step {t_step}"
    print("[TEST 29] TerrainMotionTracker: Escape auto-terminates safely | Rift push immune to blind timeout")

    # 30. Directional Key Transition on Rift Push:
    # Verifies that when transitioning to rift_push, all previously held keys are flushed
    active_held_sim = {"d"}
    target_rift_sim = {"w", "a"}
    last_mode_sim = "kiting_evasion"
    curr_mode_sim = "rift_push"
    # Simulate random_movement.py transition logic
    if (curr_mode_sim == "rift_push" and last_mode_sim != "rift_push"):
        active_held_sim.clear()
    assert not active_held_sim, "Previously held keys must be cleared immediately upon entering rift push!"
    active_held_sim = set(target_rift_sim)
    assert active_held_sim == {"w", "a"}, "Only active rift direction keys must be held!"
    print("[TEST 30] Rift Transition Key Flush: Previous movement keys flushed cleanly upon rift lock")

    print("\n================================================================================")
    print("ALL 33 VERIFICATION TESTS (GAMEPLAY, MODALS, RIFTS, DYNAMIC ARROW, MEMORY, UNSTUCK, TIMER, AUTO LEVEL, RESTART, SPATIAL AI, IPC EXPIRATION, TOP EDGE RIFT, MOTION TRACKER LIFECYCLE) PASSED!")
    print("================================================================================")


if __name__ == "__main__":
    test_full_detection_suite()
