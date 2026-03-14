import { describe, expect, it } from "vitest";

import {
  getImageLabel,
  getImageSrc,
  parseStructuredContent,
} from "../viewer/frontend/app/components/trajectory/content-utils";

describe("viewer trajectory content utils", () => {
  it("parses JSON-stringified base64 image content", () => {
    const parsed = parseStructuredContent(
      JSON.stringify({
        type: "image",
        source: {
          type: "base64",
          media_type: "image/png",
          data: "abc123",
        },
      })
    );

    expect(parsed).toEqual([
      {
        type: "image",
        source: {
          type: "base64",
          media_type: "image/png",
          data: "abc123",
        },
      },
    ]);
  });

  it("builds a data URL for base64 images", () => {
    const src = getImageSrc(
      {
        type: "image",
        source: {
          type: "base64",
          media_type: "image/png",
          data: "abc123",
        },
      },
      "job-id"
    );

    expect(src).toBe("data:image/png;base64,abc123");
  });

  it("builds an artifact URL for path-based images", () => {
    const src = getImageSrc(
      {
        type: "image",
        source: {
          media_type: "image/png",
          path: "figures/output.png",
        },
      },
      "job-id"
    );

    expect(src).toBe("/api/jobs/job-id/artifacts/figures/output.png");
  });

  it("returns the correct image label for embedded images", () => {
    const label = getImageLabel({
      type: "image",
      source: {
        type: "base64",
        media_type: "image/png",
        data: "abc123",
      },
    });

    expect(label).toBe("image/png");
  });

  it("returns null for plain text strings", () => {
    expect(parseStructuredContent("just text")).toBeNull();
  });
});
