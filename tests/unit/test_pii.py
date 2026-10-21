from book_review_api.rag.pii import luhn_valid, mask_pii


def test_masks_email_phone_card() -> None:
    r = mask_pii(
        "Mail a.b+c@example.com, ĐT 0912 345 678 và +84 912.345.678, thẻ 4111-1111-1111-1111."
    )
    assert r.text == "Mail [EMAIL], ĐT [PHONE] và [PHONE], thẻ [CARD]."
    assert (r.emails, r.phones, r.cards, r.total) == (1, 2, 1, 4)


def test_keeps_non_card_digit_runs() -> None:
    # 16 chữ số nhưng sai Luhn, và năm/số lượng thông thường không bị che.
    text = "Mã đơn 1234567890123456 xuất bản năm 1936, bán 1.000.000 bản."
    assert mask_pii(text).text == text


def test_luhn() -> None:
    assert luhn_valid("4111111111111111")
    assert not luhn_valid("4111111111111112")
