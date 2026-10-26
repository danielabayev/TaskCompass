"""All Hebrew user-facing text in one place."""

# Card field labels.
FIELD_LABELS = {
    "type": "סוג המשימה",
    "deliverable": "התוצר",
    "done_tests": "מבחני סיום",
    "boundaries": "גבולות (מה לא בכלל)",
    "first_step": "צעד ראשון",
}

# Code-test failure reasons.
REASON_TYPE_MISSING = "עדיין לא נבחר סוג משימה פעיל."
REASON_EMPTY = "עדיין ריק."
REASON_TOO_MANY_TESTS = "יותר מ-5 מבחנים. צריך לבחור את החשובים, או לפצל את המשימה."
REASON_NO_BOUNDARY = "צריך לפחות דבר אחד מוחשי שלא נכלל במשימה."
