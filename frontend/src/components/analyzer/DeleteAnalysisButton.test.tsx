// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DeleteAnalysisButton } from "./DeleteAnalysisButton";

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: nav.push,
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

function errorResponse(code: string, message: string, status: number): Response {
  return new Response(JSON.stringify({ error: { code, message } }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("DeleteAnalysisButton", () => {
  it("opens a modal confirm focused on the safe default; Cancel closes + refocuses", async () => {
    const user = userEvent.setup();
    render(<DeleteAnalysisButton analysisId="analysis-1" title="Login SRS" />);
    expect(screen.queryByRole("dialog")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog", { name: "Delete this analysis?" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(screen.getByText("Login SRS")).toBeDefined();
    expect(screen.getByText(/cannot be undone/)).toBeDefined();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Keep analysis" }));

    await user.click(screen.getByRole("button", { name: "Keep analysis" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Delete" }));
  });

  it("Escape cancels without calling the API", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<DeleteAnalysisButton analysisId="analysis-1" title="Login SRS" />);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("traps Tab between the two dialog buttons", async () => {
    const user = userEvent.setup();
    render(<DeleteAnalysisButton analysisId="analysis-1" title="Login SRS" />);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const keep = screen.getByRole("button", { name: "Keep analysis" });
    const confirm = screen.getByRole("button", { name: "Delete analysis" });
    expect(document.activeElement).toBe(keep);
    await user.tab();
    expect(document.activeElement).toBe(confirm);
    await user.tab();
    expect(document.activeElement).toBe(keep);
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(confirm);
  });

  it("deletes on confirm and returns to the Analyzer", async () => {
    const user = userEvent.setup();
    let seenUrl = "";
    let seenMethod = "";
    const fetchMock = vi.fn(async (input: unknown, init?: { method?: string }) => {
      seenUrl = String(input);
      seenMethod = init?.method ?? "";
      return new Response(null, { status: 204 });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<DeleteAnalysisButton analysisId="analysis-1" title="Login SRS" />);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Delete analysis" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(seenUrl).toContain("/analysis/analysis-1");
    expect(seenMethod).toBe("DELETE");
    expect(nav.push).toHaveBeenCalledWith("/analyzer");
  });

  it("treats already-gone (404) as deleted", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () =>
      errorResponse("not_found", "No analysis with id analysis-1.", 404),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<DeleteAnalysisButton analysisId="analysis-1" title="Login SRS" />);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Delete analysis" }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/analyzer"));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("keeps the dialog open with the honest error on failure", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () =>
      errorResponse("internal_error", "The database is unreachable.", 500),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<DeleteAnalysisButton analysisId="analysis-1" title="Login SRS" />);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Delete analysis" }));
    // Code-mapped copy (Stage 10) — the server sentence is never displayed.
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Something went wrong. Please try again.",
    );
    expect(nav.push).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Delete this analysis?" })).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Keep analysis" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("compact trigger is title-named; onDeleted stays on the page after delete", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const onDeleted = vi.fn();
    render(
      <DeleteAnalysisButton
        analysisId="analysis-1"
        title="Login SRS"
        compact
        onDeleted={onDeleted}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Delete Login SRS" }));
    await user.click(screen.getByRole("button", { name: "Delete analysis" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(onDeleted).toHaveBeenCalledTimes(1);
    expect(nav.push).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("compact 404-at-confirm still resolves through onDeleted", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () =>
      errorResponse("analysis_not_found", "No analysis with id analysis-1.", 404),
    );
    vi.stubGlobal("fetch", fetchMock);
    const onDeleted = vi.fn();
    render(
      <DeleteAnalysisButton
        analysisId="analysis-1"
        title="Login SRS"
        compact
        onDeleted={onDeleted}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Delete Login SRS" }));
    await user.click(screen.getByRole("button", { name: "Delete analysis" }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
    expect(nav.push).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
