// Every string the extension shows, in one place (like texts_he.py in the app).
export const T = {
  blockedTitle: "האתר הזה חסום עד שהמשימה תסתיים",
  blockedBody: (domain) => `${domain} לא נראה כמו משהו שעוזר למשימה שרצה עכשיו.`,
  ok: "אישור, חזרה לדף הקודם",
  need: "אני צריך את האתר הזה",
  popupOn: "מיקוד פעיל",
  popupOff: "אין משימה רצה, ולכן שום אתר לא חסום.",
  popupBlocked: (n) => (n === 0 ? "עדיין אין אתרים חסומים." : `אתרים חסומים: ${n}`),
  popupServerDown: "השרת לא עונה. בדוק ש-Task Compass רץ בטרמינל.",
  popupRefresh: "רענן",
};
