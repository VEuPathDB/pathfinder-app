"use client";

import { createContext, useContext } from "react";

const ReadOnlyThreadContext = createContext(false);

export const ReadOnlyThreadProvider = ReadOnlyThreadContext.Provider;

export function useReadOnlyThread(): boolean {
  return useContext(ReadOnlyThreadContext);
}
