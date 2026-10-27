// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CopyButton } from "./CopyButton";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("CopyButton", () => {
  it("copies exactly the given text and confirms inline", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<CopyButton text="The system shall allow login." label="Copy" />);
    await user.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText).toHaveBeenCalledWith("The system shall allow login.");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Copy — copied" })).toBeDefined(),
    );
    expect(screen.getByText("Copied")).toBeDefined();
  });

  it("reports clipboard failure honestly instead of silently doing nothing", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn(async () => {
      throw new DOMException("denied", "NotAllowedError");
    });
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<CopyButton text="x" label="Copy suggestion" />);
    await user.click(screen.getByRole("button", { name: "Copy suggestion" }));
    expect(await screen.findByText("Copy failed")).toBeDefined();
  });
});
