"""OCR service with mock mode, optional PaddleOCR, and optional Azure hook."""

import base64
import hashlib
import importlib.util
import io
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Optional

from app.models.errors import ErrorCode, MCPError

logger = logging.getLogger(__name__)


class OCRService:
    def __init__(self, endpoint: str = "", api_key: str = "", provider: str = "mock"):
        self.endpoint = endpoint
        self.api_key = api_key
        self.provider = (provider or "mock").lower()
        self.is_mock = self.provider == "mock"

    async def extract_invoice_data(
        self,
        image_data: str,
        language: str = "de",
        vendor_id: Optional[str] = None,
    ) -> dict:
        language = (language or "auto").strip().lower()
        if self.provider == "paddle":
            return await self._paddle_extract(image_data, language)
        if self.provider == "azure" and self.endpoint and self.api_key:
            logger.warning("Azure OCR is configured, but real Azure OCR is not enabled in this local build.")
            return await self._mock_extract(image_data)
        return await self._mock_extract(image_data)

    async def _paddle_extract(self, image_data: str, language: str) -> dict:
        """Run local open-source OCR with PaddleOCR, then parse invoice fields."""
        os.environ.setdefault("FLAGS_use_onednn", "0")
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            pdf_text = self._extract_pdf_text_from_base64(image_data)
            if pdf_text and self._is_useful_pdf_text(pdf_text):
                parsed = self._parse_invoice_text(pdf_text)
                parsed["raw_text"] = pdf_text
                if parsed.get("invoice_number") or parsed.get("invoice_date"):
                    parsed["confidence_score"] = 0.9
                parsed["ocr_provider"] = "pdf-text"
                parsed["ocr_warning"] = "PaddleOCR is not installed. Used embedded PDF text instead."
                parsed["ocr_fallback_reason"] = str(exc)
                return parsed
            if not self._has_module("rapidocr_onnxruntime"):
                raise MCPError(
                    ErrorCode.AI_SERVICE_ERROR,
                    "PaddleOCR is not installed in the active Python environment. Start the server with the project venv Python.",
                    details=f"active_python={sys.executable}",
                ) from exc
            return await self._rapidocr_extract(image_data, language, f"PaddleOCR is not installed: {exc}")

        try:
            image_bytes = base64.b64decode(image_data)
        except Exception as exc:
            raise MCPError(
                ErrorCode.VALIDATION_ERROR,
                "The uploaded file could not be read. Please upload a valid image or PDF.",
                details=str(exc),
            ) from exc

        suffix = self._detect_suffix(image_bytes)
        if suffix == ".pdf":
            # Prefer embedded PDF text when available; this is usually more accurate than OCR.
            pdf_text = self._extract_text_from_pdf_bytes(image_bytes)
            if pdf_text.strip() and self._is_useful_pdf_text(pdf_text):
                parsed = self._parse_invoice_text(pdf_text)
                parsed["raw_text"] = pdf_text
                if parsed.get("invoice_number") or parsed.get("invoice_date"):
                    parsed["confidence_score"] = 0.9
                parsed["ocr_provider"] = "pdf-text"
                return parsed

            # If the PDF is scanned, render first page as image and OCR that image.
            rendered = self._render_pdf_first_page_to_png(image_bytes)
            if rendered:
                image_bytes = rendered
                suffix = ".png"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(image_bytes)
            tmp_path = Path(tmp.name)

        try:
            candidate_langs = ["german", "en"] if language == "auto" else ["german" if language == "de" else "en"]
            best_candidate: Optional[dict] = None

            for paddle_lang in candidate_langs:
                ocr = PaddleOCR(use_angle_cls=True, lang=paddle_lang)
                raw_result = self._run_paddle(ocr, str(tmp_path))
                lines = self._extract_text_lines(raw_result)
                raw_text = "\n".join(lines)

                if not raw_text.strip():
                    continue

                parsed = self._parse_invoice_text(raw_text)
                confidence = self._extract_confidence(raw_result)
                score = self._parsed_quality_score(parsed, raw_text, confidence)

                candidate = {
                    "parsed": parsed,
                    "raw_text": raw_text,
                    "confidence": confidence,
                    "score": score,
                    "language": paddle_lang,
                }
                if best_candidate is None or candidate["score"] > best_candidate["score"]:
                    best_candidate = candidate

            raw_text = "" if best_candidate is None else best_candidate["raw_text"]

            if not raw_text.strip():
                pdf_text = self._extract_pdf_text_from_base64(image_data)
                if pdf_text and self._is_useful_pdf_text(pdf_text):
                    parsed = self._parse_invoice_text(pdf_text)
                    parsed["raw_text"] = pdf_text
                    if parsed.get("invoice_number") or parsed.get("invoice_date"):
                        parsed["confidence_score"] = 0.9
                    parsed["ocr_provider"] = "pdf-text"
                    parsed["ocr_warning"] = "PaddleOCR did not return text. Used embedded PDF text instead."
                    parsed["ocr_fallback_reason"] = "PaddleOCR did not return readable text."
                    return parsed
                raise MCPError(
                    ErrorCode.AI_SERVICE_ERROR,
                    "I could not read text from this invoice. Please upload a clearer image or a text-based PDF.",
                )

            parsed = best_candidate["parsed"]
            parsed["raw_text"] = raw_text
            parsed["confidence_score"] = best_candidate["confidence"]
            parsed["ocr_provider"] = "paddle"
            parsed["detected_language"] = self._detect_language_from_text(raw_text)
            return parsed
        except MCPError:
            raise
        except Exception as exc:
            logger.exception("PaddleOCR runtime failure")
            pdf_text = self._extract_pdf_text_from_base64(image_data)
            if pdf_text and self._is_useful_pdf_text(pdf_text):
                parsed = self._parse_invoice_text(pdf_text)
                parsed["raw_text"] = pdf_text
                if parsed.get("invoice_number") or parsed.get("invoice_date"):
                    parsed["confidence_score"] = 0.9
                parsed["ocr_provider"] = "pdf-text"
                parsed["ocr_warning"] = "PaddleOCR failed at runtime. Used embedded PDF text instead."
                parsed["ocr_fallback_reason"] = str(exc)
                return parsed
            return await self._rapidocr_extract(image_data, language, f"PaddleOCR failed at runtime: {exc}")
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                logger.debug("Could not remove temporary OCR file: %s", tmp_path)

    def _extract_pdf_text_from_base64(self, image_data: str) -> str:
        try:
            image_bytes = base64.b64decode(image_data)
        except Exception as exc:
            raise MCPError(
                ErrorCode.VALIDATION_ERROR,
                "The uploaded file could not be read. Please upload a valid image or PDF.",
                details=str(exc),
            ) from exc

        suffix = self._detect_suffix(image_bytes)
        if suffix != ".pdf":
            return ""
        return self._extract_text_from_pdf_bytes(image_bytes)

    async def _rapidocr_extract(self, image_data: str, language: str, reason: str) -> dict:
        """Fallback OCR path using RapidOCR for photos and scanned PDFs."""
        try:
            image_bytes = base64.b64decode(image_data)
        except Exception as exc:
            raise MCPError(
                ErrorCode.VALIDATION_ERROR,
                "The uploaded file could not be read. Please upload a valid image or PDF.",
                details=str(exc),
            ) from exc

        suffix = self._detect_suffix(image_bytes)
        if suffix == ".pdf":
            pdf_text = self._extract_text_from_pdf_bytes(image_bytes)
            if pdf_text.strip() and self._is_useful_pdf_text(pdf_text):
                parsed = self._parse_invoice_text(pdf_text)
                parsed["raw_text"] = pdf_text
                if parsed.get("invoice_number") or parsed.get("invoice_date"):
                    parsed["confidence_score"] = 0.9
                parsed["ocr_provider"] = "pdf-text"
                parsed["ocr_warning"] = "Used embedded PDF text instead of OCR."
                parsed["ocr_fallback_reason"] = reason
                return parsed

            image_bytes = self._render_pdf_first_page_to_png(image_bytes)
            if not image_bytes:
                if not self._has_module("fitz") and not self._has_module("pypdfium2"):
                    raise MCPError(
                        ErrorCode.AI_SERVICE_ERROR,
                        "PDF OCR dependencies are missing in the active Python environment. Start the server with the project venv Python.",
                        details=f"active_python={sys.executable}",
                    )
                raise MCPError(
                    ErrorCode.AI_SERVICE_ERROR,
                    "OCR could not process this PDF. Please upload a clearer file.",
                    details=reason,
                )
            suffix = ".png"

        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise MCPError(
                ErrorCode.AI_SERVICE_ERROR,
                "A local OCR engine is unavailable. Please install RapidOCR or PaddleOCR.",
                details=str(exc),
            ) from exc

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(image_bytes)
            tmp_path = Path(tmp.name)

        try:
            ocr = RapidOCR()
            result = ocr(str(tmp_path))
            lines = self._extract_text_lines(result)
            raw_text = "\n".join(lines)

            if not raw_text.strip():
                raise MCPError(
                    ErrorCode.AI_SERVICE_ERROR,
                    "OCR could not read any text from this file. Please upload a clearer image.",
                    details=reason,
                )

            parsed = self._parse_invoice_text(raw_text)
            parsed["raw_text"] = raw_text
            parsed["confidence_score"] = self._extract_confidence(result)
            parsed["ocr_provider"] = "rapidocr"
            parsed["ocr_warning"] = "PaddleOCR was unavailable, so RapidOCR handled this invoice instead."
            parsed["ocr_fallback_reason"] = reason
            return parsed
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                logger.debug("Could not remove temporary OCR file: %s", tmp_path)

    def _extract_text_from_pdf_bytes(self, pdf_bytes: bytes) -> str:
        try:
            import fitz
        except ImportError:
            return ""

        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                texts = [page.get_text("text") for page in doc]
            return "\n".join(part.strip() for part in texts if part and part.strip())
        except Exception:
            logger.exception("Could not extract embedded text from PDF")
            return ""

    def _is_useful_pdf_text(self, text: str) -> bool:
        lower = text.lower()
        if "file:///" in lower and len(text.splitlines()) <= 6:
            return False

        token_hits = sum(
            1
            for token in ["invoice", "rechnung", "facture", "netto", "mwst", "vat", "brutto", "due", "faellig"]
            if token in lower
        )
        money_hits = len(re.findall(self._money_pattern(), text))
        return token_hits >= 1 or money_hits >= 2

    def _render_pdf_first_page_to_png(self, pdf_bytes: bytes) -> bytes:
        try:
            import fitz
        except ImportError:
            fitz = None

        if fitz is not None:
            try:
                with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                    if doc.page_count > 0:
                        pix = doc[0].get_pixmap(dpi=200)
                        return pix.tobytes("png")
            except Exception:
                logger.exception("PyMuPDF failed to render PDF first page")

        try:
            import pypdfium2 as pdfium

            doc = pdfium.PdfDocument(pdf_bytes)
            if len(doc) == 0:
                return b""
            page = doc[0]
            bitmap = page.render(scale=2.0)
            pil_image = bitmap.to_pil()
            with io.BytesIO() as buffer:
                pil_image.save(buffer, format="PNG")
                return buffer.getvalue()
        except Exception:
            logger.exception("pypdfium2 failed to render PDF first page")
            return b""

    def _run_paddle(self, ocr, file_path: str):
        """Support both PaddleOCR v2 and v3 Python APIs."""
        if hasattr(ocr, "ocr"):
            try:
                return ocr.ocr(file_path, cls=True)
            except TypeError:
                return ocr.ocr(file_path)
        if hasattr(ocr, "predict"):
            return ocr.predict(file_path)
        raise MCPError(
            ErrorCode.AI_SERVICE_ERROR,
            "PaddleOCR is installed, but the Python API is not recognized.",
        )

    def _detect_suffix(self, image_bytes: bytes) -> str:
        header = image_bytes[:32].lstrip()
        if header.startswith(b"%PDF"):
            return ".pdf"
        if image_bytes.startswith(b"\x89PNG"):
            return ".png"
        if image_bytes.startswith(b"\xff\xd8"):
            return ".jpg"
        return ".bin"

    def _extract_text_lines(self, raw_result) -> list[str]:
        lines: list[str] = []

        def visit(value):
            if value is None:
                return
            if isinstance(value, str):
                text = value.strip()
                if text:
                    lines.append(text)
                return
            if isinstance(value, dict):
                for key in ("rec_texts", "texts"):
                    if isinstance(value.get(key), list):
                        for item in value[key]:
                            visit(item)
                for key in ("text", "transcription"):
                    visit(value.get(key))
                return
            if isinstance(value, (list, tuple)):
                if len(value) >= 3 and isinstance(value[1], str):
                    visit(value[1])
                    return
                if len(value) >= 2 and isinstance(value[1], (list, tuple)) and value[1]:
                    if isinstance(value[1][0], str):
                        visit(value[1][0])
                        return
                for item in value:
                    visit(item)

        if isinstance(raw_result, list):
            for page in raw_result:
                if hasattr(page, "json"):
                    try:
                        visit(page.json)
                    except Exception:
                        visit(str(page))
                else:
                    visit(page)
        else:
            visit(raw_result)

        deduped: list[str] = []
        for line in lines:
            if line not in deduped:
                deduped.append(line)
        return deduped

    def _extract_confidence(self, raw_result) -> float:
        scores: list[float] = []

        def visit(value):
            if isinstance(value, dict):
                for key in ("rec_scores", "scores"):
                    if isinstance(value.get(key), list):
                        scores.extend(float(item) for item in value[key] if self._is_number(item))
                for item in value.values():
                    visit(item)
            elif isinstance(value, (list, tuple)):
                if len(value) >= 3 and self._is_number(value[2]):
                    scores.append(float(value[2]))
                if len(value) >= 2 and isinstance(value[1], (list, tuple)) and len(value[1]) >= 2:
                    if self._is_number(value[1][1]):
                        scores.append(float(value[1][1]))
                for item in value:
                    visit(item)

        visit(raw_result)
        if not scores:
            return 0.65
        return round(max(0.0, min(1.0, sum(scores) / len(scores))), 2)

    def _is_number(self, value) -> bool:
        try:
            float(value)
            return True
        except (TypeError, ValueError):
            return False

    def _has_module(self, module_name: str) -> bool:
        return importlib.util.find_spec(module_name) is not None

    def _parse_invoice_text(self, raw_text: str) -> dict:
        text = self._normalize_text(raw_text)
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        invoice_number = self._extract_invoice_number(text, lines)

        invoice_date_raw = self._extract_labeled_date(
            lines,
            ["datum", "date", "rechnungsdatum", "invoice date"],
        )
        if not invoice_date_raw:
            invoice_date_raw = self._first_match(
                text,
                [
                    r"(?:datum|date|rechnungsdatum)[\s:.-]*(\d{1,2}[.\/-]\d{1,2}[.\/-]\d{2,4})",
                    r"(?:datum|date|rechnungsdatum)[\s:.-]*([A-Za-z]{3,9}\s+\d{1,2},?\s*\d{4})",
                ],
            )

        due_date_raw = self._extract_labeled_date(
            lines,
            ["fallig", "faellig", "due", "payment due", "payer avant"],
        )
        if not due_date_raw:
            due_date_raw = self._first_match(
                text,
                [
                    r"(?:fallig|faellig|due|payer avant)[\w\s:.-]*(\d{1,2}[.\/-]\d{1,2}[.\/-]\d{2,4})",
                    r"(?:fallig|faellig|due|payer avant)[\w\s:.-]*([A-Za-z]{3,9}\s+\d{1,2},?\s*\d{4})",
                ],
            )

        invoice_date = self._parse_date(invoice_date_raw)
        due_date = self._parse_date(due_date_raw)
        if not due_date and invoice_date and re.search(r"payment due date", text, flags=re.IGNORECASE):
            due_date = invoice_date

        amounts = self._extract_amounts(text, lines)
        vat_rate = self._extract_vat_rate(text, amounts["total_net"], amounts["total_vat"], amounts["total_gross"])
        line_items = self._extract_line_items(lines)

        line_items = self._sanitize_line_items(line_items, amounts["total_gross"])
        invoice_number = self._clean_invoice_number(invoice_number or "")

        vendor_name = self._guess_vendor(lines)
        if self._looks_like_noise(vendor_name):
            vendor_name = ""

        if due_date and invoice_date and due_date < invoice_date:
            due_date = None

        profile = self._detect_document_profile(text, lines)
        field_confidence = self._compute_field_confidence(
            vendor_name=vendor_name,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            due_date=due_date,
            total_net=amounts["total_net"],
            total_vat=amounts["total_vat"],
            total_gross=amounts["total_gross"],
            line_items=line_items,
            raw_text=raw_text,
        )
        extraction_trace = self._build_extraction_trace(
            lines=lines,
            vendor_name=vendor_name,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            due_date=due_date,
            total_gross=amounts["total_gross"],
            first_item_desc=(line_items[0].get("description") if line_items else ""),
        )
        quality_score = self._compute_quality_score(field_confidence, amounts["total_net"], amounts["total_vat"], amounts["total_gross"], line_items)

        if not self._looks_like_invoice_document(
            text,
            invoice_number,
            invoice_date,
            amounts["total_net"],
            amounts["total_vat"],
            amounts["total_gross"],
            len(line_items),
        ):
            return {
                "vendor_name": "",
                "vendor_address": "",
                "invoice_number": "",
                "invoice_date": "",
                "due_date": None,
                "currency": self._extract_currency(raw_text),
                "total_net": 0.0,
                "total_vat": 0.0,
                "total_gross": 0.0,
                "vat_rate": None,
                "line_items": [],
                "confidence_score": 0.2,
                "quality_score": 20,
                "field_confidence": {
                    "vendor_name": 0.0,
                    "invoice_number": 0.0,
                    "invoice_date": 0.0,
                    "due_date": 0.0,
                    "totals": 0.0,
                    "line_items": 0.0,
                },
                "extraction_trace": {},
                "document_profile": profile,
                "detected_language": self._detect_language_from_text(raw_text),
                "raw_text": raw_text,
            }

        return {
            "vendor_name": vendor_name,
            "vendor_address": self._guess_address(lines),
            "invoice_number": invoice_number or "",
            "invoice_date": invoice_date or "",
            "due_date": due_date,
            "currency": self._extract_currency(raw_text),
            "total_net": amounts["total_net"],
            "total_vat": amounts["total_vat"],
            "total_gross": amounts["total_gross"],
            "vat_rate": vat_rate,
            "line_items": line_items,
            "confidence_score": 0.65,
            "quality_score": quality_score,
            "field_confidence": field_confidence,
            "extraction_trace": extraction_trace,
            "document_profile": profile,
            "detected_language": self._detect_language_from_text(raw_text),
            "raw_text": raw_text,
        }

    def _detect_document_profile(self, text: str, lines: list[str]) -> str:
        lower = text.lower()
        if "customer name" in lower and ("update billed amount in delivery note" in lower or "payment due date" in lower):
            return "erpnext-print"
        if any(token in lower for token in ["rechnung", "invoice", "facture"]) and any(token in lower for token in ["netto", "vat", "mwst", "brutto"]):
            return "standard-invoice"
        if len(lines) <= 6 and "file:///" in lower:
            return "rendered-browser-print"
        return "generic-ocr"

    def _compute_field_confidence(
        self,
        vendor_name: str,
        invoice_number: str,
        invoice_date: Optional[str],
        due_date: Optional[str],
        total_net: float,
        total_vat: float,
        total_gross: float,
        line_items: list[dict],
        raw_text: str,
    ) -> dict:
        def score_text(value: str) -> float:
            if not value:
                return 0.0
            if "?" in value:
                return 0.45
            if re.search(r"[^A-Za-z0-9À-ÖØ-öø-ÿ\s\-./]", value):
                return 0.55
            return 0.85

        totals_score = 0.2
        if total_gross > 0:
            totals_score = 0.75
            if abs((total_net + total_vat) - total_gross) <= 0.05:
                totals_score = 0.9

        item_score = 0.0
        if line_items:
            unresolved = sum(1 for item in line_items if "?" in str(item.get("description", "")))
            item_score = max(0.35, 0.85 - (0.2 * unresolved))

        return {
            "vendor_name": score_text(vendor_name),
            "invoice_number": score_text(invoice_number),
            "invoice_date": 0.9 if invoice_date else 0.0,
            "due_date": 0.85 if due_date else 0.0,
            "totals": round(totals_score, 2),
            "line_items": round(item_score, 2),
            "raw_text_density": round(min(len(raw_text) / 1200.0, 1.0), 2),
        }

    def _build_extraction_trace(
        self,
        lines: list[str],
        vendor_name: str,
        invoice_number: str,
        invoice_date: Optional[str],
        due_date: Optional[str],
        total_gross: float,
        first_item_desc: str,
    ) -> dict:
        def find_line(hint: str) -> Optional[dict]:
            if not hint:
                return None
            needle = hint.lower()
            for idx, line in enumerate(lines, start=1):
                if needle in line.lower():
                    return {"line": idx, "text": line}
            return None

        trace: dict = {}
        if vendor_name:
            trace["vendor_name"] = find_line(vendor_name)
        if invoice_number:
            trace["invoice_number"] = find_line(invoice_number)
        if invoice_date:
            trace["invoice_date"] = find_line(invoice_date.replace("-", ".")) or find_line(invoice_date)
        if due_date:
            trace["due_date"] = find_line(due_date.replace("-", ".")) or find_line(due_date)
        if total_gross > 0:
            trace["total_gross"] = find_line(str(total_gross).replace(".", ",")) or find_line(str(total_gross))
        if first_item_desc:
            trace["first_line_item"] = find_line(first_item_desc)
        return {k: v for k, v in trace.items() if v}

    def _compute_quality_score(self, field_confidence: dict, total_net: float, total_vat: float, total_gross: float, line_items: list[dict]) -> int:
        base = 0.0
        weights = {
            "vendor_name": 0.15,
            "invoice_number": 0.2,
            "invoice_date": 0.15,
            "due_date": 0.1,
            "totals": 0.25,
            "line_items": 0.15,
        }
        for key, weight in weights.items():
            base += float(field_confidence.get(key, 0.0)) * weight

        if total_gross > 0 and abs((total_net + total_vat) - total_gross) <= 0.05:
            base += 0.05
        if line_items:
            base += 0.03
        return max(0, min(100, int(round(base * 100))))

    def _parsed_quality_score(self, parsed: dict, raw_text: str, confidence: float) -> float:
        score = confidence
        if parsed.get("invoice_number") and re.search(r"\d", parsed["invoice_number"]):
            score += 0.5
        if parsed.get("invoice_date"):
            score += 0.4
        if parsed.get("total_gross", 0) > 0:
            score += 0.6
        if parsed.get("line_items"):
            score += 0.4
        score += min(len(raw_text.strip()) / 1000.0, 0.3)
        return score

    def _extract_invoice_number(self, text: str, lines: list[str]) -> str:
        candidates: list[str] = []

        patterns = [
            r"(?:rechnung(?:s)?(?:nr|nummer)?|invoice(?:\s*(?:no|number))?|facture(?:\s*no)?|bill(?:\s*no)?)\s*[:#-]?\s*([A-Z0-9][A-Z0-9_\/?.-]*\d[A-Z0-9_\/?.-]*)",
            r"\b([A-Z]{1,8}[-_/?]?\d{2,}(?:[-_/?]?\d+)*)\b",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                candidates.append(match.group(1).strip())

        for line in lines:
            if any(token in line.lower() for token in ("invoice", "rechnung", "bill", "facture", "nr")):
                for match in re.finditer(r"([A-Z0-9][A-Z0-9_\/?.-]*\d[A-Z0-9_\/?.-]*)", line, flags=re.IGNORECASE):
                    candidates.append(match.group(1).strip())

        for candidate in candidates:
            clean = self._clean_invoice_number(candidate)
            if clean:
                return clean
        return ""

    def _clean_invoice_number(self, value: str) -> str:
        cleaned = value.strip().strip("-:#. ")
        if ".html" in cleaned.lower() or "invoice_" in cleaned.lower() or cleaned.startswith("s/"):
            return ""
        upper = re.sub(r"[^A-Z0-9]", "", cleaned.upper())
        banned = {
            "RECHNUNGSNR",
            "RECHNUNGSNUMMER",
            "RECHNUNG",
            "INVOICE",
            "INVOICENO",
            "BILL",
            "NR",
            "NO",
        }
        if upper in banned:
            return ""
        if not re.search(r"\d", cleaned):
            return ""
        # Reject heavily truncated IDs like "INV-20" that come from blurry OCR corruption.
        if len(re.findall(r"\d", cleaned)) < 3:
            return ""
        return cleaned

    def _extract_labeled_date(self, lines: list[str], labels: list[str]) -> Optional[str]:
        date_pattern = r"\d{1,2}[.\/-]\d{1,2}[.\/-]\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s*\d{4}"

        for idx, line in enumerate(lines):
            lower = line.lower()
            matched_label = next((label for label in labels if label in lower), None)
            if not matched_label:
                continue
            after_label = line.lower().split(matched_label, 1)[1]
            match = re.search(date_pattern, after_label)
            if match:
                return match.group(0)
            match = re.search(date_pattern, line)
            if match and idx + 1 < len(lines):
                # Line can contain invoice and due dates together; if label-bound date not found,
                # inspect the next line before accepting the first date from current line.
                match_next = re.search(date_pattern, lines[idx + 1])
                if match_next:
                    return match_next.group(0)
            for look_ahead in range(1, 4):
                if idx + look_ahead >= len(lines):
                    break
                match_next = re.search(date_pattern, lines[idx + look_ahead])
                if match_next:
                    return match_next.group(0)
        return None

    def _normalize_text(self, text: str) -> str:
        return (
            text.replace("\u00a0", " ")
            .replace("EUR", " EUR")
            .replace("$US", " USD")
            .replace("$", " USD")
            .replace("MwSt", "mwst")
            .replace("MWST", "mwst")
            .replace("ß", "ss")
        )

    def _first_match(self, text: str, patterns: list[str]) -> Optional[str]:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _parse_date(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        match = re.match(r"(\d{1,2})[.\/-](\d{1,2})[.\/-](\d{2,4})", value)
        if match:
            day, month, year = match.groups()
            if len(year) == 2:
                year = f"20{year}"
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

        match = re.match(r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})", value.strip())
        if not match:
            return value
        month_name, day, year = match.groups()
        month_map = {
            "jan": 1,
            "january": 1,
            "feb": 2,
            "february": 2,
            "mar": 3,
            "march": 3,
            "apr": 4,
            "april": 4,
            "may": 5,
            "jun": 6,
            "june": 6,
            "jul": 7,
            "july": 7,
            "aug": 8,
            "august": 8,
            "sep": 9,
            "sept": 9,
            "september": 9,
            "oct": 10,
            "october": 10,
            "nov": 11,
            "november": 11,
            "dec": 12,
            "december": 12,
        }
        month = month_map.get(month_name.lower())
        if not month:
            return value
        if len(year) == 2:
            year = f"20{year}"
        return f"{int(year):04d}-{month:02d}-{int(day):02d}"

    def _extract_amounts(self, text: str, lines: list[str]) -> dict:
        def amount_from_lines(labels: list[str]) -> float:
            found: list[float] = []
            for line in lines:
                lower = line.lower()
                if not any(label in lower for label in labels):
                    continue
                if "+" in line and "=" in line:
                    # Skip explanatory formulas that frequently pollute OCR text.
                    continue
                monies = re.findall(self._money_pattern(), line)
                if monies:
                    found.append(self._money_to_float(monies[-1]))
            return found[-1] if found else 0.0

        def amount_after(labels: list[str]) -> float:
            for label in labels:
                pattern = rf"{label}[\s\S]{{0,60}}?({self._money_pattern()})"
                matches = re.findall(pattern, text, flags=re.IGNORECASE)
                if matches:
                    return self._money_to_float(matches[-1])
            return 0.0

        net_labels = ["netto", "net amount", "subtotal", "sous-total"]
        vat_labels = ["mwst", "mehrwertsteuer", "vat", "tax", "impot", "impôt"]
        gross_labels = ["solde a payer", "solde à payer", "brutto", "gesamtbetrag", "invoice total", "grand total", "total"]

        total_net = amount_from_lines(net_labels) or amount_after(net_labels)
        total_vat = amount_from_lines(vat_labels) or amount_after(vat_labels)
        total_gross = amount_from_lines(gross_labels) or amount_after(gross_labels)

        if total_gross == 0.0:
            values = [self._money_to_float(item) for item in re.findall(self._money_pattern(), text)]
            if values:
                total_gross = max(values)

        if total_net == 0.0 and total_gross > 0.0 and total_vat > 0.0:
            total_net = round(total_gross - total_vat, 2)
        if total_vat == 0.0 and total_net > 0.0 and total_gross > 0.0:
            total_vat = round(total_gross - total_net, 2)
        if total_net == 0.0 and total_vat == 0.0 and total_gross > 0.0:
            if re.search(r"(?:imp.t|tax|vat|mwst)[^\d]{0,10}0\s*%", text, flags=re.IGNORECASE):
                total_net = total_gross
            else:
                has_tax_keywords = re.search(r"\b(?:tax|vat|mwst|mehrwertsteuer|impot|impôt)\b", text, flags=re.IGNORECASE)
                has_tax_rate = re.search(r"\b(?:7|19)\s*%", text)
                if not has_tax_keywords and not has_tax_rate:
                    total_net = total_gross

        return {
            "total_net": round(total_net, 2),
            "total_vat": round(total_vat, 2),
            "total_gross": round(total_gross, 2),
        }

    def _looks_like_noise(self, value: str) -> bool:
        candidate = (value or "").strip().lower()
        if not candidate:
            return True
        if ".html" in candidate or candidate.startswith("s/"):
            return True
        if re.search(r"\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}", candidate):
            return True
        return False

    def _looks_like_invoice_document(
        self,
        text: str,
        invoice_number: str,
        invoice_date: Optional[str],
        total_net: float,
        total_vat: float,
        total_gross: float,
        line_items_count: int,
    ) -> bool:
        if invoice_number and re.search(r"\d", invoice_number):
            return True
        if invoice_date:
            return True

        # If we already extracted structured finance data, keep it instead of hard-resetting.
        if total_net > 0 or total_vat > 0 or total_gross > 0 or line_items_count > 0:
            return True

        lower = text.lower()
        header_hits = sum(1 for token in ["invoice", "rechnung", "facture"] if token in lower)
        finance_hits = sum(
            1 for token in ["due", "faellig", "nett", "netto", "mwst", "vat", "brutto", "subtotal", "grand total"] if token in lower
        )
        return header_hits >= 1 and finance_hits >= 1

    def _money_pattern(self) -> str:
        return r"\d{1,3}(?:[ ]\d{3})*(?:[,.]\d{2})|\d+(?:[,.]\d{2})"

    def _money_to_float(self, value: str) -> float:
        cleaned = value.replace(" ", "").replace(",", ".")
        return float(cleaned)

    def _extract_currency(self, text: str) -> str:
        upper = text.upper()
        if "$US" in upper or "USD" in upper:
            return "USD"
        if "CHF" in upper:
            return "CHF"
        if "GBP" in upper:
            return "GBP"
        return "EUR"

    def _extract_vat_rate(self, text: str, total_net: float, total_vat: float, total_gross: float) -> Optional[int]:
        if re.search(r"(?:imp.t|tax|vat|mwst)[^\d]{0,10}0\s*%", text, flags=re.IGNORECASE):
            return 0
        if total_net > 0 and total_vat == 0 and abs(total_gross - total_net) <= 0.01:
            # Net equals gross and no VAT amount detected: treat as zero VAT.
            return 0
        rates = {int(rate) for rate in re.findall(r"\b(7|19)\s*%", text)}
        if len(rates) > 1:
            return None
        if len(rates) == 1:
            return next(iter(rates))
        if total_net > 0 and total_vat > 0:
            calculated = round((total_vat / total_net) * 100)
            if calculated in {7, 19}:
                return calculated
        return None

    def _guess_vendor(self, lines: list[str]) -> str:
        skip = ("rechnung", "invoice", "facture", "datum", "date", "tel", "www", "email", "adresse", "modalites", "modalités")

        for idx, line in enumerate(lines[:15]):
            lower = line.strip().lower()
            if not lower.startswith("customer name"):
                continue
            for offset in range(0, 3):
                pos = idx + offset
                if pos >= len(lines):
                    break
                candidate = lines[pos].strip()
                if not candidate:
                    continue
                parts = re.split(r":", candidate, maxsplit=1)
                value = parts[-1].strip()
                if value and len(value) > 3 and not self._looks_like_noise(value):
                    return value

        for line in lines[:8]:
            cleaned = line.strip()
            if cleaned.startswith("#"):
                continue
            lower = cleaned.lower()
            # Ignore browser-print artifacts and timestamp/page noise from rendered PDFs.
            if "file:///" in lower or re.fullmatch(r"\d+\s*/\s*\d+", lower):
                continue
            if re.search(r"\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}", lower):
                continue
            if "ocr test" in lower:
                continue
            if len(cleaned) <= 3:
                continue
            if len(cleaned) >= 2 and not any(word in cleaned.lower() for word in skip):
                return cleaned
        return lines[0] if lines else ""

    def _guess_address(self, lines: list[str]) -> str:
        for line in lines[:10]:
            if re.search(r"\b\d{5}\b", line) or re.search(r"(strasse|straße|weg|platz|allee)", line, re.IGNORECASE):
                return line
        return ""

    def _extract_line_items(self, lines: list[str]) -> list[dict]:
        items: list[dict] = []
        clean_lines = [line.strip() for line in lines if line.strip()]
        forbidden = ("netto", "brutto", "mwst", "total", "gesamt", "rechnung", "invoice", "facture", "sous-total", "solde", "impot", "impôt")
        pattern = re.compile(
            r"^(?P<desc>.+?)\s+(?P<qty>\d+(?:[,.]\d+)?)\s*(?:x|stk|stuck|pcs)?\s+"
            rf"(?P<unit>{self._money_pattern()})\s+(?P<total>{self._money_pattern()})$",
            re.IGNORECASE,
        )
        single_amount_pattern = re.compile(
            r"^(?P<desc>.+?)\s+(?P<qty>\d+(?:[,.]\d+)?)\s+(?P<total>\d+(?:[,.]\d{2}))$",
            re.IGNORECASE,
        )
        mixed_vat_item_pattern = re.compile(
            rf"^(?P<desc>.+?)\s+(?P<vat>7|19)\s*%\s+(?P<total>{self._money_pattern()})$",
            re.IGNORECASE,
        )

        for line in lines:
            normalized = line.replace("EUR", "").replace(",", ".").strip()
            if any(word in normalized.lower() for word in forbidden):
                continue
            match = pattern.match(normalized)
            if match:
                items.append(
                    {
                        "description": match.group("desc").strip(" -:"),
                        "quantity": float(match.group("qty")),
                        "unit_price": self._money_to_float(match.group("unit")),
                        "total_price": self._money_to_float(match.group("total")),
                        "matched_item_code": None,
                        "match_confidence": 0.0,
                    }
                )
                continue

            single = single_amount_pattern.match(normalized)
            if single:
                quantity = float(single.group("qty"))
                total = self._money_to_float(single.group("total"))
                unit = round(total / quantity, 2) if quantity else total
                items.append(
                    {
                        "description": single.group("desc").strip(" -:"),
                        "quantity": quantity,
                        "unit_price": unit,
                        "total_price": total,
                        "matched_item_code": None,
                        "match_confidence": 0.0,
                    }
                )
                continue

            mixed_vat = mixed_vat_item_pattern.match(normalized)
            if not mixed_vat:
                continue
            total = self._money_to_float(mixed_vat.group("total"))
            items.append(
                {
                    "description": mixed_vat.group("desc").strip(" -:"),
                    "quantity": 1.0,
                    "unit_price": total,
                    "total_price": total,
                    "matched_item_code": None,
                    "match_confidence": 0.0,
                }
            )
        if items:
            return self._append_unreadable_item_placeholders(items, clean_lines)

        header_words = ("objet", "description", "quantite", "quantité", "prix", "montant")
        for index, line in enumerate(clean_lines):
            lower = line.lower()
            if any(word in lower for word in forbidden + header_words):
                continue
            if self._line_is_money(line) or self._line_is_quantity(line):
                continue
            if index + 2 >= len(clean_lines):
                continue
            qty_line = clean_lines[index + 1]
            unit_line = clean_lines[index + 2]

            # Mixed-VAT tables often come as: description / 7% or 19% / amount.
            if re.fullmatch(r"(?:7|19)\s*%", qty_line.strip()) and self._line_is_money(unit_line):
                total_price = self._money_to_float(self._first_money(unit_line) or "0")
                items.append(
                    {
                        "description": line,
                        "quantity": 1.0,
                        "unit_price": total_price,
                        "total_price": total_price,
                        "matched_item_code": None,
                        "match_confidence": 0.0,
                    }
                )
                continue

            if not self._line_is_quantity(qty_line) or not self._line_is_money(unit_line):
                continue
            quantity = float(qty_line.replace(",", "."))
            unit_price = self._money_to_float(self._first_money(unit_line) or "0")
            total_price = round(quantity * unit_price, 2)

            # If the next line is a summary label (Netto/Total/etc.), never treat it as an item total.
            next_line = clean_lines[index + 3] if index + 3 < len(clean_lines) else ""
            next_lower = next_line.lower()
            if next_line and self._line_is_money(next_line) and not any(word in next_lower for word in forbidden):
                total_price = self._money_to_float(self._first_money(next_line) or str(total_price))

            # OCR fallback can misread single-price rows as quantity+unit rows (e.g. qty=50, unit=50).
            if quantity > 0 and unit_price > 0 and unit_price >= quantity and total_price == round(quantity * unit_price, 2):
                total_price = round(unit_price, 2)
                unit_price = round(total_price / quantity, 2)

            items.append(
                {
                    "description": line,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "total_price": total_price,
                    "matched_item_code": None,
                    "match_confidence": 0.0,
                }
            )

        if items:
            return self._append_unreadable_item_placeholders(items, clean_lines)

        # ERPNext-style OCR can split a row across multiple lines: code / qty+uom / amount.
        code_pattern = re.compile(r"^[A-Z]{2,}(?:-[A-Z0-9]{2,}){1,}$")
        qty_pattern = re.compile(r"(?P<qty>\d+(?:[,.]\d+)?)\s*(?:nos|pcs|stk|stuck)\b", re.IGNORECASE)

        for index, line in enumerate(clean_lines):
            code = line.strip().upper()
            if not code_pattern.fullmatch(code):
                continue
            window = clean_lines[index + 1 : index + 7]
            quantity = 1.0
            amount_candidates: list[float] = []

            for candidate in window:
                qty_match = qty_pattern.search(candidate)
                if qty_match:
                    quantity = float(qty_match.group("qty").replace(",", "."))

                for money in re.findall(self._money_pattern(), candidate):
                    value = self._money_to_float(money)
                    if value > 0:
                        amount_candidates.append(value)

            if not amount_candidates:
                continue

            total = max(amount_candidates)
            unit = round(total / quantity, 2) if quantity else total
            items.append(
                {
                    "description": code,
                    "quantity": quantity,
                    "unit_price": unit,
                    "total_price": total,
                    "matched_item_code": None,
                    "match_confidence": 0.0,
                }
            )

        return self._append_unreadable_item_placeholders(items, clean_lines)

    def _append_unreadable_item_placeholders(self, items: list[dict], clean_lines: list[str]) -> list[dict]:
        existing_desc = {str(item.get("description", "")).lower() for item in items}

        for index, line in enumerate(clean_lines):
            lower = line.lower()
            if "nicht lesbar" not in lower and "[" not in line:
                continue
            if lower in existing_desc:
                continue

            total = 0.0
            for candidate in clean_lines[index + 1 : index + 4]:
                candidate_lower = candidate.lower()
                if any(token in candidate_lower for token in ("netto", "brutto", "mwst", "total", "gesamt")):
                    continue
                if re.fullmatch(r"\?+", candidate.strip()):
                    continue
                money = self._first_money(candidate)
                if money:
                    total = self._money_to_float(money)
                    break

            items.append(
                {
                    "description": line.strip(" -:"),
                    "quantity": 1.0,
                    "unit_price": total,
                    "total_price": total,
                    "matched_item_code": None,
                    "match_confidence": 0.0,
                }
            )
        return items

    def _sanitize_line_items(self, items: list[dict], total_gross: float) -> list[dict]:
        if not items:
            return items

        cleaned: list[dict] = []
        for item in items:
            quantity = max(0.0, float(item.get("quantity") or 0.0))
            unit_price = max(0.0, float(item.get("unit_price") or 0.0))
            total_price = max(0.0, float(item.get("total_price") or 0.0))

            if quantity > 0 and total_price > 0 and unit_price > 0:
                # If one row dominates invoice total, it's usually a misparsed unit/total pair.
                if total_gross > 0 and total_price > total_gross * 1.5:
                    corrected_total = min(total_price, unit_price)
                    unit_price = round(corrected_total / quantity, 2)
                    total_price = round(corrected_total, 2)

            cleaned.append(
                {
                    **item,
                    "quantity": round(quantity, 3),
                    "unit_price": round(unit_price, 2),
                    "total_price": round(total_price, 2),
                }
            )

        if total_gross > 0:
            summed = sum(float(it.get("total_price") or 0.0) for it in cleaned)
            if summed > total_gross * 2.5:
                return []
        return cleaned

    def _first_money(self, value: str) -> Optional[str]:
        match = re.search(self._money_pattern(), value.replace("\u00a0", " "))
        return match.group(0) if match else None

    def _line_is_money(self, line: str) -> bool:
        return self._first_money(line) is not None

    def _line_is_quantity(self, line: str) -> bool:
        return re.fullmatch(r"\d+(?:[,.]\d+)?", line.strip()) is not None

    def _detect_language_from_text(self, text: str) -> str:
        lower = text.lower()
        german_hits = sum(
            lower.count(token)
            for token in ["rechnung", "faellig", "mwst", "gesamt", "lieferant", "nettobetrag"]
        )
        english_hits = sum(
            lower.count(token)
            for token in ["invoice", "due", "vat", "total", "supplier", "net amount"]
        )
        if german_hits >= english_hits and german_hits > 0:
            return "de"
        if english_hits > 0:
            return "en"
        return "unknown"

    async def _mock_extract(self, image_data: str) -> dict:
        scenario = int(hashlib.md5(image_data.encode()[:100]).hexdigest(), 16) % 6
        data = [
            self._standard_invoice(),
            self._unknown_supplier_invoice(),
            self._mixed_vat_invoice(),
            self._low_confidence_invoice(),
            self._no_items_invoice(),
            self._wrong_totals_invoice(),
        ][scenario]
        data["mock_scenario"] = scenario
        return data

    def _standard_invoice(self) -> dict:
        return {
            "vendor_name": "Blumen Grosshandel GmbH",
            "vendor_address": "Musterstrasse 12, 80331 Muenchen",
            "invoice_number": "INV-2026-0042",
            "invoice_date": "2026-04-08",
            "due_date": "2026-04-22",
            "currency": "EUR",
            "total_net": 94.00,
            "total_vat": 6.58,
            "total_gross": 100.58,
            "vat_rate": 7,
            "line_items": [
                {"description": "Rote Rosen", "quantity": 50, "unit_price": 1.20, "total_price": 60.00, "matched_item_code": None, "match_confidence": 0.0},
                {"description": "Tulpen Mix", "quantity": 30, "unit_price": 0.80, "total_price": 24.00, "matched_item_code": None, "match_confidence": 0.0},
                {"description": "Schleierkraut", "quantity": 20, "unit_price": 0.50, "total_price": 10.00, "matched_item_code": None, "match_confidence": 0.0},
            ],
            "confidence_score": 0.92,
            "raw_text": "Mock OCR text for INV-2026-0042",
        }

    def _unknown_supplier_invoice(self) -> dict:
        data = self._standard_invoice()
        data.update(
            vendor_name="Neue Blumen AG",
            vendor_address="Gartenweg 5, 10115 Berlin",
            invoice_number="NB-2026-118",
            invoice_date="2026-04-05",
            due_date="2026-04-19",
            total_net=150.00,
            total_vat=10.50,
            total_gross=160.50,
            confidence_score=0.88,
        )
        data["line_items"] = [
            {"description": "Sonnenblumen", "quantity": 40, "unit_price": 1.50, "total_price": 60.00, "matched_item_code": None, "match_confidence": 0.0},
            {"description": "Lilien Weiss", "quantity": 25, "unit_price": 2.40, "total_price": 60.00, "matched_item_code": None, "match_confidence": 0.0},
            {"description": "Eukalyptus Bund", "quantity": 15, "unit_price": 2.00, "total_price": 30.00, "matched_item_code": None, "match_confidence": 0.0},
        ]
        return data

    def _mixed_vat_invoice(self) -> dict:
        data = self._standard_invoice()
        data.update(
            invoice_number="INV-2026-0055",
            invoice_date="2026-04-10",
            due_date="2026-04-24",
            total_net=85.00,
            total_vat=11.83,
            total_gross=96.83,
            vat_rate=None,
            confidence_score=0.81,
        )
        data["line_items"] = [
            {"description": "Rosen Rot", "quantity": 30, "unit_price": 1.20, "total_price": 36.00, "matched_item_code": None, "match_confidence": 0.0},
            {"description": "Glasvase Gross", "quantity": 5, "unit_price": 9.80, "total_price": 49.00, "matched_item_code": None, "match_confidence": 0.0},
        ]
        return data

    def _low_confidence_invoice(self) -> dict:
        data = self._standard_invoice()
        data.update(
            vendor_name="Bl?men Gr??handel",
            vendor_address="",
            invoice_number="INV-20?6-00??",
            invoice_date="2026-04-07",
            due_date=None,
            total_net=67.00,
            total_vat=4.69,
            total_gross=71.69,
            confidence_score=0.45,
            line_items=[{"description": "R?sen", "quantity": 30, "unit_price": 1.20, "total_price": 36.00, "matched_item_code": None, "match_confidence": 0.0}],
        )
        return data

    def _no_items_invoice(self) -> dict:
        data = self._standard_invoice()
        data.update(
            vendor_name="Flora Express GmbH",
            vendor_address="Blumenallee 8, 50667 Koeln",
            invoice_number="FE-2026-0789",
            invoice_date="2026-04-09",
            due_date="2026-04-23",
            total_net=230.00,
            total_vat=16.10,
            total_gross=246.10,
            confidence_score=0.65,
            line_items=[],
        )
        return data

    def _wrong_totals_invoice(self) -> dict:
        data = self._standard_invoice()
        data.update(
            invoice_number="INV-2026-0060",
            invoice_date="2026-04-11",
            due_date="2026-04-25",
            total_net=94.00,
            total_vat=6.58,
            total_gross=105.00,
            confidence_score=0.78,
            line_items=[
                {"description": "Gerbera Mix", "quantity": 40, "unit_price": 1.10, "total_price": 44.00, "matched_item_code": None, "match_confidence": 0.0},
                {"description": "Nelken Bunt", "quantity": 50, "unit_price": 1.00, "total_price": 50.00, "matched_item_code": None, "match_confidence": 0.0},
            ],
        )
        return data


def create_ocr_service() -> OCRService:
    from app.config.settings import settings

    return OCRService(
        settings.azure_ocr_endpoint,
        settings.azure_ocr_key,
        settings.ocr_provider,
    )
