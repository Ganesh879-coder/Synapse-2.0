# Kavach Evaluation Report

## Results Table

| File | Variant | Edit Description | Doc Type | Score | Level | Failed Checks | Top Finding | Best IoU |
| :--- | :--- | :--- | :--- | ---: | :--- | ---: | :--- | ---: |
| `bill_clean.jpg.jpeg` | original | Clean original | INVOICE_BILL | 25 | LOW | 0 | (none) | — |
| `gst_2018.jpg.jpeg` | original | Clean original | GST_CERT | 20 | LOW | 0 | Unrecognized GST REG-06 layout | — |
| `gst_2023.jpg.jpeg` | original | Clean original | GST_CERT | 89 | HIGH | 1 | State code vs. address mismatch | — |
| `kea_receipt.jpg.jpeg` | original | Clean original | PAYMENT_RECEIPT | 17 | LOW | 0 | Visual tampering indicators detected | — |
| `phonepe_stmt.png.jpeg` | original | Clean original | BANK_UPI_STATEMENT | 0 | LOW | 0 | (none) | — |
| `bill_clean_a_net_total.jpg` | original | Change net total 2,560.00 -> 3,560.00 | INVOICE_BILL | 75 | HIGH | 1 | Line item sum mismatch | 0.230 |
| `bill_clean_a_net_total_wa.jpg` | whatsapp | Change net total 2,560.00 -> 3,560.00 (WhatsApp compressed) | INVOICE_BILL | 90 | HIGH | 1 | Line item sum mismatch | 0.235 |
| `bill_clean_b_line_total.jpg` | original | Change line total 500.00 -> 800.00 | INVOICE_BILL | 92 | HIGH | 2 | Line item calculation mismatch | 0.688 |
| `bill_clean_b_line_total_wa.jpg` | whatsapp | Change line total 500.00 -> 800.00 (WhatsApp compressed) | INVOICE_BILL | 97 | HIGH | 2 | Line item calculation mismatch | 0.201 |
| `gst_2018_a_gstin.jpg` | original | Change one character in GSTIN | UNKNOWN | 7 | LOW | 0 | (none) | 0.000 |
| `gst_2018_a_gstin_wa.jpg` | whatsapp | Change one character in GSTIN (WhatsApp compressed) | UNKNOWN | 22 | LOW | 0 | (none) | 0.000 |
| `gst_2018_b_legal_name.jpg` | original | Replace legal name | UNKNOWN | 8 | LOW | 0 | (none) | 0.434 |
| `gst_2018_b_legal_name_wa.jpg` | whatsapp | Replace legal name (WhatsApp compressed) | GST_CERT | 26 | LOW | 0 | Unreliable GSTIN read | 0.000 |
| `gst_2018_c_issue_date.jpg` | original | Change date of issue | UNKNOWN | 8 | LOW | 0 | (none) | 0.214 |
| `gst_2018_c_issue_date_wa.jpg` | whatsapp | Change date of issue (WhatsApp compressed) | GST_CERT | 18 | LOW | 0 | Unreliable GSTIN read | 0.000 |
| `gst_2023_a_gstin.jpg` | original | Change one character in GSTIN | UNKNOWN | 70 | HIGH | 0 | Visual tampering indicators detected | 0.000 |
| `gst_2023_a_gstin_wa.jpg` | whatsapp | Change one character in GSTIN (WhatsApp compressed) | GST_CERT | 82 | HIGH | 1 | GSTIN checksum mismatch | 0.000 |
| `gst_2023_b_legal_name.jpg` | original | Replace legal name | UNKNOWN | 70 | HIGH | 0 | Visual tampering indicators detected | 0.279 |
| `gst_2023_b_legal_name_wa.jpg` | whatsapp | Replace legal name (WhatsApp compressed) | GST_CERT | 82 | HIGH | 1 | GSTIN checksum mismatch | 0.000 |
| `gst_2023_c_issue_date.jpg` | original | Change date of issue | UNKNOWN | 26 | LOW | 0 | Visual tampering indicators detected | 0.749 |
| `gst_2023_c_issue_date_wa.jpg` | whatsapp | Change date of issue (WhatsApp compressed) | GST_CERT | 82 | HIGH | 1 | GSTIN checksum mismatch | 0.000 |
| `kea_receipt_a_amount.jpg` | original | Change payment amount 121610 -> 21610 | PAYMENT_RECEIPT | 17 | LOW | 0 | Visual tampering indicators detected | 0.000 |
| `kea_receipt_a_amount_wa.jpg` | whatsapp | Change payment amount 121610 -> 21610 (WhatsApp compressed) | PAYMENT_RECEIPT | 17 | LOW | 0 | Visual tampering indicators detected | 0.000 |
| `phonepe_stmt_a_amount.jpg` | original | Change amount 90 -> 900 on one row | BANK_UPI_STATEMENT | 0 | LOW | 0 | (none) | 0.000 |
| `phonepe_stmt_a_amount_wa.jpg` | whatsapp | Change amount 90 -> 900 on one row (WhatsApp compressed) | BANK_UPI_STATEMENT | 62 | MEDIUM | 0 | Visual tampering indicators detected | 0.000 |
| `phonepe_stmt_b_row_date.jpg` | original | Change row date to disagree with Transaction ID | BANK_UPI_STATEMENT | 89 | HIGH | 2 | UPI transaction ID date mismatch | 0.881 |
| `phonepe_stmt_b_row_date_wa.jpg` | whatsapp | Change row date to disagree with Transaction ID (WhatsApp compressed) | BANK_UPI_STATEMENT | 88 | HIGH | 1 | UPI transaction ID date mismatch | 0.133 |

## Summary Metrics

- **Detection Rate (Tampered MEDIUM/HIGH)**: 54.5% (12/22)
- **False-Positive Rate (Clean MEDIUM/HIGH)**: 20.0% (1/5)
- **Mean IoU on Text Edits**: 0.1839
- **Original-Quality Tampered**: detection=45.5%, mean IoU=0.3160
- **WhatsApp-Compressed Tampered**: detection=63.6%, mean IoU=0.0517

## Misses (Tampered Scored LOW)

- `gst_2018_a_gstin.jpg` (Change one character in GSTIN): score=7, signals=['forensics:noise:7.0'], failed_checks=[]
- `gst_2018_a_gstin_wa.jpg` (Change one character in GSTIN (WhatsApp compressed)): score=22, signals=['forensics:text_patch:8.96', 'forensics:noise:6.84', 'forensics:jpeg_ghost:6.2'], failed_checks=[]
- `gst_2018_b_legal_name.jpg` (Replace legal name): score=8, signals=['forensics:text_patch:8.0'], failed_checks=[]
- `gst_2018_b_legal_name_wa.jpg` (Replace legal name (WhatsApp compressed)): score=26, signals=['forensics:text_patch:8.95', 'forensics:jpeg_ghost:6.19', 'warn:gst:gstin_format:5.43', 'warn:gst:template_layout:5.43'], failed_checks=[]
- `gst_2018_c_issue_date.jpg` (Change date of issue): score=8, signals=['forensics:text_patch:8.0'], failed_checks=[]
- `gst_2018_c_issue_date_wa.jpg` (Change date of issue (WhatsApp compressed)): score=18, signals=['forensics:jpeg_ghost:6.52', 'warn:gst:gstin_format:5.74', 'warn:gst:template_layout:5.74'], failed_checks=[]
- `gst_2023_c_issue_date.jpg` (Change date of issue): score=26, signals=['forensics:copy_move:9.74', 'forensics:jpeg_ghost:9.01', 'forensics:ela:7.25'], failed_checks=[]
- `kea_receipt_a_amount.jpg` (Change payment amount 121610 -> 21610): score=17, signals=['forensics:noise:17.0'], failed_checks=[]
- `kea_receipt_a_amount_wa.jpg` (Change payment amount 121610 -> 21610 (WhatsApp compressed)): score=17, signals=['forensics:noise:17.0'], failed_checks=[]
- `phonepe_stmt_a_amount.jpg` (Change amount 90 -> 900 on one row): score=0, signals=[], failed_checks=[]

## False Positives (Clean Scored MEDIUM/HIGH)

- `gst_2023.jpg.jpeg`: score=89 (HIGH), signals=['rules:gst:state_code:37.51', 'forensics:text_patch:35.88', 'forensics:jpeg_ghost:4.8', 'forensics:copy_move:4.4', 'forensics:ela:3.98', 'warn:gst:template_layout:2.43'], failed_checks=['gst:state_code']
