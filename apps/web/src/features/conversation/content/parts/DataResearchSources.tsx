import type { ResearchSourcesPayload } from "@pathfinder/shared";

import { Figure } from "@/features/conversation/thread/Figure";

/**
 * The sources behind one research call. Both served tools emit this part with
 * their whole result, so only the query and the sources are read here.
 */
export function DataResearchSources({ data }: { data: ResearchSourcesPayload }) {
  const sources = data.sources ?? [];
  if (sources.length === 0) return null;
  return (
    <Figure
      testId="data-research-sources"
      title="Sources"
      caption={`${sources.length.toLocaleString()} sources for ${data.query}`}
    >
      <ol className="space-y-0.5 text-xs">
        {sources.map((source) => (
          <li key={source.id} className="truncate">
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer noopener"
              className="underline underline-offset-2"
            >
              {source.title === undefined || source.title === ""
                ? source.url
                : source.title}
            </a>
          </li>
        ))}
      </ol>
    </Figure>
  );
}
