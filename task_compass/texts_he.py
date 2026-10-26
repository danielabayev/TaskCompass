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
ERROR_NO_KEY = "לא הוגדר מפתח API. צריך להוסיף ANTHROPIC_API_KEY לקובץ ‎.env ולהפעיל מחדש."
ERROR_MINUTES = "צריך מספר שלם של דקות, בין 1 ל-43200 (30 יום)."
ERROR_BLIND_LOCKED = "ההערכה העיוורת כבר נשמרה ולא משתנה."
ERROR_SECOND_EXTENSION = "כבר השתמשת בהארכה. אפשר לפצל, לצמצם או לעצור."
ERROR_REDUCE_NEEDS_TESTS = "בצמצום צריך להשאיר לפחות מבחן סיום אחד."
ERROR_SPLIT_NEEDS_CHILDREN = "בפיצול צריך לכתוב לפחות משימה אחת (שורה לכל משימה)."
ERROR_HINDSIGHT = "הזמן בדיעבד צריך להיות קצר מהזמן שנמדד."

# Labels used by the web templates (accessed as ui.<key>).
UI = {
    "app_name": "מצפן משימות",
    "nav_home": "משימות",
    "nav_history": "היסטוריה",
    "nav_spend": "הוצאה חודשית",
    "new_task_title": "משימה חדשה",
    "new_task_hint": "כתוב את המשימה כמו שהיא בראש שלך, גם אם היא עמומה.",
    "new_task_button": "להתחיל להגדיר",
    "open_tasks": "משימות פתוחות",
    "no_open_tasks": "אין משימות פתוחות.",
    "waiting": "רגע...",
    "retry": "לנסות שוב",
    "pending_interview": "השלב הבא עוד לא רץ. התשובה שלך שמורה.",
    "start_interview": "להתחיל את הראיון",
    "answer_label": "התשובה שלך",
    "answer_button": "לשלוח",
    "stuck_hint": "תשובה של 'מספיק' לא מסיימת את הראיון. הוא נגמר רק כשכל השדות עוברים.",
    "show_sample": "תקוע? הנה דוגמה",
    "round": "סבב",
    "of": "מתוך",
    "change_type": "לשנות סוג",
    "stuck_title": "המשימה לא מתבהרת",
    "split_option": "לפצל חלק קטן יותר",
    "split_child_label": "החלק הקטן שתגדיר עכשיו",
    "investigate_option": "לפתוח משימת תחקור",
    "investigate_child_label": "מה צריך לברר (אפשר להשאיר ריק)",
    "estimate_title": "הערכת זמן",
    "blind_label": "ההערכה שלך, בדקות, לפני שאתה רואה את ההצעה של המודל",
    "blind_button": "לנעול את ההערכה",
    "blind_hint": "ההערכה הזאת ננעלת ולא משתנה. היא הבסיס שאליו משווים את הזמן בפועל.",
    "pending_estimate": "ההערכה שלך שמורה. הצעת המודל עוד לא התקבלה.",
    "your_blind": "ההערכה העיוורת שלך",
    "model_estimate": "הצעת המודל",
    "breakdown": "פירוק",
    "minutes": "דקות",
    "min_short": "דק׳",
    "gap_title": "פער של פי 2 או יותר",
    "gap_hint": "פער כזה אומר בדרך כלל שאתה והמודל מבינים את המשימה אחרת. מה מסביר את הפער? מה חסר או לא ברור בכרטיס?",
    "clarify_button": "לשלוח הבהרה",
    "corrected": "ההערכה שלך אחרי התיקון האישי",
    "personal_correction": "התיקון האישי שלך",
    "correction_type": "לפי משימות מאותו סוג",
    "correction_global": "לפי כל המשימות (אין עדיין 3 מאותו סוג)",
    "correction_none": "אין עדיין היסטוריית כיול",
    "binding_label": "ההערכה המחייבת, בדקות",
    "binding_hint": "זה הזמן שאתה מתחייב אליו. הכלי לא קובע אותו בשבילך.",
    "binding_button": "לקבוע",
    "clarification_given": "ההבהרה שלך",
    "planned_title": "מוכן להתחיל",
    "binding": "ההערכה המחייבת",
    "first_step": "הצעד הראשון",
    "start_button": "להתחיל עכשיו",
    "running_title": "בביצוע",
    "time_left": "זמן שנותר",
    "finish_button": "סיימתי",
    "extension_used": "כולל הארכה של",
    "checkpoint_title": "נקודת עצירה: הזמן נגמר",
    "q_done_tests": "אילו ממבחני הסיום כבר עוברים?",
    "q_remaining": "מה נשאר, ומה הפתיע אותך?",
    "q_cause": "מה הסיבה העיקרית לעיכוב?",
    "how_continue": "איך ממשיכים?",
    "choice_extend": "להאריך (פעם אחת בלבד)",
    "choice_split": "לפצל למשימות קטנות",
    "choice_reduce": "לצמצם את ההיקף",
    "choice_stop": "לעצור",
    "extend_minutes": "כמה דקות להוסיף",
    "reduce_tests": "מבחני הסיום שנשארים (שורה לכל מבחן)",
    "reduce_minutes": "כמה דקות לסיים את ההיקף המצומצם",
    "split_children": "המשימות החדשות (שורה לכל משימה)",
    "checkpoint_button": "להמשיך",
    "finished_anyway": "בעצם סיימתי",
    "retro_title": "רטרוספקטיבה",
    "actual": "זמן בפועל",
    "deviation": "יחס לזמן המחייב",
    "direction_over": "לקח יותר זמן מהמתוכנן",
    "direction_under": "לקח פחות זמן מהמתוכנן",
    "direction_on": "קרוב להערכה, אבל קרה משהו חריג בדרך",
    "q_too_simple": "האם המשימה הייתה פשוטה מדי בשביל הזמן שהוקצב לה?",
    "yes": "כן",
    "no": "לא",
    "q_hindsight": "כמה דקות היו מספיקות, בדיעבד?",
    "q_retro_cause": "מה גרם לסטייה?",
    "q_definition_gap": "מה היה חסר או לא ברור בהגדרת המשימה?",
    "q_lesson": "מה ללמוד מזה למשימה הבאה מאותו סוג?",
    "retro_button": "לשמור ולסגור",
    "closed_title": "המשימה סגורה",
    "short_retro": "הסתיים קרוב להערכה. המספרים נשמרו, בלי שאלות.",
    "outcome": "תוצאה",
    "shortened": "קוצר בדיעבד",
    "children": "משימות שנפתחו ממנה",
    "parent": "נפתחה מתוך",
    "history_title": "היסטוריית משימות",
    "col_task": "משימה",
    "col_type": "סוג",
    "col_status": "מצב",
    "col_blind": "עיוורת",
    "col_binding": "מחייבת",
    "col_actual": "בפועל",
    "col_ratio": "בפועל / עיוורת",
    "spend_title": "הוצאה על המודל החודש",
    "spend_total": "הוצאה עד עכשיו",
    "spend_cap": "התקרה המקומית",
    "spend_alert": "עברת 70% מהתקרה החודשית.",
    "spend_failed": "קריאות שנכשלו החודש",
    "col_purpose": "שימוש",
    "col_model": "מודל",
    "col_calls": "קריאות",
    "col_cost": "עלות (דולר)",
    "no_calls": "אין עדיין קריאות החודש.",
}

STATUS_LABELS = {
    "interview": "בהגדרה",
    "stuck": "תקועה",
    "estimate": "בהערכת זמן",
    "planned": "מוכנה להתחלה",
    "running": "בביצוע",
    "checkpoint": "בנקודת עצירה",
    "retro": "ברטרו",
    "closed": "סגורה",
}

OUTCOME_LABELS = {
    "completed": "הושלמה",
    "stopped": "נעצרה",
    "split": "פוצלה",
    "investigate": "הועברה לתחקור",
}

PURPOSE_LABELS = {"judge": "בדיקת הכרטיס", "ask": "שאלות הראיון", "propose": "הצעת זמן"}
ERROR_STALE_ANSWER = "השאלה הזאת כבר נענתה (אולי נשלח פעמיים). הנה השאלה הנוכחית."
