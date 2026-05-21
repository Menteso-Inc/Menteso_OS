import { describe, expect, it } from "vitest";
import {
  findModerateDuplicateReason,
  inferIntentCluster,
  jaccardSimilarity,
  slugify,
  topicFingerprint,
} from "../textUtils";

describe("textUtils moderate duplicate logic", () => {
  it("slugifies titles safely", () => {
    expect(slugify("How Much Does Patent Filing Cost in the United States?")).toBe(
      "how-much-does-patent-filing-cost-in-the-united-states",
    );
  });

  it("infers useful intent clusters for patent-adjacent queries", () => {
    expect(inferIntentCluster("provisional patent filing checklist")).toBe("provisional patents");
    expect(inferIntentCluster("software patent filing cost for saas startups")).toBe("software and ai patents");
    expect(inferIntentCluster("office action response timeline")).toBe("office actions");
  });

  it("flags exact and same-intent recent duplicates with moderate protection", () => {
    const ledger = [
      {
        date: "2026-05-01",
        topicId: "software-patent-filing-cost",
        primaryKeyword: "software patent filing cost",
        secondaryKeywords: [],
        slug: "software-patent-filing-cost",
        wpPostId: 20,
        wpUrl: "https://example.com/software-patent-filing-cost",
        status: "publish",
        source: "dashboard",
        fingerprint: topicFingerprint("Software and AI Patent Protection", "cost guide", "software patent filing cost"),
        intentCluster: "software and ai patents",
      },
    ];

    const exactReason = findModerateDuplicateReason(
      {
        primaryKeyword: "software patent filing cost",
        fingerprint: topicFingerprint("Software and AI Patent Protection", "cost guide", "software patent filing cost"),
        slug: "software-patent-filing-cost",
        intentCluster: "software and ai patents",
      },
      ledger as any,
      [],
      new Date("2026-05-10T00:00:00Z"),
    );

    const sameIntentReason = findModerateDuplicateReason(
      {
        primaryKeyword: "software patent filing costs",
        fingerprint: topicFingerprint("Software and AI Patent Protection", "pricing", "software patent filing costs"),
        slug: "software-patent-filing-costs",
        intentCluster: "software and ai patents",
      },
      ledger as any,
      [],
      new Date("2026-05-10T00:00:00Z"),
    );

    expect(exactReason).toBeTruthy();
    expect(sameIntentReason).toBeTruthy();
  });

  it("allows related follow-up topics when the angle materially differs", () => {
    const ledger = [
      {
        date: "2026-05-01",
        topicId: "provisional-patent-filing-cost",
        primaryKeyword: "provisional patent filing cost",
        secondaryKeywords: [],
        slug: "provisional-patent-filing-cost",
        wpPostId: 21,
        wpUrl: "https://example.com/provisional-patent-filing-cost",
        status: "publish",
        source: "dashboard",
        fingerprint: topicFingerprint("Provisional Patent Strategy", "cost", "provisional patent filing cost"),
        intentCluster: "provisional patents",
      },
    ];

    const reason = findModerateDuplicateReason(
      {
        primaryKeyword: "provisional patent filing checklist for startups",
        fingerprint: topicFingerprint(
          "Provisional Patent Strategy",
          "checklist",
          "provisional patent filing checklist for startups",
        ),
        slug: "provisional-patent-filing-checklist-for-startups",
        intentCluster: "provisional patents",
      },
      ledger as any,
      [],
      new Date("2026-05-10T00:00:00Z"),
    );

    expect(reason).toBeNull();
    expect(jaccardSimilarity("provisional patent filing cost", "provisional patent filing checklist for startups")).toBeLessThan(0.8);
  });

  it("blocks same-cluster provisional topics that reuse the same core terms", () => {
    const ledger = [
      {
        date: "2026-05-20",
        topicId: "provisional-patents-provisional-patent-filing-uspto",
        primaryKeyword: "Provisional patent filing USPTO",
        secondaryKeywords: [],
        slug: "strategic-provisional-patent-filing-uspto",
        wpPostId: 42,
        wpUrl: "https://example.com/strategic-provisional-patent-filing-uspto",
        status: "publish",
        source: "dashboard",
        fingerprint: topicFingerprint("Provisional Patent Strategy", "search demand", "Provisional patent filing USPTO"),
        intentCluster: "provisional patents",
      },
    ];

    const reason = findModerateDuplicateReason(
      {
        primaryKeyword: "How to file a provisional patent with USPTO",
        fingerprint: topicFingerprint(
          "Provisional Patent Strategy",
          "search demand",
          "How to file a provisional patent with USPTO",
        ),
        slug: "how-to-file-a-provisional-patent-with-uspto",
        intentCluster: "provisional patents",
      },
      ledger as any,
      [],
      new Date("2026-05-20T00:00:00Z"),
    );

    expect(reason).toBeTruthy();
  });
});
