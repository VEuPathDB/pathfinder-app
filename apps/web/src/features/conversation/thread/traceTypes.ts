import type { Trace } from "@veupathdb/assistant-client";

export type TraceGroupView = Trace["groups"][number];

export type TraceRowView = TraceGroupView["rows"][number];
