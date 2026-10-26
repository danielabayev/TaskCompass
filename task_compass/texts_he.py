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

# Model errors (shown with a "try again" button; nothing is lost).
ERROR_COST_CAP = "הגעת לתקרת ההוצאה החודשית שהגדרת, ולכן הכלי לא פונה למודל עד סוף החודש. אפשר להעלות את התקרה בקובץ ‎.env."
ERROR_INVALID_ANSWER = "המודל החזיר תשובה לא תקינה פעמיים. התשובה שלך נשמרה. אפשר לנסות שוב."
ERROR_CALL_FAILED = "לא הצלחתי להגיע למודל (רשת, עומס או מגבלת קצב). התשובה שלך נשמרה. אפשר לנסות שוב."

# Interview.
ENOUGH_WORDS = {"מספיק", "די", "זהו", "זה מספיק", "די כבר", "סיימתי", "enough"}
ENOUGH_NOTE = "עוד לא אפשר לעבור להערכת זמן. חסר:"
REASON_NOT_CHECKED = "עוד לא נבדק."
INVESTIGATE_PREFIX = "תחקור כדי להבהיר את המשימה: "
TYPE_CHANGED_ANSWER = "(שיניתי את סוג המשימה ל-{}. נא לבדוק את הכרטיס מחדש לפי הסוג החדש.)"

# General errors.
ERROR_EMPTY_INPUT = "צריך לכתוב משהו."
ERROR_WRONG_STAGE = "הפעולה הזאת לא מתאימה לשלב שבו המשימה נמצאת עכשיו."
ERROR_UNKNOWN_TYPE = "סוג משימה לא מוכר."
ERROR_NOT_FOUND = "המשימה לא נמצאה."

# Card and interview screen.
CARD_TITLE = "כרטיס המשימה"
MARKS = {"pass": "✓", "fail": "✗", "unchecked": "–"}
MARK_LABELS = {"pass": "עבר", "fail": "נכשל", "unchecked": "לא נבדק"}
SAMPLE_LABEL = "דוגמה לתשובה:"
CARD_READY = "הכרטיס מוכן. אפשר לעבור להערכת זמן."
STUCK_EXPLAIN = "עברו 12 סבבים והכרטיס עדיין לא עובר את כל המבחנים. כנראה שהמשימה גדולה או עמומה מדי. אפשר לפצל ממנה חלק קטן יותר, או לפתוח משימת תחקור שתבהיר אותה."
CLI_OPENING_PROMPT = "מה המשימה? "
CLI_RETRY_PROMPT = "לחץ Enter כדי לנסות שוב..."
