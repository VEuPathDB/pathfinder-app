import { siteShortName } from "@pathfinder/shared";

import { yourDataUrl } from "@/lib/routes";
import type { SiteFrame } from "@/lib/sites/currentSite";

import { InfoList, InfoPage, InfoSection, InternalLink } from "./InfoPage";
import { SettingsTabLink } from "./SettingsTabLink";

function SiteChoice({ site }: { site: SiteFrame }) {
  switch (site.kind) {
    case "locked":
      return (
        <p>
          Here, PathFinder works on {siteShortName(site.siteId)}. If you open a
          conversation that you started on another site, PathFinder gives you a link to
          open it on that site.
        </p>
      );
    case "switchable":
      return (
        <p>
          To start a conversation on another site, choose Switch site at the bottom of
          the left bar and pick the site.
        </p>
      );
    case "unknown":
      return null;
  }
}

export function HelpPage({ site }: { site: SiteFrame }) {
  return (
    <InfoPage title="Help">
      <InfoSection id="what" title="What PathFinder does">
        <p>
          PathFinder helps you build search strategies on a VEuPathDB site. You describe
          what you are looking for in your own words. The assistant finds the
          site&apos;s searches, sets their parameters and combines them into a strategy.
          You can then ask it to add, change or remove steps.
        </p>
        <p>It can also:</p>
        <InfoList>
          <li>
            Check a strategy against genes you already know. You give it genes the
            strategy should find and genes it should not find. It tells you how many of
            each the strategy finds.
          </li>
          <li>
            Look for searches that separate your known genes. It runs candidate searches
            on the site, measures how well each one separates your genes, and offers you
            the best strategy it found. This takes about five minutes.
          </li>
          <li>
            Try other settings for one search and score each setting against your known
            genes. This takes about fifteen minutes.
          </li>
          <li>
            Explore study data. In the Studies panel, you can open a study that the site
            publishes, analyze its data with the assistant, and add a group of genes
            from it to your strategy as a step.
          </li>
          <li>Remember useful results from one conversation to the next.</li>
        </InfoList>
      </InfoSection>

      <InfoSection id="sign-in" title="Signing in and choosing a site">
        <p>
          You sign in with your VEuPathDB account, on the VEuPathDB website. PathFinder
          does not work unless you are signed in.
        </p>
        <p>
          PathFinder works on one site at a time: the VEuPathDB portal or a component
          site such as PlasmoDB or ToxoDB. Each conversation stays on the site where you
          started it.
        </p>
        <SiteChoice site={site} />
      </InfoSection>

      <InfoSection id="conversation" title="How a conversation works">
        <p>
          Before it builds, the assistant may ask you a few questions. Answer them, or
          choose Skip these questions.
        </p>
        <p>Some actions wait for your answer before they run:</p>
        <InfoList>
          <li>
            When the assistant proposes a change to your strategy, or offers the
            strategy a separation found, choose Yes or No.
          </li>
          <li>
            Before it deletes a step, replaces part of a strategy, clears a strategy,
            tries other settings for a search, runs a separation or saves a preference,
            it asks you to Approve or Deny.
          </li>
        </InfoList>
        <p>
          To stop a reply while it is being written, choose Stop in the message box.
        </p>
        <p>
          Longer tasks, such as checking known genes or a separation, keep running after
          the reply ends. The Tasks panel on the right shows their progress. You can
          close the page and come back later.
        </p>
      </InfoSection>

      <InfoSection id="check" title="What to check">
        <p>
          The searches, the results and the counts come from VEuPathDB itself, on the
          site you are using. The assistant chooses and combines the searches and
          explains them. Its reply is a short note. The counts, gene IDs and links of
          each turn are shown with the reply, taken from the site&apos;s answers. The
          model does not write them.
        </p>
        <p>
          The assistant can still choose the wrong search or misread your question. Each
          strategy it builds is a normal VEuPathDB strategy in your account. Choose Open
          in, followed by the site name, to open it on the site. There you can look at
          every step, change it and run it yourself.
        </p>
      </InfoSection>

      <InfoSection id="memory" title="Memory">
        <p>
          PathFinder can remember things from one conversation to the next. When the
          result of a strategy checks out on the site, it saves a short memory of the
          strategy and how it got there. It saves a preference only after you approve
          it. You can also ask it to remember something.
        </p>
        <p>
          To read, edit or delete your memories, open Settings and the{" "}
          <SettingsTabLink tab="memory">Memory</SettingsTabLink> tab. A memory you
          delete is not saved again automatically.
        </p>
      </InfoSection>

      <InfoSection id="models" title="Models">
        <p>
          Unless you pick a model, PathFinder uses the default model of the deployment,
          which is an OpenAI model. To change it, open Settings and the{" "}
          <SettingsTabLink tab="model">Model</SettingsTabLink> tab.
        </p>
        <p>
          In Settings, under <SettingsTabLink tab="keys">Provider keys</SettingsTabLink>
          , you can add your own OpenAI, Anthropic or Google key. Your key unlocks
          models that the deployment does not pay for, such as Claude Sonnet 5.5 and
          Claude Opus 5.5. The model list marks these models &quot;needs your key&quot;.
        </p>
      </InfoSection>

      <InfoSection id="declined" title="When a model declines">
        <p>
          A provider&apos;s safety filters sometimes block a legitimate research
          question. Read{" "}
          <InternalLink href={yourDataUrl("declined")}>
            what PathFinder does when a model declines
          </InternalLink>
          .
        </p>
      </InfoSection>

      <InfoSection id="saving" title="Saving and exporting">
        <InfoList>
          <li>
            Saved strategies, in the left bar, lists the strategies you saved with Save
            as reusable. You can insert them into any conversation.
          </li>
          <li>
            A gene set appears as a card in the conversation. From the card you can
            publish it to your VEuPathDB workspace or delete it.
          </li>
          <li>
            Type /export in the message box to download the current strategy (JSON),
            this conversation (Markdown or JSON), or your latest gene set on this site
            (CSV or TXT).
          </li>
          <li>
            Type /import in the message box to make a gene set from gene IDs you paste.
          </li>
          <li>Audits, in the left bar, lists the gene-model audits on your account.</li>
        </InfoList>
      </InfoSection>

      <InfoSection id="your-data" title="Your data">
        <p>
          What PathFinder sends to model providers, what it keeps, and how to delete it:{" "}
          <InternalLink href={yourDataUrl()}>Your data in PathFinder</InternalLink>.
        </p>
      </InfoSection>
    </InfoPage>
  );
}
