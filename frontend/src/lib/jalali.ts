export interface JalaliDate {
  jy: number;
  jm: number;
  jd: number;
}

const G_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
const J_DAYS_IN_MONTH = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29];

export const J_MONTHS = [
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
  "شهریور",
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
];

function floorDiv(a: number, b: number): number {
  return Math.floor(a / b);
}

function floorMod(a: number, b: number): number {
  return a - Math.floor(a / b) * b;
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

export function gregorianToJalali(gy: number, gm: number, gd: number): JalaliDate {
  const y = gy - 1600;
  const m = gm - 1;
  let jDayNo =
    365 * y + floorDiv(y + 3, 4) - floorDiv(y + 99, 100) + floorDiv(y + 399, 400) + gd - 1 - 79;
  for (let i = 0; i < m; i++) jDayNo += G_DAYS_IN_MONTH[i];
  if (m > 1 && ((y % 4 === 0 && y % 100 !== 0) || y % 400 === 0)) jDayNo += 1;

  const jNp = floorDiv(jDayNo, 12053);
  jDayNo = floorMod(jDayNo, 12053);
  let jy = 979 + 33 * jNp + 4 * floorDiv(jDayNo, 1461);
  jDayNo = floorMod(jDayNo, 1461);
  if (jDayNo >= 366) {
    jDayNo -= 1;
    jy += floorDiv(jDayNo, 365);
    jDayNo = floorMod(jDayNo, 365);
  }

  let i = 0;
  for (; i < 11; i++) {
    if (jDayNo < J_DAYS_IN_MONTH[i]) break;
    jDayNo -= J_DAYS_IN_MONTH[i];
  }
  return { jy, jm: i <= 10 ? i + 1 : 12, jd: jDayNo + 1 };
}

export function jalaliToGregorian(jyIn: number, jm: number, jd: number): {
  gy: number;
  gm: number;
  gd: number;
} {
  const jy = jyIn - 979;
  let gDayNo =
    365 * jy + floorDiv(jy, 33) * 8 + floorDiv(floorMod(jy, 33) + 3, 4) + jd - 1 + 79;
  for (let i = 0; i < jm - 1; i++) gDayNo += J_DAYS_IN_MONTH[i];

  let gy = 1600 + 400 * floorDiv(gDayNo, 146097);
  gDayNo = floorMod(gDayNo, 146097);
  let leap = 1;
  if (gDayNo >= 36525) {
    gDayNo -= 1;
    gy += 100 * floorDiv(gDayNo, 36524);
    gDayNo = floorMod(gDayNo, 36524);
    if (gDayNo >= 365) gDayNo += 1;
    else leap = 0;
  }
  gy += 4 * floorDiv(gDayNo, 1461);
  gDayNo = floorMod(gDayNo, 1461);
  if (gDayNo >= 366) {
    leap = 0;
    gDayNo -= 1;
    gy += floorDiv(gDayNo, 365);
    gDayNo = floorMod(gDayNo, 365);
  }

  let i = 0;
  while (gDayNo >= G_DAYS_IN_MONTH[i] + (i === 1 && leap ? 1 : 0)) {
    gDayNo -= G_DAYS_IN_MONTH[i] + (i === 1 && leap ? 1 : 0);
    i += 1;
  }
  return { gy, gm: i + 1, gd: gDayNo + 1 };
}

export function isoToJalali(iso: string): JalaliDate {
  const [y, m, d] = iso.split("-").map(Number);
  return gregorianToJalali(y, m, d);
}

export function jalaliToIso(j: JalaliDate): string {
  const { gy, gm, gd } = jalaliToGregorian(j.jy, j.jm, j.jd);
  return `${gy}-${pad2(gm)}-${pad2(gd)}`;
}

export function isJalaliLeap(jy: number): boolean {
  const g = jalaliToGregorian(jy, 12, 30);
  const back = gregorianToJalali(g.gy, g.gm, g.gd);
  return back.jy === jy && back.jm === 12 && back.jd === 30;
}

export function daysInMonth(jy: number, jm: number): number {
  if (jm <= 11) return J_DAYS_IN_MONTH[jm - 1];
  return isJalaliLeap(jy) ? 30 : 29;
}

export function todayJalali(): JalaliDate {
  const now = new Date();
  return gregorianToJalali(now.getFullYear(), now.getMonth() + 1, now.getDate());
}

export function todayIso(): string {
  const now = new Date();
  return `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`;
}

export function formatJalali(j: JalaliDate): string {
  return `${j.jy}/${j.jm}/${j.jd}`.replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);
}
