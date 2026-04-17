from app.services.ocr_service import OCRService


def test_parse_blurry_invoice_keeps_unreadable_placeholder_and_metadata():
    raw_text = """16/04/2026 14:41
Blurry OCR Test
BI?men Gr??handel
R?chnung INV-20?6-00??
Datum:07.04.2026
Artikel
Menge
Gesamt
R?sen
30
36,00 EUR
[nicht lesbar]
??
iiii
Netto 67.00 EUR
MwSt 7%4,69 EUR
Brutto 71,69EUR
"""

    parsed = OCRService(provider="mock")._parse_invoice_text(raw_text)

    assert parsed["invoice_date"] == "2026-04-07"
    assert parsed["total_net"] == 67.0
    assert parsed["total_vat"] == 4.69
    assert parsed["total_gross"] == 71.69
    assert parsed["line_items"]
    assert any("nicht lesbar" in item["description"].lower() for item in parsed["line_items"])
    assert parsed["document_profile"] in {"standard-invoice", "generic-ocr"}
    assert isinstance(parsed["quality_score"], int)
    assert parsed["quality_score"] >= 0
    assert "field_confidence" in parsed
    assert "extraction_trace" in parsed


def test_parse_erpnext_image_invoice_sets_zero_vat_and_profile():
    raw_text = """Customer Name:
Vajrapu Prathyusha
Date:
15.01.2026
Payment Due Date:
15.01.2026
ACC-WRAP-CEL
1 Nos
18,00
Total
18,00
Grand Total:
18,00
"""

    parsed = OCRService(provider="mock")._parse_invoice_text(raw_text)

    assert parsed["invoice_date"] == "2026-01-15"
    assert parsed["due_date"] == "2026-01-15"
    assert parsed["total_gross"] == 18.0
    assert parsed["total_net"] == 18.0
    assert parsed["total_vat"] == 0.0
    assert parsed["vat_rate"] == 0
    assert parsed["line_items"]
    assert parsed["document_profile"] == "erpnext-print"
