import { yourDataUrl } from "@/lib/routes";

import { InfoList, InfoPage, InfoSection, InternalLink } from "./InfoPage";

export function HelpPage() {
  return (
    <InfoPage title="Help">
      <InfoSection id="what" title="What PathFinder does">
        <p>
          PathFinder helps you build VEuPathDB search strategies. You describe what you
          are looking for in your own words. The assistant finds searches on the site,
          sets their parameters and combines them into a strategy.
        </p>
        <p>
          It can also check a strategy against genes you already know, and tell you how
          many of them the strategy finds.
        </p>
      </InfoSection>

      <InfoSection id="sign-in" title="Signing in and choosing a site">
        <p>
          You sign in with your VEuPathDB account, on the VEuPathDB website. PathFinder
          does not work without a signed-in account.
        </p>
        <p>
          PathFinder works on one site at a time: the VEuPathDB portal or a component
          site such as PlasmoDB or ToxoDB. To change the site, use Switch site at the
          bottom of the left bar.
        </p>
      </InfoSection>

      <InfoSection id="conversation" title="How a conversation works">
        <p>
          Before it builds, the assistant may ask you a few questions. Answer them, or
          choose Skip these questions.
        </p>
        <p>
          Some actions wait for your answer before they run. When the assistant proposes
          a change, choose Yes or No. Before it deletes a step or clears a strategy, it
          asks you to Approve or Deny.
        </p>
      </InfoSection>

      <InfoSection id="check" title="What to check">
        <p>
          The searches, the results and the counts come from VEuPathDB itself, on the
          site you are using. The assistant chooses and combines the searches and
          explains them. It does not write counts or gene IDs itself: the ones in its
          replies are filled in from the site&apos;s answers.
        </p>
        <p>
          The assistant can still choose the wrong search or misread your question. Each
          strategy it builds is a normal VEuPathDB strategy in your account. Choose Open
          in, followed by the site name, to open it on the site. There you can look at
          every step, change it and run it yourself.
        </p>
      </InfoSection>

      <InfoSection id="models" title="Models">
        <p>
          Unless you pick a model, PathFinder uses the default model of the deployment,
          which is an OpenAI model. To change it, choose AI model in the left bar, or
          open Settings and the Model tab.
        </p>
        <p>
          In Settings, under Provider keys, you can add your own OpenAI, Anthropic or
          Google key. Your key unlocks models that the deployment does not pay for, such
          as Claude Sonnet 5.5 and Claude Opus 5.5. The model list marks these models
          &quot;needs your key&quot;.
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
