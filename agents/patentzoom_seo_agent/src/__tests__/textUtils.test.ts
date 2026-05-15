import { describe, expect, it } from "vitest";
import { isLedgerDuplicate, slugify, topicFingerprint } from "../textUtils";

describe("textUtils", () => {
  it("slugifies titles safely", () => {
    expect(slugify("How Much Does Patent Filing Cost in the United States?")).toBe(
      "how-much-does-patent-filing-cost-in-the-united-states",
    );
  });

  it("detects duplicate fingerprints and near-identical keywords within 180 days", () => {
    const fingerprint = topicFingerprint("Patent Filing Strategy", "foundational strategy", "patent filing strategy for startups");
    const ledger = [
      {
        date: "2026-05-01",
        topicId: "startup-patent-strategy",
        pillar: "Patent Filing Strategy",
        angle: "foundational strategy",
        primaryKeyword: "patent filing strategy for startups",
        secondaryKeywords: [],
        slug: "startup-patent-strategy",
        wpPostId: 10,
        wpUrl: "https://example.com/startup-patent-strategy",
        status: "draft",
        source: "dashboard",
        fingerprint,
      },
    ];

    expect(isLedgerDuplicate(fingerprint, "patent filing strategy for startups", ledger, new Date("2026-05-10"))).toBe(true);
    expect(
      isLedgerDuplicate(
        topicFingerprint("Patent Filing Strategy", "timing strategy", "patent filing strategies for startup"),
        "patent filing strategies for startup",
        ledger,
        new Date("2026-05-10"),
      ),
    ).toBe(true);
  });
});

