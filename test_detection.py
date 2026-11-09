"""Comprehensive test suite verifying Modals and Rift Navigation against all screenshots."""

from pathlib import Path
import cv2
from level_detector import LevelUpDetector, ModalType, PerkSelector, RiftDetector

IMG_GAME = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794246547003_9f896a2d.jpg")
IMG_LEVEL = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794246547023_3277cda0.jpg")
IMG_ITEM_2 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794248970121_c6ac9675.jpg")
IMG_ITEM_3 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794249424909_6ea4c7eb.jpg")

IMG_RIFT_1 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794250009314_49489dee.jpg")
IMG_RIFT_2 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794250009337_56b9edf2.jpg")
IMG_RIFT_3 = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794250009362_6d3f7c6c.jpg")
IMG_RIFT_PORTAL = Path(r"C:/Users/lucky/.gemini/antigravity/brain/f3fa9a92-8159-463b-9fc8-fe253c1b3159/.user_uploaded/media_1794251264263_beef5d72.jpg")


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

    # 8. Rift Physical Portal Tear (On screen right next to Mewtwo)
    im_portal = cv2.imread(str(IMG_RIFT_PORTAL))
    rift_portal = rift_detector.detect(im_portal)
    print(f"[TEST 8] Physical Portal: active={rift_portal.is_active}, mode={rift_portal.mode}, keys={rift_portal.direction_keys}, angle={rift_portal.angle_deg}")
    assert rift_portal.is_active, "Rift physical portal should be active!"
    assert rift_portal.mode == "portal_tear", f"Expected 'portal_tear', got {rift_portal.mode}"
    assert rift_portal.direction_keys == ["d"], f"Expected ['d'], got {rift_portal.direction_keys}"

    print("\n================================================================================")
    print("ALL 8 VERIFICATION TESTS (GAMEPLAY, LEVEL-UP, ITEM-2, ITEM-3, RIFTS 1-4) PASSED!")
    print("================================================================================")


if __name__ == "__main__":
    test_full_detection_suite()
