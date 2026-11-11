// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { expect, it } from "vitest";
import { useDraftPersistence } from "./useDraftPersistence";
import { workspaceStore } from "../store/workspace";
import { storeIdentity } from "../test/setup";

it("keeps a session draft in the shared account workspace", () => {
  storeIdentity(); workspaceStore.startAccount(1, "A"); workspaceStore.ensureSessionBucket("A");
  const { result } = renderHook(() => useDraftPersistence("A"));
  act(() => result.current.setDraft("我的草稿"));
  expect(result.current.draft).toBe("我的草稿");
  expect(workspaceStore.getSnapshot().buckets.A.draft).toBe("我的草稿");
});
