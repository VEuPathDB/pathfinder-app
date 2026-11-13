import type { EdaEntityCount } from "@strategist/shared";

/** One entity clause, in the one format the trace and the figures share. The
 * display name is kept exactly as the wire gives it. */
function entityCountLine(entity: EdaEntityCount): string {
  const name =
    entity.entityDisplayName.length > 0 ? entity.entityDisplayName : entity.entityId;
  return `${entity.count.toLocaleString()} of ${entity.unfilteredCount.toLocaleString()} ${name}`;
}

export function entityCountCaption(entities: readonly EdaEntityCount[]): string {
  return entities.map(entityCountLine).join(", ");
}
