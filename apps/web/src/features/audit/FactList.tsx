import type { Fact } from "@pathfinder/shared/generated/types/Fact";

export function FactList({ facts }: { facts: readonly Fact[] }) {
  return (
    <dl className="mt-1 text-sm">
      {facts.map((fact) => (
        <div key={fact.label} className="mt-1">
          <dt className="text-xs text-muted-foreground">{fact.label}</dt>
          <dd>{fact.value}</dd>
        </div>
      ))}
    </dl>
  );
}
