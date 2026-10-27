// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { AnalysisResult } from "@/types/analysis";
import type { DocumentMetadata } from "@/types/documents";

import { DocumentUploadForm } from "./DocumentUploadForm";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function envelope(code: string, status: number, details: unknown = null): Response {
  return jsonResponse({ error: { code, message: `server ${code}`, details } }, status);
}

function documentMetadata(): DocumentMetadata {
  return {
    id: "doc-1",
    filename: "srs.txt",
    file_type: "txt",
    mime_type: "text/plain",
    byte_size: 42,
    sha256: "abc123",
    extracted_chars: 42,
    extraction_status: "ok",
    created_at: "2026-09-24T00:00:00Z",
  };
}

function analysisResult(): AnalysisResult {
  return {
    id: "analysis-1",
    title: "srs.txt",
    status: "analyzed",
    source_type: "document",
    document: { filename: "srs.txt", file_type: "txt" },
    score: 100,
    band: "low",
    score_breakdown: {
      base: 100,
      deductions: [],
      counts: { low: 0, medium: 0, high: 0, critical: 0 },
    },
    requirements_count: 1,
    issues_count: 0,
    health: { measurability: 100, specificity: 100, clarity: 100, completeness: 100 },
    ai_overview: null,
    ai_provider: null,
    ai_status: "skipped",
    ai_error: null,
    requirements: [
      {
        id: "req-1",
        position: 0,
        identifier: "FR-001",
        section: null,
        text: "The system shall allow login.",
        score: 100,
        severity: null,
        issues_count: 0,
        suggested_rewrite: null,
        suggestion_source: null,
        segmentation: {
          strategy: "requirement_id",
          confidence: 0.95,
          start_offset: 7,
          end_offset: 36,
          line_start: 1,
          line_end: 1,
        },
        issues: [],
      },
    ],
    created_at: "2026-09-24T00:00:00Z",
    updated_at: "2026-09-24T00:00:00Z",
  };
}

function textFile(name = "srs.txt"): File {
  return new File(["FR-001: The system shall allow login."], name, { type: "text/plain" });
}

/** Override the (content-derived) size without allocating megabytes. */
function sizedFile(name: string, size: number): File {
  const file = new File(["tiny"], name);
  Object.defineProperty(file, "size", { value: size });
  return file;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("DocumentUploadForm", () => {
  it("renders the dropzone, title field, and actions (submit disabled until a file)", () => {
    render(<DocumentUploadForm onResult={() => {}} />);
    expect(screen.getByLabelText("Title (optional)")).toBeDefined();
    expect(screen.getByLabelText("SRS file")).toBeDefined();
    expect(screen.getByText(/Drag your file here/)).toBeDefined();
    expect(screen.getByText(/One PDF, DOCX, or TXT file/)).toBeDefined();
    const submit = screen.getByRole("button", { name: "Upload and analyze" });
    expect(submit.getAttribute("disabled")).not.toBeNull();
  });

  it("shows the picked file with its size, removable", async () => {
    const user = userEvent.setup();
    render(<DocumentUploadForm onResult={() => {}} />);
    fireEvent.change(screen.getByLabelText("SRS file"), { target: { files: [textFile()] } });
    expect(screen.getByText("srs.txt")).toBeDefined();
    expect(screen.getByText("37 B")).toBeDefined();
    expect(
      screen.getByRole("button", { name: "Upload and analyze" }).getAttribute("disabled"),
    ).toBeNull();
    await user.click(screen.getByRole("button", { name: "Remove srs.txt" }));
    expect(screen.queryByText("srs.txt")).toBeNull();
    expect(screen.getByText(/Drag your file here/)).toBeDefined();
  });

  it("rejects unsupported extensions client-side with no request", () => {
    const fetchMock = vi.fn(async () => jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    render(<DocumentUploadForm onResult={() => {}} />);
    fireEvent.change(screen.getByLabelText("SRS file"), {
      target: { files: [new File(["x"], "sheet.xlsx")] },
    });
    expect(
      screen.getByText("Choose a PDF, DOCX, or TXT file. Other formats are not supported."),
    ).toBeDefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects oversize and empty files client-side with no request", () => {
    const fetchMock = vi.fn(async () => jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    render(<DocumentUploadForm onResult={() => {}} />);
    fireEvent.change(screen.getByLabelText("SRS file"), {
      target: { files: [sizedFile("big.pdf", 10 * 1024 * 1024 + 1)] },
    });
    expect(screen.getByText(/uploads are limited to 10\.0 MB/)).toBeDefined();
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("SRS file"), {
      target: { files: [new File([], "empty.txt", { type: "text/plain" })] },
    });
    expect(screen.getByText("That file is empty, so there is nothing to analyze.")).toBeDefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects multiple files client-side with no request", () => {
    const fetchMock = vi.fn(async () => jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    render(<DocumentUploadForm onResult={() => {}} />);
    fireEvent.change(screen.getByLabelText("SRS file"), {
      target: { files: [textFile("a.txt"), textFile("b.txt")] },
    });
    expect(screen.getByText("Drop one file at a time.")).toBeDefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("blocks empty submit with an inline error and no request", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    render(<DocumentUploadForm onResult={() => {}} />);
    // Submit is disabled without a file — enable the path via the form event.
    fireEvent.change(screen.getByLabelText("SRS file"), { target: { files: [textFile()] } });
    await user.click(screen.getByRole("button", { name: "Remove srs.txt" }));
    fireEvent.submit(screen.getByRole("button", { name: "Upload and analyze" }).closest("form")!);
    expect(screen.getByText("Choose a file to begin.")).toBeDefined();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("flags an over-long title live, with the submit disabled", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async () => jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    render(<DocumentUploadForm onResult={() => {}} />);
    fireEvent.change(screen.getByLabelText("SRS file"), { target: { files: [textFile()] } });
    await user.type(screen.getByLabelText("Title (optional)"), "t".repeat(201));
    expect(screen.getByText("Keep the title under 200 characters.")).toBeDefined();
    const submit = screen.getByRole("button", { name: "Upload and analyze" });
    expect(submit.getAttribute("disabled")).not.toBeNull();
    fireEvent.click(submit);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits once as multipart, shows pending state, reports result + title", async () => {
    const user = userEvent.setup();
    let release!: (value: Response) => void;
    let calls = 0;
    let sent: FormData | null = null;
    let url = "";
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        calls += 1;
        url = String(input);
        sent = init?.body as FormData;
        return new Promise<Response>((resolve) => {
          release = resolve;
        });
      }),
    );
    const onResult = vi.fn();
    render(<DocumentUploadForm onResult={onResult} />);
    fireEvent.change(screen.getByLabelText("SRS file"), { target: { files: [textFile()] } });
    fireEvent.change(screen.getByLabelText("Title (optional)"), {
      target: { value: "Login SRS" },
    });
    await user.click(screen.getByRole("button", { name: "Upload and analyze" }));
    expect(
      screen.getByRole("button", { name: "Uploading and analyzing…" }).getAttribute("disabled"),
    ).not.toBeNull();
    release(jsonResponse({ document: documentMetadata(), analysis: analysisResult() }));
    await waitFor(() => expect(onResult).toHaveBeenCalledTimes(1));
    expect(onResult).toHaveBeenCalledWith(analysisResult(), { title: "Login SRS" });
    expect(calls).toBe(1);
    expect(url).toContain("/documents/upload");
    expect(sent).toBeInstanceOf(FormData);
    expect((sent as unknown as FormData).get("title")).toBe("Login SRS");
    const uploaded = (sent as unknown as FormData).get("files");
    expect(uploaded).toBeInstanceOf(File);
    expect((uploaded as File).name).toBe("srs.txt");
  });

  it("omits a blank title so the server falls back to the filename", async () => {
    const user = userEvent.setup();
    let sent: FormData | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        sent = init?.body as FormData;
        return jsonResponse({ document: documentMetadata(), analysis: analysisResult() });
      }),
    );
    render(<DocumentUploadForm onResult={() => {}} />);
    fireEvent.change(screen.getByLabelText("SRS file"), { target: { files: [textFile()] } });
    await user.click(screen.getByRole("button", { name: "Upload and analyze" }));
    await waitFor(() => expect(sent).toBeInstanceOf(FormData));
    expect((sent as unknown as FormData).has("title")).toBe(false);
    expect((sent as unknown as FormData).has("files")).toBe(true);
  });

  it("maps no_extractable_text to guidance copy (never server strings)", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => envelope("no_extractable_text", 422)),
    );
    const onResult = vi.fn();
    render(<DocumentUploadForm onResult={onResult} />);
    fireEvent.change(screen.getByLabelText("SRS file"), { target: { files: [textFile()] } });
    await user.click(screen.getByRole("button", { name: "Upload and analyze" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("image-only PDFs are not supported");
    expect(alert.textContent).not.toContain("server no_extractable_text");
    expect(onResult).not.toHaveBeenCalled();
  });

  it("maps file_too_large from the server (authoritative over client checks)", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => envelope("file_too_large", 400)),
    );
    render(<DocumentUploadForm onResult={() => {}} />);
    fireEvent.change(screen.getByLabelText("SRS file"), { target: { files: [textFile()] } });
    await user.click(screen.getByRole("button", { name: "Upload and analyze" }));
    expect(await screen.findByText(/larger than 10 MB/)).toBeDefined();
  });

  it("sends ai_enhance explicitly (false by default, true when checked)", async () => {
    const user = userEvent.setup();
    const flags: Array<string | null> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        flags.push((init?.body as FormData).get("ai_enhance") as string | null);
        return jsonResponse({ document: documentMetadata(), analysis: analysisResult() });
      }),
    );
    render(<DocumentUploadForm onResult={() => {}} />);
    fireEvent.change(screen.getByLabelText("SRS file"), { target: { files: [textFile()] } });
    const checkbox = screen.getByRole("checkbox", { name: "Enhance with AI" });
    expect((checkbox as HTMLInputElement).checked).toBe(false);
    await user.click(screen.getByRole("button", { name: "Upload and analyze" }));
    await waitFor(() => expect(flags).toHaveLength(1));
    expect(flags[0]).toBe("false");
    await user.click(checkbox);
    await user.click(screen.getByRole("button", { name: "Upload and analyze" }));
    await waitFor(() => expect(flags).toHaveLength(2));
    expect(flags[1]).toBe("true");
  });

  it("links to Settings for provider management", () => {
    render(<DocumentUploadForm onResult={() => {}} />);
    expect(
      screen.getByRole("link", { name: "Manage providers in Settings" }).getAttribute("href"),
    ).toBe("/settings");
  });

  it("names AI in the pending state when enhancement is checked", async () => {
    const user = userEvent.setup();
    let release!: (value: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Promise<Response>((resolve) => {
            release = resolve;
          }),
      ),
    );
    const onResult = vi.fn();
    render(<DocumentUploadForm onResult={onResult} />);
    fireEvent.change(screen.getByLabelText("SRS file"), { target: { files: [textFile()] } });
    await user.click(screen.getByRole("checkbox", { name: "Enhance with AI" }));
    await user.click(screen.getByRole("button", { name: "Upload and analyze" }));
    expect(screen.getByRole("button", { name: "Uploading and analyzing with AI…" })).toBeDefined();
    release(jsonResponse({ document: documentMetadata(), analysis: analysisResult() }));
    await waitFor(() => expect(onResult).toHaveBeenCalledTimes(1));
  });
});
