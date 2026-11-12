import { describe, expect, it } from "vitest";
import { date, dateGroup, dateTime, inr, inrAxis, inrParts, inrWords, monthYear, pct, setIndianGrouping, signedInr } from "./format";

describe("indian formatting", () => {
  it("groups digits the Indian way", () => {
    expect(inr(12345678)).toBe("₹1,23,45,678");
    expect(inr(1234567.5, 2)).toBe("₹12,34,567.50");
    expect(inr(100000)).toBe("₹1,00,000");
    expect(inr(-1500)).toBe("−₹1,500");
    expect(inr(null)).toBe("—");
  });
  it("can switch to international grouping", () => {
    setIndianGrouping(false);
    expect(inr(12345678)).toBe("₹12,345,678");
    setIndianGrouping(true);
  });
  it("signs changes", () => {
    expect(signedInr(1200)).toBe("+₹1,200");
    expect(signedInr(-1200)).toBe("−₹1,200");
    expect(signedInr(0.2)).toBe("₹0");
  });
  it("splits hero values", () => {
    expect(inrParts(824000)).toEqual({ whole: "₹8,24,000", fraction: ".00" });
  });
  it("uses lakh and crore", () => {
    expect(inrWords(1250000)).toBe("₹12.5 lakh");
    expect(inrWords(32000000)).toBe("₹3.2 crore");
    expect(inrAxis(120000)).toBe("₹1.2L");
    expect(inrAxis(45000)).toBe("₹45K");
  });
  it("formats percentages from fractions", () => {
    expect(pct(0.1234)).toBe("12.3%");
    expect(pct(0.05, 1, true)).toBe("+5.0%");
    expect(pct(-0.05)).toBe("−5.0%");
  });
  it("formats dates in IST", () => {
    expect(date("2026-10-31T10:00:00Z")).toBe("31 Oct 2026");
    expect(date("2026-10-31T20:00:00Z")).toBe("1 Nov 2026"); // 01:30 IST next day
    expect(dateTime("2026-10-31T14:45:00Z")).toBe("31 Oct 2026, 8:15 pm IST");
  });
  it("groups chats by date", () => {
    const now = new Date("2026-10-31T12:00:00+05:30");
    expect(dateGroup("2026-10-31T01:00:00+05:30", now)).toBe("Today");
    expect(dateGroup("2026-10-30T23:00:00+05:30", now)).toBe("Yesterday");
    expect(dateGroup("2026-10-26T10:00:00+05:30", now)).toBe("Previous 7 days");
    expect(dateGroup("2026-08-01T10:00:00+05:30", now)).toBe("August 2026");
  });
});

describe("timeline months", () => {
  it("names the month and year in IST", () => {
    expect(monthYear("2026-11-01")).toBe("Nov 2026");
    expect(monthYear("2027-01-01")).toBe("Jan 2027");
  });
});
