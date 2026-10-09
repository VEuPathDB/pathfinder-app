import type { ReactNode } from "react";

import type { YourDataSection } from "@/lib/routes";

import { ExternalLink, InfoList, InfoPage, InfoSection } from "./InfoPage";
import { YOUR_DATA_IN_BRIEF, YOUR_DATA_LAST_UPDATED } from "./yourDataBrief";

function Section({
  id,
  title,
  children,
}: {
  id: YourDataSection;
  title: string;
  children: ReactNode;
}) {
  return (
    <InfoSection id={id} title={title}>
      {children}
    </InfoSection>
  );
}

export function YourDataPage() {
  return (
    <InfoPage
      title="Your data in PathFinder"
      lead={
        <p className="mt-2 text-sm text-muted-foreground">
          Last updated: {YOUR_DATA_LAST_UPDATED}
        </p>
      }
    >
      <InfoSection id="in-brief" title="In brief">
        <InfoList>
          {YOUR_DATA_IN_BRIEF.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </InfoList>
      </InfoSection>

      <Section id="sent" title="What goes to AI model providers">
        <p>
          With your message and its files, PathFinder sends the model your last few
          messages and replies, a summary of the work so far (the strategy, the
          assistant&apos;s notes, your saved preferences and any memory it looks up),
          and what it read from VEuPathDB for this answer: search names, parameters,
          counts, gene IDs and record fields. A file goes only with the message you
          attach it to.
        </p>
        <p>
          This goes to the provider of the model that answers: OpenAI by default,
          Anthropic for a Claude model, Google for a Gemini model. Some small requests
          go to OpenAI whichever model you pick: a check of your message and of tool
          output for hidden instructions, unless the deployment turns it off; naming a
          new conversation from your first message, or the next one if naming fails;
          condensing long notes; and turning memory summaries and search words into
          vectors.
        </p>
        <p>
          Each provider&apos;s own terms say what it does with this data:{" "}
          <ExternalLink href="https://openai.com/enterprise-privacy/">
            OpenAI enterprise privacy
          </ExternalLink>
          ,{" "}
          <ExternalLink href="https://www.anthropic.com/legal/commercial-terms">
            Anthropic commercial terms
          </ExternalLink>
          ,{" "}
          <ExternalLink href="https://www.anthropic.com/legal/privacy">
            Anthropic privacy policy
          </ExternalLink>{" "}
          and{" "}
          <ExternalLink href="https://ai.google.dev/gemini-api/terms">
            Gemini API terms
          </ExternalLink>
          .
        </p>
      </Section>

      <Section id="other-services" title="Other services">
        <p>
          You sign in on the VEuPathDB website, and PathFinder receives the sign-in
          token it gives your browser, never your password. To read a count, PathFinder
          sometimes makes a temporary strategy in your account and then deletes it.
        </p>
        <p>
          If the deployment turns on literature and web search, the search words the
          assistant writes go to a search service the deployment runs, to DuckDuckGo,
          Mojeek, Yahoo, Startpage and Google, and to Europe PMC, Crossref, OpenAlex,
          Semantic Scholar, PubMed, arXiv, bioRxiv and medRxiv.
        </p>
      </Section>

      <Section id="kept" title="What PathFinder keeps, and who can see it">
        <p>
          The database of this deployment keeps your conversations with their files and
          notes, the strategies PathFinder built and their history, your gene sets,
          control sets, scored runs, memories and ratings, your sealed provider keys,
          your monthly spend and the email address of your VEuPathDB account.
        </p>
        <p>
          Each message you send, and each background task, waits in a queue with its
          request, its files and your sign-in token. The queue deletes it when the work
          ends. A file you export is kept for 10 minutes.
        </p>
        <p>
          Server logs record your account ID with each event. If the deployment turns on
          detailed traces, they hold your messages and the replies.
        </p>
        <p>
          Other researchers cannot open your conversations, gene sets, memories or
          exports. The people who operate this deployment can read its database and
          logs.
        </p>
        <p>
          Whatever you choose for learning, people on the PathFinder team may read a
          conversation, its strategy and the logs of its turns to find and fix a
          problem, for example when a turn fails, an answer is wrong, or you report
          something. Reading a conversation for this does not copy it, keep it as a test
          case or share it.
        </p>
      </Section>

      <Section id="deleting" title="Deleting your data">
        <p>
          Delete a conversation from the list of conversations. One that holds a
          strategy goes to Recently deleted first, and Delete permanently removes it
          with any copy waiting for review. Its strategy stays in your VEuPathDB account
          unless you tick Also delete strategy from the site. Memories, provider keys
          and everything at once are deleted in Settings, on the Memory, Provider keys
          and Data tabs.
        </p>
        <p>
          Deleting does not remove your monthly spend, the email address of your
          account, logs, traces, or a copy already accepted as a test case.
        </p>
      </Section>

      <Section id="learning" title="Learning from your strategies">
        <p>
          This is your choice. You make it when you first sign in, and you can change it
          at any time in Settings, on the Privacy tab. Nothing is copied until you have
          seen the notice for this version of the statement.
        </p>
        <p>
          When it is on, PathFinder may use copies of your conversations and strategies
          to improve PathFinder for everyone. That can include:
        </p>
        <InfoList>
          <li>reviewing how well the assistant answered, by a person on the team;</li>
          <li>finding and fixing mistakes;</li>
          <li>keeping parts as test cases that check new versions of PathFinder;</li>
          <li>
            improving the assistant&apos;s instructions and how it chooses searches;
          </li>
          <li>
            shared examples or a knowledge base that the assistant draws on when helping
            other researchers;
          </li>
          <li>
            measuring how well PathFinder works, and reporting those findings in
            summaries, talks or publications about PathFinder.
          </li>
        </InfoList>
        <p>
          Today, PathFinder copies your finished conversations each night, and a
          conversation when you dislike one of its replies. A copy holds your messages,
          the replies and the strategy. A person reads each copy, and a copy that is
          accepted is kept as a test case.
        </p>
        <p>
          A copy used beyond review never carries your name, your account or a link to
          your conversation. Findings are reported only in summaries, never as your
          conversation. PathFinder does not sell copies or give them to anyone to train
          their AI models. Before review, PathFinder removes email addresses and
          passwords in web addresses.
        </p>
        <p>
          If we start using copies in a way this page does not describe, we update this
          page, and you see the notice again before the new use applies.
        </p>
        <p>
          Turning learning off deletes your copies that are waiting for review and stops
          new ones. A copy already accepted stays, without your account.
        </p>
      </Section>

      <Section id="your-key" title="Using your own key">
        <p>
          Add a key in Settings, on the Provider keys tab. PathFinder checks it with one
          short request, stores it sealed and sends it only to its provider, which then
          bills you for every model of that provider except the check for hidden
          instructions. Claude Sonnet 5.5 and Claude Opus 5.5 run only on your own
          Anthropic key.
        </p>
      </Section>

      <Section id="declined" title="When a model declines">
        <p>
          Provider safety filters sometimes block a legitimate research question.
          PathFinder then shows a Request declined notice and puts your words back in
          the message box, so you can rephrase them or pick another model. No later turn
          sends the declined message, but it was already sent once, and it stays in the
          stored record until you delete the conversation.
        </p>
      </Section>

      <Section id="contact" title="Questions or concerns">
        <p>
          Write to the VEuPathDB team at{" "}
          <a
            href="mailto:help@veupathdb.org"
            className="text-primary underline underline-offset-2"
          >
            help@veupathdb.org
          </a>
          .
        </p>
      </Section>
    </InfoPage>
  );
}
