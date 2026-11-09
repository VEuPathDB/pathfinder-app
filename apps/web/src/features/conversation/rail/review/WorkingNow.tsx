"use client";

import type { TaskListItem } from "@pathfinder/shared/generated/types/TaskListItem";
import { motion } from "motion/react";

import { useEntrance } from "@/lib/motion";
import { phaseLabel } from "@/lib/models/phaseRoles";

import { humanizeToolName } from "../../toolNames";

interface WorkingNowProps {
  phase: string | null;
  tasks: readonly TaskListItem[];
}

function TaskProgress({ task }: { task: TaskListItem }) {
  const percent =
    task.latestPercent == null ? null : Math.round(task.latestPercent * 100);
  const fill = useEntrance({
    initial: { width: 0 },
    transition: { duration: 0.5, ease: "easeOut" },
  });
  return (
    <li className="flex flex-col gap-1.5">
      <div className="flex justify-between gap-2 text-sm">
        <span className="text-foreground">{humanizeToolName(task.toolName)}</span>
        {percent !== null && (
          <span className="tabular-nums text-muted-foreground">{percent}%</span>
        )}
      </div>
      {percent !== null && (
        <div className="h-1 overflow-hidden rounded-full bg-border">
          <motion.div
            {...fill}
            animate={{ width: `${percent}%` }}
            className="h-full rounded-full bg-primary"
          />
        </div>
      )}
      {task.latestMessage != null && task.latestMessage !== "" && (
        <p className="truncate text-xs text-muted-foreground">{task.latestMessage}</p>
      )}
    </li>
  );
}

export function WorkingNow({ phase, tasks }: WorkingNowProps) {
  return (
    <section className="flex flex-col gap-2.5 border-b border-border bg-primary/5 px-4 py-4">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">Working now</h3>
        {phase !== null && (
          <span className="text-xs text-muted-foreground">{phaseLabel(phase)}</span>
        )}
      </div>
      {tasks.length > 0 && (
        <ul className="flex flex-col gap-3">
          {tasks.map((task) => (
            <TaskProgress key={task.taskId} task={task} />
          ))}
        </ul>
      )}
    </section>
  );
}
