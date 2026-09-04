import type { Trace } from "@pathfinder/assistant-client";

export type TraceGroupView = Trace["groups"][number];

export type TraceRowView = TraceGroupView["rows"][number];
