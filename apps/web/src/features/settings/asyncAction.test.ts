// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useAsyncAction } from "./asyncAction";

describe("useAsyncAction", () => {
  it("runs a function, returns its result, and leaves no error", async () => {
    const { result } = renderHook(() => useAsyncAction());
    let value: number | undefined;
    await act(async () => {
      value = await result.current.run(async () => 42);
    });
    expect(value).toBe(42);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("captures an Error message and returns undefined", async () => {
    const { result } = renderHook(() => useAsyncAction());
    let value: unknown;
    await act(async () => {
      value = await result.current.run(async () => {
        throw new Error("boom");
      });
    });
    expect(value).toBeUndefined();
    expect(result.current.error).toBe("boom");

    act(() => {
      result.current.clearError();
    });
    expect(result.current.error).toBeNull();
  });

  it("stringifies non-Error throws (string + number)", async () => {
    const { result } = renderHook(() => useAsyncAction());
    await act(async () => {
      await result.current.run(async () => {
        throw "str-err";
      });
    });
    expect(result.current.error).toBe("str-err");

    await act(async () => {
      await result.current.run(async () => {
        throw 123;
      });
    });
    expect(result.current.error).toBe("123");
  });
});
