import { describe, expect, it } from "vitest";

import { ALL_QUEUE_NAMES, QUEUE_NAMES } from "../queue-names";

describe("queue names", () => {
  it("includes all production queues", () => {
    expect(ALL_QUEUE_NAMES).toEqual([
      QUEUE_NAMES.keywordResearch,
      QUEUE_NAMES.articleGeneration,
      QUEUE_NAMES.publishing,
      QUEUE_NAMES.indexing,
      QUEUE_NAMES.contentRefresh,
      QUEUE_NAMES.reporting,
    ]);
  });
});
