# Floravi Invoice OCR Agent - MCP Server

FastAPI server for the Floravi Invoice Assistant. It exposes four tool endpoints:

- `process_ocr_document`
- `validate_supplier`
- `validate_items`
- `create_purchase_invoice`

The OCR implementation runs in mock mode by default. For real local OCR, enable PaddleOCR.

## Quick Start

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

- http://localhost:8000
- http://localhost:8000/health
- http://localhost:8000/docs
- http://localhost:8000/agent

If port `8000` is blocked on Windows, use another port:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Then open:

- http://127.0.0.1:8010/agent

Recommended local command (uses project venv and avoids watcher noise from venv packages):

```powershell
.\run-local.ps1
```

Then open:

- http://127.0.0.1:8011/agent

## Real Open-Source OCR

For the strongest open-source local OCR path, use PaddleOCR.

Install it:

```powershell
pip install paddleocr==3.4.0
```

If PaddleOCR asks for PaddlePaddle separately, install the CPU build:

```powershell
pip install paddlepaddle
```

Enable it for the current terminal session:

```powershell
$env:OCR_PROVIDER="paddle"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Or add this to `.env`:

```text
OCR_PROVIDER=paddle
```

Notes:

- `OCR_PROVIDER=mock` returns fake invoices for testing.
- `OCR_PROVIDER=paddle` reads real uploaded invoices locally.
- PaddleOCR extracts text; this app then parses invoice number, dates, totals, VAT, and line items with invoice-specific rules.
- Real invoices vary a lot, so the UI keeps all fields editable before draft creation.

## Safety Rules

- The invoice creation tool only creates ERPNext drafts.
- `confirmed=true` is required before creating a draft.
- Financial totals are validated before ERPNext is called.
- Tenant IDs are required for every tool call.
