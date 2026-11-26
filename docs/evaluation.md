# Kavach Evaluation Report

## Results Table

| File | Variant | Edit Description | Doc Type | Score | Level | Failed Checks | Top Finding | Best IoU | Detected By | Catchable By Rules |
| :--- | :--- | :--- | :--- | ---: | :--- | ---: | :--- | ---: | :--- | :--- |
| `bill_clean.jpg.jpeg` | original | Clean original | INVOICE_BILL | 25 | LOW | 0 | (none) | — | — | — |
| `gst_2018.jpg.jpeg` | original | Clean original | GST_CERT | 0 | LOW | 0 | (none) | — | — | — |
| `gst_2023.jpg.jpeg` | original | Clean original | GST_CERT | 26 | LOW | 0 | Visual tampering indicators detected | — | — | — |
| `kea_receipt.jpg.jpeg` | original | Clean original | PAYMENT_RECEIPT | 17 | LOW | 0 | Visual tampering indicators detected | — | — | — |
| `phonepe_stmt.png.jpeg` | original | Clean original | BANK_UPI_STATEMENT | 0 | LOW | 0 | (none) | — | — | — |
| `bill_clean_a_net_total.jpg` | original | Change net total 2,560.00 -> 3,560.00 | INVOICE_BILL | 75 | HIGH | 1 | Line item sum mismatch | 0.812 | consistency check | yes |
| `bill_clean_a_net_total_wa.jpg` | whatsapp | Change net total 2,560.00 -> 3,560.00 (WhatsApp compressed) | INVOICE_BILL | 90 | HIGH | 1 | Line item sum mismatch | 0.783 | consistency check | yes |
| `bill_clean_b_line_total.jpg` | original | Change line total 500.00 -> 800.00 | INVOICE_BILL | 92 | HIGH | 2 | Line item calculation mismatch | 0.688 | consistency check | yes |
| `bill_clean_b_line_total_wa.jpg` | whatsapp | Change line total 500.00 -> 800.00 (WhatsApp compressed) | INVOICE_BILL | 97 | HIGH | 2 | Line item calculation mismatch | 0.201 | consistency check | yes |
| `gst_2018_a_gstin.jpg` | original | Change one character in GSTIN | GST_CERT | 7 | LOW | 0 | (none) | 0.000 | — | yes |
| `gst_2018_a_gstin_wa.jpg` | whatsapp | Change one character in GSTIN (WhatsApp compressed) | GST_CERT | 14 | LOW | 0 | (none) | 0.000 | — | yes |
| `gst_2018_b_legal_name.jpg` | original | Replace legal name | GST_CERT | 0 | LOW | 0 | (none) | 0.434 | — | yes |
| `gst_2018_b_legal_name_wa.jpg` | whatsapp | Replace legal name (WhatsApp compressed) | GST_CERT | 11 | LOW | 0 | GSTIN could not be read reliably | 0.000 | — | yes |
| `gst_2018_c_issue_date.jpg` | original | Change date of issue | GST_CERT | 0 | LOW | 0 | (none) | 0.214 | — | yes |
| `gst_2018_c_issue_date_wa.jpg` | whatsapp | Change date of issue (WhatsApp compressed) | GST_CERT | 11 | LOW | 0 | GSTIN could not be read reliably | 0.000 | — | yes |
| `gst_2023_a_gstin.jpg` | original | Change one character in GSTIN | GST_CERT | 26 | LOW | 0 | GSTIN could not be read reliably | 0.000 | — | yes |
| `gst_2023_a_gstin_wa.jpg` | whatsapp | Change one character in GSTIN (WhatsApp compressed) | GST_CERT | 26 | LOW | 0 | GSTIN could not be read reliably | 0.000 | — | yes |
| `gst_2023_b_legal_name.jpg` | original | Replace legal name | GST_CERT | 26 | LOW | 0 | GSTIN could not be read reliably | 0.279 | — | yes |
| `gst_2023_b_legal_name_wa.jpg` | whatsapp | Replace legal name (WhatsApp compressed) | GST_CERT | 25 | LOW | 0 | GSTIN could not be read reliably | 0.000 | — | yes |
| `gst_2023_c_issue_date.jpg` | original | Change date of issue | GST_CERT | 26 | LOW | 0 | GSTIN could not be read reliably | 0.749 | — | yes |
| `gst_2023_c_issue_date_wa.jpg` | whatsapp | Change date of issue (WhatsApp compressed) | GST_CERT | 25 | LOW | 0 | GSTIN could not be read reliably | 0.000 | — | yes |
| `kea_receipt_a_amount.jpg` | original | Change payment amount 121610 -> 21610 | PAYMENT_RECEIPT | 17 | LOW | 0 | Visual tampering indicators detected | 0.000 | — | no |
| `kea_receipt_a_amount_wa.jpg` | whatsapp | Change payment amount 121610 -> 21610 (WhatsApp compressed) | PAYMENT_RECEIPT | 17 | LOW | 0 | Visual tampering indicators detected | 0.000 | — | no |
| `phonepe_stmt_a_amount.jpg` | original | Change amount 90 -> 900 on one row | BANK_UPI_STATEMENT | 0 | LOW | 0 | (none) | 0.000 | — | no |
| `phonepe_stmt_a_amount_wa.jpg` | whatsapp | Change amount 90 -> 900 on one row (WhatsApp compressed) | BANK_UPI_STATEMENT | 26 | LOW | 0 | Visual tampering indicators detected | 0.000 | — | no |
| `phonepe_stmt_b_row_date.jpg` | original | Change row date to disagree with Transaction ID | BANK_UPI_STATEMENT | 89 | HIGH | 2 | UPI transaction ID date mismatch | 0.881 | consistency check | yes |
| `phonepe_stmt_b_row_date_wa.jpg` | whatsapp | Change row date to disagree with Transaction ID (WhatsApp compressed) | BANK_UPI_STATEMENT | 76 | HIGH | 1 | UPI transaction ID date mismatch | 0.133 | consistency check | yes |

## Summary Metrics

- **Detection Rate (All Tampered MEDIUM/HIGH)**: 27.3% (6/22)
- **Rule-Catchable Edits Detection Rate**: 33.3% (6/18)
- **Visual-Only Edits Detection Rate**: 0.0% (0/4)
- **False-Positive Rate (Clean MEDIUM/HIGH)**: 0.0% (0/5)
- **Mean IoU on Text Edits**: 0.2352
- **Original-Quality Tampered**: detection=27.3%, mean IoU=0.3689
- **WhatsApp-Compressed Tampered**: detection=27.3%, mean IoU=0.1015

## Misses (Tampered Scored LOW)

- `gst_2018_a_gstin.jpg` (Change one character in GSTIN): score=7, signals=['forensics:noise:7.0'], failed_checks=[]
- `gst_2018_a_gstin_wa.jpg` (Change one character in GSTIN (WhatsApp compressed)): score=14, signals=['forensics:noise:7.34', 'forensics:jpeg_ghost:6.66'], failed_checks=[]
- `gst_2018_b_legal_name.jpg` (Replace legal name): score=0, signals=[], failed_checks=[]
- `gst_2018_b_legal_name_wa.jpg` (Replace legal name (WhatsApp compressed)): score=11, signals=['forensics:jpeg_ghost:6.94', 'warn:gst:gstin_format:4.06'], failed_checks=[]
- `gst_2018_c_issue_date.jpg` (Change date of issue): score=0, signals=[], failed_checks=[]
- `gst_2018_c_issue_date_wa.jpg` (Change date of issue (WhatsApp compressed)): score=11, signals=['forensics:jpeg_ghost:6.93', 'warn:gst:gstin_format:4.07'], failed_checks=[]
- `gst_2023_a_gstin.jpg` (Change one character in GSTIN): score=26, signals=['forensics:copy_move:6.57', 'forensics:jpeg_ghost:6.27', 'forensics:text_patch:6.07', 'forensics:ela:4.89', 'warn:gst:gstin_format:2.21'], failed_checks=[]
- `gst_2023_a_gstin_wa.jpg` (Change one character in GSTIN (WhatsApp compressed)): score=26, signals=['forensics:jpeg_ghost:9.5', 'forensics:copy_move:7.4', 'forensics:ela:6.38', 'warn:gst:gstin_format:2.73'], failed_checks=[]
- `gst_2023_b_legal_name.jpg` (Replace legal name): score=26, signals=['forensics:copy_move:6.62', 'forensics:jpeg_ghost:6.12', 'forensics:text_patch:6.11', 'forensics:ela:4.93', 'warn:gst:gstin_format:2.22'], failed_checks=[]
- `gst_2023_b_legal_name_wa.jpg` (Replace legal name (WhatsApp compressed)): score=25, signals=['forensics:jpeg_ghost:12.76', 'forensics:ela:8.56', 'warn:gst:gstin_format:3.67'], failed_checks=[]
- `gst_2023_c_issue_date.jpg` (Change date of issue): score=26, signals=['forensics:copy_move:8.65', 'forensics:jpeg_ghost:8.0', 'forensics:ela:6.44', 'warn:gst:gstin_format:2.91'], failed_checks=[]
- `gst_2023_c_issue_date_wa.jpg` (Change date of issue (WhatsApp compressed)): score=25, signals=['forensics:jpeg_ghost:12.77', 'forensics:ela:8.57', 'warn:gst:gstin_format:3.66'], failed_checks=[]
- `kea_receipt_a_amount.jpg` (Change payment amount 121610 -> 21610): score=17, signals=['forensics:noise:17.0'], failed_checks=[]
- `kea_receipt_a_amount_wa.jpg` (Change payment amount 121610 -> 21610 (WhatsApp compressed)): score=17, signals=['forensics:noise:17.0'], failed_checks=[]
- `phonepe_stmt_a_amount.jpg` (Change amount 90 -> 900 on one row): score=0, signals=[], failed_checks=[]
- `phonepe_stmt_a_amount_wa.jpg` (Change amount 90 -> 900 on one row (WhatsApp compressed)): score=26, signals=['forensics:noise:9.77', 'forensics:ela:5.7', 'forensics:jpeg_ghost:5.36', 'forensics:text_patch:5.17'], failed_checks=[]

## False Positives (Clean Scored MEDIUM/HIGH)

- None

## Known Limitations

- **Low-resolution 480x640 inputs**: Small web/WhatsApp thumbnails lack sufficient pixel detail around dense text, which can cause OCR character drops and noisy local visual statistics.
- **Single-occurrence amounts with no cross-check**: When an amount appears only once on a document (such as a payment receipt total or a single bank statement row without running balances), consistency rules cannot verify it mathematically.
- **OCR latency on large or recompressed images**: RapidOCR inference on high-resolution or heavily recompressed images can be slow on CPU; if an analyzer exceeds its timeout budget, Kavach marks the result as unverified (`confidence <= 0.3`).
