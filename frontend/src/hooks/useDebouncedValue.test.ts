// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";

import { useDebouncedValue } from "./useDebouncedValue";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("useDebouncedValue", () => {
  it("emits immediately on mount, then only after quiet", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(
      ({ value }: { value: string }) => useDebouncedValue(value, 300),
      { initialProps: { value: "" } },
    );
    expect(result.current).toBe("");
    rerender({ value: "a" });
    expect(result.current).toBe("");
    act(() => vi.advanceTimersByTime(299));
    expect(result.current).toBe("");
    rerender({ value: "ab" });
    act(() => vi.advanceTimersByTime(299));
    expect(result.current).toBe("");
    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe("ab");
  });

  it("cancels the pending emit on unmount", () => {
    vi.useFakeTimers();
    const { result, rerender, unmount } = renderHook(
      ({ value }: { value: string }) => useDebouncedValue(value, 300),
      { initialProps: { value: "" } },
    );
    rerender({ value: "typed" });
    unmount();
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current).toBe("");
  });
});
