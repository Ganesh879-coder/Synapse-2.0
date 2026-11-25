"""Consistency checks for GST Registration Certificates (FORM GST REG-06)."""

from __future__ import annotations

import re
from datetime import date

from app.models.schemas import CheckResult, ExtractedField, Finding, Region, Signal
from app.rules.common import make_failure, parse_date

GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

_MOD36_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

GST_STATE_CODES: dict[str, tuple[str, ...]] = {
    "01": ("jammu", "kashmir", "jammu and kashmir"),
    "02": ("himachal", "himachal pradesh"),
    "03": ("punjab",),
    "04": ("chandigarh",),
    "05": ("uttarakhand",),
    "06": ("haryana",),
    "07": ("delhi", "new delhi"),
    "08": ("rajasthan",),
    "09": ("uttar pradesh",),
    "10": ("bihar",),
    "11": ("sikkim",),
    "12": ("arunachal pradesh",),
    "13": ("nagaland",),
    "14": ("manipur",),
    "15": ("mizoram",),
    "16": ("tripura",),
    "17": ("meghalaya",),
    "18": ("assam",),
    "19": ("west bengal",),
    "20": ("jharkhand",),
    "21": ("odisha", "orissa"),
    "22": ("chhattisgarh",),
    "23": ("madhya pradesh",),
    "24": ("gujarat",),
    "25": ("daman", "diu"),
    "26": ("dadra", "nagar haveli", "daman and diu"),
    "27": ("maharashtra",),
    "28": ("andhra pradesh",),
    "29": ("karnataka",),
    "30": ("goa",),
    "31": ("lakshadweep",),
    "32": ("kerala",),
    "33": ("tamil nadu",),
    "34": ("puducherry", "pondicherry"),
    "35": ("andaman", "nicobar"),
    "36": ("telangana",),
    "37": ("andhra pradesh",),
    "38": ("ladakh",),
}

_ENTITY_CONSTITUTION_MAP: dict[str, tuple[str, ...]] = {
    "P": ("proprietorship", "individual", "proprietor"),
    "C": ("private limited", "public limited", "company", "opc"),
    "F": ("partnership", "llp", "limited liability partnership"),
    "H": ("hindu undivided family", "huf"),
    "T": ("trust",),
    "A": ("association of persons", "aop"),
    "B": ("body of individuals", "boi"),
    "G": ("government",),
    "L": ("local authority",),
    "J": ("artificial juridical person",),
}

_KNOWN_REG06_2018 = ["gstin", "legal_name", "trade_name", "constitution", "address"]
_KNOWN_REG06_2023 = ["gstin", "legal_name", "trade_name", "constitution", "date_of_liability"]


def compute_gstin_check_digit(gstin_14: str) -> str:
    """Compute the 15th mod-36 weighted checksum character for a 14-char GSTIN prefix."""
    total = 0
    for idx, ch in enumerate(gstin_14.upper()):
        code_point = _MOD36_CHARS.index(ch)
        factor = 1 if idx % 2 == 0 else 2
        product = code_point * factor
        total += (product // 36) + (product % 36)
    remainder = total % 36
    check_code = (36 - remainder) % 36
    return _MOD36_CHARS[check_code]


def verify_gstin_checksum(gstin: str) -> bool:
    """Verify 15-character GSTIN format and mod-36 weighted checksum."""
    candidate = gstin.strip().upper()
    if not GSTIN_REGEX.fullmatch(candidate):
        return False
    return compute_gstin_check_digit(candidate[:14]) == candidate[14]


_DIGIT_POSITIONS = frozenset({0, 1, 7, 8, 9, 10})
_LETTER_POSITIONS = frozenset({2, 3, 4, 5, 6, 11, 13})
_TO_DIGIT = {"O": "0", "I": "1", "S": "5", "B": "8"}
_TO_LETTER = {"0": "O", "1": "I", "5": "S", "8": "B"}


def normalize_gstin_with_confusion(raw: str) -> tuple[str, bool]:
    """Retry GSTIN validation using O/0, I/1, S/5, B/8 confusion mapping if needed."""
    candidate = raw.strip().upper()
    if verify_gstin_checksum(candidate):
        return candidate, False
    if len(candidate) != 15:
        return candidate, False

    chars = list(candidate)
    changed = False
    for idx, ch in enumerate(chars):
        if idx in _DIGIT_POSITIONS and ch in _TO_DIGIT:
            chars[idx] = _TO_DIGIT[ch]
            changed = True
        elif idx in _LETTER_POSITIONS and ch in _TO_LETTER:
            chars[idx] = _TO_LETTER[ch]
            changed = True
        elif idx == 13 and ch != "Z":
            chars[idx] = "Z"
            changed = True

    corrected = "".join(chars)
    if changed and verify_gstin_checksum(corrected):
        return corrected, True
    return candidate, False


def run_gst_checks(
    fields: dict[str, ExtractedField],
    today: date | None = None,
) -> tuple[list[CheckResult], list[Finding], list[Region], list[Signal]]:
    """Run all GST certificate consistency checks."""
    checks: list[CheckResult] = []
    findings: list[Finding] = []
    regions: list[Region] = []
    signals: list[Signal] = []
    current_date = today or date.today()

    def _add_issue(
        name: str,
        detail: str,
        title: str,
        severity: str,
        field: ExtractedField | None,
        status: str = "fail",
        weight: float = 0.7,
    ) -> None:
        chk, fnd, reg = make_failure(
            name,
            detail,
            title,
            "consistency" if status == "fail" else "format",
            severity,  # type: ignore[arg-type]
            field=field,
            status=status,
        )
        checks.append(chk)
        findings.append(fnd)
        if reg is not None:
            regions.append(reg)
        signals.append(
            Signal(
                name=f"rules:{name}",
                category="consistency",
                weight_hint=weight,
                confidence=0.85 if status == "fail" else 0.4,
                region_ids=[reg.id] if reg is not None else [],
            )
        )

    gstin_field = fields.get("gstin")
    raw_gstin = str(gstin_field.value).strip().upper() if gstin_field else ""
    gstin, gstin_corrected = normalize_gstin_with_confusion(raw_gstin) if raw_gstin else ("", False)

    if not gstin_field:
        checks.append(
            CheckResult(name="gst:gstin_format", status="skipped", detail="GSTIN not found.")
        )
    else:
        if not GSTIN_REGEX.fullmatch(gstin):
            _add_issue(
                "gst:gstin_format",
                "The GSTIN does not match the standard 15-character Indian GSTIN format.",
                "Invalid GSTIN format",
                "high",
                gstin_field,
            )
        else:
            corr_note = " (OCR confusion correction applied)" if gstin_corrected else ""
            checks.append(
                CheckResult(
                    name="gst:gstin_format",
                    status="pass",
                    detail=f"GSTIN matches the 15-character format.{corr_note}",
                )
            )
            if not verify_gstin_checksum(gstin):
                _add_issue(
                    "gst:gstin_checksum",
                    "The GSTIN check digit does not match the mod-36 checksum.",
                    "GSTIN checksum mismatch",
                    "high",
                    gstin_field,
                    weight=0.85,
                )
            else:
                checks.append(
                    CheckResult(
                        name="gst:gstin_checksum",
                        status="pass",
                        detail=f"GSTIN mod-36 checksum is valid.{corr_note}",
                    )
                )

            # State code vs address state check
            state_code = gstin[:2]
            addr_field = fields.get("address") or fields.get("state")
            if state_code not in GST_STATE_CODES:
                _add_issue(
                    "gst:state_code",
                    f"GSTIN state code '{state_code}' is not a valid Indian state/UT code.",
                    "Unknown GSTIN state code",
                    "high",
                    gstin_field,
                )
            elif addr_field is not None:
                addr_lower = str(addr_field.value).lower()
                expected_names = GST_STATE_CODES[state_code]
                if not any(name in addr_lower for name in expected_names):
                    _add_issue(
                        "gst:state_code",
                        (
                            f"GSTIN state code '{state_code}' ({expected_names[0].title()}) "
                            "does not match the state in the certificate address."
                        ),
                        "State code vs. address mismatch",
                        "high",
                        addr_field,
                    )
                else:
                    checks.append(
                        CheckResult(
                            name="gst:state_code",
                            status="pass",
                            detail="GSTIN state code matches the certificate address.",
                        )
                    )

            # PAN entity type (4th char of PAN = gstin[5]) vs Constitution of Business
            pan = gstin[2:12]
            entity_char = pan[3]
            const_field = fields.get("constitution")
            if const_field is not None:
                const_lower = str(const_field.value).lower()
                expected_terms = _ENTITY_CONSTITUTION_MAP.get(entity_char, ())
                if expected_terms and not any(t in const_lower for t in expected_terms):
                    _add_issue(
                        "gst:pan_constitution",
                        (
                            f"PAN entity code '{entity_char}' in the GSTIN does not match "
                            f"the stated Constitution of Business ('{const_field.value}')."
                        ),
                        "PAN entity type vs. constitution mismatch",
                        "high",
                        const_field,
                    )
                else:
                    checks.append(
                        CheckResult(
                            name="gst:pan_constitution",
                            status="pass",
                            detail="PAN entity type matches Constitution of Business.",
                        )
                    )

            # PAN 5th char (pan[4]) vs legal/trade name initial
            pan_fifth = pan[4]
            legal_field = fields.get("legal_name")
            trade_field = fields.get("trade_name")
            if legal_field is not None or trade_field is not None:
                legal_raw = str(legal_field.value if legal_field else "")
                trade_raw = str(trade_field.value if trade_field else "")
                legal_str = re.sub(r"[^A-Za-z\s]", "", legal_raw).strip()
                trade_str = re.sub(r"[^A-Za-z\s]", "", trade_raw).strip()
                if entity_char == "P" and legal_str:
                    parts = [p for p in legal_str.split() if p]
                    surname_initial = parts[-1][0].upper() if parts else ""
                    if surname_initial and surname_initial != pan_fifth:
                        _add_issue(
                            "gst:pan_name_initial",
                            (
                                f"The 5th PAN letter '{pan_fifth}' in the GSTIN does not match "
                                f"the proprietor surname initial ('{surname_initial}')."
                            ),
                            "PAN initial vs. legal name mismatch",
                            "medium",
                            legal_field,
                        )
                    else:
                        checks.append(
                            CheckResult(
                                name="gst:pan_name_initial",
                                status="pass",
                                detail="PAN 5th character matches proprietor surname initial.",
                            )
                        )
                elif entity_char != "P":
                    candidate_initial = (
                        (trade_str or legal_str).split()[0][0].upper()
                        if (trade_str or legal_str).split()
                        else ""
                    )
                    if candidate_initial and candidate_initial != pan_fifth:
                        _add_issue(
                            "gst:pan_name_initial",
                            (
                                f"The 5th PAN letter '{pan_fifth}' in the GSTIN does not match "
                                f"the entity name initial ('{candidate_initial}')."
                            ),
                            "PAN initial vs. entity name mismatch",
                            "medium",
                            legal_field or trade_field,
                        )
                    else:
                        checks.append(
                            CheckResult(
                                name="gst:pan_name_initial",
                                status="pass",
                                detail="PAN 5th character matches entity name initial.",
                            )
                        )

    # Date checks: date_of_issue >= date_of_liability / validity_from; no future dates
    issue_f = fields.get("date_of_issue")
    liab_f = fields.get("date_of_liability") or fields.get("validity_from")
    issue_d = parse_date(str(issue_f.value)) if issue_f else None
    liab_d = parse_date(str(liab_f.value)) if liab_f else None

    for label, d_val, f_obj in (
        ("date_of_issue", issue_d, issue_f),
        ("date_of_liability", liab_d, liab_f),
    ):
        if d_val is not None and d_val > current_date:
            _add_issue(
                f"gst:future_{label}",
                f"The {label.replace('_', ' ')} ({d_val.isoformat()}) is in the future.",
                "Future date on GST certificate",
                "high",
                f_obj,
            )

    if issue_d is not None and liab_d is not None:
        if issue_d < liab_d:
            _add_issue(
                "gst:date_order",
                "The date of issue is earlier than the date of liability/validity.",
                "Inconsistent issue and liability dates",
                "medium",
                issue_f,
            )
        else:
            checks.append(
                CheckResult(
                    name="gst:date_order",
                    status="pass",
                    detail="Issue date is on or after liability/validity date.",
                )
            )

    # Digital signature warning
    if fields.get("digitally_signed") and fields.get("signature_not_verified"):
        _add_issue(
            "gst:signature_status",
            "The document states 'Digitally signed' but the signature is marked 'Not Verified'.",
            "Unverified digital signature notice",
            "low",
            None,
            status="warn",
            weight=0.3,
        )

    # Template version check (2018 vs 2023 REG-06 layout)
    order_field = fields.get("field_order")
    if order_field and isinstance(order_field.value, list):
        order = [str(x) for x in order_field.value]
        matches_2018 = all(k in order for k in _KNOWN_REG06_2018[:3])
        matches_2023 = all(k in order for k in _KNOWN_REG06_2023[:3])
        if matches_2018 or matches_2023:
            checks.append(
                CheckResult(
                    name="gst:template_layout",
                    status="pass",
                    detail="Field layout matches a known GST REG-06 template.",
                )
            )
        else:
            _add_issue(
                "gst:template_layout",
                "Field order does not match standard 2018 or 2023 GST REG-06 layouts.",
                "Unrecognized GST REG-06 layout",
                "low",
                None,
                status="warn",
                weight=0.2,
            )

    return checks, findings, regions, signals
